# =============================================================================
#  CipherElite Userbot Plugin - aireply.py v1.1 (Stage 1)
#  AI replies in whitelisted groups using CipherElite's ai_config
# =============================================================================

from telethon import events
from telethon.errors import FloodWaitError
from utils.utils import CipherElite
from utils.decorators import rishabh
from plugins.bot import add_handler
from plugins.ai_setup import ai_config
import asyncio
import json
import re
import random
from datetime import datetime
from pathlib import Path
from google import genai
from google.genai import types

VERSION = "1.1.0"
CATEGORY = "utilities"

# ═══════════════════════════════════════════════════════════════
#  CONFIG
# ═══════════════════════════════════════════════════════════════

AI_LOG_CHAT_ID = -1004374819145   # AI REPLY LOG group
QUEUE_CHAT_ID  = -1003860044937   # QUEUE group

# Keywords with word-boundary matching (won't match "this" for "hi")
KEYWORDS = ['gm', 'hi', 'hello', 'hey', 'wagmi', 'moon', 'airdrop', 'lfg']
WORD_LIMIT = 5
REPLY_DELAY_MIN = 3
REPLY_DELAY_MAX = 8
MIN_GAP_SAME_USER = 0        # ⚡ DISABLED as requested
RATE_LIMIT_HOURLY = 20
RATE_LIMIT_DAILY = 150
DEBUG = True                 # 🔍 diagnostic prints — set False once stable

SPEED_MODES = {
    "fast": (1, 3),
    "normal": (3, 8),
    "slow": (8, 20),
}
CURRENT_SPEED = "normal"

REACT_TO_GM = True
REACT_PROBABILITY = 0.3
REACTION_EMOJIS = ["🔥", "👀", "🫡", "💪", "😂"]

GEMINI_MODEL = "gemini-3.5-flash-lite"
SYSTEM_PROMPT = """You are KCE — a real person in a crypto Telegram group.

Write ONE short reply.
- Maximum 5 words
- Lowercase where natural
- Casual Nigerian crypto-native tone
- No hashtags, no links, no "great question"
- 0-1 emoji max (only 🔥, 👀, 🫡, 💪)
- Never sound like an AI assistant
- Match the vibe of the message

Reply with just the text, nothing else."""


def dbg(msg):
    if DEBUG:
        print(f"[aireply] {msg}")


# ═══════════════════════════════════════════════════════════════
#  STORAGE
# ═══════════════════════════════════════════════════════════════

PROJECT_ROOT = Path(__file__).parent.parent
DB_DIR = PROJECT_ROOT / "DB"
DB_DIR.mkdir(exist_ok=True)
DB_FILE = DB_DIR / "aireply.json"


def load_db():
    try:
        if DB_FILE.exists():
            return json.loads(DB_FILE.read_text(encoding="utf-8"))
    except Exception as e:
        print(f"[aireply] load error: {e}")
    return {
        "whitelist": [],
        "replies": [],
        "replied_users": {},
        "hourly": {},
        "daily": {"date": "", "count": 0},
        "started": datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S"),
    }


def save_db(data):
    try:
        DB_FILE.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
    except Exception as e:
        print(f"[aireply] save error: {e}")


DB = load_db()


def today_str():
    return datetime.utcnow().strftime("%Y-%m-%d")


def reset_daily_if_needed():
    if DB.get("daily", {}).get("date") != today_str():
        DB["daily"] = {"date": today_str(), "count": 0}
        save_db(DB)


def now_dict():
    n = datetime.utcnow()
    return {"time12": n.strftime("%I:%M:%S %p"), "ts": n.timestamp()}


def is_whitelisted(chat_id):
    return chat_id in DB.get("whitelist", [])


# Word-boundary keyword matcher — "hi" won't match "this"
KEYWORD_PATTERNS = [re.compile(rf"\b{re.escape(k)}\b", re.IGNORECASE) for k in KEYWORDS]


def has_trigger(text):
    if not text:
        return False
    for pat in KEYWORD_PATTERNS:
        if pat.search(text):
            return True
    return False


def can_reply_to_user(user_id):
    if MIN_GAP_SAME_USER <= 0:
        return True
    last = DB.get("replied_users", {}).get(str(user_id), 0)
    return (datetime.utcnow().timestamp() - last) >= MIN_GAP_SAME_USER


