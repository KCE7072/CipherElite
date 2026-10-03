# =============================================================================
#  CipherElite Userbot Plugin - aireply.py v3.0
#  AI replies + queue buttons + quiz mode + wallet drop + WAT timezone
#  Stage 2 complete
# =============================================================================

from telethon import events, Button, TelegramClient
from telethon.errors import FloodWaitError
from telethon.tl import functions
from utils.utils import CipherElite
from utils.decorators import rishabh
from plugins.bot import add_handler
from plugins.ai_setup import ai_config
import asyncio
import json
import re
import os
import random
from datetime import datetime, timedelta, timezone
from pathlib import Path
from google import genai
from google.genai import types

VERSION = "3.0.0"
CATEGORY = "utilities"

# ═══════════════════════════════════════════════════════════════
#  TIMEZONE
# ═══════════════════════════════════════════════════════════════

WAT = timezone(timedelta(hours=1))

def wat_now():
    return datetime.now(WAT)

# ═══════════════════════════════════════════════════════════════
#  CONFIG
# ═══════════════════════════════════════════════════════════════

AI_LOG_CHAT_ID = -1004374819145
QUEUE_CHAT_ID  = -1003860044937

KEYWORDS = ['gm', 'hi', 'hello', 'hey', 'wagmi', 'moon', 'airdrop', 'lfg']
WORD_LIMIT = 3
MIN_GAP_SAME_USER = 0
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

RECENT_REPLIES = []
MAX_RECENT = 10

DM_ALERT_KEYWORDS = [
    'bot', 'ai', 'robot', 'real', 'human', 'who is', 'who are',
    'automated', 'script', 'kce', 'cipher', 'reply bot'
]

# ── Quiz mode
QUIZ_CORRECT_RATIO = 4          # 4 correct
QUIZ_WRONG_RATIO = 1            # : 1 wrong
QUIZ_WRONG_EMOJIS = ["💀", "😂"]

# Signals from mods that indicate a correct answer
QUIZ_CORRECT_SIGNALS = [
    'correct', '✅', 'right', 'yes', 'winner', 'win', 'spot on',
    'accurate', 'correcto', '✔', '👍'
]

# ── Wallet regex
WALLET_PATTERNS = {
    'sol': re.compile(r'\b[1-9A-HJ-NP-Za-km-z]{32,44}\b'),
    'evm': re.compile(r'\b0x[a-fA-F0-9]{40}\b'),
    'sui': re.compile(r'\b0x[a-fA-F0-9]{64}\b'),
}

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
WALLET_FILE = DB_DIR / "aireply_wallets.json"
BOT_SESSION_FILE = DB_DIR / "queue_bot"
QUEUE_BOT_CONFIG_FILE = DB_DIR / "queue_bot_config.json"


def _load_bot_token():
    try:
        if QUEUE_BOT_CONFIG_FILE.exists():
            data = json.loads(QUEUE_BOT_CONFIG_FILE.read_text(encoding="utf-8"))
            tok = data.get("token", "").strip()
            if tok:
                return tok
    except Exception as e:
        print(f"[aireply] bot config load error: {e}")
    return ""


QUEUE_BOT_TOKEN = _load_bot_token()


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
        "dm_blacklist": [],
        "dm_whitelist": [],
        # v3 flags per group
        "quiz_groups": [],       # list of chat_ids with quiz mode ON
        "wallet_groups": [],     # list of chat_ids with wallet drop ON
        "reply_groups": [],      # list of chat_ids where bot replies (already whitelist)
        "trusted_mods": {},      # {chat_id: [user_id, ...]} — extra trusted mods beyond admins
        # quiz state per group
        "quiz_state": {},        # {chat_id: {"seen": [...], "learned_style": "...", "counter": 0}}
        "started": wat_now().strftime("%Y-%m-%d %H:%M:%S"),
    }


def save_db(data):
    try:
        DB_FILE.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
    except Exception as e:
        print(f"[aireply] save error: {e}")


DB = load_db()


def load_wallets():
    try:
        if WALLET_FILE.exists():
            return json.loads(WALLET_FILE.read_text(encoding="utf-8"))
    except Exception as e:
        print(f"[aireply] wallet load error: {e}")
    return {"sol": "", "evm": "", "sui": ""}


def save_wallets(data):
    try:
        WALLET_FILE.write_text(json.dumps(data, indent=2), encoding="utf-8")
    except Exception as e:
        print(f"[aireply] wallet save error: {e}")


WALLETS = load_wallets()


def validate_wallet(chain, addr):
    """Return (ok, reason)."""
    addr = (addr or "").strip()
    if not addr:
        return False, "empty"
    if chain == "sol":
        if not re.fullmatch(r'[1-9A-HJ-NP-Za-km-z]{32,44}', addr):
            return False, "SOL wallet must be 32-44 base58 chars"
    elif chain == "evm":
        if not re.fullmatch(r'0x[a-fA-F0-9]{40}', addr):
            return False, "EVM wallet must be 0x + 40 hex chars"
    elif chain == "sui":
        if not re.fullmatch(r'0x[a-fA-F0-9]{64}', addr):
            return False, "SUI wallet must be 0x + 64 hex chars"
    else:
        return False, f"unknown chain: {chain}"
    return True, "ok"


def today_str():
    return wat_now().strftime("%Y-%m-%d")


def reset_daily_if_needed():
    if DB.get("daily", {}).get("date") != today_str():
        DB["daily"] = {"date": today_str(), "count": 0}
        save_db(DB)


def now_dict():
    n = wat_now()
    return {
        "date": n.strftime("%Y-%m-%d"),
        "time12": n.strftime("%I:%M:%S %p"),
        "ts": n.timestamp()
    }


def is_whitelisted(chat_id):
    return chat_id in DB.get("whitelist", [])


def is_quiz_group(chat_id):
    return chat_id in DB.get("quiz_groups", [])


def is_wallet_group(chat_id):
    return chat_id in DB.get("wallet_groups", [])


def is_dm_blacklisted(user_id):
    return user_id in DB.get("dm_blacklist", [])


def get_trusted_mods(chat_id):
    return DB.get("trusted_mods", {}).get(str(chat_id), [])


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
    return (wat_now().timestamp() - last) >= MIN_GAP_SAME_USER


def can_reply_in_group(group_id):
    now = wat_now().timestamp()
    hour_ago = now - 3600
    timestamps = DB.get("hourly", {}).get(str(group_id), [])
    recent = [t for t in timestamps if t > hour_ago]
    return len(recent) < RATE_LIMIT_HOURLY


def can_reply_daily():
    reset_daily_if_needed()
    return DB["daily"].get("count", 0) < RATE_LIMIT_DAILY


def track_reply(group_id, user_id):
    now = wat_now().timestamp()
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


def build_jump_link(chat_id, msg_id):
    try:
        cid_str = str(chat_id)
        if cid_str.startswith("-100"):
            internal = cid_str[4:]
        elif cid_str.startswith("-"):
            internal = cid_str[1:]
        else:
            internal = cid_str
        return f"https://t.me/c/{internal}/{msg_id}"
    except Exception:
        return None


def format_user(sender):
    if not sender:
        return "Unknown"
    name = getattr(sender, "first_name", "") or ""
    uname = getattr(sender, "username", "") or ""
    if name and uname:
        return f"{name} (@{uname})"
    elif uname:
        return f"@{uname}"
    elif name:
        return name
    return "Unknown"


def resolve_link_to_chat_id(link):
    """Return chat_id from a t.me link, or None. Must be async — see plugin."""
    return None  # resolved async in command handler

# ═══ END OF BATCH 1 ═══

# ═══════════════════════════════════════════════════════════════
#  GEMINI — keyword replies + quiz answer style
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
            dbg(f"gemini bad length: '{text}'")
            return None

        if text.lower() in [r.lower() for r in RECENT_REPLIES]:
            dbg(f"duplicate: '{text}' — retrying")
            try:
                retry_prompt = user_prompt + (
                    f"\n\nIMPORTANT: You already said '{text}'. "
                    f"Do NOT repeat it. Say something completely different, max {WORD_LIMIT} words."
                )
                r2 = await client.aio.models.generate_content(
                    model=GEMINI_MODEL,
                    contents=[types.Content(role="user", parts=[types.Part(text=retry_prompt)])],
                    config=types.GenerateContentConfig(
                        system_instruction=SYSTEM_PROMPT,
                        max_output_tokens=200,
                        temperature=1.5,
                        top_p=0.98,
                    ),
                )
                t2 = (r2.text or "").strip().replace("\n", " ").strip('"').strip("'")
                w2 = t2.split()
                if len(w2) > WORD_LIMIT:
                    t2 = " ".join(w2[:WORD_LIMIT])
                if t2 and len(t2) >= 2 and t2.lower() not in [r.lower() for r in RECENT_REPLIES]:
                    text = t2
                    dbg(f"retry ok: '{text}'")
            except Exception as e:
                dbg(f"retry failed: {e}")

        RECENT_REPLIES.append(text)
        if len(RECENT_REPLIES) > MAX_RECENT:
            RECENT_REPLIES.pop(0)

        dbg(f"gemini ok: '{text}'")
        return text
    except Exception as e:
        print(f"[aireply] Gemini error: {e}")
        return None


