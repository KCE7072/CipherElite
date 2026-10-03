
# =============================================================================
#  CipherElite Userbot Plugin - aireply.py v1.2 + v1.5 (Stage 1 Complete)
#  AI replies in whitelisted groups using CipherElite's ai_config
#  Features: smarter context, anti-repeat, anti-AI prompt, DM forwarding,
#  auto-online during reply, typing indicator, clickable log links
# =============================================================================

from telethon import events
from telethon.errors import FloodWaitError
from telethon.tl import functions
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

VERSION = "1.2.0"
CATEGORY = "utilities"

# ═══════════════════════════════════════════════════════════════
#  CONFIG
# ═══════════════════════════════════════════════════════════════

AI_LOG_CHAT_ID = -1004374819145   # AI REPLY LOG group
QUEUE_CHAT_ID  = -1003860044937   # QUEUE group — DMs, errors, reviews

KEYWORDS = ['gm', 'hi', 'hello', 'hey', 'wagmi', 'moon', 'airdrop', 'lfg']
WORD_LIMIT = 3
REPLY_DELAY_MIN = 3
REPLY_DELAY_MAX = 8
MIN_GAP_SAME_USER = 0        # disabled
RATE_LIMIT_HOURLY = 20
RATE_LIMIT_DAILY = 150
DEBUG = True

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

# Anti-repeat cache
RECENT_REPLIES = []
MAX_RECENT = 10

# DM suspicion keywords — forward DMs matching these to QUEUE
DM_ALERT_KEYWORDS = [
    'bot', 'ai', 'robot', 'real', 'human', 'who is', 'who are',
    'automated', 'script', 'kce', 'cipher', 'reply bot'
]

SYSTEM_PROMPT = """You are KCE — a real Nigerian guy in a crypto Telegram group. You're not helpful. You're not polite. You're just vibing.

Rules:
- Maximum 3 words. No exceptions.
- NEVER say: "gm bro", "we move", "we outside", "let's go", "nice one", "good morning", "great", "awesome", "amazing", "yes", "sure", "sounds good"
- Lowercase only. No capital letters unless it's a name.
- 0 emoji, OR 1 emoji max (only: 🔥 👀 🫡 💪 😂 💀)
- Match the energy: if they say "moon", talk about price action. If they say "gm", say something fresh. If they say "wagmi", don't parrot it back.
- No questions. No "how are you". No assistant behavior.
- Sound like a guy half-scrolling his phone, not an AI.
- Sometimes use slang: "omo", "na", "dey", "sha", "abi", "chale"
- Never explain. Never clarify. Never offer help.

Examples of GOOD replies:
- "gm" → "morning my g"
- "moon" → "we touching soon"
- "wagmi" → "no other way"
- "hi" → "yo"
- "what's up" → "chilling fam"

Examples of BAD replies (do NOT copy this style):
- "good morning bro 🫡"
- "we move 🔥"
- "nice one"
- "how are you doing?"

Reply with just the text. Nothing else."""


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
    return {
        "date": n.strftime("%Y-%m-%d"),
        "time12": n.strftime("%I:%M:%S %p"),
        "ts": n.timestamp()
    }


def is_whitelisted(chat_id):
    return chat_id in DB.get("whitelist", [])


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

