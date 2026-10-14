# =============================================================================
#  CipherElite Userbot Plugin - aireply.py v3.5
#  CONTEST MODE — calm/kind + individual LB + full learning signals
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
import os
import random
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from google import genai
from google.genai import types

print("[aireply] IMPORTING v3.5")

VERSION = "3.5.0"
CATEGORY = "utilities"
DEBUG = True

WAT = timezone(timedelta(hours=1))

def wat_now():
    return datetime.now(WAT)


def dbg(msg):
    if DEBUG:
        print(f"[aireply] {msg}")


# ═══════════════════════════════════════════════════════════════
#  CONFIG
# ═══════════════════════════════════════════════════════════════

AI_LOG_CHAT_ID = -1004374819145
QUEUE_CHAT_ID  = -1003860044937

KEYWORDS = ['gm', 'hi', 'hello', 'hey', 'wagmi', 'moon', 'airdrop', 'lfg']

WORD_LIMIT_MIN = 3
WORD_LIMIT_MAX = 5

BEAT_MARGIN = 1.2
MIN_PACE_SEC = 20
MAX_PACE_SEC = 300
IDLE_PACE_SEC = 600

CONTEXT_WINDOW_SEC = 86400
CONTEXT_MAX_MESSAGES = 500

ROOM_DETECT_WINDOW = 60

SPEED_MODES = {
    "fast": (2, 5),
    "normal": (5, 12),
    "slow": (12, 30),
}
CURRENT_SPEED = "normal"

REACT_TO_GM = True
REACT_PROBABILITY = 0.4
REACTION_EMOJIS = ["❤️", "🤝", "💛", "🫡", "😊", "🔥"]
GOOD_REACTION_EMOJIS = {"❤️", "🤝", "💛", "🫡", "😊", "🔥"}

GEMINI_MODEL = "gemini-3.5-flash-lite"

RECENT_REPLIES = []
MAX_RECENT = 20

DM_ALERT_KEYWORDS = [
    'bot', 'ai', 'robot', 'real', 'human', 'who is', 'who are',
    'automated', 'script', 'kce', 'cipher', 'reply bot'
]

WALLET_PATTERNS = {
    'sol': re.compile(r'\b[1-9A-HJ-NP-Za-km-z]{32,44}\b'),
    'evm': re.compile(r'\b0x[a-fA-F0-9]{40}\b'),
    'sui': re.compile(r'\b0x[a-fA-F0-9]{64}\b'),
}

LEARN_BATCH_SECONDS = 60
SLOW_MODE_THRESHOLD = 5
SLOW_MODE_EXTRA_DELAY = 10
SLOW_MODE_RESET = 3

SYSTEM_PROMPT = """You are KCE — a warm, kind, calm Nigerian guy in a crypto Telegram group. You're the friendliest person in the room.

Your vibe:
- Calm, never loud
- Kind, never rude
- Warm, never cold
- Positive, never negative

Rules:
- Reply in 3-5 words maximum.
- Match the group's language: pidgin if they pidgin, English if they English.
- Lowercase only unless it's a name.
- 0-1 emoji max (only: ❤️ 🤝 💛 🫡 😊 🔥)
- NEVER insult, mock, or argue.
- NEVER take sides in drama.
- If happy → celebrate. If sad → comfort. If angry → calm.
- NEVER say "gm bro", "we move", "we outside", "nice one", "let's go", "no cap".
- Sound like a real warm friend.

Good examples:
- "gm" → "morning my friend"
- "wagmi" → "always and forever"
- "sol going up?" → "we hope so 🤝"
- "i made money" → "congrats my g 🔥"

Reply with just the text. Nothing else."""


# ═══════════════════════════════════════════════════════════════
#  STORAGE
# ═══════════════════════════════════════════════════════════════

PROJECT_ROOT = Path(__file__).parent.parent
DB_DIR = PROJECT_ROOT / "DB"
DB_DIR.mkdir(exist_ok=True)
DB_FILE = DB_DIR / "aireply.json"
WALLET_FILE = DB_DIR / "aireply_wallets.json"


def load_db():
    try:
        if DB_FILE.exists():
            return json.loads(DB_FILE.read_text(encoding="utf-8"))
    except Exception as e:
        print(f"[aireply] load err: {e}")
    return {
        "whitelist": [],
        "replies": [],
        "replied_users": {},
        "hourly": {},
        "daily": {"date": "", "count": 0},
        "dm_blacklist": [],
        "dm_whitelist": [],
        "wallet_groups": [],
        "group_memory": {},
        "persona_phrases": [],
        "banned_phrases": [],
        "aggressive": False,
        "slow_mode_until": 0,
        "admin_last_seen": {},
        "leaderboard": {},
        "group_messages": {},
        "bot_pace": {},
        "started": wat_now().strftime("%Y-%m-%d %H:%M:%S"),
    }


def save_db(data):
    try:
        DB_FILE.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
    except Exception as e:
        print(f"[aireply] save err: {e}")


DB = load_db()


def load_wallets():
    try:
        if WALLET_FILE.exists():
            return json.loads(WALLET_FILE.read_text(encoding="utf-8"))
    except Exception as e:
        print(f"[aireply] wallet load err: {e}")
    return {"sol": "", "evm": "", "sui": ""}


def save_wallets(data):
    try:
        WALLET_FILE.write_text(json.dumps(data, indent=2), encoding="utf-8")
    except Exception as e:
        print(f"[aireply] wallet save err: {e}")


WALLETS = load_wallets()


print("[aireply] MODULE LOADED — chunk 1")

# ═══ END OF CHUNK 1 ═══
# ═══════════════════════════════════════════════════════════════
#  HELPERS
# ═══════════════════════════════════════════════════════════════

def validate_wallet(chain, addr):
    addr = (addr or "").strip()
    if not addr:
        return False, "empty"
    if chain == "sol":
        if not re.fullmatch(r'[1-9A-HJ-NP-Za-km-z]{32,44}', addr):
            return False, "SOL must be 32-44 base58"
    elif chain == "evm":
        if not re.fullmatch(r'0x[a-fA-F0-9]{40}', addr):
            return False, "EVM must be 0x + 40 hex"
    elif chain == "sui":
        if not re.fullmatch(r'0x[a-fA-F0-9]{64}', addr):
            return False, "SUI must be 0x + 64 hex"
    else:
        return False, f"unknown chain: {chain}"
    return True, "ok"


def today_str():
    return wat_now().strftime("%Y-%m-%d")


def now_dict():
    n = wat_now()
    return {
        "date": n.strftime("%Y-%m-%d"),
        "time12": n.strftime("%I:%M:%S %p"),
        "ts": n.timestamp(),
    }


def is_whitelisted(chat_id):
    return chat_id in DB.get("whitelist", [])


def is_wallet_group(chat_id):
    return chat_id in DB.get("wallet_groups", [])


def is_dm_blacklisted(user_id):
    return user_id in DB.get("dm_blacklist", [])


def is_aggressive():
    return bool(DB.get("aggressive", False))


KEYWORD_PATTERNS = [re.compile(rf"\b{re.escape(k)}\b", re.IGNORECASE) for k in KEYWORDS]


def has_trigger(text):
    if not text:
        return False
    for pat in KEYWORD_PATTERNS:
        if pat.search(text):
            return True
    return False


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


def get_persona_block():
    pp = DB.get("persona_phrases", [])
    if not pp:
        return ""
    return f"Phrases you actually use: {', '.join(pp[-15:])}"


def get_banned_block():
    bp = DB.get("banned_phrases", [])
    if not bp:
        return ""
    return "NEVER say these (user deleted them before):\n- " + "\n- ".join(bp[-20:])


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