def can_reply_in_group(group_id):
    now = datetime.utcnow().timestamp()
    hour_ago = now - 3600
    timestamps = DB.get("hourly", {}).get(str(group_id), [])
    recent = [t for t in timestamps if t > hour_ago]
    return len(recent) < RATE_LIMIT_HOURLY


def can_reply_daily():
    reset_daily_if_needed()
    return DB["daily"].get("count", 0) < RATE_LIMIT_DAILY


def track_reply(group_id, user_id):
    now = datetime.utcnow().timestamp()
    DB.setdefault("replied_users", {})[str(user_id)] = now
    hourly = DB.setdefault("hourly", {})
    group_ts = hourly.get(str(group_id), [])
    group_ts.append(now)
    hourly[str(group_id)] = group_ts[-100:]
    DB["daily"]["count"] = DB["daily"].get("count", 0) + 1
    save_db(DB)


def get_delay():
    lo, hi = SPEED_MODES.get(CURRENT_SPEED, SPEED_MODES["normal"])
    return random.randint(lo, hi)


# ═══════════════════════════════════════════════════════════════
#  GEMINI CALL
# ═══════════════════════════════════════════════════════════════

async def generate_reply(their_message, context_messages=None):
    if not ai_config.is_enabled():
        dbg("gemini skip: ai_config disabled")
        return None
    api_key = ai_config.get_api_key()
    if not api_key:
        dbg("gemini skip: no api key")
        return None

    context = ""
    if context_messages:
        context = "\n".join([f"- {m}" for m in context_messages[-5:]])

    user_prompt = f"""Recent context:
{context if context else "(no context)"}

Message to reply to:
\"{their_message[:200]}\"

Your reply:"""

    try:
        client = genai.Client(api_key=api_key)
        config = types.GenerateContentConfig(
            system_instruction=SYSTEM_PROMPT,
            max_output_tokens=50,
            temperature=1.1,
            top_p=0.95,
        )
        response = await client.aio.models.generate_content(
            model=GEMINI_MODEL,
            contents=[types.Content(role="user", parts=[types.Part(text=user_prompt)])],
            config=config,
        )
        text = (response.text or "").strip()
        text = text.replace("\n", " ").strip('"').strip("'")
        text = re.sub(r'^(reply|response|answer):\s*', '', text, flags=re.IGNORECASE)
        words = text.split()
        if len(words) > WORD_LIMIT:
            text = " ".join(words[:WORD_LIMIT])
        if len(text) < 2 or len(text) > 100:
            dbg(f"gemini returned bad length: '{text}'")
            return None
        dbg(f"gemini ok: '{text}'")
        return text
    except Exception as e:
        print(f"[aireply] Gemini error: {e}")
        return None


# ═══════════════════════════════════════════════════════════════
#  LOG CARD + SENDERS
# ═══════════════════════════════════════════════════════════════

def build_reply_card(n, group_name, user_name, their_msg, bot_reply, speed="normal"):
    return f"""╔══════════════════════════════════════╗
║  🎯⚡💥🔥  KCE AI REPLY  🎯⚡💥🔥
║  ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
║  📍 {group_name[:30]}
║  👤 {user_name[:30]}
║  🕐 {datetime.utcnow().strftime('%I:%M:%S %p')} — {datetime.utcnow().strftime('%d/%m/%Y')}
╚══════════════════════════════════════╝

📩 THEY SAID
\"{their_msg[:150]}\"

🤖 KCE REPLIED
\"{bot_reply}\"

✅ SENT  •  ⚡ {speed}
🔗 Auto-generated reply  •  #{n}
━━━━━━━━━━━━━━━━━━━━━━━━━━━━

[👍 Good]  [👎 Bad]  [✏️ Correct]"""


async def send_log(text):
    try:
        return await CipherElite.send_message(AI_LOG_CHAT_ID, text)
    except Exception as e:
        print(f"[aireply] log error: {e}")
        return None


async def queue_item(text):
    try:
        await CipherElite.send_message(QUEUE_CHAT_ID, text)
    except Exception as e:
        print(f"[aireply] queue error: {e}")

# ═══ END OF CHUNK 1 ═══


# ═══════════════════════════════════════════════════════════════
#  CHUNK 2 — COMMANDS + HANDLERS + AUTO-ONLINE
# ═══════════════════════════════════════════════════════════════


