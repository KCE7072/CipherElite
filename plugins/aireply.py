# =============================================================================
#  CipherElite Userbot Plugin - aireply.py v1.0 (Stage 1)
#  AI replies in whitelisted groups + learning system
# =============================================================================

from telethon import events
from telethon.errors import FloodWaitError
from utils.utils import CipherElite
from utils.decorators import rishabh
from plugins.bot import add_handler
import asyncio
import json
import re
import aiohttp
import random
from datetime import datetime
from pathlib import Path

VERSION = "1.0.0"
CATEGORY = "utilities"

# ═══════════════════════════════════════════════════════════════
#  CONFIG
# ═══════════════════════════════════════════════════════════════

import os
GEMINI_API_KEY = "AQ.Ab8RN6IOtHAVIblk3zNNJpBHs7wh5hU6U_GZhnE6gYpErCJ_FQ"
AI_LOG_CHAT_ID = -1004374819145 # or 0 if no group yet
QUEUE_CHAT_ID = -1003860044937 # or 0

# Trigger keywords
KEYWORDS = ['gm', 'hi', 'hello', 'wagmi', 'moon', 'airdrop', 'lfg', 'wagmi fam']
is
# Reply settings
WORD_LIMIT = 5       # Max words in reply
CONFIDENCE_MIN = 70  # Min confidence to reply
REPLY_DELAY_MIN = 3  # Min seconds before reply
REPLY_DELAY_MAX = 8  # Max seconds before reply

# Anti-ban
MIN_GAP_SAME_USER = 30  # Seconds between replies to same user
RATE_LIMIT_HOURLY = 20  # Max replies per hour per group
RATE_LIMIT_DAILY = 150  # Max replies per day total

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
        "replied_users": {},   # user_id: last_reply_ts
        "hourly": {},          # group_id: [timestamps]
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


# ═══════════════════════════════════════════════════════════════
#  HELPERS
# ═══════════════════════════════════════════════════════════════

def now_dict():
    n = datetime.utcnow()
    return {
        "date": n.strftime("%Y-%m-%d"),
        "time": n.strftime("%H:%M:%S"),
        "time12": n.strftime("%I:%M:%S %p"),
        "ts": n.timestamp()
    }


def is_whitelisted(chat_id):
    return chat_id in DB.get("whitelist", [])


def has_trigger(text):
    lower = (text or "").lower()
    return any(k in lower for k in KEYWORDS)


def can_reply_to_user(user_id):
    """Check min gap between replies to same user."""
    last = DB.get("replied_users", {}).get(str(user_id), 0)
    return (datetime.utcnow().timestamp() - last) >= MIN_GAP_SAME_USER


def can_reply_in_group(group_id):
    """Check hourly rate limit per group."""
    now = datetime.utcnow().timestamp()
    hour_ago = now - 3600
    timestamps = DB.get("hourly", {}).get(str(group_id), [])
    recent = [t for t in timestamps if t > hour_ago]
    return len(recent) < RATE_LIMIT_HOURLY


def can_reply_daily():
    """Check daily limit."""
    reset_daily_if_needed()
    return DB["daily"].get("count", 0) < RATE_LIMIT_DAILY


def track_reply(group_id, user_id):
    """Record a reply for rate limits."""
    now = datetime.utcnow().timestamp()
    # Track user
    DB.setdefault("replied_users", {})[str(user_id)] = now
    # Track hourly per group
    hourly = DB.setdefault("hourly", {})
    group_ts = hourly.get(str(group_id), [])
    group_ts.append(now)
    # Keep last 100 only
    hourly[str(group_id)] = group_ts[-100:]
    # Track daily
    DB["daily"]["count"] = DB["daily"].get("count", 0) + 1
    save_db(DB)

# ═══ END OF CHUNK 1 ═══
# ═══════════════════════════════════════════════════════════════
#  GEMINI AI INTEGRATION
# ═══════════════════════════════════════════════════════════════

GEMINI_URL = "https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash:generateContent"