async def generate_quiz_answer(question, learned_examples, learned_style):
    """Generate a quiz answer mimicking learned style."""
    if not ai_config.is_enabled():
        return None
    api_key = ai_config.get_api_key()
    if not api_key:
        return None

    examples_text = ""
    if learned_examples:
        examples_text = "Correct answers I've seen in this group:\n" + "\n".join(
            [f"- {e}" for e in learned_examples[-8:]]
        )

    style_hint = learned_style or "(short, lowercase, no punctuation)"

    prompt = f"""You are answering a quiz question in a Telegram group.

{examples_text}

Style to mimic: {style_hint}

QUESTION:
\"{question[:300]}\"

Answer in 1-3 words, matching the group's answer style. Just the answer, nothing else."""

    try:
        client = genai.Client(api_key=api_key)
        config = types.GenerateContentConfig(
            max_output_tokens=30,
            temperature=0.9,
        )
        resp = await client.aio.models.generate_content(
            model=GEMINI_MODEL,
            contents=[types.Content(role="user", parts=[types.Part(text=prompt)])],
            config=config,
        )
        text = (resp.text or "").strip().replace("\n", " ").strip('"').strip("'")
        if len(text) < 1 or len(text) > 60:
            return None
        dbg(f"quiz answer generated: '{text}'")
        return text
    except Exception as e:
        print(f"[aireply] quiz gemini error: {e}")
        return None


# ═══════════════════════════════════════════════════════════════
#  QUEUE BOT CLIENT
# ═══════════════════════════════════════════════════════════════

QUEUE_BOT = None
BOT_SUPERVISOR_TASK = None
BOT_RUNNING = False


async def _queue_bot_start():
    global QUEUE_BOT, BOT_RUNNING
    if BOT_RUNNING and QUEUE_BOT and QUEUE_BOT.is_connected():
        return
    if not QUEUE_BOT_TOKEN:
        dbg("queue bot: no token")
        return
    try:
        bot = TelegramClient(str(BOT_SESSION_FILE), 6, "eb06d4abfb49dc3eeb1aeb98ae0f581e")
        await bot.start(bot_token=QUEUE_BOT_TOKEN)

        @bot.on(events.CallbackQuery)
        async def _on_callback(event):
            try:
                data = event.data.decode() if isinstance(event.data, bytes) else str(event.data)
                await _handle_button(event, data)
            except Exception as e:
                print(f"[aireply] callback error: {e}")
                try:
                    await event.answer("Error", alert=False)
                except Exception:
                    pass

        QUEUE_BOT = bot
        BOT_RUNNING = True
        me = await bot.get_me()
        dbg(f"queue bot: connected ✅ @{me.username}")
    except Exception as e:
        BOT_RUNNING = False
        print(f"[aireply] queue bot start error: {e}")


async def _queue_bot_supervisor():
    global BOT_RUNNING
    await asyncio.sleep(30)
    while True:
        try:
            if QUEUE_BOT_TOKEN:
                alive = QUEUE_BOT and QUEUE_BOT.is_connected()
                if not alive:
                    dbg("supervisor: restarting")
                    BOT_RUNNING = False
                    await _queue_bot_start()
        except Exception as e:
            print(f"[aireply] supervisor error: {e}")
        await asyncio.sleep(60)


async def _handle_button(event, data):
    try:
        parts = data.split(":")
        action = parts[0]
        target_id = parts[1] if len(parts) > 1 else None

        if action == "ack":
            await event.answer("✅ Acked")
            try:
                await event.edit(event.message.text + "\n\n✅ ACKED")
            except Exception:
                pass
            return

        if action == "block_dm":
            try:
                uid = int(target_id)
                bl = DB.get("dm_blacklist", [])
                if uid not in bl:
                    bl.append(uid)
                    DB["dm_blacklist"] = bl
                    save_db(DB)
                await event.answer(f"🚫 Blocked {uid}")
            except Exception as e:
                await event.answer(f"Error: {e}")
            return

        if action == "unblock_dm":
            try:
                uid = int(target_id)
                bl = DB.get("dm_blacklist", [])
                if uid in bl:
                    bl.remove(uid)
                    DB["dm_blacklist"] = bl
                    save_db(DB)
                await event.answer(f"🔓 Unblocked {uid}")
            except Exception as e:
                await event.answer(f"Error: {e}")
            return

        if action == "allow_dm":
            try:
                uid = int(target_id)
                wl = DB.get("dm_whitelist", [])
                if uid not in wl:
                    wl.append(uid)
                    DB["dm_whitelist"] = wl
                    save_db(DB)
                await event.answer(f"✅ Allowed {uid}")
            except Exception as e:
                await event.answer(f"Error: {e}")
            return

        if action == "clear":
            try:
                await event.delete()
                await event.answer("🗑️ Cleared", alert=False)
            except Exception:
                await event.answer("Cleared")
            return

        if action in ("good", "bad", "correct"):
            try:
                n = int(target_id)
                replies = DB.get("replies", [])
                for r in replies:
                    if r.get("n") == n:
                        r["feedback"] = action
                        break
                save_db(DB)
                await event.answer(f"✅ Logged as {action}")
            except Exception as e:
                await event.answer(f"Error: {e}")
            return

        # quiz button click
        if action == "quizclick":
            # data: quizclick:chat_id:msg_id:row:col
            try:
                chat_id = int(parts[1])
                msg_id = int(parts[2])
                row = int(parts[3])
                col = int(parts[4])
                try:
                    msg = await CipherElite.get_messages(chat_id, ids=msg_id)
                    if msg and msg.buttons:
                        await msg.click(row, col)
                        await event.answer("✅ Clicked")
                    else:
                        await event.answer("⚠️ No buttons on msg")
                except Exception as e:
                    await event.answer(f"❌ {e}")
            except Exception as e:
                await event.answer(f"Error: {e}")
            return

        await event.answer("Unknown action")
    except Exception as e:
        print(f"[aireply] button handler error: {e}")
        try:
            await event.answer("Error")
        except Exception:
            pass

# ═══ END OF BATCH 2 ═══

# ═══════════════════════════════════════════════════════════════
#  SENDERS — log card + queue
# ═══════════════════════════════════════════════════════════════