async def resolve_link_to_chat_id(link):
    try:
        link = link.strip()
        if link.lstrip("-").isdigit():
            return int(link)
        m = re.search(r't\.me/c/(\d+)', link)
        if m:
            return int(f"-100{m.group(1)}")
        if link.startswith("https://t.me/"):
            link = link.replace("https://t.me/", "")
        elif link.startswith("t.me/"):
            link = link.replace("t.me/", "")
        if link.startswith("+"):
            try:
                inv = await CipherElite(functions.messages.CheckChatInviteRequest(link))
                chat = getattr(inv, "chat", None)
                if chat:
                    return chat.id
                return None
            except Exception as e:
                dbg(f"invite resolve err: {e}")
                return None
        try:
            entity = await CipherElite.get_entity(link)
            return entity.id
        except Exception as e:
            dbg(f"entity resolve err: {e}")
            return None
    except Exception as e:
        dbg(f"link resolve err: {e}")
        return None


def get_delay():
    if is_aggressive():
        lo, hi = (1, 3)
    else:
        lo, hi = SPEED_MODES.get(CURRENT_SPEED, SPEED_MODES["normal"])
    return random.randint(lo, hi)


def get_slow_mode_extra():
    until = DB.get("slow_mode_until", 0)
    if until and time.time() < until:
        return SLOW_MODE_EXTRA_DELAY
    return 0


def _looks_like_friendly_question(text):
    if not text:
        return False
    t = text.strip()
    if len(t) < 4 or len(t) > 200:
        return False
    lower = t.lower()
    has_q = "?" in t
    q_words = ("who", "what", "when", "where", "why", "how", "which",
               "anyone", "someone", "is there", "are there", "does anyone")
    starts_q = any(lower.startswith(w) for w in q_words)
    if not (has_q or starts_q):
        return False
    skip = ("price", "presale", "contract", "address", "wallet", "dm me",
            "check dm", "click", "join", "invest", "guaranteed")
    if any(s in lower for s in skip):
        return False
    if len(t.split()) > 15:
        return False
    return True


print("[aireply] MODULE LOADED — chunk 2")

# ═══ END OF CHUNK 2 ═══
# ═══════════════════════════════════════════════════════════════
#  INDIVIDUAL LEADERBOARD
# ═══════════════════════════════════════════════════════════════

def _get_lb(chat_id):
    lb = DB.get("leaderboard", {})
    key = str(chat_id)
    if key not in lb:
        lb[key] = {"window_start": time.time(), "counts": {}}
        DB["leaderboard"] = lb
        save_db(DB)
    return lb[key]


def record_individual(chat_id, user_id, user_name):
    lb = _get_lb(chat_id)
    if time.time() - lb.get("window_start", 0) > CONTEXT_WINDOW_SEC:
        lb["window_start"] = time.time()
        lb["counts"] = {}
    key = str(user_id)
    counts = lb["counts"]
    if key not in counts:
        counts[key] = {"name": user_name, "count": 0, "last_msg": 0}
    counts[key]["count"] += 1
    counts[key]["last_msg"] = time.time()
    counts[key]["name"] = user_name
    DB["leaderboard"][str(chat_id)] = lb
    if counts[key]["count"] % 10 == 0:
        save_db(DB)


def get_top_human(chat_id, me_id):
    lb = _get_lb(chat_id)
    counts = lb.get("counts", {})
    best_uid, best = None, None
    for uid, info in counts.items():
        if int(uid) == me_id:
            continue
        if best is None or info["count"] > best["count"]:
            best_uid = uid
            best = info
    if best is None:
        return None, None, 0
    return int(best_uid), best.get("name", "?"), best["count"]


def get_bot_count(chat_id, me_id):
    lb = _get_lb(chat_id)
    info = lb.get("counts", {}).get(str(me_id))
    return info["count"] if info else 0


# ═══════════════════════════════════════════════════════════════
#  GROUP MESSAGES CACHE
# ═══════════════════════════════════════════════════════════════

def record_group_message(chat_id, user_name, text, reply_to_name=None, reply_to_text=None):
    gm = DB.get("group_messages", {})
    key = str(chat_id)
    msgs = gm.get(key, [])
    msgs.append({
        "name": user_name,
        "text": text[:300],
        "reply_to_name": reply_to_name,
        "reply_to_text": (reply_to_text or "")[:200],
        "ts": time.time(),
    })
    cutoff = time.time() - CONTEXT_WINDOW_SEC
    msgs = [m for m in msgs if m["ts"] > cutoff]
    if len(msgs) > CONTEXT_MAX_MESSAGES:
        msgs = msgs[-CONTEXT_MAX_MESSAGES:]
    gm[key] = msgs
    DB["group_messages"] = gm
    if len(msgs) % 10 == 0:
        save_db(DB)


def get_context(chat_id, limit=400):
    gm = DB.get("group_messages", {}).get(str(chat_id), [])
    msgs = gm[-limit:]
    if not msgs:
        return ""
    lines = []
    for m in msgs:
        name = m.get("name", "?")
        text = m.get("text", "")
        rt_name = m.get("reply_to_name")
        if rt_name:
            lines.append(f"[{name} → {rt_name}]: {text}")
        else:
            lines.append(f"[{name}]: {text}")
    return "\n".join(lines)


# ═══════════════════════════════════════════════════════════════
#  PACE ENGINE
# ═══════════════════════════════════════════════════════════════