async def ask_gemini(prompt, max_retries=2):
    """Send prompt to Gemini and get response."""
    if not GEMINI_API_KEY:
        return None
    
    payload = {
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {
            "temperature": 1.1,
            "maxOutputTokens": 50,
            "topP": 0.95,
        }
    }
    
    for attempt in range(max_retries):
        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    f"{GEMINI_URL}?key={GEMINI_API_KEY}",
                    json=payload,
                    timeout=aiohttp.ClientTimeout(total=15)
                ) as resp:
                    if resp.status != 200:
                        print(f"[aireply] Gemini HTTP {resp.status}")
                        continue
                    data = await resp.json()
                    text = data.get("candidates", [{}])[0].get("content", {}).get("parts", [{}])[0].get("text", "")
                    return text.strip()
        except Exception as e:
            print(f"[aireply] Gemini error: {e}")
            await asyncio.sleep(1)
    
    return None


async def generate_reply(their_message, context_messages=None):
    """Generate a human-like reply to a message."""
    context = ""
    if context_messages:
        context = "\n".join([f"- {m}" for m in context_messages[-5:]])
    
    prompt = f"""You are KCE — a real person in a crypto Telegram group.

Write ONE short reply to the message below.
- Maximum 5 words
- Lowercase where natural
- Casual Nigerian crypto-native tone
- No hashtags, no links, no "great question"
- 0-1 emoji max (only 🔥, 👀, 🫡, 💪)
- Never sound like an AI assistant
- Match the vibe of the message

Recent context:
{context if context else "(no context)"}

Message to reply to:
\"{their_message[:200]}\"

Your reply (just the text, nothing else):"""
    
    response = await ask_gemini(prompt)
    if not response:
        return None
    
    # Clean up
    response = response.replace("\n", " ").strip()
    response = response.strip('"').strip("'")
    response = re.sub(r'^(reply|response|answer):\s*', '', response, flags=re.IGNORECASE)
    
    # Enforce word limit
    words = response.split()
    if len(words) > WORD_LIMIT:
        response = " ".join(words[:WORD_LIMIT])
    
    # Reject if too short or too long
    if len(response) < 2 or len(response) > 100:
        return None
    
    return response


# ═══════════════════════════════════════════════════════════════
#  LOG CARD BUILDER
# ═══════════════════════════════════════════════════════════════

def build_reply_card(raid_id, group_name, user_name, their_msg, bot_reply, status="sent"):
    """Build a beautiful animated log card."""
    emoji = "🎯⚡💥🔥"
    
    status_line = "✅ SENT" if status == "sent" else f"❌ {status.upper()}"
    
    card = f"""╔══════════════════════════════════════╗
║  {emoji}  KCE AI REPLY  {emoji}
║  ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
║  📍 {group_name[:30]}
║  👤 {user_name[:30]}
║  🕐 {datetime.utcnow().strftime('%I:%M:%S %p')} — {datetime.utcnow().strftime('%d/%m/%Y')}
╚══════════════════════════════════════╝

📩 THEY SAID
\"{their_msg[:150]}\"

🤖 KCE REPLIED
\"{bot_reply}\"

✅ {status_line}
🔗 Auto-generated reply
━━━━━━━━━━━━━━━━━━━━━━━━━━━━

[👍 Good]  [👎 Bad]  [✏️ Correct]"""
    
    return card


async def send_log(text):
    """Send to AI REPLY LOG group."""
    if not AI_LOG_CHAT_ID:
        print(f"[aireply] LOG: {text[:100]}")
        return None
    try:
        return await CipherElite.send_message(AI_LOG_CHAT_ID, text)
    except Exception as e:
        print(f"[aireply] log error: {e}")
        return None


async def queue_item(text):
    """Send to QUEUE group for manual handling."""
    if not QUEUE_CHAT_ID:
        return
    try:
        await CipherElite.send_message(QUEUE_CHAT_ID, text)
    except Exception as e:
        print(f"[aireply] queue error: {e}")


# ═══════════════════════════════════════════════════════════════
#  INIT
# ═══════════════════════════════════════════════════════════════

def init(client_instance):
    commands = [
        "..aiwl - Whitelist current group for AI replies",
        "..aiwl off - Remove from whitelist",
        "..aiwl list - Show whitelisted groups",
        ".ai on - Enable AI replies globally",
        ".ai off - Disable AI replies",
        ".ai status - Show AI reply status",
    ]
    description = "🤖 AI Reply v1.0 — Replies as you in whitelisted groups"
    add_handler("aireply", commands, description)