def build_reply_card(n, group_name, user_name, their_msg, bot_reply,
                     speed="normal", jump_link=None):
    header = (
        "╔══════════════════════════════════════╗\n"
        "║  🎯⚡💥🔥  KCE AI REPLY  🎯⚡💥🔥\n"
        "║  ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        f"║  📍 {group_name[:30]}\n"
        f"║  👤 {user_name[:40]}\n"
        f"║  🕐 {wat_now().strftime('%I:%M:%S %p')} — {wat_now().strftime('%d/%m/%Y')} WAT\n"
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


def build_quiz_card(n, group_name, question, answer, correct, jump_link=None):
    emoji = "✅" if correct else "❌"
    header = (
        "╔══════════════════════════════════════╗\n"
        "║  🎯⚡💥🔥  KCE QUIZ REPLY  🎯⚡💥🔥\n"
        "║  ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        f"║  📍 {group_name[:30]}\n"
        f"║  🕐 {wat_now().strftime('%I:%M:%S %p')} — {wat_now().strftime('%d/%m/%Y')} WAT\n"
        "╚══════════════════════════════════════╝"
    )
    body = (
        f'\n❓ QUIZ\n"{question[:150]}"\n'
        f'\n🤖 KCE ANSWERED\n"{answer}"\n'
        f"\n{emoji} {'CORRECT' if correct else 'DELIBERATE WRONG'}\n"
        f"🔗 Quiz reply  •  #{n}\n"
    )
    if jump_link:
        body += f"🔗 Jump to message: {jump_link}\n"
    body += "━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    return header + body


async def send_log(text, buttons=None):
    """Log cards sent via queue bot so feedback buttons work."""
    try:
        if QUEUE_BOT and QUEUE_BOT.is_connected():
            try:
                return await QUEUE_BOT.send_message(AI_LOG_CHAT_ID, text, buttons=buttons)
            except Exception as e:
                dbg(f"log via bot failed, fallback to userbot: {e}")
        if buttons:
            text += "\n\n_(buttons unavailable — bot offline)_"
        return await CipherElite.send_message(AI_LOG_CHAT_ID, text)
    except Exception as e:
        print(f"[aireply] log error: {e}")
        return None


async def queue_item(text, alert=False, buttons=None):
    try:
        prefix = "🚨 " if alert else "📥 "
        full_text = prefix + text
        if QUEUE_BOT and QUEUE_BOT.is_connected():
            try:
                return await QUEUE_BOT.send_message(QUEUE_CHAT_ID, full_text, buttons=buttons)
            except Exception as e:
                dbg(f"queue via bot failed: {e}")
        if buttons:
            full_text += "\n\n_(buttons unavailable)_"
        await CipherElite.send_message(QUEUE_CHAT_ID, full_text)
    except Exception as e:
        print(f"[aireply] queue error: {e}")


def make_dm_buttons(sender_id):
    return [[
        Button.inline("✅ Allow", f"allow_dm:{sender_id}".encode()),
        Button.inline("🚫 Block", f"block_dm:{sender_id}".encode()),
    ]]


def make_suspicious_buttons(sender_id):
    return [[
        Button.inline("✅ Ack", b"ack"),
        Button.inline("🚫 Block user", f"block_dm:{sender_id}".encode()),
    ]]


def make_error_buttons():
    return [[Button.inline("✅ Ack", b"ack"), Button.inline("🗑️ Clear", b"clear")]]


def make_cap_buttons():
    return [[Button.inline("✅ Ack", b"ack")]]


def make_feedback_buttons(reply_num):
    return [[
        Button.inline("👍 Good", f"good:{reply_num}".encode()),
        Button.inline("👎 Bad", f"bad:{reply_num}".encode()),
        Button.inline("✏️ Correct", f"correct:{reply_num}".encode()),
    ]]


# ═══════════════════════════════════════════════════════════════
#  INIT
# ═══════════════════════════════════════════════════════════════

def init(client_instance):
    commands = [
        ".kce - status",
        ".kce stats - reply stats",
        ".kce memory - memory info",
        ".kce replies [n] - last N replies",
        ".kce reset - clear memory",
        ".kce help - all commands",
        ".kce speed fast|normal|slow",
        ".kce online - heartbeat",
        ".kce tz - timezone",
        ".kce setbot <token> - save queue bot token",
        ".kce bot status / restart / diag",
        ".kce dm block/unblock/list",
        ".kcew - whitelist current group",
        ".kcew off - remove whitelist",
        ".kcew list - list whitelisted",
        ".kce quiz on/off <link>",
        ".kce wallet on/off <link>",
        ".kce wallet set sol|evm|sui <addr>",
        ".kce wallet list",
        ".kce reply on/off <link>",
        ".kce mods add/remove/list [<link>]",
        ".kce flags list",
    ]
    description = "🤖 KCE AI Reply v3.0 — replies + quiz + wallet + buttons"
    add_handler("aireply", commands, description)


async def _safe_reply(event, text):
    try:
        if event.is_private:
            await event.reply(text)
        else:
            await send_log(text)
    except Exception as e:
        print(f"[aireply] safe_reply error: {e}")


async def _is_owner(event):
    try:
        me = await CipherElite.get_me()
        return event.sender_id == me.id
    except Exception:
        return False


async def resolve_link_to_chat_id(link):
    """Resolve t.me link to chat_id via CipherElite."""
    try:
        link = link.strip()
        if link.startswith("https://t.me/"):
            link = link.replace("https://t.me/", "")
        elif link.startswith("t.me/"):
            link = link.replace("t.me/", "")
        # strip invite prefix
        if link.startswith("+"):
            try:
                inv = await CipherElite(functions.messages.CheckChatInviteRequest(link))
                return getattr(inv.chat, "id", None)
            except Exception as e:
                dbg(f"invite resolve error: {e}")
                return None
        # public username
        try:
            entity = await CipherElite.get_entity(link)
            return entity.id
        except Exception as e:
            dbg(f"entity resolve error: {e}")
            return None
    except Exception as e:
        dbg(f"link resolve error: {e}")
        return None


# ═══════════════════════════════════════════════════════════════
#  BOT LIFECYCLE COMMANDS
# ═══════════════════════════════════════════════════════════════

@CipherElite.on(events.NewMessage(pattern=r"\.kce\s+setbot\s+(\S+)$"))
@rishabh()
async def cmd_setbot(event):
    if not await _is_owner(event):
        return
    try:
        token = event.pattern_match.group(1).strip()
        if ":" not in token or len(token) < 40:
            return await _safe_reply(event, f"❌ Invalid token (len={len(token)})")
        try: await event.delete()
        except: pass
        QUEUE_BOT_CONFIG_FILE.write_text(
            json.dumps({"token": token, "saved_at": wat_now().strftime("%Y-%m-%d %H:%M:%S")}, indent=2),
            encoding="utf-8"
        )
        await _safe_reply(event, f"✅ Token saved ({len(token)} chars). Run `.kce bot restart`.")
    except Exception as e:
        await send_log(f"❌ setbot error: `{e}`")


@CipherElite.on(events.NewMessage(pattern=r"\.kce\s+bot\s+status$"))
@rishabh()
async def cmd_bot_status(event):
    if not await _is_owner(event):
        return
    try:
        if not QUEUE_BOT_TOKEN:
            return await _safe_reply(event, "❌ No token. Run `.kce setbot <token>`.")
        if QUEUE_BOT and QUEUE_BOT.is_connected():
            me = await QUEUE_BOT.get_me()
            return await _safe_reply(event, f"✅ **Queue bot online**\n👤 @{me.username}\n🆔 `{me.id}`")
        await _safe_reply(event, "⚠️ Not connected — try `.kce bot restart`")
    except Exception as e:
        await send_log(f"❌ bot status error: `{e}`")


@CipherElite.on(events.NewMessage(pattern=r"\.kce\s+bot\s+restart$"))
@rishabh()
async def cmd_bot_restart(event):
    if not await _is_owner(event):
        return
    try:
        global QUEUE_BOT, BOT_RUNNING, QUEUE_BOT_TOKEN
        try:
            if QUEUE_BOT and QUEUE_BOT.is_connected():
                await QUEUE_BOT.disconnect()
        except Exception:
            pass
        QUEUE_BOT = None
        BOT_RUNNING = False
        QUEUE_BOT_TOKEN = _load_bot_token()
        if not QUEUE_BOT_TOKEN:
            return await _safe_reply(event, "❌ No token. `.kce setbot <token>`")
        await _safe_reply(event, f"🔄 Restarting (len={len(QUEUE_BOT_TOKEN)})...")
        await _queue_bot_start()
        await asyncio.sleep(2)
        status = "✅ online" if (QUEUE_BOT and QUEUE_BOT.is_connected()) else "❌ offline"
        await _safe_reply(event, f"Queue bot: {status}")
    except Exception as e:
        await send_log(f"❌ bot restart error: `{e}`")


@CipherElite.on(events.NewMessage(pattern=r"\.kce\s+diag$"))
@rishabh()
async def cmd_diag(event):
    if not await _is_owner(event):
        return
    try:
        lines = ["🔍 **KCE Diagnostics**", "━━━━━━━━━━━━━━━━━━━━"]
        lines.append(f"{'✅' if QUEUE_BOT_TOKEN else '❌'} Token: {'set' if QUEUE_BOT_TOKEN else 'empty'}")
        lines.append(f"{'✅' if QUEUE_BOT_CONFIG_FILE.exists() else '❌'} Config file")
        if QUEUE_BOT:
            conn = QUEUE_BOT.is_connected()
            lines.append(f"🤖 Client: {'🟢 connected' if conn else '🔴 disconnected'}")
        else:
            lines.append("🤖 Client: **None**")
        lines.append(f"⚙️ BOT_RUNNING: `{BOT_RUNNING}`")
        lines.append(f"📝 Whitelisted: `{len(DB.get('whitelist', []))}`")
        lines.append(f"❓ Quiz groups: `{len(DB.get('quiz_groups', []))}`")
        lines.append(f"💰 Wallet groups: `{len(DB.get('wallet_groups', []))}`")
        await _safe_reply(event, "\n".join(lines))
    except Exception as e:
        await _safe_reply(event, f"❌ Diag error: `{e}`")


# ═══════════════════════════════════════════════════════════════
#  GROUP FLAG COMMANDS (.kce quiz/wallet/reply on|off <link>)
# ═══════════════════════════════════════════════════════════════

@CipherElite.on(events.NewMessage(pattern=r"\.kce\s+quiz\s+(on|off)\s+(\S+)$"))
@rishabh()
async def cmd_quiz_flag(event):
    if not await _is_owner(event):
        return
    try:
        action = event.pattern_match.group(1).lower()
        link = event.pattern_match.group(2)
        cid = await resolve_link_to_chat_id(link)
        if cid is None:
            return await _safe_reply(event, f"❌ Could not resolve `{link}`")
        groups = DB.get("quiz_groups", [])
        if action == "on":
            if cid in groups:
                return await _safe_reply(event, f"ℹ️ Quiz already ON for `{cid}`")
            groups.append(cid)
            DB["quiz_groups"] = groups
            save_db(DB)
            await _safe_reply(event, f"✅ Quiz mode **ON** for `{cid}`")
        else:
            if cid not in groups:
                return await _safe_reply(event, f"ℹ️ Quiz already OFF for `{cid}`")
            groups.remove(cid)
            DB["quiz_groups"] = groups
            save_db(DB)
            await _safe_reply(event, f"⏹️ Quiz mode **OFF** for `{cid}`")
    except Exception as e:
        await send_log(f"❌ quiz flag error: `{e}`")


@CipherElite.on(events.NewMessage(pattern=r"\.kce\s+wallet\s+(on|off)\s+(\S+)$"))
@rishabh()
async def cmd_wallet_flag(event):
    if not await _is_owner(event):
        return
    try:
        action = event.pattern_match.group(1).lower()
        link = event.pattern_match.group(2)
        cid = await resolve_link_to_chat_id(link)
        if cid is None:
            return await _safe_reply(event, f"❌ Could not resolve `{link}`")
        groups = DB.get("wallet_groups", [])
        if action == "on":
            if cid in groups:
                return await _safe_reply(event, f"ℹ️ Wallet already ON for `{cid}`")
            groups.append(cid)
            DB["wallet_groups"] = groups
            save_db(DB)
            await _safe_reply(event, f"✅ Wallet drop **ON** for `{cid}`")
        else:
            if cid not in groups:
                return await _safe_reply(event, f"ℹ️ Wallet already OFF for `{cid}`")
            groups.remove(cid)
            DB["wallet_groups"] = groups
            save_db(DB)
            await _safe_reply(event, f"⏹️ Wallet drop **OFF** for `{cid}`")
    except Exception as e:
        await send_log(f"❌ wallet flag error: `{e}`")


@CipherElite.on(events.NewMessage(pattern=r"\.kce\s+reply\s+(on|off)\s+(\S+)$"))
@rishabh()
async def cmd_reply_flag(event):
    if not await _is_owner(event):
# ═══════════════════════════════════════════════════════════════
#  SENDERS — log card + queue
# ═══════════════════════════════════════════════════════════════

def build_reply_card(n, group_name, user_name, their_msg, bot_reply,
                     speed="normal", jump_link=None):
    header = (
        "╔══════════════════════════════════════╗\n"
        "║  🎯⚡💥🔥  KCE AI REPLY  🎯⚡💥🔥\n"
        "║  ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        f"║  📍 {group_name[:30]}\n"
        f"║  👤 {user_name[:40]}\n"
        f"║  🕐 {wat_now().strftime('%I:%M:%S %p')} — {wat_now().strftime('%d/%m/%Y')} WAT\n"
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


def build_quiz_card(n, group_name, question, answer, correct, jump_link=None):
    emoji = "✅" if correct else "❌"
    header = (
        "╔══════════════════════════════════════╗\n"
        "║  🎯⚡💥🔥  KCE QUIZ REPLY  🎯⚡💥🔥\n"
        "║  ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        f"║  📍 {group_name[:30]}\n"
        f"║  🕐 {wat_now().strftime('%I:%M:%S %p')} — {wat_now().strftime('%d/%m/%Y')} WAT\n"
        "╚══════════════════════════════════════╝"
    )
    body = (
        f'\n❓ QUIZ\n"{question[:150]}"\n'
        f'\n🤖 KCE ANSWERED\n"{answer}"\n'
        f"\n{emoji} {'CORRECT' if correct else 'DELIBERATE WRONG'}\n"
        f"🔗 Quiz reply  •  #{n}\n"
    )
    if jump_link:
        body += f"🔗 Jump to message: {jump_link}\n"
    body += "━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    return header + body


async def send_log(text, buttons=None):
    """Log cards sent via queue bot so feedback buttons work."""
    try:
        if QUEUE_BOT and QUEUE_BOT.is_connected():
            try:
                return await QUEUE_BOT.send_message(AI_LOG_CHAT_ID, text, buttons=buttons)
            except Exception as e:
                dbg(f"log via bot failed, fallback: {e}")
        if buttons:
            text += "\n\n_(buttons unavailable — bot offline)_"
        return await CipherElite.send_message(AI_LOG_CHAT_ID, text)
    except Exception as e:
        print(f"[aireply] log error: {e}")
        return None


async def queue_item(text, alert=False, buttons=None):
    try:
        prefix = "🚨 " if alert else "📥 "
        full_text = prefix + text
        if QUEUE_BOT and QUEUE_BOT.is_connected():
            try:
                return await QUEUE_BOT.send_message(QUEUE_CHAT_ID, full_text, buttons=buttons)
            except Exception as e:
                dbg(f"queue via bot failed: {e}")
        if buttons:
            full_text += "\n\n_(buttons unavailable)_"
        await CipherElite.send_message(QUEUE_CHAT_ID, full_text)
    except Exception as e:
        print(f"[aireply] queue error: {e}")


def make_dm_buttons(sender_id):
    return [[
        Button.inline("✅ Allow", f"allow_dm:{sender_id}".encode()),
        Button.inline("🚫 Block", f"block_dm:{sender_id}".encode()),
    ]]


def make_suspicious_buttons(sender_id):
    return [[
        Button.inline("✅ Ack", b"ack"),
        Button.inline("🚫 Block user", f"block_dm:{sender_id}".encode()),
    ]]


def make_error_buttons():
    return [[Button.inline("✅ Ack", b"ack"), Button.inline("🗑️ Clear", b"clear")]]


def make_cap_buttons():
    return [[Button.inline("✅ Ack", b"ack")]]


def make_feedback_buttons(reply_num):
    return [[
        Button.inline("👍 Good", f"good:{reply_num}".encode()),
        Button.inline("👎 Bad", f"bad:{reply_num}".encode()),
        Button.inline("✏️ Correct", f"correct:{reply_num}".encode()),
    ]]


# ═══════════════════════════════════════════════════════════════
#  INIT
# ═══════════════════════════════════════════════════════════════

def init(client_instance):
    commands = [
        ".kce - status",
        ".kce stats - reply stats",
        ".kce memory - memory info",
        ".kce replies [n] - last N replies",
        ".kce reset - clear memory",
        ".kce help - all commands",
        ".kce speed fast|normal|slow",
        ".kce online - heartbeat",
        ".kce tz - timezone",
        ".kce setbot <token> - save queue bot token",
        ".kce bot status / restart / diag",
        ".kce dm block/unblock/list",
        ".kcew - whitelist current group",
        ".kcew off - remove whitelist",
        ".kcew list - list whitelisted",
        ".kce quiz on/off <link|id>",
        ".kce wallet on/off <link|id>",
        ".kce wallet set sol|evm|sui <addr>",
        ".kce wallet list",
        ".kce reply on/off <link|id>",
        ".kce mods add/remove/list [<link|id>]",
        ".kce flags list",
    ]
    description = "🤖 KCE AI Reply v3.0 — replies + quiz + wallet + buttons"
    add_handler("aireply", commands, description)


async def _safe_reply(event, text):
    try:
        if event.is_private:
            await event.reply(text)
        else:
            await send_log(text)
    except Exception as e:
        print(f"[aireply] safe_reply error: {e}")


async def _is_owner(event):
    try:
        me = await CipherElite.get_me()
        return event.sender_id == me.id
    except Exception:
        return False


async def resolve_link_to_chat_id(link):
    """Resolve t.me link OR numeric ID to chat_id."""
    try:
        link = link.strip()

        # numeric ID
        if link.lstrip("-").isdigit():
            return int(link)

        # t.me/c/XXX/msg — internal link
        m = re.search(r't\.me/c/(\d+)', link)
        if m:
            return int(f"-100{m.group(1)}")

        # strip t.me prefix
        if link.startswith("https://t.me/"):
            link = link.replace("https://t.me/", "")
        elif link.startswith("t.me/"):
            link = link.replace("t.me/", "")

        # invite link
        if link.startswith("+"):
            try:
                inv = await CipherElite(functions.messages.CheckChatInviteRequest(link))
                chat = getattr(inv, "chat", None)
                if chat:
                    return chat.id
                # already participant — try to get chat via invite hash won't help; return None
                dbg("invite resolve: no chat field (already member?)")
                return None
            except Exception as e:
                dbg(f"invite resolve error: {e}")
                return None

        # public username
        try:
            entity = await CipherElite.get_entity(link)
            return entity.id
        except Exception as e:
            dbg(f"entity resolve error: {e}")
            return None
    except Exception as e:
        dbg(f"link resolve error: {e}")
        return None


# ═══════════════════════════════════════════════════════════════
#  BOT LIFECYCLE COMMANDS
# ═══════════════════════════════════════════════════════════════

@CipherElite.on(events.NewMessage(pattern=r"\.kce\s+setbot\s+(\S+)$"))
@rishabh()
async def cmd_setbot(event):
    if not await _is_owner(event):
        return
    try:
        token = event.pattern_match.group(1).strip()
        if ":" not in token or len(token) < 40:
            return await _safe_reply(event, f"❌ Invalid token (len={len(token)})")
        try: await event.delete()
        except: pass
        QUEUE_BOT_CONFIG_FILE.write_text(
            json.dumps({"token": token, "saved_at": wat_now().strftime("%Y-%m-%d %H:%M:%S")}, indent=2),
            encoding="utf-8"
        )
        await _safe_reply(event, f"✅ Token saved ({len(token)} chars). Run `.kce bot restart`.")
    except Exception as e:
        await send_log(f"❌ setbot error: `{e}`")


@CipherElite.on(events.NewMessage(pattern=r"\.kce\s+bot\s+status$"))
@rishabh()
async def cmd_bot_status(event):
    if not await _is_owner(event):
        return
    try:
        if not QUEUE_BOT_TOKEN:
            return await _safe_reply(event, "❌ No token. Run `.kce setbot <token>`.")
        if QUEUE_BOT and QUEUE_BOT.is_connected():
            me = await QUEUE_BOT.get_me()
            return await _safe_reply(event, f"✅ **Queue bot online**\n👤 @{me.username}\n🆔 `{me.id}`")
        await _safe_reply(event, "⚠️ Not connected — try `.kce bot restart`")
    except Exception as e:
        await send_log(f"❌ bot status error: `{e}`")


@CipherElite.on(events.NewMessage(pattern=r"\.kce\s+bot\s+restart$"))
@rishabh()
async def cmd_bot_restart(event):
    if not await _is_owner(event):
        return
    try:
        global QUEUE_BOT, BOT_RUNNING, QUEUE_BOT_TOKEN
        try:
            if QUEUE_BOT and QUEUE_BOT.is_connected():
                await QUEUE_BOT.disconnect()
        except Exception:
            pass
        QUEUE_BOT = None
        BOT_RUNNING = False
        QUEUE_BOT_TOKEN = _load_bot_token()
        if not QUEUE_BOT_TOKEN:
            return await _safe_reply(event, "❌ No token. `.kce setbot <token>`")
        await _safe_reply(event, f"🔄 Restarting (len={len(QUEUE_BOT_TOKEN)})...")
        await _queue_bot_start()
        await asyncio.sleep(2)
        status = "✅ online" if (QUEUE_BOT and QUEUE_BOT.is_connected()) else "❌ offline"
        await _safe_reply(event, f"Queue bot: {status}")
    except Exception as e:
        await send_log(f"❌ bot restart error: `{e}`")


@CipherElite.on(events.NewMessage(pattern=r"\.kce\s+diag$"))
@rishabh()
async def cmd_diag(event):
    if not await _is_owner(event):
        return
    try:
        lines = ["🔍 **KCE Diagnostics**", "━━━━━━━━━━━━━━━━━━━━"]
        lines.append(f"{'✅' if QUEUE_BOT_TOKEN else '❌'} Token: {'set' if QUEUE_BOT_TOKEN else 'empty'}")
        lines.append(f"{'✅' if QUEUE_BOT_CONFIG_FILE.exists() else '❌'} Config file")
        if QUEUE_BOT:
            conn = QUEUE_BOT.is_connected()
            lines.append(f"🤖 Client: {'🟢 connected' if conn else '🔴 disconnected'}")
        else:
            lines.append("🤖 Client: **None**")
        lines.append(f"⚙️ BOT_RUNNING: `{BOT_RUNNING}`")
        lines.append(f"📝 Whitelisted: `{len(DB.get('whitelist', []))}`")
        lines.append(f"❓ Quiz groups: `{len(DB.get('quiz_groups', []))}`")
        lines.append(f"💰 Wallet groups: `{len(DB.get('wallet_groups', []))}`")
        lines.append(f"💬 Reply groups: `{len(DB.get('reply_groups', []))}`")
        await _safe_reply(event, "\n".join(lines))
    except Exception as e:
        await _safe_reply(event, f"❌ Diag error: `{e}`")


# ═══════════════════════════════════════════════════════════════
#  GROUP FLAG COMMANDS
# ═══════════════════════════════════════════════════════════════

@CipherElite.on(events.NewMessage(pattern=r"\.kce\s+quiz\s+(on|off)\s+(\S+)$"))
@rishabh()
async def cmd_quiz_flag(event):
    if not await _is_owner(event):
        return
    try:
        action = event.pattern_match.group(1).lower()
        link = event.pattern_match.group(2)
        cid = await resolve_link_to_chat_id(link)
        if cid is None:
            return await _safe_reply(event, f"❌ Could not resolve `{link}`\nTry numeric ID: `-100...`")
        groups = DB.get("quiz_groups", [])
        if action == "on":
            if cid in groups:
                return await _safe_reply(event, f"ℹ️ Quiz already ON for `{cid}`")
            groups.append(cid)
            DB["quiz_groups"] = groups
            save_db(DB)
            await _safe_reply(event, f"✅ Quiz mode **ON** for `{cid}`")
        else:
            if cid not in groups:
                return await _safe_reply(event, f"ℹ️ Quiz already OFF for `{cid}`")
            groups.remove(cid)
            DB["quiz_groups"] = groups
            save_db(DB)
            await _safe_reply(event, f"⏹️ Quiz mode **OFF** for `{cid}`")
    except Exception as e:
        await send_log(f"❌ quiz flag error: `{e}`")


@CipherElite.on(events.NewMessage(pattern=r"\.kce\s+wallet\s+(on|off)\s+(\S+)$"))
@rishabh()
async def cmd_wallet_flag(event):
    if not await _is_owner(event):
        return
    try:
        action = event.pattern_match.group(1).lower()
        link = event.pattern_match.group(2)
        cid = await resolve_link_to_chat_id(link)
        if cid is None:
            return await _safe_reply(event, f"❌ Could not resolve `{link}`\nTry numeric ID: `-100...`")
        groups = DB.get("wallet_groups", [])
        if action == "on":
            if cid in groups:
                return await _safe_reply(event, f"ℹ️ Wallet already ON for `{cid}`")
            groups.append(cid)
            DB["wallet_groups"] = groups
            save_db(DB)
            await _safe_reply(event, f"✅ Wallet drop **ON** for `{cid}`")
        else:
            if cid not in groups:
                return await _safe_reply(event, f"ℹ️ Wallet already OFF for `{cid}`")
            groups.remove(cid)
            DB["wallet_groups"] = groups
            save_db(DB)
            await _safe_reply(event, f"⏹️ Wallet drop **OFF** for `{cid}`")
    except Exception as e:
        await send_log(f"❌ wallet flag error: `{e}`")


@CipherElite.on(events.NewMessage(pattern=r"\.kce\s+reply\s+(on|off)\s+(\S+)$"))
@rishabh()
async def cmd_reply_flag(event):
    if not await _is_owner(event):
        return
    try:
        action = event.pattern_match.group(1).lower()
        link = event.pattern_match.group(2)
        cid = await resolve_link_to_chat_id(link)
        if cid is None:
            return await _safe_reply(event, f"❌ Could not resolve `{link}`\nTry numeric ID: `-100...`")
        groups = DB.get("reply_groups", [])
        if action == "on":
            if cid in groups:
                return await _safe_reply(event, f"ℹ️ Reply already ON for `{cid}`")
            groups.append(cid)
            DB["reply_groups"] = groups
            save_db(DB)
            await _safe_reply(event, f"✅ Reply mode **ON** for `{cid}`")
        else:
            if cid not in groups:
                return await _safe_reply(event, f"ℹ️ Reply already OFF for `{cid}`")
            groups.remove(cid)
            DB["reply_groups"] = groups
            save_db(DB)
            await _safe_reply(event, f"⏹️ Reply mode **OFF** for `{cid}`")
    except Exception as e:
        await send_log(f"❌ reply flag error: `{e}`")


@CipherElite.on(events.NewMessage(pattern=r"\.kce\s+flags\s+list$"))
@rishabh()
async def cmd_flags_list(event):
    if not await _is_owner(event):
        return
    try:
        lines = ["📋 **KCE Group Flags**\n━━━━━━━━━━━━━━━━━━━━"]

        async def _name(cid):
            try:
                e = await CipherElite.get_entity(cid)
                return getattr(e, "title", str(cid))
            except Exception:
                return str(cid)

        wl = DB.get("whitelist", [])
        qg = DB.get("quiz_groups", [])
        wg = DB.get("wallet_groups", [])
        rg = DB.get("reply_groups", [])

        lines.append(f"**Whitelisted ({len(wl)}):**")
        for cid in wl:
            lines.append(f"  • {await _name(cid)} (`{cid}`)")
        lines.append(f"\n**Quiz ON ({len(qg)}):**")
        for cid in qg:
            lines.append(f"  • {await _name(cid)} (`{cid}`)")
        lines.append(f"\n**Wallet ON ({len(wg)}):**")
        for cid in wg:
            lines.append(f"  • {await _name(cid)} (`{cid}`)")
        lines.append(f"\n**Reply ON ({len(rg)}):**")
        for cid in rg:
            lines.append(f"  • {await _name(cid)} (`{cid}`)")

        await _safe_reply(event, "\n".join(lines))
    except Exception as e:
        await send_log(f"❌ flags list error: `{e}`")

# ═══ END OF BATCH 3 (FIXED) ═══

# ═══ END OF BATCH 3 ═══

# ═══════════════════════════════════════════════════════════════
#  STATUS / STATS / MEMORY / HELP / TZ
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
        bl = DB.get("dm_blacklist", [])
        bot_status = "✅ online" if (QUEUE_BOT and QUEUE_BOT.is_connected()) else "❌ offline"
        msg = (
            "🤖 **KCE AI Reply v3.0**\n"
            "━━━━━━━━━━━━━━━━━━━━\n"
            f"🧠 Gemini: {'✅ Ready' if gemini_ok else '❌ Disabled'}\n"
            f"📝 Whitelisted: `{len(wl)}` groups\n"
            f"❓ Quiz groups: `{len(DB.get('quiz_groups', []))}`\n"
            f"💰 Wallet groups: `{len(DB.get('wallet_groups', []))}`\n"
            f"💬 Replies sent: `{len(replies)}`\n"
            f"📅 Today: `{today}/{RATE_LIMIT_DAILY}`\n"
            f"⚡ Speed: `{CURRENT_SPEED}`\n"
            f"🕐 TZ: `WAT (UTC+1)`\n"
            f"🚫 DM blocked: `{len(bl)}`\n"
            f"🤖 Queue bot: {bot_status}\n"
            f"🚀 Started: `{started}`\n"
            "━━━━━━━━━━━━━━━━━━━━\n"
            f"⚙️ Word limit: `{WORD_LIMIT}`"
        )
        await _safe_reply(event, msg)
    except Exception as e:
        await send_log(f"❌ status error: `{e}`")


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
        good = sum(1 for r in replies if r.get("feedback") == "good")
        bad = sum(1 for r in replies if r.get("feedback") == "bad")
        correct = sum(1 for r in replies if r.get("feedback") == "correct")
        quiz_total = sum(1 for r in replies if r.get("trigger") == "quiz")
        lines = [
            "📊 **KCE Stats**",
            "━━━━━━━━━━━━━━━━━━━━",
            f"💬 Total replies: `{len(replies)}`",
            f"📅 Today: `{today_count}`",
            f"❓ Quiz replies: `{quiz_total}`",
            "",
            "**Feedback:**",
            f"👍 Good: `{good}`",
            f"👎 Bad: `{bad}`",
            f"✏️ Correct: `{correct}`",
            "",
            f"⚡ Speed: `{CURRENT_SPEED}`",
            f"🕐 Per-user gap: `{MIN_GAP_SAME_USER}s`",
            f"🚦 Per-group hourly cap: `{RATE_LIMIT_HOURLY}`",
        ]
        await _safe_reply(event, "\n".join(lines))
    except Exception as e:
        await send_log(f"❌ stats error: `{e}`")


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
            f"💾 Replies: `{len(replies)}` / 500",
            f"👥 Users: `{len(users)}`",
            f"📁 DB: `DB/aireply.json`",
            f"💰 Wallets: `DB/aireply_wallets.json`",
        ]
        await _safe_reply(event, "\n".join(lines))
    except Exception as e:
        await send_log(f"❌ memory error: `{e}`")


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
            return await _safe_reply(event, "📭 No replies.")
        lines = [f"📜 **Last {len(replies)}**\n━━━━━━━━━━━━━━━━━━━━"]
        for r in replies:
            fb = r.get("feedback") or "—"
            lines.append(
                f"`#{r.get('n', '?')}` [{r.get('trigger', '?')}] **{r.get('user_name', '?')[:25]}**\n"
                f"  📩 \"{r.get('they_said', '')[:50]}\"\n"
                f"  🤖 \"{r.get('bot_reply', '')[:50]}\"\n"
                f"  🕐 {r.get('time12', '?')}  •  FB: {fb}"
            )
        await _safe_reply(event, "\n".join(lines))
    except Exception as e:
        await send_log(f"❌ replies error: `{e}`")


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
        await _safe_reply(event, "🔄 Memory cleared.")
    except Exception as e:
        await send_log(f"❌ reset error: `{e}`")


@CipherElite.on(events.NewMessage(pattern=r"\.kce\s+help$"))
@rishabh()
async def cmd_kce_help(event):
    if not await _is_owner(event):
        return
    try:
        msg = (
            "🤖 **KCE AI Reply v3.0 — Commands**\n"
            "━━━━━━━━━━━━━━━━━━━━\n"
            "`.kce` — status\n"
            "`.kce stats` — stats\n"
            "`.kce memory` — memory info\n"
            "`.kce replies [n]` — last N\n"
            "`.kce reset` — clear memory\n"
            "`.kce speed fast|normal|slow`\n"
            "`.kce online` — heartbeat\n"
            "`.kce tz` — timezone\n"
            "`.kce setbot <token>` — save bot token\n"
            "`.kce bot status|restart`\n"
            "`.kce diag` — diagnostics\n"
            "\n**Group flags (from DM):**\n"
            "`.kcew` / `.kcew off` / `.kcew list`\n"
            "`.kce quiz on|off <link>`\n"
            "`.kce wallet on|off <link>`\n"
            "`.kce reply on|off <link>`\n"
            "`.kce flags list`\n"
            "\n**Wallets:**\n"
            "`.kce wallet set sol|evm|sui <addr>`\n"
            "`.kce wallet list`\n"
            "\n**Mods:**\n"
            "`.kce mods add|remove|list [<link>]`\n"
            "\n**DM blacklist:**\n"
            "`.kce dm block|unblock|list`"
        )
        await _safe_reply(event, msg)
    except Exception as e:
        await send_log(f"❌ help error: `{e}`")


@CipherElite.on(events.NewMessage(pattern=r"\.kce\s+speed\s+(fast|normal|slow)$"))
@rishabh()
async def cmd_kce_speed(event):
    global CURRENT_SPEED
    if not await _is_owner(event):
        return
    try:
        mode = event.pattern_match.group(1).lower()
        CURRENT_SPEED = mode
        lo, hi = SPEED_MODES[mode]
        await _safe_reply(event, f"⚡ Speed: **{mode}** ({lo}-{hi}s)")
    except Exception as e:
        await send_log(f"❌ speed error: `{e}`")


@CipherElite.on(events.NewMessage(pattern=r"\.kce\s+tz$"))
@rishabh()
async def cmd_kce_tz(event):
    if not await _is_owner(event):
        return
    try:
        now = wat_now()
        await _safe_reply(
            event,
            f"🕐 **Timezone**\n📍 Nigeria (WAT)\n⚙️ `UTC+1`\n"
            f"🕐 Now: `{now.strftime('%I:%M:%S %p — %d/%m/%Y')}`"
        )
    except Exception as e:
        await send_log(f"❌ tz error: `{e}`")


# ═══════════════════════════════════════════════════════════════
#  WHITELIST (.kcew)
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
            return await send_log(f"ℹ️ Already whitelisted: **{chat_name}**")
        wl.append(chat_id)
        DB["whitelist"] = wl
        save_db(DB)
        await send_log(f"✅ Whitelisted **{chat_name}** (`{chat_id}`). Total: `{len(wl)}`")
    except Exception as e:
        await send_log(f"❌ wl add: `{e}`")


@CipherElite.on(events.NewMessage(pattern=r"\.kcew\s+off(?:\s+(-?\d+))?$"))
async def cmd_kcew_remove(event):
    if not await _is_owner(event):
        return
    try:
        target = event.pattern_match.group(1)
        if target:
            chat_id = int(target)
            chat_name = f"ID {chat_id}"
        else:
            try: await event.delete()
            except: pass
            chat = await event.get_chat()
            chat_id = event.chat_id
            chat_name = getattr(chat, "title", "Unknown")
        wl = DB.get("whitelist", [])
        if chat_id not in wl:
            return await send_log(f"ℹ️ Not whitelisted: `{chat_id}`")
        wl.remove(chat_id)
        DB["whitelist"] = wl
        save_db(DB)
        await send_log(f"🗑️ Removed **{chat_name}** (`{chat_id}`)")
    except Exception as e:
        await send_log(f"❌ wl remove: `{e}`")


@CipherElite.on(events.NewMessage(pattern=r"\.kcew\s+list$"))
@rishabh()
async def cmd_kcew_list(event):
    if not await _is_owner(event):
        return
    try:
        wl = DB.get("whitelist", [])
        if not wl:
            return await _safe_reply(event, "📭 No whitelisted groups.")
        lines = ["📋 **Whitelisted**\n"]
        for cid in wl:
            try:
                e = await CipherElite.get_entity(cid)
                name = getattr(e, "title", "Unknown")
            except Exception:
                name = "Unknown"
            lines.append(f"• **{name}** (`{cid}`)")
        await _safe_reply(event, "\n".join(lines))
    except Exception as e:
        await send_log(f"❌ wl list: `{e}`")


# ═══════════════════════════════════════════════════════════════
#  DM BLACKLIST
# ═══════════════════════════════════════════════════════════════

async def _resolve_user_id(target_str):
    try:
        target = target_str.strip().lstrip("@")
        if target.isdigit() or (target.startswith("-") and target[1:].isdigit()):
            return int(target)
        try:
            entity = await CipherElite.get_entity(target)
            return entity.id
        except Exception:
            return None
    except Exception:
        return None


@CipherElite.on(events.NewMessage(pattern=r"\.kce\s+dm\s+block\s+(\S+)$"))
@rishabh()
async def cmd_dm_block(event):
    if not await _is_owner(event):
        return
    try:
        uid = await _resolve_user_id(event.pattern_match.group(1))
        if uid is None:
            return await _safe_reply(event, "❌ Could not resolve")
        bl = DB.get("dm_blacklist", [])
        if uid in bl:
            return await _safe_reply(event, f"ℹ️ `{uid}` already blocked.")
        bl.append(uid)
        DB["dm_blacklist"] = bl
        save_db(DB)
        await _safe_reply(event, f"🚫 Blocked `{uid}`. Total: `{len(bl)}`")
    except Exception as e:
        await send_log(f"❌ dm block: `{e}`")


@CipherElite.on(events.NewMessage(pattern=r"\.kce\s+dm\s+unblock(?:\s+(\S+))?$"))
@rishabh()
async def cmd_dm_unblock(event):
    if not await _is_owner(event):
        return
    try:
        target = event.pattern_match.group(1)
        if not target:
            if not event.is_reply:
                return await _safe_reply(
                    event,
                    "❌ Reply to a card, or use `.kce dm unblock <id|@user>`"
                )
            replied = await event.get_reply_message()
            text = replied.raw_text or ""
            m = re.search(r'🆔\s*`(\d+)`', text) or re.search(r'`(\d{6,})`', text)
            if not m:
                return await _safe_reply(event, "❌ Could not find ID in card.")
            uid = int(m.group(1))
        else:
            uid = await _resolve_user_id(target)
            if uid is None:
                return await _safe_reply(event, f"❌ Could not resolve `{target}`")
        bl = DB.get("dm_blacklist", [])
        if uid not in bl:
            return await _safe_reply(event, f"ℹ️ `{uid}` not blocked.")
        bl.remove(uid)
        DB["dm_blacklist"] = bl
        save_db(DB)
        await _safe_reply(event, f"✅ Unblocked `{uid}`. Total: `{len(bl)}`")
    except Exception as e:
        await send_log(f"❌ dm unblock: `{e}`")


@CipherElite.on(events.NewMessage(pattern=r"\.kce\s+dm\s+list$"))
@rishabh()
async def cmd_dm_list(event):
    if not await _is_owner(event):
        return
    try:
        bl = DB.get("dm_blacklist", [])
        if not bl:
            return await _safe_reply(event, "📭 No blocked DMs.")
        lines = [f"🚫 **Blocked ({len(bl)})**\n"]
        for uid in bl:
            try:
                e = await CipherElite.get_entity(uid)
                name = format_user(e)
            except Exception:
                name = "Unknown"
            lines.append(f"• **{name}** (`{uid}`)")
        await _safe_reply(event, "\n".join(lines))
    except Exception as e:
        await send_log(f"❌ dm list: `{e}`")


# ═══════════════════════════════════════════════════════════════
#  WALLET CONFIG
# ═══════════════════════════════════════════════════════════════

@CipherElite.on(events.NewMessage(pattern=r"\.kce\s+wallet\s+set\s+(sol|evm|sui)\s+(\S+)$"))
@rishabh()
async def cmd_wallet_set(event):
    if not await _is_owner(event):
        return
    try:
        chain = event.pattern_match.group(1).lower()
        addr = event.pattern_match.group(2).strip()
        ok, reason = validate_wallet(chain, addr)
        if not ok:
            return await _safe_reply(event, f"❌ Invalid {chain.upper()}: {reason}")
        try: await event.delete()
        except: pass
        WALLETS[chain] = addr
        save_wallets(WALLETS)
        await _safe_reply(event, f"✅ {chain.upper()} wallet saved:\n`{addr}`")
    except Exception as e:
        await send_log(f"❌ wallet set: `{e}`")


@CipherElite.on(events.NewMessage(pattern=r"\.kce\s+wallet\s+list$"))
@rishabh()
async def cmd_wallet_list(event):
    if not await _is_owner(event):
        return
    try:
        lines = ["💰 **Wallet Config**\n━━━━━━━━━━━━━━━━━━━━"]
        for chain in ("sol", "evm", "sui"):
            addr = WALLETS.get(chain, "")
            if addr:
                lines.append(f"✅ **{chain.upper()}**: `{addr}`")
            else:
                lines.append(f"❌ **{chain.upper()}**: not set")
        await _safe_reply(event, "\n".join(lines))
    except Exception as e:
        await send_log(f"❌ wallet list: `{e}`")


# ═══════════════════════════════════════════════════════════════
#  MODS
# ═══════════════════════════════════════════════════════════════

@CipherElite.on(events.NewMessage(pattern=r"\.kce\s+mods\s+(add|remove)\s+(\S+)(?:\s+(\S+))?$"))
@rishabh()
async def cmd_mods_add_remove(event):
    if not await _is_owner(event):
        return
    try:
        action = event.pattern_match.group(1).lower()
        user_str = event.pattern_match.group(2)
        link = event.pattern_match.group(3)
        uid = await _resolve_user_id(user_str)
        if uid is None:
            return await _safe_reply(event, f"❌ Could not resolve `{user_str}`")
        if link:
            cid = await resolve_link_to_chat_id(link)
            if cid is None:
                return await _safe_reply(event, f"❌ Could not resolve `{link}`")
        else:
            cid = event.chat_id if event.is_group else None
            if cid is None:
                return await _safe_reply(event, "❌ Specify group link or run in group.")
        tm = DB.get("trusted_mods", {})
        lst = tm.get(str(cid), [])
        if action == "add":
            if uid in lst:
                return await _safe_reply(event, f"ℹ️ `{uid}` already trusted in `{cid}`")
            lst.append(uid)
            tm[str(cid)] = lst
            DB["trusted_mods"] = tm
            save_db(DB)
            await _safe_reply(event, f"✅ Added mod `{uid}` in `{cid}`")
        else:
            if uid not in lst:
                return await _safe_reply(event, f"ℹ️ `{uid}` not in mods for `{cid}`")
            lst.remove(uid)
            tm[str(cid)] = lst
            DB["trusted_mods"] = tm
            save_db(DB)
            await _safe_reply(event, f"🗑️ Removed mod `{uid}` from `{cid}`")
    except Exception as e:
        await send_log(f"❌ mods error: `{e}`")


@CipherElite.on(events.NewMessage(pattern=r"\.kce\s+mods\s+list(?:\s+(\S+))?$"))
@rishabh()
async def cmd_mods_list(event):
    if not await _is_owner(event):
        return
    try:
        link = event.pattern_match.group(1)
        if link:
            cid = await resolve_link_to_chat_id(link)
            if cid is None:
                return await _safe_reply(event, f"❌ Could not resolve `{link}`")
        else:
            cid = event.chat_id if event.is_group else None
            if cid is None:
                return await _safe_reply(event, "❌ Specify link or run in group.")
        tm = DB.get("trusted_mods", {})
        lst = tm.get(str(cid), [])
        if not lst:
            return await _safe_reply(event, f"📭 No custom mods in `{cid}`.")
        lines = [f"👑 **Trusted mods in `{cid}`**\n"]
        for uid in lst:
            try:
                e = await CipherElite.get_entity(uid)
                name = format_user(e)
            except Exception:
                name = "Unknown"
            lines.append(f"• **{name}** (`{uid}`)")
        await _safe_reply(event, "\n".join(lines))
    except Exception as e:
        await send_log(f"❌ mods list: `{e}`")

# ═══ END OF BATCH 4 ═══


# ═══════════════════════════════════════════════════════════════
#  SMART CONTEXT
# ═══════════════════════════════════════════════════════════════

async def _get_smart_context(event, me, limit=5):
    ctx = []
    try:
        if event.is_reply:
            replied = await event.get_reply_message()
            if replied and replied.raw_text:
                name = "KCE" if replied.sender_id == me.id else "them"
                ctx.append(f"[{name}]: {replied.raw_text[:150]}")
        sender_id = event.sender_id
        msgs = await CipherElite.get_messages(event.chat_id, limit=limit + 3)
        same_user_msgs = []
        for m in msgs:
            if m.id == event.message.id:
                continue
            if m.sender_id == sender_id and m.raw_text and not m.raw_text.startswith((".", "..")):
                same_user_msgs.append(f"[them]: {m.raw_text[:150]}")
        same_user_msgs = same_user_msgs[:3]
        ctx.extend(same_user_msgs)
    except Exception as e:
        dbg(f"context error: {e}")
    return ctx[-limit:]


async def _fire_online():
    try:
        await CipherElite(functions.account.UpdateStatusRequest(offline=False))
    except Exception as e:
        dbg(f"online ping error: {e}")


# ═══════════════════════════════════════════════════════════════
#  AI REPLY HANDLER (keyword mode)
# ═══════════════════════════════════════════════════════════════

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
            dbg("block: user gap")
            return
        if not can_reply_in_group(event.chat_id):
            dbg("block: hourly cap")
            chat = await event.get_chat()
            await queue_item(
                f"⚠️ Hourly cap in **{getattr(chat, 'title', '?')}**",
                buttons=make_cap_buttons()
            )
            return
        if not can_reply_daily():
            dbg("block: daily cap")
            await queue_item("🚨 **Daily cap reached**", alert=True, buttons=make_cap_buttons())
            return

        context = await _get_smart_context(event, me, limit=5)
        reply_text = await generate_reply(text, context)
        if not reply_text:
            chat = await event.get_chat()
            await queue_item(
                f"⚠️ **Gemini failed**\nGroup: `{getattr(chat, 'title', '?')}`\nSaid: \"{text[:100]}\"",
                buttons=make_error_buttons()
            )
            return

        delay = get_delay()
        dbg(f"delay {delay}s")
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
            dbg(f"typing failed: {e}")
            await asyncio.sleep(delay)

        try:
            sent = await event.reply(reply_text)
            dbg(f"sent: '{reply_text}'")
        except FloodWaitError as e:
            await asyncio.sleep(e.seconds + 1)
            sent = await event.reply(reply_text)
        except Exception as e:
            print(f"[aireply] send error: {e}")
            await queue_item(f"❌ **Reply failed** in `{event.chat_id}`: `{e}`",
                             alert=True, buttons=make_error_buttons())
            return

        track_reply(event.chat_id, user_id)

        stamp = now_dict()
        chat = await event.get_chat()
        chat_name = getattr(chat, "title", "Unknown")
        user_name = format_user(sender)

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
        await send_log(card, buttons=make_feedback_buttons(reply_num))

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
#  DM WATCHER (suspicious only)
# ═══════════════════════════════════════════════════════════════

@CipherElite.on(events.NewMessage(func=lambda e: e.is_private and not e.out))
async def kce_dm_watcher(event):
    try:
        text = event.raw_text or ""
        if not text or text.startswith((".", "..")):
            return
        sender = await event.get_sender()
        sender_id = event.sender_id

        lower = text.lower()
        is_suspicious = any(k in lower for k in DM_ALERT_KEYWORDS)
        if not is_suspicious:
            return

        if is_dm_blacklisted(sender_id):
            dbg(f"suspicious DM from {sender_id} — blacklisted, skip")
            return

        sender_name = format_user(sender)
        msg = (
            f"🚨 **SUSPICIOUS DM**\n━━━━━━━━━━━━━━━━━━━━\n"
            f"👤 **{sender_name}**\n🆔 `{sender_id}`\n"
            f"🕐 {wat_now().strftime('%I:%M:%S %p')} — {wat_now().strftime('%d/%m/%Y')} WAT\n"
            f"━━━━━━━━━━━━━━━━━━━━\n💬 \"{text[:400]}\""
        )
        await queue_item(msg, alert=True, buttons=make_suspicious_buttons(sender_id))
    except Exception as e:
        print(f"[aireply] DM watcher error: {e}")


# ═══════════════════════════════════════════════════════════════
#  SUSPICIOUS REPLY WATCHER
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
        sender_name = format_user(sender)
        chat = await event.get_chat()
        chat_name = getattr(chat, "title", "Unknown")
        await queue_item(
            f"🚨 **SUSPICIOUS REPLY TO BOT**\n━━━━━━━━━━━━━━━━━━━━\n"
            f"📍 **{chat_name}**\n"
            f"👤 **{sender_name}** (`{event.sender_id}`)\n"
            f"🕐 {wat_now().strftime('%I:%M:%S %p')} WAT\n"
            f"━━━━━━━━━━━━━━━━━━━━\n💬 \"{text[:400]}\"",
            alert=True, buttons=make_suspicious_buttons(event.sender_id)
        )
    except Exception as e:
        print(f"[aireply] suspicious watcher error: {e}")


# ═══════════════════════════════════════════════════════════════
#  WALLET DROP WATCHER
# ═══════════════════════════════════════════════════════════════

@CipherElite.on(events.NewMessage)
async def kce_wallet_watcher(event):
    try:
        if event.out:
            return
        if not is_wallet_group(event.chat_id):
            return
        text = event.raw_text or ""
        if not text or text.startswith((".", "..")):
            return

        me = await CipherElite.get_me()
        sender = await event.get_sender()
        if sender and sender.id == me.id:
            return

        # check for any wallet pattern
        hits = []
        for chain, pat in WALLET_PATTERNS.items():
            matches = pat.findall(text)
            if matches:
                hits.append(chain)

        if not hits:
            return

        # prioritize: evm/sui (longer 0x) over sol if multiple matched
        chain = None
        if "sui" in hits and WALLETS.get("sui"):
            chain = "sui"
        elif "evm" in hits and WALLETS.get("evm"):
            chain = "evm"
        elif "sol" in hits and WALLETS.get("sol"):
            chain = "sol"

        if not chain:
            dbg(f"wallet detected but no config for {hits}")
            return

        addr = WALLETS.get(chain)
        dbg(f"wallet drop: chain={chain} reply={addr[:8]}...")

        # beast mode — no delay
        try:
            await _fire_online()
            async with CipherElite.action(event.chat_id, "typing"):
                await asyncio.sleep(0.5)
            sent = await event.reply(addr)
        except Exception as e:
            print(f"[aireply] wallet send error: {e}")
            return

        stamp = now_dict()
        chat = await event.get_chat()
        chat_name = getattr(chat, "title", "Unknown")
        user_name = format_user(sender)
        jump_link = build_jump_link(event.chat_id, event.message.id)

        replies = DB.get("replies", [])
        reply_num = len(replies) + 1
        record = {
            "n": reply_num,
            "group_name": chat_name,
            "group_id": event.chat_id,
            "user_name": user_name,
            "user_id": event.sender_id,
            "they_said": text[:200],
            "bot_reply": addr,
            "time12": stamp["time12"],
            "date": stamp["date"],
            "ts": stamp["ts"],
            "trigger": "wallet",
            "speed": "beast",
            "jump_link": jump_link,
            "feedback": None,
        }
        replies.append(record)
        DB["replies"] = replies[-500:]
        save_db(DB)

        card = (
            "╔══════════════════════════════════════╗\n"
            "║  💰⚡💥🔥  KCE WALLET DROP  🔥💥⚡💰\n"
            "║  ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            f"║  📍 {chat_name[:30]}\n"
            f"║  👤 {user_name[:40]}\n"
            f"║  🕐 {stamp['time12']} — {stamp['date']} WAT\n"
            "╚══════════════════════════════════════╝\n"
            f"\n💬 THEY DROPPED\n\"{text[:150]}\"\n"
            f"\n💰 KCE REPLIED ({chain.upper()})\n\"{addr}\"\n"
            f"\n⚡ BEAST MODE\n🔗 #{reply_num}\n"
        )
        if jump_link:
            card += f"🔗 Jump: {jump_link}\n"
        card += "━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
        await send_log(card)
    except Exception as e:
        print(f"[aireply] wallet watcher error: {e}")

# ═══ END OF BATCH 5 ═══

# ═══════════════════════════════════════════════════════════════
#  QUIZ HANDLER — learn from mods, answer from 3rd question
# ═══════════════════════════════════════════════════════════════

async def _is_admin_or_trusted(chat_id, user_id):
    """Check if user is Telegram admin or in trusted mods list."""
    if user_id in get_trusted_mods(chat_id):
        return True
    try:
        perms = await CipherElite.get_permissions(chat_id, user_id)
        return bool(getattr(perms, "is_admin", False) or getattr(perms, "is_creator", False))
    except Exception:
        return False


def _get_quiz_state(chat_id):
    qs = DB.get("quiz_state", {})
    return qs.get(str(chat_id), {
        "seen_questions": [],
        "learned_answers": [],
        "learned_style": "",
        "counter": 0,
        "last_question_msg_id": None,
        "last_question_text": None,
        "pending_answers": {},   # {user_id: (msg_id, answer_text)}
    })


def _save_quiz_state(chat_id, state):
    qs = DB.get("quiz_state", {})
    qs[str(chat_id)] = state
    DB["quiz_state"] = qs
    save_db(DB)


@CipherElite.on(events.NewMessage)
async def kce_quiz_handler(event):
    """
    Two behaviors:
    1. Learn: when a mod replies to someone's answer with a 'correct' signal,
       remember that answer + style.
    2. Answer: when a new quiz question appears and we've seen >= 2 answers
       learned, answer in the learned style. 4 correct : 1 wrong pattern.
    """
    try:
        if event.out:
            return
        if not is_quiz_group(event.chat_id):
            return
        text = event.raw_text or ""
        if not text or text.startswith((".", "..")):
            return

        me = await CipherElite.get_me()
        sender = await event.get_sender()
        if sender and sender.id == me.id:
            return

        state = _get_quiz_state(event.chat_id)
        sender_id = event.sender_id
        lower = text.lower()

        # ── LEARNING: this message is a mod's "correct" reply to an answer
        if event.is_reply:
            is_mod = await _is_admin_or_trusted(event.chat_id, sender_id)
            if is_mod:
                contains_signal = any(sig in lower for sig in QUIZ_CORRECT_SIGNALS)
                if contains_signal:
                    replied = await event.get_reply_message()
                    if replied and replied.raw_text:
                        correct_answer = replied.raw_text.strip()[:100]
                        # add to learned answers (dedupe)
                        learned = state.get("learned_answers", [])
                        if correct_answer not in learned:
                            learned.append(correct_answer)
                            state["learned_answers"] = learned[-20:]
                        # learned style — simplest: infer from recent corrects
                        if len(learned) >= 2:
                            # take the shortest learned answer as style hint
                            shortest = min(learned[-5:], key=len)
                            state["learned_style"] = f"like: '{shortest}'"
                        _save_quiz_state(event.chat_id, state)
                        dbg(f"quiz learned: '{correct_answer}' (total: {len(learned)})")
                        return

        # ── DETECT: is this a question?
        # Question heuristics: ends with ? OR contains "what/which/who/when/where/why/how"
        # OR is from a mod/admin
        is_mod_sender = await _is_admin_or_trusted(event.chat_id, sender_id)
        has_q_mark = "?" in text
        has_q_word = any(
            w in lower for w in
            ("what", "which", "who ", "when", "where", "why", "how ", "name the", "pick")
        )
        is_question = is_mod_sender and (has_q_mark or has_q_word) and len(text) > 10

        if is_question:
            # track as latest question
            state["last_question_msg_id"] = event.message.id
            state["last_question_text"] = text[:300]
            state["pending_answers"] = {}
            _save_quiz_state(event.chat_id, state)
            dbg(f"quiz question detected: '{text[:60]}'")

            # can we answer? need at least 2 learned answers
            learned = state.get("learned_answers", [])
            if len(learned) < 2:
                dbg(f"quiz learn phase — only {len(learned)} learned, skip")
                return

            # counter — 4 correct : 1 wrong
            counter = state.get("counter", 0)
            counter += 1
            want_wrong = (counter % (QUIZ_CORRECT_RATIO + QUIZ_WRONG_RATIO) == 0)
            state["counter"] = counter
            _save_quiz_state(event.chat_id, state)

            if want_wrong:
                # deliberate wrong — pick random other learned answer or shuffle
                pool = [a for a in learned if a.lower() not in lower]
                if pool:
                    answer_text = random.choice(pool)
                    is_correct = False
                else:
                    answer_text = random.choice(learned)
                    is_correct = False
                dbg(f"quiz — deliberate WRONG: '{answer_text}'")
            else:
                answer_text = await generate_quiz_answer(
                    text, learned, state.get("learned_style", "")
                )
                if not answer_text:
                    answer_text = random.choice(learned)
                is_correct = True
                dbg(f"quiz — CORRECT attempt: '{answer_text}'")

            # beast mode — no delay
            try:
                await _fire_online()
                async with CipherElite.action(event.chat_id, "typing"):
                    await asyncio.sleep(0.6)
                sent = await event.reply(answer_text)
                dbg(f"quiz answered: '{answer_text}'")
            except Exception as e:
                print(f"[aireply] quiz send error: {e}")
                return

            # log card
            stamp = now_dict()
            chat = await event.get_chat()
            chat_name = getattr(chat, "title", "Unknown")
            jump_link = build_jump_link(event.chat_id, event.message.id)

            replies = DB.get("replies", [])
            reply_num = len(replies) + 1
            record = {
                "n": reply_num,
                "group_name": chat_name,
                "group_id": event.chat_id,
                "user_name": "QUIZ",
                "user_id": 0,
                "they_said": text[:200],
                "bot_reply": answer_text,
                "time12": stamp["time12"],
                "date": stamp["date"],
                "ts": stamp["ts"],
                "trigger": "quiz",
                "speed": "beast",
                "jump_link": jump_link,
                "feedback": None,
                "quiz_correct": is_correct,
            }
            replies.append(record)
            DB["replies"] = replies[-500:]
            save_db(DB)

            card = build_quiz_card(
                reply_num, chat_name, text, answer_text, is_correct, jump_link=jump_link
            )
            await send_log(card, buttons=make_feedback_buttons(reply_num))
            return

        # ── Track peer answers (for potential future learning)
        # if the last msg was a question and this is a reply to it, track pending answer
        last_q_id = state.get("last_question_msg_id")
        if last_q_id and event.is_reply:
            replied = await event.get_reply_message()
            if replied and replied.id == last_q_id:
                pending = state.get("pending_answers", {})
                pending[str(sender_id)] = (event.message.id, text[:100])
                state["pending_answers"] = pending
                _save_quiz_state(event.chat_id, state)

    except Exception as e:
        print(f"[aireply] quiz handler error: {e}")


# ═══════════════════════════════════════════════════════════════
#  HEARTBEAT + BOOTSTRAP
# ═══════════════════════════════════════════════════════════════

HEARTBEAT_TASK = None


async def _heartbeat_loop():
    await asyncio.sleep(5)
    while True:
        try:
            me = await CipherElite.get_me()
            dbg(f"heartbeat — @{getattr(me, 'username', '?')}")
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
            return await _safe_reply(event, "✅ Heartbeat running.")
        HEARTBEAT_TASK = asyncio.create_task(_heartbeat_loop())
        await _safe_reply(event, "🚀 Heartbeat started.")
    except Exception as e:
        await send_log(f"❌ online error: `{e}`")


async def _plugin_bootstrap():
    try:
        await asyncio.sleep(8)
        global HEARTBEAT_TASK
        if not HEARTBEAT_TASK or HEARTBEAT_TASK.done():
            HEARTBEAT_TASK = asyncio.create_task(_heartbeat_loop())
        try:
            await _queue_bot_start()
        except Exception as e:
            print(f"[aireply] bootstrap bot: {e}")
        try:
            asyncio.create_task(_queue_bot_supervisor())
        except Exception as e:
            print(f"[aireply] bootstrap supervisor: {e}")
    except Exception as e:
        print(f"[aireply] bootstrap: {e}")


try:
    asyncio.create_task(_plugin_bootstrap())
except Exception as e:
    print(f"[aireply] bootstrap init: {e}")


# ╔══════════════════════════════════════════════════════════════╗
# ║  === END OF AIRREPLY v3.0 — STAGE 2 COMPLETE ===             ║
# ║                                                              ║
# ║  Features:                                                   ║
# ║  • Nigeria WAT timezone everywhere                           ║
# ║  • Username display in log cards                             ║
# ║  • Keyword AI replies (whitelisted groups)                   ║
# ║  • Quiz mode — learns from mods, answers from 3rd, 4:1       ║
# ║  • Wallet drop detection + instant reply (beast mode)        ║
# ║  • Wallet config from DM (.kce wallet set)                   ║
# ║  • Mods config from DM (.kce mods add)                       ║
# ║  • Group flags: quiz / wallet / reply (from DM with link)    ║
# ║  • DM blacklist + suspicious DM alerts                       ║
# ║  • Queue bot sends log cards (feedback buttons work!)        ║
# ║  • Feedback buttons: 👍 Good  👎 Bad  ✏️ Correct             ║
# ║  • Queue cards with Allow/Block/Ack/Clear buttons            ║
# ║  • Auto-online + typing indicator                            ║
# ║  • Anti-repeat, anti-AI prompt, smart context                ║
# ╚══════════════════════════════════════════════════════════════╝
