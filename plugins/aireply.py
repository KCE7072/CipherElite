# =============================================================================
#  CipherElite Userbot Plugin - aireply.py v1.0 (Stage 1)
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

VERSION = "1.0.0"
CATEGORY = "utilities"

# ═══════════════════════════════════════════════════════════════
#  CONFIG
# ═══════════════════════════════════════════════════════════════

AI_LOG_CHAT_ID = -1004453857887
QUEUE_CHAT_ID = -1004453857887

KEYWORDS = ['gm', 'hi', 'hello', 'wagmi', 'moon', 'airdrop', 'lfg', 'wagmi fam']
WORD_LIMIT = 5
REPLY_DELAY_MIN = 3
REPLY_DELAY_MAX = 8
MIN_GAP_SAME_USER = 30
RATE_LIMIT_HOURLY = 20
RATE_LIMIT_DAILY = 150

# Speed modes
SPEED_MODES = {
    "fast": (1, 3),
    "normal": (3, 8),
    "slow": (8, 20),
}
CURRENT_SPEED = "normal"

# Reaction settings
REACT_TO_GM = True
REACT_PROBABILITY = 0.3  # 30% chance when triggered
REACTION_EMOJIS = ["🔥", "👀", "🫡", "💪", "😂"]

GEMINI_MODEL = "gemini-3.7-flash"

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


def has_trigger(text):
    lower = (text or "").lower()
    return any(k in lower for k in KEYWORDS)


def can_reply_to_user(user_id):
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
    """Get delay range based on current speed mode."""
    lo, hi = SPEED_MODES.get(CURRENT_SPEED, SPEED_MODES["normal"])
    return random.randint(lo, hi)


# ═══════════════════════════════════════════════════════════════
#  GEMINI CALL (uses CipherElite's ai_config)
# ═══════════════════════════════════════════════════════════════

async def generate_reply(their_message, context_messages=None):
    if not ai_config.is_enabled():
        return None
    api_key = ai_config.get_api_key()
    if not api_key:
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
            return None
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
#  INIT
# ═══════════════════════════════════════════════════════════════

def init(client_instance):
    commands = [
        ".kce status — Show AI reply status",
        ".kce stats — Show reply stats",
        ".kce replies [n] — Show last N replies",
        ".kce reset — Clear memory (keeps whitelist)",
        ".kce speed fast|normal|slow — Change reply speed",
        ".kce help — Command reference",
        ".kcew — Whitelist current group",
        ".kcew off — Remove current group from whitelist",
        ".kcew list — Show whitelisted groups",
    ]
    description = "🤖 AI Reply v1.0 — Replies as you in whitelisted groups"
    add_handler("aireply", commands, description)


# ═══════════════════════════════════════════════════════════════
#  WHITELIST COMMANDS (.kcew)
# ═══════════════════════════════════════════════════════════════

@CipherElite.on(events.NewMessage(pattern=r"\.kcew$"))
async def cmd_kcew_add(event):
    try:
        try:
            await event.delete()
        except:
            pass
        chat = await event.get_chat()
        chat_id = event.chat_id
        chat_name = getattr(chat, "title", "Unknown")
        wl = DB.get("whitelist", [])
        if chat_id in wl:
            await send_log(f"ℹ️ Already whitelisted: **{chat_name}**")
            return
        wl.append(chat_id)
        DB["whitelist"] = wl
        save_db(DB)
        await send_log(
            f"✅ **KCE AI WHITELIST UPDATED**\n"
            f"Group: **{chat_name}**\n"
            f"ID: `{chat_id}`\n"
            f"Total: `{len(wl)}` groups"
        )
    except Exception as e:
        await send_log(f"❌ WL add error: `{e}`")


@CipherElite.on(events.NewMessage(pattern=r"\.kcew\s+off$"))
async def cmd_kcew_remove(event):
    try:
        try:
            await event.delete()
        except:
            pass
        chat = await event.get_chat()
        chat_id = event.chat_id
        chat_name = getattr(chat, "title", "Unknown")
        wl = DB.get("whitelist", [])
        if chat_id not in wl:
            await send_log(f"ℹ️ Not whitelisted: **{chat_name}**")
            return
        wl.remove(chat_id)
        DB["whitelist"] = wl
        save_db(DB)
        await send_log(f"🗑️ Removed: **{chat_name}**\nRemaining: `{len(wl)}`")
    except Exception as e:
        await send_log(f"❌ WL remove error: `{e}`")