def init(client_instance):
    commands = [
        ".kce - status",
        ".kce stats - reply stats",
        ".kce memory - memory info",
        ".kce replies [n] - show last N replies",
        ".kce reset - clear memory",
        ".kce help - all commands",
        ".kce speed fast|normal|slow - set speed",
        ".kce online - start heartbeat",
        ".kcew - whitelist current group",
        ".kcew off - un-whitelist current group",
        ".kcew off <chat_id> - un-whitelist by ID",
        ".kcew list - list whitelisted groups",
    ]
    description = "🤖 KCE AI Reply v1.1 — auto-reply in whitelisted groups"
    add_handler("aireply", commands, description)


# ─── Silent reply: DM → reply, group → log only ────────────────
async def _safe_reply(event, text):
    try:
        if event.is_private:
            await event.reply(text)
        else:
            await send_log(text)
    except Exception as e:
        print(f"[aireply] safe_reply error: {e}")


# ─── Owner check ───────────────────────────────────────────────
async def _is_owner(event):
    try:
        me = await CipherElite.get_me()
        return event.sender_id == me.id
    except Exception:
        return False


# ═══════════════════════════════════════════════════════════════
#  STATUS / STATS / MEMORY / HELP
# ═══════════════════════════════════════════════════════════════

@CipherElite.on(events.NewMessage(pattern=r"\.kce$"))
@rishabh()
async def cmd_kce_status(event):
    if not await _is_owner(event):
        return
    try:
        reset_daily_if_needed()
        wl = DB.get("whitelist", [])
        replies = DB.get("replies", [])
        today = DB["daily"].get("count", 0)
        started = DB.get("started", "?")
        gemini_ok = ai_config.is_enabled() and bool(ai_config.get_api_key())
        msg = (
            "🤖 **KCE AI Reply v1.1**\n"
            "━━━━━━━━━━━━━━━━━━━━\n"
            f"🧠 Gemini: {'✅ Ready' if gemini_ok else '❌ Disabled'}\n"
            f"📝 Whitelisted: `{len(wl)}` groups\n"
            f"💬 Replies sent: `{len(replies)}`\n"
            f"📅 Today: `{today}/{RATE_LIMIT_DAILY}`\n"
            f"⚡ Speed: `{CURRENT_SPEED}`\n"
            f"🚀 Started: `{started}`\n"
            "━━━━━━━━━━━━━━━━━━━━\n"
            f"⚙️ Word limit: `{WORD_LIMIT}`"
        )
        await _safe_reply(event, msg)
    except Exception as e:
        await send_log(f"❌ cmd_kce_status error: `{e}`")


@CipherElite.on(events.NewMessage(pattern=r"\.kce\s+stats$"))
@rishabh()
async def cmd_kce_stats(event):
    if not await _is_owner(event):
        return
    try:
        reset_daily_if_needed()
        replies = DB.get("replies", [])
        today = today_str()
        today_count = sum(1 for r in replies if r.get("date") == today)
        per_group = {}
        for r in replies:
            g = r.get("group_name", "?")
            per_group[g] = per_group.get(g, 0) + 1
        top = sorted(per_group.items(), key=lambda x: -x[1])[:5]
        lines = [
            "📊 **KCE Reply Stats**",
            "━━━━━━━━━━━━━━━━━━━━",
            f"💬 Total replies: `{len(replies)}`",
            f"📅 Today: `{today_count}`",
            f"📈 Daily cap: `{DB['daily'].get('count', 0)}/{RATE_LIMIT_DAILY}`",
            f"⚡ Speed mode: `{CURRENT_SPEED}`",
            f"🕐 Per-user gap: `{MIN_GAP_SAME_USER}s` (disabled if 0)",
            f"🚦 Per-group hourly cap: `{RATE_LIMIT_HOURLY}`",
        ]
        if top:
            lines.append("\n**Top groups:**")
            for g, c in top:
                lines.append(f"• {g[:30]} — `{c}`")
        await _safe_reply(event, "\n".join(lines))
    except Exception as e:
        await send_log(f"❌ cmd_kce_stats error: `{e}`")