# ═══ END OF BATCH 1 ═══
# ═══════════════════════════════════════════════════════════════
#  GEMINI CALL — smarter context, anti-repeat, anti-AI
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

    banned = ", ".join(RECENT_REPLIES[-5:]) if RECENT_REPLIES else "(none yet)"

    user_prompt = f"""Recent context:
{context if context else "(no context)"}

Recent replies you already sent (DO NOT repeat these):
{banned}

Message to reply to:
\"{their_message[:200]}\"

Your reply:"""

    try:
        client = genai.Client(api_key=api_key)
        config = types.GenerateContentConfig(
            system_instruction=SYSTEM_PROMPT,
            max_output_tokens=200,
            temperature=1.2,
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

        # ── anti-repeat: retry once with higher temp if duplicate
        if text.lower() in [r.lower() for r in RECENT_REPLIES]:
            dbg(f"duplicate detected: '{text}' — retrying")
            try:
                retry_prompt = user_prompt + (
                    f"\n\nIMPORTANT: You already said '{text}'. "
                    f"Do NOT repeat it. Say something completely different, still max {WORD_LIMIT} words."
                )
                response2 = await client.aio.models.generate_content(
                    model=GEMINI_MODEL,
                    contents=[types.Content(role="user", parts=[types.Part(text=retry_prompt)])],
                    config=types.GenerateContentConfig(
                        system_instruction=SYSTEM_PROMPT,
                        max_output_tokens=200,
                        temperature=1.5,
                        top_p=0.98,
                    ),
                )
                text2 = (response2.text or "").strip().replace("\n", " ").strip('"').strip("'")
                words2 = text2.split()
                if len(words2) > WORD_LIMIT:
                    text2 = " ".join(words2[:WORD_LIMIT])
                if text2 and len(text2) >= 2 and text2.lower() not in [r.lower() for r in RECENT_REPLIES]:
                    text = text2
                    dbg(f"retry succeeded: '{text}'")
            except Exception as e:
                dbg(f"retry failed: {e}")

        # ── store in cache
        RECENT_REPLIES.append(text)
        if len(RECENT_REPLIES) > MAX_RECENT:
            RECENT_REPLIES.pop(0)

        dbg(f"gemini ok: '{text}'")
        return text
    except Exception as e:
        print(f"[aireply] Gemini error: {e}")
        return None


# ═══════════════════════════════════════════════════════════════
#  LOG CARD + SENDERS
# ═══════════════════════════════════════════════════════════════

def build_jump_link(chat_id, msg_id):
    """Build a clickable t.me link — handles public and private groups."""
    try:
        cid_str = str(chat_id)
        if cid_str.startswith("-100"):
            internal = cid_str[4:]
            return f"https://t.me/c/{internal}/{msg_id}"
        elif cid_str.startswith("-"):
            internal = cid_str[1:]
            return f"https://t.me/c/{internal}/{msg_id}"
        else:
            return f"https://t.me/c/{cid_str}/{msg_id}"
    except Exception:
        return None


def build_reply_card(n, group_name, user_name, their_msg, bot_reply,
                     speed="normal", jump_link=None):
    header = (
        "╔══════════════════════════════════════╗\n"
        "║  🎯⚡💥🔥  KCE AI REPLY  🎯⚡💥🔥\n"
        "║  ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        f"║  📍 {group_name[:30]}\n"
        f"║  👤 {user_name[:30]}\n"
        f"║  🕐 {datetime.utcnow().strftime('%I:%M:%S %p')} — {datetime.utcnow().strftime('%d/%m/%Y')}\n"
        "╚══════════════════════════════════════╝"
    )
    body = (
        f'\n📩 THEY SAID\n"{their_msg[:150]}"\n'
        f'\n🤖 KCE REPLIED\n"{bot_reply}"\n'
        f"\n✅ SENT  •  ⚡ {speed}\n"
        f"🔗 Auto-generated reply  •  #{n}\n"
    )
    if jump_link:
        body += f"🔗 Jump to message: {jump_link}\n"
    body += "━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    return header + body


async def send_log(text):
    try:
        return await CipherElite.send_message(AI_LOG_CHAT_ID, text)
    except Exception as e:
        print(f"[aireply] log error: {e}")
        return None


async def queue_item(text, alert=False):
    """Send to QUEUE group — used for errors, DMs, reviews."""
    try:
        prefix = "🚨 " if alert else "📥 "
        await CipherElite.send_message(QUEUE_CHAT_ID, prefix + text)
    except Exception as e:
        print(f"[aireply] queue error: {e}")

# ═══ END OF BATCH 2 ═══
# ═══════════════════════════════════════════════════════════════
#  INIT — register commands
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
    description = "🤖 KCE AI Reply v1.2 — auto-reply in whitelisted groups"
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
            "🤖 **KCE AI Reply v1.2**\n"
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

# ═══ END OF BATCH 3 ═══
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
#  SMART CONTEXT — same user's last 3 + replied-to msg
# ═══════════════════════════════════════════════════════════════

async def _get_smart_context(event, me, limit=5):
    """Fetch context: same user's recent msgs + replied-to msg."""
    ctx = []
    try:
        # replied-to message (if any)
        if event.is_reply:
            replied = await event.get_reply_message()
            if replied and replied.raw_text:
                name = "KCE" if replied.sender_id == me.id else "them"
                ctx.append(f"[{name}]: {replied.raw_text[:150]}")

        # same sender's last few messages in this chat
        sender_id = event.sender_id
        msgs = await CipherElite.get_messages(event.chat_id, limit=limit + 3)
        same_user_msgs = []
        for m in msgs:
            if m.id == event.message.id:
                continue
            if m.sender_id == sender_id and m.raw_text and not m.raw_text.startswith((".", "..")):
                same_user_msgs.append(f"[them]: {m.raw_text[:150]}")

        # take most recent 3 from same user
        same_user_msgs = same_user_msgs[:3]
        ctx.extend(same_user_msgs)
    except Exception as e:
        dbg(f"context fetch error: {e}")
    return ctx[-limit:]


# ═══════════════════════════════════════════════════════════════
#  AI REPLY HANDLER — mention / reply-to-me / keyword
# ═══════════════════════════════════════════════════════════════

async def _fire_online():
    """Fire UpdateStatusRequest to show online — unrestricted."""
    try:
        await CipherElite(functions.account.UpdateStatusRequest(offline=False))
    except Exception as e:
        dbg(f"online ping error: {e}")


@CipherElite.on(events.NewMessage)
async def kce_reply_handler(event):
    try:
        if not is_whitelisted(event.chat_id):
            return
        if event.out:
            return
        text = event.raw_text or ""
        if not text or text.startswith((".", "..")):
            return

        me = await CipherElite.get_me()
        sender = await event.get_sender()
        if sender and sender.id == me.id:
            return

        triggered = False
        trigger_type = None

        if event.is_reply:
            replied = await event.get_reply_message()
            if replied and replied.sender_id == me.id:
                triggered, trigger_type = True, "reply"
        if not triggered and me.username and f"@{me.username.lower()}" in text.lower():
            triggered, trigger_type = True, "mention"
        if not triggered and has_trigger(text):
            triggered, trigger_type = True, "keyword"

        if not triggered:
            return

        dbg(f"trigger={trigger_type} chat={event.chat_id} user={sender.id if sender else '?'} text='{text[:50]}'")

        user_id = event.sender_id
        if not can_reply_to_user(user_id):
            dbg("block: per-user gap")
            return
        if not can_reply_in_group(event.chat_id):
            dbg("block: hourly cap")
            await queue_item(
                f"⚠️ Hourly cap reached in **{getattr(await event.get_chat(), 'title', '?')}**\n"
                f"Trigger: `{trigger_type}`"
            )
            return
        if not can_reply_daily():
            dbg("block: daily cap")
            await queue_item("🚨 **Daily cap reached** — replies paused until midnight UTC")
            return

        context = await _get_smart_context(event, me, limit=5)
        reply_text = await generate_reply(text, context)
        if not reply_text:
            await queue_item(
                f"⚠️ **Gemini failed to generate reply**\n"
                f"Group: `{getattr(await event.get_chat(), 'title', '?')}`\n"
                f"They said: \"{text[:100]}\"\n"
                f"Check API quota / logs."
            )
            return

        delay = get_delay()
        dbg(f"delay {delay}s before reply")

        # ── typing pattern B: typing → pause → typing → send
        try:
            await _fire_online()
            first_half = max(1, delay // 2)
            second_half = max(1, delay - first_half)
            async with CipherElite.action(event.chat_id, "typing"):
                await asyncio.sleep(first_half)
            await asyncio.sleep(random.uniform(0.5, 1.5))
            async with CipherElite.action(event.chat_id, "typing"):
                await asyncio.sleep(second_half)
        except Exception as e:
            dbg(f"typing indicator failed: {e}")
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
            await queue_item(f"❌ **Reply send failed** in `{event.chat_id}`: `{e}`")
            return

        track_reply(event.chat_id, user_id)

        stamp = now_dict()
        chat = await event.get_chat()
        chat_name = getattr(chat, "title", "Unknown")
        user_name = (getattr(sender, "first_name", "") or getattr(sender, "username", "") or "Unknown")[:30]

        replies = DB.get("replies", [])
        reply_num = len(replies) + 1

        jump_link = build_jump_link(event.chat_id, event.message.id)

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
            "jump_link": jump_link,
            "feedback": None,
        }
        replies.append(record)
        DB["replies"] = replies[-500:]
        save_db(DB)

        card = build_reply_card(
            reply_num, chat_name, user_name, text, reply_text,
            speed=CURRENT_SPEED, jump_link=jump_link
        )
        await send_log(card)

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

# ═══ END OF BATCH 4 ═══
# ═══════════════════════════════════════════════════════════════
#  DM WATCHER — forwards ALL DMs to QUEUE group
# ═══════════════════════════════════════════════════════════════

@CipherElite.on(events.NewMessage(func=lambda e: e.is_private and not e.out))
async def kce_dm_watcher(event):
    try:
        text = event.raw_text or ""
        if not text or text.startswith((".", "..")):
            return

        sender = await event.get_sender()
        sender_name = (
            getattr(sender, "first_name", "") or
            getattr(sender, "username", "") or
            "Unknown"
        )[:30]
        sender_id = event.sender_id

        # check if suspicious
        lower = text.lower()
        is_suspicious = any(k in lower for k in DM_ALERT_KEYWORDS)

        header = "🚨 **SUSPICIOUS DM**" if is_suspicious else "📥 **DM received**"
        msg = (
            f"{header}\n"
            f"━━━━━━━━━━━━━━━━━━━━\n"
            f"👤 **{sender_name}**\n"
            f"🆔 `{sender_id}`\n"
            f"🕐 {datetime.utcnow().strftime('%I:%M:%S %p')} — {datetime.utcnow().strftime('%d/%m/%Y')}\n"
            f"━━━━━━━━━━━━━━━━━━━━\n"
            f"💬 \"{text[:400]}\""
        )
        await queue_item(msg, alert=is_suspicious)
    except Exception as e:
        print(f"[aireply] DM watcher error: {e}")


# ═══════════════════════════════════════════════════════════════
#  SUSPICIOUS REPLY WATCHER — replies to bot's own replies
# ═══════════════════════════════════════════════════════════════

@CipherElite.on(events.NewMessage)
async def kce_suspicious_reply_watcher(event):
    try:
        if event.out:
            return
        if not is_whitelisted(event.chat_id):
            return
        if not event.is_reply:
            return

        text = event.raw_text or ""
        if not text:
            return

        me = await CipherElite.get_me()
        replied = await event.get_reply_message()
        if not replied or replied.sender_id != me.id:
            return

        lower = text.lower()
        is_suspicious = any(k in lower for k in DM_ALERT_KEYWORDS)

        if not is_suspicious:
            return

        sender = await event.get_sender()
        sender_name = (
            getattr(sender, "first_name", "") or
            getattr(sender, "username", "") or
            "Unknown"
        )[:30]
        chat = await event.get_chat()
        chat_name = getattr(chat, "title", "Unknown")

        await queue_item(
            f"🚨 **SUSPICIOUS REPLY TO BOT**\n"
            f"━━━━━━━━━━━━━━━━━━━━\n"
            f"📍 **{chat_name}**\n"
            f"👤 **{sender_name}** (`{event.sender_id}`)\n"
            f"🕐 {datetime.utcnow().strftime('%I:%M:%S %p')}\n"
            f"━━━━━━━━━━━━━━━━━━━━\n"
            f"💬 \"{text[:400]}\"",
            alert=True
        )
    except Exception as e:
        print(f"[aireply] suspicious watcher error: {e}")


# ═══════════════════════════════════════════════════════════════
#  AUTO-ONLINE + HEARTBEAT (30s)
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
# ║  === END OF AIRREPLY v1.2 + v1.5 — STAGE 1 COMPLETE ===      ║
# ║  Features included:                                          ║
# ║  • Smarter context (same user last 3 + replied-to msg)       ║
# ║  • Anti-repeat cache (last 10, retry on duplicate)           ║
# ║  • Anti-AI system prompt (banned phrases + slang + few-shot) ║
# ║  • Word limit = 3                                            ║
# ║  • Clickable jump links in log cards                         ║
# ║  • QUEUE = DMs + errors + failed replies + caps              ║
# ║  • Auto-online during reply cycle (unrestricted fire)        ║
# ║  • Typing indicator (typing → pause → typing → send)         ║
# ║  • Suspicious DM + reply-to-bot watcher                      ║
# ║  • Multi-key rotation (via CipherElite's .addai)             ║
# ║  Deferred to Stage 4:                                        ║
# ║  • Inline feedback buttons (👍 👎 ✏️)                         ║
# ╚══════════════════════════════════════════════════════════════╝