@CipherElite.on(events.NewMessage(pattern=r"\.kcew\s+list$"))
@rishabh()
async def cmd_kcew_list(event):
    try:
        wl = DB.get("whitelist", [])
        if not wl:
            return await event.reply("📭 No whitelisted groups for AI replies.")
        lines = ["📋 **KCE AI Whitelist**\n"]
        for cid in wl:
            try:
                entity = await CipherElite.get_entity(cid)
                name = getattr(entity, "title", "Unknown")
            except Exception:
                name = "Unknown"
            lines.append(f"• **{name}** (`{cid}`)")
        await event.reply("\n".join(lines))
    except Exception as e:
        await event.reply(f"❌ Error: `{e}`")


# ═══════════════════════════════════════════════════════════════
#  STATUS / STATS / MEMORY COMMANDS (.kce)
# ═══════════════════════════════════════════════════════════════

@CipherElite.on(events.NewMessage(pattern=r"\.kce\s+status$"))
@rishabh()
async def cmd_kce_status(event):
    try:
        reset_daily_if_needed()
        wl = DB.get("whitelist", [])
        replies = DB.get("replies", [])
        daily = DB.get("daily", {})
        ai_ready = "✅ Ready" if ai_config.is_enabled() else "❌ Key Not Set"
        await event.reply(
            f"🤖 **KCE AI Reply v1.0**\n"
            f"━━━━━━━━━━━━━━━━━━━━\n"
            f"🧠 Gemini: {ai_ready}\n"
            f"📝 Whitelisted: `{len(wl)}` groups\n"
            f"💬 Replies sent: `{len(replies)}`\n"
            f"📅 Today: `{daily.get('count', 0)}/{RATE_LIMIT_DAILY}`\n"
            f"⚡ Speed: `{CURRENT_SPEED}`\n"
            f"🚀 Started: `{DB.get('started', '?')}`\n"
            f"━━━━━━━━━━━━━━━━━━━━\n"
            f"⚙️ Word limit: `{WORD_LIMIT}`"
        )
    except Exception as e:
        await event.reply(f"❌ Error: `{e}`")


@CipherElite.on(events.NewMessage(pattern=r"\.kce\s+stats$"))
@rishabh()
async def cmd_kce_stats(event):
    try:
        reset_daily_if_needed()
        replies = DB.get("replies", [])
        daily = DB.get("daily", {})
        lines = [
            f"📊 **KCE AI Stats**",
            f"━━━━━━━━━━━━━━━━━━━━",
            f"💬 Total replies: `{len(replies)}`",
            f"📅 Today: `{daily.get('count', 0)}/{RATE_LIMIT_DAILY}`",
            f"📝 Whitelisted: `{len(DB.get('whitelist', []))}` groups",
        ]
        if replies:
            lines.append("")
            lines.append("**Last 3:**")
            for r in replies[-3:]:
                lines.append(f"• [{r.get('time12', '?')}] {r.get('bot_reply', '')[:40]}")
        await event.reply("\n".join(lines))
    except Exception as e:
        await event.reply(f"❌ Error: `{e}`")


@CipherElite.on(events.NewMessage(pattern=r"\.kce\s+replies(?:\s+(\d+))?$"))
@rishabh()
async def cmd_kce_replies(event):
    try:
        n = int(event.pattern_match.group(1) or 10)
        replies = DB.get("replies", [])[-n:]
        if not replies:
            return await event.reply("📭 No replies recorded yet.")
        lines = [f"📜 **Last {len(replies)} AI Replies**\n"]
        for r in replies:
            lines.append(
                f"💬 [{r.get('time12', '?')}] {r.get('group_name', '?')[:20]}\n"
                f"   👤 {r.get('user_name', '?')[:20]}: \"{r.get('their_msg', '')[:40]}\"\n"
                f"   🤖 \"{r.get('bot_reply', '')}\""
            )
        await event.reply("\n".join(lines))
    except Exception as e:
        await event.reply(f"❌ Error: `{e}`")


@CipherElite.on(events.NewMessage(pattern=r"\.kce\s+reset$"))
@rishabh()
async def cmd_kce_reset(event):
    try:
        DB["replies"] = []
        DB["replied_users"] = {}
        DB["hourly"] = {}
        DB["daily"] = {"date": today_str(), "count": 0}
        save_db(DB)
        await event.reply("🔄 Memory reset. Whitelist preserved.")
    except Exception as e:
        await event.reply(f"❌ Error: `{e}`")


@CipherElite.on(events.NewMessage(pattern=r"\.kce\s+speed\s+(fast|normal|slow)$"))
@rishabh()
async def cmd_kce_speed(event):
    global CURRENT_SPEED
    try:
        mode = event.pattern_match.group(1).lower()
        if mode in SPEED_MODES:
            CURRENT_SPEED = mode
            lo, hi = SPEED_MODES[mode]
            await event.reply(
                f"⚡ **Speed updated**\n"
                f"Mode: `{mode}`\n"
                f"Reply delay: `{lo}-{hi}s`"
            )
    except Exception as e:
        await event.reply(f"❌ Error: `{e}`")