@CipherElite.on(events.NewMessage(pattern=r"\.kce\s+memory$"))
@rishabh()
async def cmd_kce_memory(event):
    if not await _is_owner(event):
        return
    try:
        replies = DB.get("replies", [])
        users = DB.get("replied_users", {})
        lines = [
            "🧠 **KCE Memory**",
            "━━━━━━━━━━━━━━━━━━━━",
            f"💾 Replies stored: `{len(replies)}` / 500",
            f"👥 Users tracked: `{len(users)}`",
            f"📁 DB: `DB/aireply.json`",
        ]
        await _safe_reply(event, "\n".join(lines))
    except Exception as e:
        await send_log(f"❌ cmd_kce_memory error: `{e}`")


@CipherElite.on(events.NewMessage(pattern=r"\.kce\s+replies(?:\s+(\d+))?$"))
@rishabh()
async def cmd_kce_replies(event):
    if not await _is_owner(event):
        return
    try:
        n = int(event.pattern_match.group(1) or 10)
        n = max(1, min(n, 50))
        replies = DB.get("replies", [])[-n:]
        if not replies:
            return await _safe_reply(event, "📭 No replies yet.")
        lines = [f"📜 **Last {len(replies)} replies**\n━━━━━━━━━━━━━━━━━━━━"]
        for r in replies:
            lines.append(
                f"`#{r.get('n', '?')}` **{r.get('user_name', '?')[:20]}** in *{r.get('group_name', '?')[:25]}*\n"
                f"  📩 \"{r.get('they_said', '')[:50]}\"\n"
                f"  🤖 \"{r.get('bot_reply', '')[:50]}\"\n"
                f"  🕐 {r.get('time12', '?')}"
            )
        await _safe_reply(event, "\n".join(lines))
    except Exception as e:
        await send_log(f"❌ cmd_kce_replies error: `{e}`")


@CipherElite.on(events.NewMessage(pattern=r"\.kce\s+reset$"))
@rishabh()
async def cmd_kce_reset(event):
    if not await _is_owner(event):
        return
    try:
        DB["replies"] = []
        DB["replied_users"] = {}
        DB["hourly"] = {}
        DB["daily"] = {"date": today_str(), "count": 0}
        save_db(DB)
        await _safe_reply(event, "🔄 Memory cleared (whitelist kept).")
    except Exception as e:
        await send_log(f"❌ cmd_kce_reset error: `{e}`")


@CipherElite.on(events.NewMessage(pattern=r"\.kce\s+help$"))
@rishabh()
async def cmd_kce_help(event):
    if not await _is_owner(event):
        return
    try:
        msg = (
            "🤖 **KCE AI Reply — Commands**\n"
            "━━━━━━━━━━━━━━━━━━━━\n"
            "`.kce` — status\n"
            "`.kce stats` — reply stats\n"
            "`.kce memory` — memory info\n"
            "`.kce replies [n]` — last N replies\n"
            "`.kce reset` — clear memory\n"
            "`.kce speed fast|normal|slow` — set speed\n"
            "`.kce online` — start heartbeat\n"
            "`.kce help` — this menu\n\n"
            "**Whitelist:**\n"
            "`.kcew` — whitelist current group\n"
            "`.kcew off` — remove whitelist (from that group)\n"
            "`.kcew off <chat_id>` — remove by ID\n"
            "`.kcew list` — list whitelisted"
        )
        await _safe_reply(event, msg)
    except Exception as e:
        await send_log(f"❌ cmd_kce_help error: `{e}`")


@CipherElite.on(events.NewMessage(pattern=r"\.kce\s+speed\s+(fast|normal|slow)$"))
@rishabh()
async def cmd_kce_speed(event):
    global CURRENT_SPEED
    if not await _is_owner(event):
        return
    try:
        mode = event.pattern_match.group(1).lower()
        if mode not in SPEED_MODES:
            return await _safe_reply(event, f"❌ Unknown mode.")
        CURRENT_SPEED = mode
        lo, hi = SPEED_MODES[mode]
        await _safe_reply(event, f"⚡ Speed set to **{mode}** ({lo}-{hi}s delay)")
    except Exception as e:
        await send_log(f"❌ cmd_kce_speed error: `{e}`")


# ═══════════════════════════════════════════════════════════════
#  WHITELIST COMMANDS (.kcew)
# ═══════════════════════════════════════════════════════════════