def compute_pace(chat_id, me_id):
    _, top_name, top_count = get_top_human(chat_id, me_id)
    bot_count = get_bot_count(chat_id, me_id)

    if top_count == 0:
        return IDLE_PACE_SEC, "idle (no competition)"

    target = int(top_count * BEAT_MARGIN)
    gap = target - bot_count
    if gap <= 0:
        return MAX_PACE_SEC, f"ahead (bot={bot_count}, top={top_count})"

    remaining_sec = max(
        60,
        CONTEXT_WINDOW_SEC - (time.time() - _get_lb(chat_id).get("window_start", time.time()))
    )
    pace = max(MIN_PACE_SEC, remaining_sec // max(gap, 1))
    pace = min(pace, MAX_PACE_SEC)
    return pace, f"competing (bot={bot_count}, top={top_name}={top_count}, target={target})"


def should_fire_now(chat_id):
    bp = DB.get("bot_pace", {}).get(str(chat_id), {})
    last = bp.get("last_fire_ts", 0)
    pace, _ = compute_pace(chat_id, bp.get("me_id", 0))
    return (time.time() - last) >= pace


def mark_fired(chat_id, me_id):
    bp = DB.get("bot_pace", {})
    key = str(chat_id)
    bp[key] = {
        "last_fire_ts": time.time(),
        "me_id": me_id,
    }
    DB["bot_pace"] = bp
    save_db(DB)


print("[aireply] MODULE LOADED — chunk 3")

# ═══ END OF CHUNK 3 ═══
# ═══════════════════════════════════════════════════════════════
#  ROOM READING
# ═══════════════════════════════════════════════════════════════

def read_room(chat_id):
    gm = DB.get("group_messages", {}).get(str(chat_id), [])
    cutoff = time.time() - ROOM_DETECT_WINDOW
    recent = [m for m in gm if m["ts"] > cutoff]

    if len(recent) < 2:
        return "dead"

    rate_per_min = len(recent) / (ROOM_DETECT_WINDOW / 60)
    text_all = " ".join(m.get("text", "").lower() for m in recent)

    sad_words = ["sad", "lost", "dip", "down", "rug", "scam", "dump", "wen"]
    happy_words = ["pump", "win", "moon", "gm", "bullish", "ath", "congrats", "let's go", "wagmi"]
    drama_words = ["idiot", "fool", "stupid", "shut up", "dumb", "fake", "scam", "you liar"]

    has_drama = sum(text_all.count(w) for w in drama_words) >= 2
    has_happy = sum(text_all.count(w) for w in happy_words) >= 2
    has_sad = sum(text_all.count(w) for w in sad_words) >= 2

    if has_drama:
        return "drama"
    if rate_per_min >= 8:
        return "hyped"
    if has_happy:
        return "celebratory"
    if has_sad:
        return "serious"
    avg_len = sum(len(m.get("text", "")) for m in recent) / len(recent)
    if avg_len > 80:
        return "serious"
    if rate_per_min < 0.5:
        return "dead"
    return "normal"


def room_hint(mode):
    return {
        "hyped": "Room is HYPED. Short, warm, energetic. Maybe 1 emoji.",
        "serious": "Room is serious. Clean English. No slang. Warm but respectful.",
        "drama": "Room has DRAMA. Stay calm, don't take sides, don't engage conflict. Just be warm and neutral.",
        "dead": "Room is quiet. Reply gently, maybe ask a small question to revive.",
        "celebratory": "Room is celebrating. Join them, congratulate, hype warmly.",
        "normal": "Room is normal. Warm, casual, natural.",
    }.get(mode, "Room is normal.")


# ═══════════════════════════════════════════════════════════════
#  LOG CARDS
# ═══════════════════════════════════════════════════════════════

def build_reply_card(n, group_name, user_name, their_msg, bot_reply,
                     speed="normal", jump_link=None, mode=None, followup=None):
    mode_tag = f"  •  🎭 {mode}" if mode else ""
    header = (
        "╔══════════════════════════════════════╗\n"
        "║  🎯⚡💥🔥  KCE AI REPLY  🎯⚡💥🔥\n"
        "║  ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        f"║  📍 {group_name[:30]}\n"
        f"║  👤 {user_name[:40]}\n"
        f"║  🕐 {wat_now().strftime('%I:%M:%S %p')} — {wat_now().strftime('%d/%m/%Y')} WAT\n"
        f"║  ⚡ {speed}{mode_tag}\n"
        "╚══════════════════════════════════════╝"
    )
    body = (
        f'\n📩 THEY SAID\n"{their_msg[:150]}"\n'
        f'\n🤖 KCE REPLIED\n"{bot_reply}"\n'
    )
    if followup:
        body += f'\n💬 FOLLOW-UP\n"{followup}"\n'
    body += (
        f"\n✅ SENT  •  ⚡ {speed}\n"
        f"🔗 Auto-generated reply  •  #{n}\n"
    )
    if jump_link:
        body += f"🔗 Jump: {jump_link}\n"
    body += "━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
    body += "💡 Reply `good` / `bad`  •  React ❤️ = good  •  Edit = learn  •  Delete = bad"
    return header + body


def build_forward_card(group_name, user_name, their_msg, reason, jump_link=None):
    header = (
        "╔══════════════════════════════════════╗\n"
        "║  📩🚨  KCE NEEDS YOU  🚨📩\n"
        "║  ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        f"║  📍 {group_name[:30]}\n"
        f"║  👤 {user_name[:40]}\n"
        f"║  🕐 {wat_now().strftime('%I:%M:%S %p')} — {wat_now().strftime('%d/%m/%Y')} WAT\n"
        "╚══════════════════════════════════════╝"
    )
    body = (
        f'\n💬 THEY SAID\n"{their_msg[:200]}"\n'
        f'\n🤔 WHY KCE COULDN\'T REPLY\n"{reason[:150]}"\n'
    )
    if jump_link:
        body += f"\n🔗 Jump: {jump_link}\n"
    body += "\n━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
    body += "👆 Handle this one manually if needed"
    return header + body


# ═══════════════════════════════════════════════════════════════
#  SENDERS
# ═══════════════════════════════════════════════════════════════

async def send_log(text):
    try:
        return await CipherElite.send_message(AI_LOG_CHAT_ID, text)
    except Exception as e:
        print(f"[aireply] log err: {e}")
        return None


async def queue_item(text, alert=False):
    try:
        prefix = "🚨 " if alert else "📥 "
        await CipherElite.send_message(QUEUE_CHAT_ID, prefix + text)
    except Exception as e:
        print(f"[aireply] queue err: {e}")


async def _safe_reply(event, text):
    try:
        if event.is_private:
            await event.reply(text)
        else:
            await send_log(text)
    except Exception as e:
        print(f"[aireply] safe_reply err: {e}")


async def _is_owner(event):
    try:
        me = await CipherElite.get_me()
        return event.sender_id == me.id
    except Exception:
        return False


print("[aireply] MODULE LOADED — chunk 4")

# ═══ END OF CHUNK 4 ═══
# ═══════════════════════════════════════════════════════════════
#  INIT
# ═══════════════════════════════════════════════════════════════

def init(client_instance):
    print("[aireply] init called")
    commands = [
        ".kce - status",
        ".kce stats - reply stats",
        ".kce memory - memory info",
        ".kce replies [n] - last N replies",
        ".kce reset - clear memory",
        ".kce help - all commands",
        ".kce speed fast|normal|slow",
        ".kce tz - timezone",
        ".kce room - current room read",
        ".kce leaderboard - top 10",
        ".kce persona list - learned phrases",
        ".kce banned - banned phrases",
        ".kce summary - manual daily summary",
        ".kce dm block/unblock/list",
        ".kce wallet set sol|evm|sui <addr>",
        ".kce wallet list",
        ".kce wallet on|off <link|id>",
        ".kcew - whitelist current group",
        ".kcew add <id> - whitelist by ID",
        ".kcew off - remove whitelist",
        ".kcew off <id> - remove by ID",
        ".kcew list - list whitelisted",
    ]
    description = "🤖 KCE AI Reply v3.5 — CONTEST MODE"
    add_handler("aireply", commands, description)
    print("[aireply] commands registered")


# ═══════════════════════════════════════════════════════════════
#  STATUS
# ═══════════════════════════════════════════════════════════════

@CipherElite.on(events.NewMessage(pattern=r"\.kce$"))
@rishabh()
async def cmd_status(event):
    if not await _is_owner(event):
        return
    try:
        wl = DB.get("whitelist", [])
        replies = DB.get("replies", [])
        started = DB.get("started", "?")
        gemini_ok = ai_config.is_enabled() and bool(ai_config.get_api_key())
        bl = DB.get("dm_blacklist", [])
        wg = DB.get("wallet_groups", [])
        pp = len(DB.get("persona_phrases", []))
        bp = len(DB.get("banned_phrases", []))
        msg = (
            "🤖 **KCE AI Reply v3.5** — CONTEST MODE\n"
            "━━━━━━━━━━━━━━━━━━━━\n"
            f"🧠 Gemini: {'✅ Ready' if gemini_ok else '❌ Disabled'}\n"
            f"📝 Whitelisted: `{len(wl)}` groups\n"
            f"💰 Wallet groups: `{len(wg)}`\n"
            f"💬 Replies sent: `{len(replies)}`\n"
            f"🧬 Persona: `{pp}`  🚫 Banned: `{bp}`\n"
            f"⚡ Speed: `{CURRENT_SPEED}`\n"
            f"🕐 TZ: `WAT (UTC+1)`\n"
            f"🚫 DM blocked: `{len(bl)}`\n"
            f"🚀 Started: `{started}`\n"
            "━━━━━━━━━━━━━━━━━━━━\n"
            f"🎭 Personality: `calm / warm / kind`"
        )
        await _safe_reply(event, msg)
    except Exception as e:
        await send_log(f"❌ status err: `{e}`")


# ═══════════════════════════════════════════════════════════════
#  STATS
# ═══════════════════════════════════════════════════════════════

@CipherElite.on(events.NewMessage(pattern=r"\.kce\s+stats$"))
@rishabh()
async def cmd_stats(event):
    if not await _is_owner(event):
        return
    try:
        replies = DB.get("replies", [])
        today = today_str()
        today_count = sum(1 for r in replies if r.get("date") == today)
        good = sum(1 for r in replies if r.get("feedback") == "good")
        bad = sum(1 for r in replies if r.get("feedback") == "bad")
        deleted = sum(1 for r in replies if r.get("feedback") == "deleted")
        edited = sum(1 for r in replies if r.get("user_edited"))
        lines = [
            "📊 **KCE Stats**",
            "━━━━━━━━━━━━━━━━━━━━",
            f"💬 Total replies: `{len(replies)}`",
            f"📅 Today: `{today_count}`",
            f"👍 Good: `{good}`  👎 Bad: `{bad}`",
            f"🗑️ Deleted (learned): `{deleted}`",
            f"✏️ Edited (learned): `{edited}`",
            f"⚡ Speed: `{CURRENT_SPEED}`",
        ]
        await _safe_reply(event, "\n".join(lines))
    except Exception as e:
        await send_log(f"❌ stats err: `{e}`")


# ═══════════════════════════════════════════════════════════════
#  MEMORY
# ═══════════════════════════════════════════════════════════════

@CipherElite.on(events.NewMessage(pattern=r"\.kce\s+memory$"))
@rishabh()
async def cmd_memory(event):
    if not await _is_owner(event):
        return
    try:
        replies = DB.get("replies", [])
        users = DB.get("replied_users", {})
        gm = DB.get("group_memory", {})
        lb = DB.get("leaderboard", {})
        lines = [
            "🧠 **KCE Memory**",
            "━━━━━━━━━━━━━━━━━━━━",
            f"💾 Replies: `{len(replies)}` / 500",
            f"👥 Users: `{len(users)}`",
            f"📁 Groups learned: `{len(gm)}`",
            f"🏆 Groups tracking LB: `{len(lb)}`",
            f"🧬 Persona: `{len(DB.get('persona_phrases', []))}`",
            f"🚫 Banned: `{len(DB.get('banned_phrases', []))}`",
        ]
        await _safe_reply(event, "\n".join(lines))
    except Exception as e:
        await send_log(f"❌ memory err: `{e}`")


# ═══════════════════════════════════════════════════════════════
#  ROOM
# ═══════════════════════════════════════════════════════════════

@CipherElite.on(events.NewMessage(pattern=r"\.kce\s+room$"))
@rishabh()
async def cmd_room(event):
    if not await _is_owner(event):
        return
    try:
        cid = event.chat_id
        mode = read_room(cid)
        me = await CipherElite.get_me()
        pace, reason = compute_pace(cid, me.id)
        _, top_name, top_count = get_top_human(cid, me.id)
        bot_count = get_bot_count(cid, me.id)
        lines = [
            "🏠 **Room read**",
            "━━━━━━━━━━━━━━━━━━━━",
            f"🎭 Room mode: `{mode}`",
            f"⚡ Pace: `1 per {pace}s`",
            f"📊 Bot count: `{bot_count}`",
            f"🏆 Top human: `{top_name}` = `{top_count}`",
            f"💡 Reason: {reason}",
        ]
        await _safe_reply(event, "\n".join(lines))
    except Exception as e:
        await send_log(f"❌ room err: `{e}`")


# ═══════════════════════════════════════════════════════════════
#  LEADERBOARD
# ═══════════════════════════════════════════════════════════════

@CipherElite.on(events.NewMessage(pattern=r"\.kce\s+leaderboard$"))
@rishabh()
async def cmd_leaderboard(event):
    if not await _is_owner(event):
        return
    try:
        cid = event.chat_id
        lb = _get_lb(cid)
        counts = lb.get("counts", {})
        if not counts:
            return await _safe_reply(event, "📭 No leaderboard data yet. Send some messages in this group.")
        sorted_users = sorted(counts.items(), key=lambda kv: -kv[1]["count"])[:10]
        me = await CipherElite.get_me()
        lines = ["🏆 **Leaderboard (24h)**\n━━━━━━━━━━━━━━━━━━━━"]
        for i, (uid, info) in enumerate(sorted_users, 1):
            tag = " 🤖" if int(uid) == me.id else ""
            lines.append(f"{i}. **{info['name'][:25]}**{tag} — `{info['count']}`")
        await _safe_reply(event, "\n".join(lines))
    except Exception as e:
        await send_log(f"❌ lb err: `{e}`")


# ═══════════════════════════════════════════════════════════════
#  PERSONA
# ═══════════════════════════════════════════════════════════════

@CipherElite.on(events.NewMessage(pattern=r"\.kce\s+persona(?:\s+list)?$"))
@rishabh()
async def cmd_persona(event):
    if not await _is_owner(event):
        return
    try:
        pp = DB.get("persona_phrases", [])
        if not pp:
            return await _safe_reply(event, "📭 No persona phrases yet.")
        lines = [f"🧬 **Persona Phrases ({len(pp)})**\n"]
        for p in pp[-30:]:
            lines.append(f"• `{p}`")
        await _safe_reply(event, "\n".join(lines))
    except Exception as e:
        await send_log(f"❌ persona err: `{e}`")


# ═══════════════════════════════════════════════════════════════
#  BANNED
# ═══════════════════════════════════════════════════════════════

@CipherElite.on(events.NewMessage(pattern=r"\.kce\s+banned$"))
@rishabh()
async def cmd_banned(event):
    if not await _is_owner(event):
        return
    try:
        bp = DB.get("banned_phrases", [])
        if not bp:
            return await _safe_reply(event, "📭 No banned phrases yet.")
        lines = [f"🚫 **Banned Phrases ({len(bp)})**\n"]
        for p in bp[-30:]:
            lines.append(f"• `{p}`")
        await _safe_reply(event, "\n".join(lines))
    except Exception as e:
        await send_log(f"❌ banned err: `{e}`")


# ═══════════════════════════════════════════════════════════════
#  SPEED
# ═══════════════════════════════════════════════════════════════

@CipherElite.on(events.NewMessage(pattern=r"\.kce\s+speed\s+(fast|normal|slow)$"))
@rishabh()
async def cmd_speed(event):
    global CURRENT_SPEED
    if not await _is_owner(event):
        return
    try:
        mode = event.pattern_match.group(1).lower()
        CURRENT_SPEED = mode
        lo, hi = SPEED_MODES[mode]
        await _safe_reply(event, f"⚡ Speed: **{mode}** ({lo}-{hi}s)")
    except Exception as e:
        await send_log(f"❌ speed err: `{e}`")


# ═══════════════════════════════════════════════════════════════
#  TZ
# ═══════════════════════════════════════════════════════════════

@CipherElite.on(events.NewMessage(pattern=r"\.kce\s+tz$"))
@rishabh()
async def cmd_tz(event):
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
        await send_log(f"❌ tz err: `{e}`")


print("[aireply] MODULE LOADED — chunk 5")

# ═══ END OF CHUNK 5 ═══
# ═══════════════════════════════════════════════════════════════
#  WHITELIST (.kcew)
# ═══════════════════════════════════════════════════════════════

@CipherElite.on(events.NewMessage(pattern=r"\.kcew$"))
async def cmd_wl_add(event):
    if not await _is_owner(event):
        return
    try:
        try: await event.delete()
        except: pass
        chat = await event.get_chat()
        cid = event.chat_id
        name = getattr(chat, "title", "Unknown")
        wl = DB.get("whitelist", [])
        if cid in wl:
            return await send_log(f"ℹ️ Already whitelisted: **{name}**")
        wl.append(cid)
        DB["whitelist"] = wl
        save_db(DB)
        await send_log(f"✅ Whitelisted **{name}** (`{cid}`). Total: `{len(wl)}`")
    except Exception as e:
        await send_log(f"❌ wl add err: `{e}`")


@CipherElite.on(events.NewMessage(pattern=r"\.kcew\s+add\s+(-?\d+)$"))
@rishabh()
async def cmd_wl_add_id(event):
    if not await _is_owner(event):
        return
    try:
        cid = int(event.pattern_match.group(1))
        name = f"ID {cid}"
        try:
            e = await CipherElite.get_entity(cid)
            name = getattr(e, "title", name)
        except Exception:
            pass
        wl = DB.get("whitelist", [])
        if cid in wl:
            return await _safe_reply(event, f"ℹ️ Already whitelisted: **{name}**")
        wl.append(cid)
        DB["whitelist"] = wl
        save_db(DB)
        await _safe_reply(event, f"✅ Whitelisted **{name}** (`{cid}`). Total: `{len(wl)}`")
    except Exception as e:
        await send_log(f"❌ wl add id err: `{e}`")


@CipherElite.on(events.NewMessage(pattern=r"\.kcew\s+off(?:\s+(-?\d+))?$"))
async def cmd_wl_remove(event):
    if not await _is_owner(event):
        return
    try:
        target = event.pattern_match.group(1)
        if target:
            cid = int(target)
            cname = f"ID {cid}"
        else:
            try: await event.delete()
            except: pass
            chat = await event.get_chat()
            cid = event.chat_id
            cname = getattr(chat, "title", "Unknown")
        wl = DB.get("whitelist", [])
        if cid not in wl:
            return await send_log(f"ℹ️ Not whitelisted: `{cid}`")
        wl.remove(cid)
        DB["whitelist"] = wl
        save_db(DB)
        await send_log(f"🗑️ Removed **{cname}** (`{cid}`)")
    except Exception as e:
        await send_log(f"❌ wl remove err: `{e}`")


@CipherElite.on(events.NewMessage(pattern=r"\.kcew\s+list$"))
@rishabh()
async def cmd_wl_list(event):
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
        await send_log(f"❌ wl list err: `{e}`")


# ═══════════════════════════════════════════════════════════════
#  DM BLACKLIST
# ═══════════════════════════════════════════════════════════════

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
        await send_log(f"❌ dm block err: `{e}`")


@CipherElite.on(events.NewMessage(pattern=r"\.kce\s+dm\s+unblock(?:\s+(\S+))?$"))
@rishabh()
async def cmd_dm_unblock(event):
    if not await _is_owner(event):
        return
    try:
        target = event.pattern_match.group(1)
        if not target:
            if not event.is_reply:
                return await _safe_reply(event, "❌ Reply to a card, or `.kce dm unblock <id|@user>`")
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
        await send_log(f"❌ dm unblock err: `{e}`")


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
        await send_log(f"❌ dm list err: `{e}`")


# ═══════════════════════════════════════════════════════════════
#  WALLET STUB
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
        await send_log(f"❌ wallet set err: `{e}`")


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
        lines.append("\n_(wallet drop detection paused)_")
        await _safe_reply(event, "\n".join(lines))
    except Exception as e:
        await send_log(f"❌ wallet list err: `{e}`")


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
            await _safe_reply(event, f"✅ Wallet ON for `{cid}` _(paused feature)_")
        else:
            if cid not in groups:
                return await _safe_reply(event, f"ℹ️ Wallet already OFF for `{cid}`")
            groups.remove(cid)
            DB["wallet_groups"] = groups
            save_db(DB)
            await _safe_reply(event, f"⏹️ Wallet OFF for `{cid}`")
    except Exception as e:
        await send_log(f"❌ wallet flag err: `{e}`")


print("[aireply] MODULE LOADED — chunk 6")

# ═══ END OF CHUNK 6 ═══
# ═══════════════════════════════════════════════════════════════
#  GEMINI
# ═══════════════════════════════════════════════════════════════

_gemini_client = None


def raid_gemini_client():
    global _gemini_client
    if _gemini_client is None:
        api_key = ai_config.get_api_key()
        if not api_key:
            return None
        from google import genai
        _gemini_client = genai.Client(api_key=api_key)
    return _gemini_client


def _build_system_prompt(chat_id):
    mode = read_room(chat_id)
    hint = room_hint(mode)
    persona = get_persona_block()
    banned = get_banned_block()
    base = SYSTEM_PROMPT
    if persona:
        base += (
            f"\n\n---\n"
            f"CRITICAL: These are KCE's OWN real phrases. Match this voice heavily.\n"
            f"{persona}\n"
            f"---"
        )
    if banned:
        base += f"\n\n{banned}"
    base += f"\n\nCurrent room: {mode.upper()}.\n{hint}"
    return base


async def generate_reply(context_block, target_message, chat_id):
    if not ai_config.is_enabled():
        return None
    api_key = ai_config.get_api_key()
    if not api_key:
        return None

    banned = ", ".join(RECENT_REPLIES[-8:]) if RECENT_REPLIES else "(none yet)"

    user_prompt = f"""CONVERSATION CONTEXT (last 24h):
{context_block if context_block else "(no context)"}

RECENT REPLIES YOU ALREADY SENT (do NOT repeat):
{banned}

MESSAGE TO REPLY TO:
\"{target_message[:200]}\"

Reply in 3-5 words. Calm, warm, kind. Match the group's language.
Just the reply text. Nothing else."""

    try:
        client = genai.Client(api_key=api_key)
        config = types.GenerateContentConfig(
            system_instruction=_build_system_prompt(chat_id),
            max_output_tokens=60,
            temperature=1.2,
            top_p=0.95,
        )
        resp = await client.aio.models.generate_content(
            model=GEMINI_MODEL,
            contents=[types.Content(role="user", parts=[types.Part(text=user_prompt)])],
            config=config,
        )
        text = (resp.text or "").strip()
        text = text.replace("\n", " ").strip('"').strip("'")
        text = re.sub(r'^(reply|response|answer):\s*', '', text, flags=re.IGNORECASE)
        words = text.split()
        if len(words) > WORD_LIMIT_MAX:
            text = " ".join(words[:WORD_LIMIT_MAX])
        if len(text) < 2 or len(text) > 80:
            return None
        if text.lower() in [r.lower() for r in RECENT_REPLIES]:
            return None
        RECENT_REPLIES.append(text)
        if len(RECENT_REPLIES) > MAX_RECENT:
            RECENT_REPLIES.pop(0)
        dbg(f"gemini reply: '{text}'")
        return text
    except Exception as e:
        print(f"[aireply] gemini err: {e}")
        return None


async def generate_followup(context_block, target_message, main_reply, chat_id):
    if not ai_config.is_enabled():
        return None
    api_key = ai_config.get_api_key()
    if not api_key:
        return None

    prompt = f"""Your last reply was: \"{main_reply}\"

To this message: \"{target_message[:150]}\"

Now send a SHORT follow-up (2-4 words) that continues the conversation naturally.
Warm, calm, kind. Could be:
- A gentle question ("you dey ok?")
- A warm agreement ("true talk fam")
- A small addition ("we move together")
- A kind check-in ("take am easy")

Just the follow-up text. Nothing else."""

    try:
        client = genai.Client(api_key=api_key)
        config = types.GenerateContentConfig(
            system_instruction=_build_system_prompt(chat_id),
            max_output_tokens=30,
            temperature=1.3,
            top_p=0.95,
        )
        resp = await client.aio.models.generate_content(
            model=GEMINI_MODEL,
            contents=[types.Content(role="user", parts=[types.Part(text=prompt)])],
            config=config,
        )
        text = (resp.text or "").strip().replace("\n", " ").strip('"').strip("'")
        words = text.split()
        if len(words) > 4:
            text = " ".join(words[:4])
        if len(text) < 2 or len(text) > 50:
            return None
        if text.lower() == main_reply.lower():
            return None
        dbg(f"gemini followup: '{text}'")
        return text
    except Exception as e:
        print(f"[aireply] followup err: {e}")
        return None


async def generate_friendly_reply(context_block, question_text, chat_id):
    if not ai_config.is_enabled():
        return None
    api_key = ai_config.get_api_key()
    if not api_key:
        return None

    prompt = f"""CONVERSATION CONTEXT:
{context_block if context_block else "(no context)"}

SOMEONE ASKED A FRIENDLY QUESTION:
\"{question_text[:200]}\"

Reply warmly in 3-5 words. Kind, simple, welcoming.
Just the reply text. Nothing else."""

    try:
        client = genai.Client(api_key=api_key)
        config = types.GenerateContentConfig(
            system_instruction=_build_system_prompt(chat_id),
            max_output_tokens=60,
            temperature=1.1,
            top_p=0.95,
        )
        resp = await client.aio.models.generate_content(
            model=GEMINI_MODEL,
            contents=[types.Content(role="user", parts=[types.Part(text=prompt)])],
            config=config,
        )
        text = (resp.text or "").strip().replace("\n", " ").strip('"').strip("'")
        words = text.split()
        if len(words) > WORD_LIMIT_MAX:
            text = " ".join(words[:WORD_LIMIT_MAX])
        if len(text) < 2 or len(text) > 80:
            return None
        dbg(f"gemini friendly: '{text}'")
        return text
    except Exception as e:
        print(f"[aireply] friendly err: {e}")
        return None


async def _fire_online():
    try:
        await CipherElite(functions.account.UpdateStatusRequest(offline=False))
    except Exception as e:
        dbg(f"online ping err: {e}")


print("[aireply] MODULE LOADED — chunk 7")

# ═══ END OF CHUNK 7 ═══
# ═══════════════════════════════════════════════════════════════
#  MESSAGE RECORDER
# ═══════════════════════════════════════════════════════════════

@CipherElite.on(events.NewMessage)
async def group_message_recorder(event):
    try:
        if not is_whitelisted(event.chat_id):
            return
        text = event.raw_text or ""
        if not text or text.startswith((".", "..")):
            return
        sender = await event.get_sender()
        if not sender:
            return
        user_name = format_user(sender)
        reply_to_name = None
        reply_to_text = None
        if event.is_reply:
            try:
                replied = await event.get_reply_message()
                if replied:
                    rsender = await replied.get_sender()
                    reply_to_name = format_user(rsender) if rsender else "?"
                    reply_to_text = (replied.raw_text or "")[:200]
            except Exception:
                pass
        record_individual(event.chat_id, sender.id, user_name)
        record_group_message(event.chat_id, user_name, text, reply_to_name, reply_to_text)
    except Exception as e:
        print(f"[aireply] recorder err: {e}")


# ═══════════════════════════════════════════════════════════════
#  MAIN REPLY HANDLER
# ═══════════════════════════════════════════════════════════════

@CipherElite.on(events.NewMessage)
async def kce_reply_handler(event):
    try:
        if event.out:
            return
        if not is_whitelisted(event.chat_id):
            return
        text = event.raw_text or ""
        if not text or text.startswith((".", "..")):
            return

        me = await CipherElite.get_me()
        sender = await event.get_sender()
        if sender and sender.id == me.id:
            return

        if not should_fire_now(event.chat_id):
            pace, _ = compute_pace(event.chat_id, me.id)
            dbg(f"pace block: need {pace}s between fires")
            return

        triggered = False
        trigger_type = None

        if event.is_reply:
            replied = await event.get_reply_message()
            if replied and replied.sender_id == me.id:
                triggered, trigger_type = True, "continuation"
        if not triggered and me.username and f"@{me.username.lower()}" in text.lower():
            triggered, trigger_type = True, "mention"
        if not triggered and has_trigger(text):
            triggered, trigger_type = True, "keyword"
        if not triggered and _looks_like_friendly_question(text):
            bp = DB.get("bot_pace", {}).get(str(event.chat_id), {})
            last = bp.get("last_fire_ts", 0)
            if time.time() - last >= 60:
                triggered, trigger_type = True, "friendly_q"

        if not triggered:
            return

        dbg(f"trigger={trigger_type} chat={event.chat_id} text='{text[:50]}'")

        context_block = get_context(event.chat_id, limit=400)

        if trigger_type == "friendly_q":
            reply_text = await generate_friendly_reply(context_block, text, event.chat_id)
        else:
            reply_text = await generate_reply(context_block, text, event.chat_id)

        if not reply_text:
            chat = await event.get_chat()
            chat_name = getattr(chat, "title", "Unknown")
            user_name = format_user(sender)
            jump = build_jump_link(event.chat_id, event.message.id)
            card = build_forward_card(
                chat_name, user_name, text,
                "Gemini couldn't generate a confident reply",
                jump
            )
            await queue_item(card, alert=True)
            return

        mode = read_room(event.chat_id)
        base_delay = get_delay()
        if mode == "hyped":
            base_delay = max(1, base_delay // 2)
        elif mode == "dead":
            base_delay = int(base_delay * 1.5)
        total_delay = base_delay + get_slow_mode_extra()

        try:
            await _fire_online()
            first = max(1, total_delay // 2)
            second = max(1, total_delay - first)
            async with CipherElite.action(event.chat_id, "typing"):
                await asyncio.sleep(first)
            await asyncio.sleep(random.uniform(0.3, 1.0))
            async with CipherElite.action(event.chat_id, "typing"):
                await asyncio.sleep(second)
        except Exception as e:
            await asyncio.sleep(total_delay)

        try:
            sent = await event.reply(reply_text)
            dbg(f"sent: '{reply_text}'")
        except FloodWaitError as e:
            await asyncio.sleep(e.seconds + 1)
            sent = await event.reply(reply_text)
        except Exception as e:
            print(f"[aireply] send err: {e}")
            return

        mark_fired(event.chat_id, me.id)
        record_individual(event.chat_id, me.id, "KCE")

        followup = None
        if random.random() < 0.4:
            followup = await generate_followup(context_block, text, reply_text, event.chat_id)
            if followup:
                await asyncio.sleep(random.uniform(2, 6))
                try:
                    await event.reply(followup)
                    record_individual(event.chat_id, me.id, "KCE")
                except Exception as e:
                    dbg(f"followup send err: {e}")

        if random.random() < 0.3:
            try:
                await sent.react(random.choice(REACTION_EMOJIS))
            except Exception:
                pass

        stamp = now_dict()
        chat = await event.get_chat()
        chat_name = getattr(chat, "title", "Unknown")
        user_name = format_user(sender)
        jump = build_jump_link(event.chat_id, event.message.id)

        replies = DB.get("replies", [])
        reply_num = len(replies) + 1
        speed_label = f"{CURRENT_SPEED} ({total_delay}s)"
        record = {
            "n": reply_num,
            "sent_msg_id": sent.id,
            "group_name": chat_name,
            "group_id": event.chat_id,
            "user_name": user_name,
            "user_id": event.sender_id,
            "they_said": text[:200],
            "bot_reply": reply_text,
            "followup": followup,
            "time12": stamp["time12"],
            "date": stamp["date"],
            "ts": stamp["ts"],
            "trigger": trigger_type,
            "speed": speed_label,
            "mode": mode,
            "jump_link": jump,
            "feedback": None,
        }
        replies.append(record)
        DB["replies"] = replies[-500:]
        save_db(DB)

        card = build_reply_card(
            reply_num, chat_name, user_name, text, reply_text,
            speed=speed_label, jump_link=jump, mode=mode, followup=followup
        )
        await send_log(card)

    except FloodWaitError as e:
        print(f"[aireply] FloodWait {e.seconds}s")
        await asyncio.sleep(e.seconds + 1)
    except Exception as e:
        print(f"[aireply] handler err: {e}")


print("[aireply] MODULE LOADED — chunk 8")

# ═══ END OF CHUNK 8 ═══
# ═══════════════════════════════════════════════════════════════
#  EDIT WATCHER — user edits bot's reply = learn preferred version
# ═══════════════════════════════════════════════════════════════

@CipherElite.on(events.MessageEdited)
async def kce_edit_watcher(event):
    try:
        if not is_whitelisted(event.chat_id):
            return
        text = event.raw_text or ""
        if not text or text.startswith((".", "..")):
            return
        me = await CipherElite.get_me()
        sender = await event.get_sender()
        if not sender or sender.id != me.id:
            return

        msg_id = event.message.id
        replies = DB.get("replies", [])
        target = None
        for r in replies:
            if r.get("sent_msg_id") == msg_id:
                target = r
                break

        old_reply = target.get("bot_reply", "") if target else ""
        new_text = text.strip()[:60]
        if len(new_text) < 2 or len(new_text) > 80:
            return

        pp = DB.get("persona_phrases", [])
        if new_text.lower() not in [p.lower() for p in pp]:
            pp.append(new_text.lower())
            DB["persona_phrases"] = pp[-50:]
            save_db(DB)
            dbg(f"persona learned from edit: '{new_text}'")

        if target:
            target["user_edited"] = new_text
            target["original_bot_reply"] = old_reply
            save_db(DB)

        await send_log(
            f"✏️ **EDIT LEARNED**\n"
            f"━━━━━━━━━━━━━━━━━━━━\n"
            f"Old: \"{old_reply[:60]}\"\n"
            f"New: \"{new_text}\"\n"
            f"→ Saved to persona"
        )
    except Exception as e:
        print(f"[aireply] edit watcher err: {e}")


# ═══════════════════════════════════════════════════════════════
#  DELETE WATCHER — user deletes bot's reply = learn to avoid
# ═══════════════════════════════════════════════════════════════

@CipherElite.on(events.MessageDeleted)
async def kce_delete_watcher(event):
    try:
        for msg_id in event.deleted_ids:
            replies = DB.get("replies", [])
            target = None
            for r in replies:
                if r.get("sent_msg_id") == msg_id:
                    target = r
                    break
            if not target:
                continue

            bad_text = target.get("bot_reply", "").strip()
            target["feedback"] = "deleted"
            target["deleted"] = True
            save_db(DB)
            dbg(f"deleted reply #{target.get('n')} — '{bad_text[:40]}'")

            if bad_text and 2 <= len(bad_text) <= 60:
                bp = DB.get("banned_phrases", [])
                if bad_text.lower() not in [b.lower() for b in bp]:
                    bp.append(bad_text.lower())
                    DB["banned_phrases"] = bp[-50:]
                    save_db(DB)

            try:
                await send_log(
                    f"🗑️ **DELETED — LEARNED**\n"
                    f"━━━━━━━━━━━━━━━━━━━━\n"
                    f"Bot said: \"{bad_text[:60]}\"\n"
                    f"→ Added to banned style"
                )
            except Exception:
                pass
    except Exception as e:
        print(f"[aireply] delete watcher err: {e}")


# ═══════════════════════════════════════════════════════════════
#  REACTION WATCHER — owner reacts ❤️/🤝/etc to bot = learn good
# ═══════════════════════════════════════════════════════════════

@CipherElite.on(events.Raw(events.Raw))
async def kce_reaction_watcher(event):
    try:
        from telethon.tl import types as tl_types
        from telethon.tl.types import ReactionEmoji

        if not isinstance(event, tl_types.UpdateMessageReactions):
            return

        peer = getattr(event, "peer", None)
        msg_id = getattr(event, "msg_id", None)
        reactions = getattr(event, "reactions", None)
        if not msg_id or not reactions:
            return

        try:
            chat_id = None
            if hasattr(peer, "channel_id"):
                chat_id = -1000000000000 - peer.channel_id
            elif hasattr(peer, "chat_id"):
                chat_id = -peer.chat_id
            elif hasattr(peer, "user_id"):
                chat_id = peer.user_id
        except Exception:
            return

        if not chat_id or not is_whitelisted(chat_id):
            return

        results = getattr(reactions, "results", []) or []
        emojis = []
        for r in results:
            reaction = getattr(r, "reaction", None)
            if isinstance(reaction, ReactionEmoji):
                emojis.append(reaction.emoticon)
        if not emojis:
            return

        hit = [e for e in emojis if e in GOOD_REACTION_EMOJIS]
        if not hit:
            return

        me = await CipherElite.get_me()
        replies = DB.get("replies", [])
        target = None
        for r in replies:
            if r.get("sent_msg_id") == msg_id:
                target = r
                break
        if not target:
            return

        recent = getattr(reactions, "recent_reactions", []) or []
        owner_reacted = False
        for rr in recent:
            if getattr(rr, "peer_id", None):
                pid = rr.peer_id
                uid = None
                if hasattr(pid, "user_id"):
                    uid = pid.user_id
                elif hasattr(pid, "channel_id"):
                    uid = pid.channel_id
                if uid and uid == me.id:
                    owner_reacted = True
                    break

        if not owner_reacted:
            return

        target["feedback"] = "good"
        target["reacted_with"] = hit[0]
        save_db(DB)
        dbg(f"reacted {hit[0]} to reply #{target.get('n')}")

        reply_text = target.get("bot_reply", "")
        if reply_text and len(reply_text) <= 30:
            pp = DB.get("persona_phrases", [])
            if reply_text.lower() not in [p.lower() for p in pp]:
                pp.append(reply_text.lower())
                DB["persona_phrases"] = pp[-50:]
                save_db(DB)

        try:
            await send_log(
                f"{hit[0]} **REACTED — LEARNED**\n"
                f"━━━━━━━━━━━━━━━━━━━━\n"
                f"Bot said: \"{reply_text[:60]}\"\n"
                f"→ Added to persona"
            )
        except Exception:
            pass
    except Exception:
        pass


# ═══════════════════════════════════════════════════════════════
#  OWNER FOLLOW-UP WATCHER — owner continues after bot
# ═══════════════════════════════════════════════════════════════

@CipherElite.on(events.NewMessage)
async def kce_owner_followup_watcher(event):
    try:
        if not is_whitelisted(event.chat_id):
            return
        if not event.out:
            return
        text = event.raw_text or ""
        if not text or text.startswith((".", "..")):
            return

        if not event.is_reply:
            return
        replied = await event.get_reply_message()
        if not replied:
            return

        replies = DB.get("replies", [])
        recent = replies[-20:]
        target = None
        for r in recent:
            if r.get("sent_msg_id") == replied.id:
                target = r
                break
        if not target:
            return

        new_text = text.strip()[:60]
        if len(new_text) < 2 or len(new_text) > 80:
            return

        pp = DB.get("persona_phrases", [])
        if new_text.lower() not in [p.lower() for p in pp]:
            pp.append(new_text.lower())
            DB["persona_phrases"] = pp[-50:]
            save_db(DB)
            dbg(f"persona from owner follow-up: '{new_text}'")

        await send_log(
            f"💬 **OWNER FOLLOW-UP LEARNED**\n"
            f"━━━━━━━━━━━━━━━━━━━━\n"
            f"After bot said: \"{target.get('bot_reply', '')[:60]}\"\n"
            f"You said: \"{new_text}\"\n"
            f"→ Saved to persona"
        )
    except Exception as e:
        print(f"[aireply] owner followup err: {e}")


print("[aireply] MODULE LOADED — chunk 9")

# ═══ END OF CHUNK 9 ═══
# ═══════════════════════════════════════════════════════════════
#  FEEDBACK WATCHER — reply `good` / `bad` to log cards
# ═══════════════════════════════════════════════════════════════

@CipherElite.on(events.NewMessage(chats=AI_LOG_CHAT_ID))
async def feedback_watcher(event):
    try:
        me = await CipherElite.get_me()
        if event.sender_id != me.id:
            return
        text = (event.raw_text or "").strip().lower()
        if text not in ("good", "bad"):
            return
        if not event.is_reply:
            return
        replied = await event.get_reply_message()
        if not replied:
            return
        card_text = replied.raw_text or ""
        m = re.search(r'#(\d+)\s*$', card_text, re.MULTILINE) or re.search(r'#(\d+)', card_text)
        if not m:
            return
        n = int(m.group(1))
        replies = DB.get("replies", [])
        target = None
        for r in replies:
            if r.get("n") == n:
                target = r
                r["feedback"] = text
                break
        if not target:
            return
        save_db(DB)
        dbg(f"feedback: #{n} = {text}")

        if text == "good":
            reply_text = target.get("bot_reply", "")
            if reply_text and len(reply_text) <= 30:
                pp = DB.get("persona_phrases", [])
                if reply_text.lower() not in [p.lower() for p in pp]:
                    pp.append(reply_text.lower())
                    DB["persona_phrases"] = pp[-50:]
                    save_db(DB)

        try:
            emoji = "👍" if text == "good" else "👎"
            await event.reply(f"{emoji} Logged #{n} as {text}")
        except Exception:
            pass
    except Exception as e:
        print(f"[aireply] feedback err: {e}")


# ═══════════════════════════════════════════════════════════════
#  DM WATCHER — suspicious only
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
            return
        sender_name = format_user(sender)
        msg = (
            f"🚨 **SUSPICIOUS DM**\n━━━━━━━━━━━━━━━━━━━━\n"
            f"👤 **{sender_name}**\n🆔 `{sender_id}`\n"
            f"🕐 {wat_now().strftime('%I:%M:%S %p')} — {wat_now().strftime('%d/%m/%Y')} WAT\n"
            f"━━━━━━━━━━━━━━━━━━━━\n💬 \"{text[:400]}\""
        )
        await queue_item(msg, alert=True)
    except Exception as e:
        print(f"[aireply] DM watcher err: {e}")


# ═══════════════════════════════════════════════════════════════
#  SUSPICIOUS REPLY WATCHER — replies to bot
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
            alert=True
        )
    except Exception as e:
        print(f"[aireply] suspicious watcher err: {e}")


# ═══════════════════════════════════════════════════════════════
#  MEMORY FLUSHER
# ═══════════════════════════════════════════════════════════════

async def memory_flusher_loop():
    await asyncio.sleep(30)
    while True:
        try:
            gm = DB.get("group_messages", {})
            cutoff = time.time() - CONTEXT_WINDOW_SEC
            changed = False
            for cid in list(gm.keys()):
                msgs = gm[cid]
                pruned = [m for m in msgs if m.get("ts", 0) > cutoff]
                if len(pruned) != len(msgs):
                    gm[cid] = pruned
                    changed = True
            if changed:
                DB["group_messages"] = gm
                save_db(DB)

            lb = DB.get("leaderboard", {})
            for cid in list(lb.keys()):
                if time.time() - lb[cid].get("window_start", 0) > CONTEXT_WINDOW_SEC:
                    lb[cid] = {"window_start": time.time(), "counts": {}}
                    save_db(DB)
        except Exception as e:
            print(f"[aireply] flusher err: {e}")
        await asyncio.sleep(LEARN_BATCH_SECONDS)


# ═══════════════════════════════════════════════════════════════
#  DAILY SUMMARY
# ═══════════════════════════════════════════════════════════════

async def send_daily_summary():
    try:
        today = today_str()
        replies = DB.get("replies", [])
        today_replies = [r for r in replies if r.get("date") == today]
        good = sum(1 for r in today_replies if r.get("feedback") == "good")
        bad = sum(1 for r in today_replies if r.get("feedback") == "bad")
        deleted = sum(1 for r in today_replies if r.get("feedback") == "deleted")

        lines = [
            "╔══════════════════════════════════════╗",
            f"║  📊  KCE DAILY SUMMARY — {today}",
            "║  ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━",
            "╚══════════════════════════════════════╝",
            "",
            f"💬 Replies today: `{len(today_replies)}`",
            f"👍 Good: `{good}`  👎 Bad: `{bad}`  🗑️ Deleted: `{deleted}`",
            f"🧬 Persona: `{len(DB.get('persona_phrases', []))}`",
            f"🚫 Banned: `{len(DB.get('banned_phrases', []))}`",
        ]
        card = "\n".join(lines)
        await send_log(card)
    except Exception as e:
        print(f"[aireply] summary err: {e}")


async def daily_summary_loop():
    await asyncio.sleep(20)
    while True:
        try:
            now = wat_now()
            if now.hour == 23 and now.minute == 59:
                last = DB.get("last_summary_date", "")
                if last != today_str():
                    DB["last_summary_date"] = today_str()
                    save_db(DB)
                    await send_daily_summary()
                await asyncio.sleep(60)
            await asyncio.sleep(30)
        except Exception as e:
            print(f"[aireply] summary loop err: {e}")
            await asyncio.sleep(60)


@CipherElite.on(events.NewMessage(pattern=r"\.kce\s+summary$"))
@rishabh()
async def cmd_summary(event):
    if not await _is_owner(event):
        return
    try:
        await _safe_reply(event, "⏳ Generating...")
        await send_daily_summary()
        await _safe_reply(event, "✅ Sent to log.")
    except Exception as e:
        await send_log(f"❌ summary err: `{e}`")


# ═══════════════════════════════════════════════════════════════
#  HEARTBEAT
# ═══════════════════════════════════════════════════════════════

HEARTBEAT_TASK = None


async def _heartbeat_loop():
    await asyncio.sleep(5)
    while True:
        try:
            me = await CipherElite.get_me()
            dbg(f"heartbeat — @{getattr(me, 'username', '?')}")
        except Exception as e:
            print(f"[aireply] heartbeat err: {e}")
        await asyncio.sleep(30)


@CipherElite.on(events.NewMessage(pattern=r"\.kce\s+online$"))
@rishabh()
async def cmd_online(event):
    global HEARTBEAT_TASK
    if not await _is_owner(event):
        return
    try:
        if HEARTBEAT_TASK and not HEARTBEAT_TASK.done():
            return await _safe_reply(event, "✅ Heartbeat running.")
        HEARTBEAT_TASK = asyncio.create_task(_heartbeat_loop())
        await _safe_reply(event, "🚀 Heartbeat started.")
    except Exception as e:
        await send_log(f"❌ online err: `{e}`")


# ═══════════════════════════════════════════════════════════════
#  BOOTSTRAP
# ═══════════════════════════════════════════════════════════════

async def _plugin_bootstrap():
    try:
        await asyncio.sleep(8)
        global HEARTBEAT_TASK
        if not HEARTBEAT_TASK or HEARTBEAT_TASK.done():
            HEARTBEAT_TASK = asyncio.create_task(_heartbeat_loop())
        try:
            asyncio.create_task(memory_flusher_loop())
            dbg("memory flusher started")
        except Exception as e:
            print(f"[aireply] flusher start err: {e}")
        try:
            asyncio.create_task(daily_summary_loop())
            dbg("daily summary started")
        except Exception as e:
            print(f"[aireply] summary start err: {e}")
        dbg("bootstrap complete")
    except Exception as e:
        print(f"[aireply] bootstrap err: {e}")


try:
    asyncio.create_task(_plugin_bootstrap())
except Exception as e:
    print(f"[aireply] bootstrap init err: {e}")


print("[aireply] MODULE LOADED SUCCESSFULLY — v3.5 ready")


# ╔══════════════════════════════════════════════════════════════╗
# ║  === END OF AIRREPLY v3.5 — CONTEST MODE ===                 ║
# ║                                                              ║
# ║  Personality: CALM / WARM / KIND                             ║
# ║                                                              ║
# ║  Learning signals:                                           ║
# ║  • Reply `good` / `bad` to log → persona / stats             ║
# ║  • EDIT bot's reply → persona learns your version            ║
# ║  • DELETE bot's reply → banned_phrases                       ║
# ║  • REACT ❤️/🤝/💛/🫡/😊/🔥 → persona learns good             ║
# ║  • Owner follows up after bot → persona learns style         ║
# ║                                                              ║
# ║  Contest mode:                                               ║
# ║  • Tracks individual 24h leaderboard                         ║
# ║  • Beats top human × 1.2                                     ║
# ║  • 24h context to Gemini                                     ║
# ║  • Room reading + tone adjust                                ║
# ║  • Multi-message follow-up (40%)                             ║
# ║  • Friendly question picker                                  ║
# ║  • Forward-to-QUEUE when unsure                              ║
# ╚══════════════════════════════════════════════════════════════╝