# ═══ END OF CHUNK 2 ═══
# ═══════════════════════════════════════════════════════════════
#  WHITELIST COMMANDS
# ═══════════════════════════════════════════════════════════════

# ═══════════════════════════════════════════════════════════════
#  WHITELIST COMMANDS
# ═══════════════════════════════════════════════════════════════

@CipherElite.on(events.NewMessage(pattern=r"\.\.aiwl$"))
async def cmd_aiwl_add(event):
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
            f"✅ **AI WHITELIST UPDATED**\n"
            f"Group: **{chat_name}**\n"
            f"ID: `{chat_id}`\n"
            f"Total: `{len(wl)}` groups"
        )
    except Exception as e:
        await send_log(f"❌ WL add error: `{e}`")


@CipherElite.on(events.NewMessage(pattern=r"\.\.aiwl\s+off$"))
async def cmd_aiwl_remove(event):
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


@CipherElite.on(events.NewMessage(pattern=r"\.\.aiwl\s+list$"))
@rishabh()
async def cmd_aiwl_list(event):
    try:
        wl = DB.get("whitelist", [])
        if not wl:
            return await event.reply("📭 No whitelisted groups for AI replies.")
        lines = ["📋 **AI Whitelist**\n"]
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


@CipherElite.on(events.NewMessage(pattern=r"\.air\s+status$"))
@rishabh()
async def cmd_ai_status(event):
    try:
        reset_daily_if_needed()
        wl = DB.get("whitelist", [])
        replies = DB.get("replies", [])
        daily = DB.get("daily", {})
        await event.reply(
            f"🤖 **AI Reply v1.0**\n"
            f"━━━━━━━━━━━━━━━━━━━━\n"
            f"📝 Whitelisted: `{len(wl)}` groups\n"
            f"💬 Replies sent: `{len(replies)}`\n"
            f"📅 Today: `{daily.get('count', 0)}/{RATE_LIMIT_DAILY}`\n"
            f"🚀 Started: `{DB.get('started', '?')}`\n"
            f"━━━━━━━━━━━━━━━━━━━━\n"
            f"⚙️ Word limit: `{WORD_LIMIT}`\n"
            f"⏱️ Reply delay: `{REPLY_DELAY_MIN}-{REPLY_DELAY_MAX}s`"
        )
    except Exception as e:
        await event.reply(f"❌ Error: `{e}`")


# ═══════════════════════════════════════════════════════════════
#  CORE REPLY HANDLER — Listens to ALL messages
# ═══════════════════════════════════════════════════════════════

@CipherElite.on(events.NewMessage)
async def ai_reply_handler(event):
    """Main handler — decides when to reply."""
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

        if event.is_private:
            await queue_item(
                f"📩 **DM RECEIVED**\n"
                f"From: {event.sender_id}\n"
                f"Message: \"{text[:200]}\"\n"
                f"⏰ {now_dict()['time12']}"
            )
            return

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

        if not can_reply_to_user(event.sender_id):
            return
        if not can_reply_in_group(chat_id):
            return
        if not can_reply_daily():
            return

        delay = random.randint(REPLY_DELAY_MIN, REPLY_DELAY_MAX)
        await asyncio.sleep(delay)

        sender = await event.get_sender()
        user_name = getattr(sender, "first_name", "Someone")

        context_msgs = []
        try:
            async for msg in CipherElite.iter_messages(chat_id, limit=5):
                if msg.id != event.id and msg.text:
                    context_msgs.append(msg.text[:80])
            context_msgs.reverse()
        except Exception:
            pass

        reply_text = await generate_reply(text, context_msgs)
        if not reply_text:
            return

        try:
            await event.reply(reply_text)
        except FloodWaitError as e:
            print(f"[aireply] FloodWait {e.seconds}s")
            return

        track_reply(chat_id, event.sender_id)

        chat = await event.get_chat()
        chat_name = getattr(chat, "title", "Unknown")
        card = build_reply_card(
            raid_id=len(DB.get("replies", [])) + 1,
            group_name=chat_name,
            user_name=user_name,
            their_msg=text,
            bot_reply=reply_text,
            status="sent"
        )
        await send_log(card)

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

    except Exception as e:
        print(f"[aireply] handler error: {e}")