@CipherElite.on(events.NewMessage(pattern=r"\.kcew$"))
async def cmd_kcew_add(event):
    if not await _is_owner(event):
        return
    try:
        try: await event.delete()
        except: pass
        chat = await event.get_chat()
        chat_id = event.chat_id
        chat_name = getattr(chat, "title", "Unknown")
        wl = DB.get("whitelist", [])
        if chat_id in wl:
            return await send_log(f"ℹ️ Already whitelisted: **{chat_name}** (`{chat_id}`)")
        wl.append(chat_id)
        DB["whitelist"] = wl
        save_db(DB)
        await send_log(
            f"✅ **KCE WHITELIST UPDATED**\n"
            f"Group: **{chat_name}**\n"
            f"ID: `{chat_id}`\n"
            f"Action: Added\n"
            f"Total: `{len(wl)}`"
        )
    except Exception as e:
        await send_log(f"❌ WL add error: `{e}`")


@CipherElite.on(events.NewMessage(pattern=r"\.kcew\s+off(?:\s+(-?\d+))?$"))
async def cmd_kcew_remove(event):
    if not await _is_owner(event):
        return
    try:
        target = event.pattern_match.group(1)
        if target:
            chat_id = int(target)
            chat_name = f"ID {chat_id}"
            try:
                entity = await CipherElite.get_entity(chat_id)
                chat_name = getattr(entity, "title", chat_name)
            except Exception:
                pass
        else:
            try: await event.delete()
            except: pass
            chat = await event.get_chat()
            chat_id = event.chat_id
            chat_name = getattr(chat, "title", "Unknown")

        wl = DB.get("whitelist", [])
        if chat_id not in wl:
            return await send_log(f"ℹ️ Not whitelisted: **{chat_name}** (`{chat_id}`)")
        wl.remove(chat_id)
        DB["whitelist"] = wl
        save_db(DB)
        await send_log(f"🗑️ Removed from KCE whitelist: **{chat_name}** (`{chat_id}`)")
    except Exception as e:
        await send_log(f"❌ WL remove error: `{e}`")


@CipherElite.on(events.NewMessage(pattern=r"\.kcew\s+list$"))
@rishabh()
async def cmd_kcew_list(event):
    if not await _is_owner(event):
        return
    try:
        wl = DB.get("whitelist", [])
        if not wl:
            return await _safe_reply(event, "📭 No whitelisted groups.")
        lines = ["📋 **KCE Whitelisted Groups**\n"]
        for cid in wl:
            try:
                entity = await CipherElite.get_entity(cid)
                name = getattr(entity, "title", "Unknown")
            except Exception:
                name = "Unknown"
            lines.append(f"• **{name}** (`{cid}`)")
        await _safe_reply(event, "\n".join(lines))
    except Exception as e:
        await send_log(f"❌ cmd_kcew_list error: `{e}`")


# ═══════════════════════════════════════════════════════════════
#  AI REPLY HANDLER — mention / reply-to-me / keyword
# ═══════════════════════════════════════════════════════════════

async def _get_context(event, limit=5):
    try:
        msgs = await CipherElite.get_messages(event.chat_id, limit=limit + 1)
        ctx = []
        for m in msgs:
            if m.id == event.message.id:
                continue
            if m.raw_text and not m.raw_text.startswith((".", "..")):
                ctx.append(m.raw_text[:150])
        return ctx[-limit:]
    except Exception:
        return []