@CipherElite.on(events.NewMessage(pattern=r"\.kce\s+help$"))
@rishabh()
async def cmd_kce_help(event):
    try:
        await event.reply(
            "🤖 **KCE AI Reply v1.0 — Commands**\n"
            "━━━━━━━━━━━━━━━━━━━━\n"
            "**Whitelist:**\n"
            "`.kcew` — Add current group\n"
            "`.kcew off` — Remove current group\n"
            "`.kcew list` — Show whitelisted\n\n"
            "**Status:**\n"
            "`.kce status` — Bot status\n"
            "`.kce stats` — Reply stats\n"
            "`.kce replies [n]` — Last N replies\n"
            "`.kce reset` — Clear memory\n"
            "`.kce speed fast|normal|slow` — Change speed\n\n"
            "**How it works:**\n"
            "• Bot listens in whitelisted groups\n"
            "• Replies when: mentioned, replied-to, or keyword\n"
            "• Uses CipherElite's AI (no separate key)\n"
            "• Random delay for human feel\n"
            "• Never replies in DMs\n"
            "━━━━━━━━━━━━━━━━━━━━"
        )
    except Exception as e:
        await event.reply(f"❌ Error: `{e}`")


# ═══════════════════════════════════════════════════════════════
#  CORE REPLY HANDLER
# ═══════════════════════════════════════════════════════════════

@CipherElite.on(events.NewMessage)
async def ai_reply_handler(event):
    try:
        text = event.raw_text or ""
        if not text or text.startswith(".") or text.startswith(".."):
            return

        me = await CipherElite.get_me()
        if event.sender_id == me.id:
            return

        chat_id = event.chat_id
        if not is_whitelisted(chat_id):
            return

        # DMs → forward to queue, never reply
        if event.is_private:
            await queue_item(
                f"📩 **DM RECEIVED**\n"
                f"From: {event.sender_id}\n"
                f"Message: \"{text[:200]}\"\n"
                f"⏰ {now_dict()['time12']}"
            )
            return

        # Trigger check
        should_reply = False
        if event.mentioned:
            should_reply = True
        elif event.is_reply:
            try:
                replied_msg = await event.get_reply_message()
                if replied_msg and replied_msg.sender_id == me.id:
                    should_reply = True
            except Exception:
                pass
        elif has_trigger(text):
            should_reply = True

        if not should_reply:
            return

        # Rate limits
        if not can_reply_to_user(event.sender_id):
            return
        if not can_reply_in_group(chat_id):
            return
        if not can_reply_daily():
            return

        # Auto-online heartbeat (silent — just appears online)
        # CipherElite already shows online when active.

        # Delay
        delay = get_delay()
        await asyncio.sleep(delay)

        sender = await event.get_sender()
        user_name = getattr(sender, "first_name", "Someone")

        # Context
        context_msgs = []
        try:
            async for msg in CipherElite.iter_messages(chat_id, limit=5):
                if msg.id != event.id and msg.text:
                    context_msgs.append(msg.text[:80])
            context_msgs.reverse()
        except Exception:
            pass

        # Generate reply
        reply_text = await generate_reply(text, context_msgs)
        if not reply_text:
            return

        # Send
        try:
            await event.reply(reply_text)
        except FloodWaitError as e:
            print(f"[aireply] FloodWait {e.seconds}s")
            return

        track_reply(chat_id, event.sender_id)

        chat = await event.get_chat()
        chat_name = getattr(chat, "title", "Unknown")

        reply_num = len(DB.get("replies", [])) + 1
        card = build_reply_card(
            n=reply_num,
            group_name=chat_name,
            user_name=user_name,
            their_msg=text,
            bot_reply=reply_text,
            speed=CURRENT_SPEED
        )
        await send_log(card)

        # Store memory
        DB.setdefault("replies", []).append({
            "group_id": chat_id,
            "group_name": chat_name,
            "user_id": event.sender_id,
            "user_name": user_name,
            "their_msg": text[:200],
            "bot_reply": reply_text,
            "time12": now_dict()["time12"],
            "ts": datetime.utcnow().timestamp()
        })
        DB["replies"] = DB["replies"][-500:]
        save_db(DB)

        # Reaction (30% chance)
        if REACT_TO_GM and random.random() < REACT_PROBABILITY:
            try:
                emoji = random.choice(REACTION_EMOJIS)
                await event.react(emoji)
            except Exception:
                pass

    except Exception as e:
        print(f"[aireply] handler error: {e}")

# ╔══════════════════════════════════════════════════════════════╗
# ║  === END OF AIReply V1.0 — STAGE 1 COMPLETE ===              ║
# ║  If you see this marker, the plugin is fully pasted.         ║
# ╚══════════════════════════════════════════════════════════════╝