# ═══ END OF CHUNK 3 ═══
# ═══════════════════════════════════════════════════════════════
#  MEMORY & STATS COMMANDS
# ═══════════════════════════════════════════════════════════════

@CipherElite.on(events.NewMessage(pattern=r"\.air\s+memory$"))
@rishabh()
async def cmd_ai_memory(event):
    try:
        replies = DB.get("replies", [])
        await event.reply(
            f"🧠 **AI Memory**\n"
            f"━━━━━━━━━━━━━━━━━━━━\n"
            f"💬 Total replies stored: `{len(replies)}`\n"
            f"📊 Keep last: `500`\n"
            f"💾 File: `DB/aireply.json`\n"
            f"━━━━━━━━━━━━━━━━━━━━"
        )
    except Exception as e:
        await event.reply(f"❌ Error: `{e}`")


@CipherElite.on(events.NewMessage(pattern=r"\.air\s+stats$"))
@rishabh()
async def cmd_ai_stats(event):
    try:
        reset_daily_if_needed()
        replies = DB.get("replies", [])
        daily = DB.get("daily", {})

        lines = [
            f"📊 **AI Reply Stats**",
            f"━━━━━━━━━━━━━━━━━━━━",
            f"💬 Total replies: `{len(replies)}`",
            f"📅 Today: `{daily.get('count', 0)}/{RATE_LIMIT_DAILY}`",
            f"📝 Whitelisted groups: `{len(DB.get('whitelist', []))}`",
        ]

        if replies:
            lines.append("")
            lines.append("**Last 3:**")
            for r in replies[-3:]:
                lines.append(f"• [{r.get('time12', '?')}] {r.get('bot_reply', '')[:40]}")

        await event.reply("\n".join(lines))
    except Exception as e:
        await event.reply(f"❌ Error: `{e}`")


@CipherElite.on(events.NewMessage(pattern=r"\.air\s+replies(?:\s+(\d+))?$"))
@rishabh()
async def cmd_ai_replies(event):
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


@CipherElite.on(events.NewMessage(pattern=r"\.air\s+reset$"))
@rishabh()
async def cmd_ai_reset(event):
    try:
        DB["replies"] = []
        DB["replied_users"] = {}
        DB["hourly"] = {}
        DB["daily"] = {"date": today_str(), "count": 0}
        save_db(DB)
        await event.reply("🔄 Memory reset. Whitelist preserved.")
    except Exception as e:
        await event.reply(f"❌ Error: `{e}`")


@CipherElite.on(events.NewMessage(pattern=r"\.air\s+help$"))
@rishabh()
async def cmd_ai_help(event):
    try:
        help_text = (
            "🤖 **AI Reply v1.0 — Commands**\n"
            "━━━━━━━━━━━━━━━━━━━━\n"
            "**Whitelist:**\n"
            "`..aiwl` — Add current group\n"
            "`..aiwl off` — Remove current group\n"
            "`..aiwl list` — Show all whitelisted\n\n"
            "**Status & Stats:**\n"
            "`.air status` — Bot status\n"
            "`.air stats` — Reply stats\n"
            "`.air memory` — Memory info\n"
            "`.air replies [n]` — Show last N replies\n"
            "`.air reset` — Clear memory (keeps whitelist)\n\n"
            "**How it works:**\n"
            "• Bot listens in whitelisted groups\n"
            "• Replies when: mentioned, replied-to, or keyword (gm, hi, wagmi...)\n"
            "• Uses AI to write 5-word max replies in your style\n"
            "• Random 3-8s delay for human feel\n"
            "• Never replies in DMs (forwarded to Queue)\n"
            "━━━━━━━━━━━━━━━━━━━━"
        )
        await event.reply(help_text)
    except Exception as e:
        await event.reply(f"❌ Error: `{e}`")

# ╔══════════════════════════════════════════════════════════════╗
# ║  === END OF AIReply V1.0 — ALL 4 CHUNKS COMPLETE ===         ║
# ║  If you see this marker, the plugin is fully pasted.         ║
# ╚══════════════════════════════════════════════════════════════╝

        