@CipherElite.on(events.NewMessage)
async def kce_reply_handler(event):
    try:
        # ── Gate 1: whitelist
        if not is_whitelisted(event.chat_id):
            return
        # ── Gate 2: outgoing
        if event.out:
            return
        # ── Gate 3: text
        text = event.raw_text or ""
        if not text or text.startswith((".", "..")):
            return

        me = await CipherElite.get_me()
        sender = await event.get_sender()

        # ── Gate 4: skip own messages
        if sender and sender.id == me.id:
            return

        triggered = False
        trigger_type = None

        # reply-to-me
        if event.is_reply:
            replied = await event.get_reply_message()
            if replied and replied.sender_id == me.id:
                triggered, trigger_type = True, "reply"
        # mention
        if not triggered and me.username and f"@{me.username.lower()}" in text.lower():
            triggered, trigger_type = True, "mention"
        # keyword
        if not triggered and has_trigger(text):
            triggered, trigger_type = True, "keyword"

        if not triggered:
            return

        dbg(f"trigger={trigger_type} chat={event.chat_id} user={sender.id if sender else '?'} text='{text[:50]}'")

        user_id = event.sender_id
        if not can_reply_to_user(user_id):
            dbg(f"block: per-user gap")
            return
        if not can_reply_in_group(event.chat_id):
            dbg(f"block: hourly cap")
            return
        if not can_reply_daily():
            dbg(f"block: daily cap")
            return

        # generate reply
        context = await _get_context(event, 5)
        reply_text = await generate_reply(text, context)
        if not reply_text:
            dbg("block: gemini returned empty")
            return

        # human delay
        delay = get_delay()
        dbg(f"delay {delay}s before reply")
        await asyncio.sleep(delay)

        try:
            sent = await event.reply(reply_text)
            dbg(f"reply sent: '{reply_text}'")
        except FloodWaitError as e:
            dbg(f"floodwait {e.seconds}s")
            await asyncio.sleep(e.seconds + 1)
            sent = await event.reply(reply_text)
        except Exception as e:
            print(f"[aireply] reply send error: {e}")
            return

        track_reply(event.chat_id, user_id)

        stamp = now_dict()
        chat = await event.get_chat()
        chat_name = getattr(chat, "title", "Unknown")
        user_name = (getattr(sender, "first_name", "") or getattr(sender, "username", "") or "Unknown")[:30]

        replies = DB.get("replies", [])
        reply_num = len(replies) + 1
        record = {
            "n": reply_num,
            "group_name": chat_name,
            "group_id": event.chat_id,
            "user_name": user_name,
            "user_id": user_id,
            "they_said": text[:200],
            "bot_reply": reply_text,
            "time12": stamp["time12"],
            "date": stamp["date"],
            "ts": stamp["ts"],
            "trigger": trigger_type,
            "speed": CURRENT_SPEED,
        }
        replies.append(record)
        DB["replies"] = replies[-500:]
        save_db(DB)

        card = build_reply_card(
            reply_num, chat_name, user_name, text, reply_text, speed=CURRENT_SPEED
        )
        await send_log(card)

        await queue_item(
            f"💬 **KCE replied in {chat_name}**\n"
            f"👤 {user_name}: \"{text[:100]}\"\n"
            f"🤖 \"{reply_text}\"\n"
            f"🕐 {stamp['time12']}  •  trigger: `{trigger_type}`"
        )

        if REACT_TO_GM and random.random() < REACT_PROBABILITY:
            try:
                await sent.react(random.choice(REACTION_EMOJIS))
            except Exception:
                pass

    except FloodWaitError as e:
        print(f"[aireply] FloodWait {e.seconds}s")
        await asyncio.sleep(e.seconds + 1)
    except Exception as e:
        print(f"[aireply] handler error: {e}")


# ═══════════════════════════════════════════════════════════════
#  AUTO-ONLINE + HEARTBEAT
# ═══════════════════════════════════════════════════════════════

HEARTBEAT_TASK = None


async def _heartbeat_loop():
    await asyncio.sleep(5)
    while True:
        try:
            me = await CipherElite.get_me()
            dbg(f"heartbeat — online as @{getattr(me, 'username', '?')}")
        except Exception as e:
            print(f"[aireply] heartbeat error: {e}")
        await asyncio.sleep(30)


@CipherElite.on(events.NewMessage(pattern=r"\.kce\s+online$"))
@rishabh()
async def cmd_kce_online(event):
    global HEARTBEAT_TASK
    if not await _is_owner(event):
        return
    try:
        if HEARTBEAT_TASK and not HEARTBEAT_TASK.done():
            return await _safe_reply(event, "✅ Heartbeat already running.")
        HEARTBEAT_TASK = asyncio.create_task(_heartbeat_loop())
        await _safe_reply(event, "🚀 Heartbeat started (30s interval).")
    except Exception as e:
        await send_log(f"❌ cmd_kce_online error: `{e}`")


try:
    HEARTBEAT_TASK = asyncio.create_task(_heartbeat_loop())
except Exception as e:
    print(f"[aireply] heartbeat init error: {e}")


# ╔══════════════════════════════════════════════════════════════╗
# ║  === END OF AIRREPLY v1.1 — STAGE 1 ===                      ║
# ╚══════════════════════════════════════════════════════════════╝
