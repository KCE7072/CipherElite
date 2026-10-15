# =============================================================================
#  CipherElite Userbot Plugin - aireply.py v3.6
#  FLOW MODE — calm/kind + voice pressure + pidgin matcher + back-to-back
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

print("[aireply] IMPORTING v3.6")

VERSION = "3.6.0"
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

KEYWORDS = [
    'gm', 'hi', 'hello', 'hey', 'wagmi', 'moon', 'airdrop', 'lfg',
    'altrix', 'altrixai', 'pump', 'bullish', 'tge', 'presale',
]

# ── Pace (aggressive) ──
BEAT_MARGIN = 1.3
MIN_PACE_SEC = 12
MAX_PACE_SEC = 120
IDLE_PACE_SEC = 90

# ── Aggressive initiation ──
INITIATE_ON_HYPE       = True
INITIATE_CHANCE_HYPED  = 0.55
INITIATE_CHANCE_NORMAL = 0.30
INITIATE_CHANCE_DEAD   = 0.15
INITIATE_MIN_GAP_SEC   = 20
HARD_CEILING_PER_HOUR  = 400
HARD_FLOOR_PER_HOUR    = 6

# ── Voice Pressure (v3.6) ──
VOICE_PRESSURE_ENABLED   = True
VOICE_PRESSURE_MAX_LINES = 3       # max back-to-back msgs
VOICE_PRESSURE_GAP_SEC   = (3, 7)  # delay between back-to-back
VOICE_PRESSURE_TRIGGER   = 0.65    # chance to go multi-line when hyped
VOICE_PRESSURE_COOLDOWN  = 90      # sec before next pressure burst in same room

# ── Flow Mode (v3.6) ──
FLOW_ENABLED             = True
FLOW_FOLLOWUP_WINDOW_SEC = 45      # if no one replies to bot within this → bot continues
FLOW_FOLLOWUP_CHANCE     = 0.5     # 50% chance to self-continue
FLOW_CHAIN_DEPTH         = 3       # track last 3 human replies
FLOW_ASK_BACK_CHANCE     = 0.35    # 35% chance bot asks back

# ── Pidgin Matcher (v3.6) ──
PIDGIN_ENABLED           = True
PIDGIN_WINDOW_SEC        = 600     # room stays "pidgin" for 10 min after last pidgin msg
PIDGIN_MARKERS = {
    'dey', 'na', 'abi', 'wahala', 'abeg', 'omo', 'sabi', 'chop',
    'wetin', 'shey', 'sha', 'sef', 'gan', 'nna', 'bros', 'broski',
    'wahala', 'oyibo', 'japa', 'yawa', 'gbege', 'kparapapa',
}
PIDGIN_PHRASES = [
    'how far', 'no wahala', 'e go be', 'i dey', 'you dey',
    'we dey', 'make i', 'make we', 'shey you', 'abi no be',
]

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

# ── System prompts ──
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

SYSTEM_PROMPT_PIDGIN = """You are KCE — a warm, kind, calm Nigerian guy in a crypto Telegram group. You speak PIDGIN naturally, like a real Naija guy.

Your vibe:
- Calm, never loud
- Kind, never rude
- Warm, never cold
- Positive, never negative
- Fluent pidgin — you chop pidgin, you no dey form

Rules:
- Reply in 3-5 words maximum.
- Speak pidgin naturally: "dey", "na", "abi", "wahala", "omo", "sabi", "shey", "sha", "sef".
- NEVER speak formal English when pidgin is right.
- Lowercase only unless it's a name.
- 0-1 emoji max (only: ❤️ 🤝 💛 🫡 😊 🔥)
- NEVER insult, mock, or argue.
- NEVER take sides in drama.
- Sound like a real Naija friend.

Good examples:
- "gm" → "morning my guy"
- "wagmi" → "we dey together"
- "sol going up?" → "e go pump bro 🤝"
- "i made money" → "chop am well 🔥"
- "how far" → "i dey o, you nko?"

Reply with just the text. Nothing else."""

SYSTEM_PROMPT_FOLLOWUP = """You are KCE, continuing a warm conversation in a Nigerian crypto Telegram group.
Your last reply was short. Now you send a SHORT follow-up (2-4 words).
- Warm, calm, kind
- Could be: gentle question, warm agreement, small addition, kind check-in
- Match pidgin if room is pidgin
- Just the follow-up. Nothing else."""

SYSTEM_PROMPT_ASK_BACK = """You are KCE. Someone said something and you want to gently ask them back.
Send a SHORT follow-up QUESTION (3-6 words) that:
- Invites them to share more
- Is warm, kind, curious
- Matches pidgin if room is pidgin
- Just the question. Nothing else.

Examples:
- "you dey trade am?"
- "how e go for you?"
- "you don try am?"
- "wetin you think?"
- "you hold any?"
"""


print("[aireply] MODULE LOADED — chunk 1")

# ═══ END OF CHUNK 1 ═══
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
        "aggressive": True,                # v3.6 default ON
        "slow_mode_until": 0,
        "admin_last_seen": {},
        "leaderboard": {},
        "group_messages": {},
        "bot_pace": {},
        "pidgin_rooms": {},                # v3.6: {chat_id: last_pidgin_ts}
        "voice_pressure_cooldown": {},     # v3.6: {chat_id: last_burst_ts}
        "flow_pending": {},                # v3.6: {chat_id: {bot_msg_id, ts, replied}}
        "started": wat_now().strftime("%Y-%m-%d %H:%M:%S"),
    }


def save_db(data):
    try:
        DB_FILE.write_text(
            json.dumps(data, indent=2, ensure_ascii=False),
            encoding="utf-8"
        )
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


print("[aireply] MODULE LOADED — chunk 2 (storage)")

# ═══ END OF CHUNK 2A — helpers continue in next chunk ═══
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
    return bool(DB.get("aggressive", True))


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


# ═══════════════════════════════════════════════════════════════
#  PIDGIN MATCHER (v3.6)
# ═══════════════════════════════════════════════════════════════

def is_pidgin_text(text):
    """Return True if text contains pidgin markers."""
    if not text:
        return False
    lower = text.lower()
    # phrase check first
    for p in PIDGIN_PHRASES:
        if p in lower:
            return True
    # word check
    words = re.findall(r"\b[a-z']+\b", lower)
    hits = sum(1 for w in words if w in PIDGIN_MARKERS)
    return hits >= 1


def mark_pidgin_room(chat_id):
    pr = DB.get("pidgin_rooms", {})
    pr[str(chat_id)] = time.time()
    DB["pidgin_rooms"] = pr
    # not saving every time — flusher handles it


def is_pidgin_room(chat_id):
    pr = DB.get("pidgin_rooms", {})
    last = pr.get(str(chat_id), 0)
    return (time.time() - last) < PIDGIN_WINDOW_SEC


def pick_system_prompt(chat_id):
    if is_pidgin_room(chat_id):
        return SYSTEM_PROMPT_PIDGIN
    return SYSTEM_PROMPT


# ═══════════════════════════════════════════════════════════════
#  HOURLY CEILING GUARD (v3.6)
# ═══════════════════════════════════════════════════════════════

def _hourly_fires(chat_id):
    bp = DB.get("bot_pace", {}).get(str(chat_id), {})
    fires = bp.get("recent_fires", [])
    cutoff = time.time() - 3600
    return [t for t in fires if t > cutoff]


def _can_fire_ceiling(chat_id):
    return len(_hourly_fires(chat_id)) < HARD_CEILING_PER_HOUR


def _mark_hourly_fire(chat_id):
    bp = DB.get("bot_pace", {})
    key = str(chat_id)
    if key not in bp:
        bp[key] = {}
    fires = bp[key].get("recent_fires", [])
    cutoff = time.time() - 3600
    fires = [t for t in fires if t > cutoff]
    fires.append(time.time())
    bp[key]["recent_fires"] = fires
    DB["bot_pace"] = bp
    if len(fires) % 5 == 0:
        save_db(DB)


# ═══════════════════════════════════════════════════════════════
#  NOISE + AGGRESSIVE INITIATION (v3.6)
# ═══════════════════════════════════════════════════════════════

def _is_noise(text, event):
    if not text:
        return True
    t = text.strip()
    if len(t) <= 2:
        return True
    if re.fullmatch(r'https?://\S+', t):
        return True
    if len(t.split()) < 2 and not any(c.isalpha() for c in t):
        return True
    return False


def _aggressive_should_fire(event, text, room_mode, me_id):
    if not INITIATE_ON_HYPE:
        return False, "disabled"
    if not is_aggressive():
        return False, "aggressive_off"
    if _is_noise(text, event):
        return False, "noise"
    if not _can_fire_ceiling(event.chat_id):
        return False, "ceiling"

    if room_mode in ("hyped", "celebratory"):
        chance = INITIATE_CHANCE_HYPED
    elif room_mode == "drama":
        return False, "drama"
    elif room_mode == "dead":
        chance = INITIATE_CHANCE_DEAD
    else:
        chance = INITIATE_CHANCE_NORMAL

    bp = DB.get("bot_pace", {}).get(str(event.chat_id), {})
    last_init = bp.get("last_initiate_ts", 0)
    if time.time() - last_init < INITIATE_MIN_GAP_SEC:
        return False, "init_gap"

    words = text.split()
    hot_words = ("lfg", "wagmi", "gm", "moon", "altrix", "altrixai",
                 "pump", "bullish", "tge", "airdrop")
    is_real = (
        len(words) >= 4
        or "?" in text
        or event.is_reply
        or (len(words) >= 2 and any(w.lower() in hot_words for w in words))
    )
    if not is_real:
        return False, "not_real"

    if random.random() > chance:
        return False, "no_roll"

    bp["last_initiate_ts"] = time.time()
    DB.setdefault("bot_pace", {})[str(event.chat_id)] = bp
    save_db(DB)
    return True, f"initiate_{room_mode}"


print("[aireply] MODULE LOADED — chunk 3")

# ═══ END OF CHUNK 3 ═══
# ═══════════════════════════════════════════════════════════════
#  FLOW MODE — Voice Pressure + Self-Continuation (v3.6)
# ═══════════════════════════════════════════════════════════════

def _in_voice_pressure_cooldown(chat_id):
    cd = DB.get("voice_pressure_cooldown", {})
    last = cd.get(str(chat_id), 0)
    return (time.time() - last) < VOICE_PRESSURE_COOLDOWN


def _mark_voice_pressure(chat_id):
    cd = DB.get("voice_pressure_cooldown", {})
    cd[str(chat_id)] = time.time()
    DB["voice_pressure_cooldown"] = cd
    save_db(DB)


def should_voice_pressure(chat_id, room_mode):
    """Decide whether to send a multi-message burst."""
    if not VOICE_PRESSURE_ENABLED:
        return False
    if not is_aggressive():
        return False
    if room_mode not in ("hyped", "celebratory", "normal"):
        return False
    if _in_voice_pressure_cooldown(chat_id):
        return False
    return random.random() < VOICE_PRESSURE_TRIGGER


def pick_pressure_line_count(room_mode):
    if room_mode in ("hyped", "celebratory"):
        return random.choice([2, 2, 3])
    return random.choice([2, 2, 2, 3])


def register_flow_pending(chat_id, bot_msg_id):
    """Track a bot msg so we can follow up if no one replies."""
    fp = DB.get("flow_pending", {})
    fp[str(chat_id)] = {
        "bot_msg_id": bot_msg_id,
        "ts": time.time(),
        "replied": False,
    }
    DB["flow_pending"] = fp


def clear_flow_pending(chat_id):
    fp = DB.get("flow_pending", {})
    if str(chat_id) in fp:
        del fp[str(chat_id)]
        DB["flow_pending"] = fp
        save_db(DB)


def should_self_continue(chat_id):
    """Check if bot should follow up on its own last msg."""
    if not FLOW_ENABLED:
        return False, None
    fp = DB.get("flow_pending", {}).get(str(chat_id))
    if not fp:
        return False, None
    if fp.get("replied"):
        return False, None
    age = time.time() - fp.get("ts", 0)
    if age < FLOW_FOLLOWUP_WINDOW_SEC:
        return False, None
    if age > 300:  # too old, forget it
        clear_flow_pending(chat_id)
        return False, None
    if random.random() > FLOW_FOLLOWUP_CHANCE:
        clear_flow_pending(chat_id)
        return False, None
    return True, fp


def should_ask_back(room_mode):
    if room_mode == "drama":
        return False
    return random.random() < FLOW_ASK_BACK_CHANCE


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
    bp[key] = bp.get(key, {})
    bp[key]["last_fire_ts"] = time.time()
    bp[key]["me_id"] = me_id
    DB["bot_pace"] = bp
    _mark_hourly_fire(chat_id)
    save_db(DB)


print("[aireply] MODULE LOADED — chunk 4")

# ═══ END OF CHUNK 4 ═══
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
    happy_words = ["pump", "win", "moon", "gm", "bullish", "ath",
                   "congrats", "let's go", "wagmi", "lfg"]
    drama_words = ["idiot", "fool", "stupid", "shut up", "dumb", "fake",
                   "scam", "you liar"]

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
        "drama": "Room has DRAMA. Stay calm, don't take sides, don't engage conflict.",
        "dead": "Room is quiet. Reply gently, maybe ask a small question to revive.",
        "celebratory": "Room is celebrating. Join them, congratulate, hype warmly.",
        "normal": "Room is normal. Warm, casual, natural.",
    }.get(mode, "Room is normal.")


# ═══════════════════════════════════════════════════════════════
#  LOG CARDS
# ═══════════════════════════════════════════════════════════════

def build_reply_card(n, group_name, user_name, their_msg, bot_reply,
                     speed="normal", jump_link=None, mode=None, followup=None,
                     extra_lines=None, pidgin=False):
    mode_tag = f"  •  🎭 {mode}" if mode else ""
    pidgin_tag = "  •  🗣️ pidgin" if pidgin else ""
    header = (
        "╔══════════════════════════════════════╗\n"
        "║  🎯⚡💥🔥  KCE AI REPLY v3.6  🎯⚡💥🔥\n"
        "║  ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        f"║  📍 {group_name[:30]}\n"
        f"║  👤 {user_name[:40]}\n"
        f"║  🕐 {wat_now().strftime('%I:%M:%S %p')} — {wat_now().strftime('%d/%m/%Y')} WAT\n"
        f"║  ⚡ {speed}{mode_tag}{pidgin_tag}\n"
        "╚══════════════════════════════════════╝"
    )
    body = (
        f'\n📩 THEY SAID\n"{their_msg[:150]}"\n'
        f'\n🤖 KCE REPLIED\n"{bot_reply}"\n'
    )
    if followup:
        body += f'\n💬 FOLLOW-UP\n"{followup}"\n'
    if extra_lines:
        for i, line in enumerate(extra_lines, 1):
            body += f'\n💥 PRESSURE #{i}\n"{line}"\n'
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
        ".kce aggressive on|off - self-initiation toggle",
        ".kce pressure on|off - voice pressure toggle",
        ".kce pidgin on|off - pidgin matcher toggle",
        ".kce flow on|off - flow mode toggle",
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
    description = "🤖 KCE AI Reply v3.6 — FLOW MODE"
    add_handler("aireply", commands, description)
    print("[aireply] commands registered")


print("[aireply] MODULE LOADED — chunk 5")

# ═══ END OF CHUNK 5 ═══
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

        def _flag(v):
            return "🟢" if v else "🔴"

        msg = (
            "🤖 **KCE AI Reply v3.6** — FLOW MODE\n"
            "━━━━━━━━━━━━━━━━━━━━\n"
            f"🧠 Gemini: {'✅ Ready' if gemini_ok else '❌ Disabled'}\n"
            f"📝 Whitelisted: `{len(wl)}` groups\n"
            f"💰 Wallet groups: `{len(wg)}`\n"
            f"💬 Replies sent: `{len(replies)}`\n"
            f"🧬 Persona: `{pp}`  🚫 Banned: `{bp}`\n"
            f"⚡ Speed: `{CURRENT_SPEED}`\n"
            f"🔥 Aggressive: {_flag(is_aggressive())}\n"
            f"💥 Pressure: {_flag(VOICE_PRESSURE_ENABLED)}\n"
            f"🗣️ Pidgin: {_flag(PIDGIN_ENABLED)}\n"
            f"🌊 Flow: {_flag(FLOW_ENABLED)}\n"
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
            f"🔥 Aggressive: `{'ON' if is_aggressive() else 'OFF'}`",
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
        pidgin = is_pidgin_room(cid)
        hourly = len(_hourly_fires(cid))
        lines = [
            "🏠 **Room read**",
            "━━━━━━━━━━━━━━━━━━━━",
            f"🎭 Room mode: `{mode}`",
            f"🗣️ Pidgin room: `{'YES' if pidgin else 'no'}`",
            f"⚡ Pace: `1 per {pace}s`",
            f"📊 Bot count: `{bot_count}`",
            f"🕐 Hourly fires: `{hourly}` / {HARD_CEILING_PER_HOUR}",
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
            return await _safe_reply(event, "📭 No leaderboard data yet.")
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
#  AGGRESSIVE TOGGLE
# ═══════════════════════════════════════════════════════════════

@CipherElite.on(events.NewMessage(pattern=r"\.kce\s+aggressive\s+(on|off)$"))
@rishabh()
async def cmd_aggressive(event):
    if not await _is_owner(event):
        return
    try:
        mode = event.pattern_match.group(1).lower()
        DB["aggressive"] = (mode == "on")
        save_db(DB)
        if mode == "on":
            await _safe_reply(
                event,
                "🔥 **Aggressive mode ON**\n"
                "━━━━━━━━━━━━━━━━━━━━\n"
                "• Bot initiates on its own\n"
                "• Fires on hyped/normal/celebratory\n"
                "• Pace: 12s min, 120s max\n"
                "• Ceiling: 400/hour"
            )
        else:
            await _safe_reply(event, "🛡️ **Aggressive OFF** — back to passive mode.")
    except Exception as e:
        await send_log(f"❌ aggressive err: `{e}`")


# ═══════════════════════════════════════════════════════════════
#  PRESSURE TOGGLE
# ═══════════════════════════════════════════════════════════════

@CipherElite.on(events.NewMessage(pattern=r"\.kce\s+pressure\s+(on|off)$"))
@rishabh()
async def cmd_pressure(event):
    global VOICE_PRESSURE_ENABLED
    if not await _is_owner(event):
        return
    try:
        mode = event.pattern_match.group(1).lower()
        VOICE_PRESSURE_ENABLED = (mode == "on")
        await _safe_reply(
            event,
            f"💥 **Voice Pressure {'ON' if VOICE_PRESSURE_ENABLED else 'OFF'}**\n"
            f"• Max burst: `{VOICE_PRESSURE_MAX_LINES}` lines\n"
            f"• Cooldown: `{VOICE_PRESSURE_COOLDOWN}s`"
        )
    except Exception as e:
        await send_log(f"❌ pressure err: `{e}`")


# ═══════════════════════════════════════════════════════════════
#  PIDGIN TOGGLE
# ═══════════════════════════════════════════════════════════════

@CipherElite.on(events.NewMessage(pattern=r"\.kce\s+pidgin\s+(on|off)$"))
@rishabh()
async def cmd_pidgin(event):
    global PIDGIN_ENABLED
    if not await _is_owner(event):
        return
    try:
        mode = event.pattern_match.group(1).lower()
        PIDGIN_ENABLED = (mode == "on")
        await _safe_reply(
            event,
            f"🗣️ **Pidgin Matcher {'ON' if PIDGIN_ENABLED else 'OFF'}**\n"
            f"• Window: `{PIDGIN_WINDOW_SEC}s` after last pidgin msg"
        )
    except Exception as e:
        await send_log(f"❌ pidgin err: `{e}`")


# ═══════════════════════════════════════════════════════════════
#  FLOW TOGGLE
# ═══════════════════════════════════════════════════════════════

@CipherElite.on(events.NewMessage(pattern=r"\.kce\s+flow\s+(on|off)$"))
@rishabh()
async def cmd_flow(event):
    global FLOW_ENABLED
    if not await _is_owner(event):
        return
    try:
        mode = event.pattern_match.group(1).lower()
        FLOW_ENABLED = (mode == "on")
        await _safe_reply(
            event,
            f"🌊 **Flow Mode {'ON' if FLOW_ENABLED else 'OFF'}**\n"
            f"• Self-continue: {int(FLOW_FOLLOWUP_CHANCE*100)}%\n"
            f"• Ask-back: {int(FLOW_ASK_BACK_CHANCE*100)}%"
        )
    except Exception as e:
        await send_log(f"❌ flow err: `{e}`")


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


print("[aireply] MODULE LOADED — chunk 6")

# ═══ END OF CHUNK 6 ═══
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
#  WALLET
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


print("[aireply] MODULE LOADED — chunk 7")

# ═══ END OF CHUNK 7 ═══
# ═══════════════════════════════════════════════════════════════
#  GEMINI
# ═══════════════════════════════════════════════════════════════

_gemini_client = None


def get_gemini_client():
    global _gemini_client
    if _gemini_client is None:
        api_key = ai_config.get_api_key()
        if not api_key:
            return None
        _gemini_client = genai.Client(api_key=api_key)
    return _gemini_client


def _build_system_prompt(chat_id, extra=None):
    mode = read_room(chat_id)
    hint = room_hint(mode)
    persona = get_persona_block()
    banned = get_banned_block()
    base = pick_system_prompt(chat_id)   # pidgin-aware
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
    if extra:
        base += f"\n\n{extra}"
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
            system_instruction=_build_system_prompt(
                chat_id, extra=SYSTEM_PROMPT_FOLLOWUP
            ),
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


# ═══════════════════════════════════════════════════════════════
#  V3.6 GENERATORS — ask-back + pressure line
# ═══════════════════════════════════════════════════════════════

async def generate_ask_back(context_block, original_text, bot_reply, chat_id):
    """Generate a short follow-up QUESTION to invite more conversation."""
    if not ai_config.is_enabled():
        return None
    api_key = ai_config.get_api_key()
    if not api_key:
        return None

    prompt = f"""CONVERSATION CONTEXT:
{context_block if context_block else "(no context)"}

SOMEONE SAID:
\"{original_text[:150]}\"

YOU REPLIED:
\"{bot_reply}\"

Now ASK THEM BACK with a SHORT QUESTION (3-6 words).
- Warm, curious, inviting
- Matches pidgin if the room is pidgin
- Not needy, not formal
- Just the question. Nothing else."""

    try:
        client = genai.Client(api_key=api_key)
        config = types.GenerateContentConfig(
            system_instruction=_build_system_prompt(
                chat_id, extra=SYSTEM_PROMPT_ASK_BACK
            ),
            max_output_tokens=30,
            temperature=1.2,
            top_p=0.95,
        )
        resp = await client.aio.models.generate_content(
            model=GEMINI_MODEL,
            contents=[types.Content(role="user", parts=[types.Part(text=prompt)])],
            config=config,
        )
        text = (resp.text or "").strip().replace("\n", " ").strip('"').strip("'")
        words = text.split()
        if len(words) > 6:
            text = " ".join(words[:6])
        if len(text) < 2 or len(text) > 60:
            return None
        if text.lower() == bot_reply.lower():
            return None
        dbg(f"gemini ask-back: '{text}'")
        return text
    except Exception as e:
        print(f"[aireply] ask-back err: {e}")
        return None


async def generate_pressure_line(context_block, original_text, bot_reply,
                                  previous_lines, chat_id):
    """Generate one more line for a voice-pressure burst."""
    if not ai_config.is_enabled():
        return None
    api_key = ai_config.get_api_key()
    if not api_key:
        return None

    prev = " | ".join(previous_lines) if previous_lines else "(none)"

    prompt = f"""CONVERSATION CONTEXT:
{context_block if context_block else "(no context)"}

SOMEONE SAID:
\"{original_text[:150]}\"

YOU ALREADY REPLIED (do NOT repeat any of these):
{prev}
\"{bot_reply}\"

Now add ONE more short line (2-4 words) that:
- Continues the same vibe warm and kind
- Adds a small thought, hype, or gentle question
- Matches pidgin if the room is pidgin
- Is NOT a repeat of any previous line
- Just the line. Nothing else."""

    try:
        client = genai.Client(api_key=api_key)
        config = types.GenerateContentConfig(
            system_instruction=_build_system_prompt(
                chat_id, extra=SYSTEM_PROMPT_FOLLOWUP
            ),
            max_output_tokens=30,
            temperature=1.35,
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
        if text.lower() in [l.lower() for l in previous_lines]:
            return None
        if text.lower() == bot_reply.lower():
            return None
        dbg(f"gemini pressure: '{text}'")
        return text
    except Exception as e:
        print(f"[aireply] pressure err: {e}")
        return None


async def _fire_online():
    try:
        await CipherElite(functions.account.UpdateStatusRequest(offline=False))
    except Exception as e:
        dbg(f"online ping err: {e}")


print("[aireply] MODULE LOADED — chunk 8")

# ═══ END OF CHUNK 8 ═══
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

        # v3.6: pidgin detection
        if PIDGIN_ENABLED and is_pidgin_text(text):
            mark_pidgin_room(event.chat_id)

        # v3.6: mark flow pending replied when human replies to bot
        me = await CipherElite.get_me()
        if event.is_reply:
            try:
                replied = await event.get_reply_message()
                if replied and replied.sender_id == me.id:
                    clear_flow_pending(event.chat_id)
            except Exception:
                pass

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

async def _do_send_with_typing(event, text, total_delay):
    """Send a reply with typing indicator + delay."""
    try:
        await _fire_online()
        first = max(1, total_delay // 2)
        second = max(1, total_delay - first)
        async with CipherElite.action(event.chat_id, "typing"):
            await asyncio.sleep(first)
        await asyncio.sleep(random.uniform(0.3, 1.0))
        async with CipherElite.action(event.chat_id, "typing"):
            await asyncio.sleep(second)
    except Exception:
        await asyncio.sleep(total_delay)

    try:
        sent = await event.reply(text)
        return sent
    except FloodWaitError as e:
        await asyncio.sleep(e.seconds + 1)
        return await event.reply(text)
    except Exception as e:
        print(f"[aireply] send err: {e}")
        return None


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

        # ceiling guard
        if not _can_fire_ceiling(event.chat_id):
            dbg(f"ceiling reached for {event.chat_id}")
            return

        if not should_fire_now(event.chat_id):
            pace, _ = compute_pace(event.chat_id, me.id)
            dbg(f"pace block: need {pace}s between fires")
            return

        triggered = False
        trigger_type = None

        # ── Trigger path 1: continuation on bot's own msg ──
        if event.is_reply:
            replied = await event.get_reply_message()
            if replied and replied.sender_id == me.id:
                triggered, trigger_type = True, "continuation"

        # ── Trigger path 2: mention ──
        if not triggered and me.username and f"@{me.username.lower()}" in text.lower():
            triggered, trigger_type = True, "mention"

        # ── Trigger path 3: keyword ──
        if not triggered and has_trigger(text):
            triggered, trigger_type = True, "keyword"

        # ── Trigger path 4: friendly question ──
        if not triggered and _looks_like_friendly_question(text):
            bp = DB.get("bot_pace", {}).get(str(event.chat_id), {})
            last = bp.get("last_fire_ts", 0)
            if time.time() - last >= 60:
                triggered, trigger_type = True, "friendly_q"

        # ── Trigger path 5: AGGRESSIVE INITIATION (v3.6) ──
        if not triggered:
            room_mode_pre = read_room(event.chat_id)
            should, reason = _aggressive_should_fire(event, text, room_mode_pre, me.id)
            if should:
                triggered = True
                trigger_type = reason
                dbg(f"AGGRESSIVE INITIATE — {reason}")
            else:
                dbg(f"skip: {reason}")
                return

        dbg(f"trigger={trigger_type} chat={event.chat_id} text='{text[:50]}'")

        context_block = get_context(event.chat_id, limit=400)

        # ── Generate main reply ──
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

        # ── Delay computation ──
        base_delay = get_delay()
        if mode == "hyped":
            base_delay = max(1, base_delay // 2)
        elif mode == "dead":
            base_delay = int(base_delay * 1.5)
        if trigger_type and trigger_type.startswith("initiate_"):
            base_delay = max(1, base_delay // 2)
        total_delay = base_delay + get_slow_mode_extra()

        sent = await _do_send_with_typing(event, reply_text, total_delay)
        if not sent:
            return

        mark_fired(event.chat_id, me.id)
        record_individual(event.chat_id, me.id, "KCE")

        # ── Register flow pending (so we can self-continue) ──
        register_flow_pending(event.chat_id, sent.id)

        # ── Voice Pressure Burst (v3.6) ──
        pressure_lines = []
        if should_voice_pressure(event.chat_id, mode):
            n_lines = pick_pressure_line_count(mode)
            for i in range(n_lines - 1):
                await asyncio.sleep(random.uniform(*VOICE_PRESSURE_GAP_SEC))
                line = await generate_pressure_line(
                    context_block, text, reply_text,
                    pressure_lines, event.chat_id
                )
                if not line:
                    break
                try:
                    async with CipherElite.action(event.chat_id, "typing"):
                        await asyncio.sleep(random.uniform(0.8, 1.8))
                    extra = await event.reply(line)
                    pressure_lines.append(line)
                    record_individual(event.chat_id, me.id, "KCE")
                    # if user replies to this extra, clear pending
                    clear_flow_pending(event.chat_id)
                except Exception as e:
                    dbg(f"pressure send err: {e}")
                    break
            if pressure_lines:
                _mark_voice_pressure(event.chat_id)

        # ── Ask-back (v3.6) — inline with main reply if rolled ──
        ask_back_text = None
        if FLOW_ENABLED and should_ask_back(mode) and not pressure_lines:
            ask_back_text = await generate_ask_back(
                context_block, text, reply_text, event.chat_id
            )
            if ask_back_text:
                await asyncio.sleep(random.uniform(2, 5))
                try:
                    async with CipherElite.action(event.chat_id, "typing"):
                        await asyncio.sleep(random.uniform(0.5, 1.5))
                    await event.reply(ask_back_text)
                    record_individual(event.chat_id, me.id, "KCE")
                except Exception as e:
                    dbg(f"ask-back send err: {e}")
                    ask_back_text = None

        # ── Follow-up (existing logic) ──
        followup = None
        if not pressure_lines and not ask_back_text and random.random() < 0.4:
            followup = await generate_followup(context_block, text, reply_text, event.chat_id)
            if followup:
                await asyncio.sleep(random.uniform(2, 6))
                try:
                    await event.reply(followup)
                    record_individual(event.chat_id, me.id, "KCE")
                except Exception as e:
                    dbg(f"followup send err: {e}")

        # ── Emoji reaction ──
        if random.random() < 0.3:
            try:
                await sent.react(random.choice(REACTION_EMOJIS))
            except Exception:
                pass

        # ── Log card ──
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
            "pressure_lines": pressure_lines,
            "ask_back": ask_back_text,
            "time12": stamp["time12"],
            "date": stamp["date"],
            "ts": stamp["ts"],
            "trigger": trigger_type,
            "speed": speed_label,
            "mode": mode,
            "pidgin": is_pidgin_room(event.chat_id),
            "jump_link": jump,
            "feedback": None,
        }
        replies.append(record)
        DB["replies"] = replies[-500:]
        save_db(DB)

        card = build_reply_card(
            reply_num, chat_name, user_name, text, reply_text,
            speed=speed_label, jump_link=jump, mode=mode,
            followup=followup or ask_back_text,
            extra_lines=pressure_lines,
            pidgin=record["pidgin"]
        )
        await send_log(card)

    except FloodWaitError as e:
        print(f"[aireply] FloodWait {e.seconds}s")
        await asyncio.sleep(e.seconds + 1)
    except Exception as e:
        print(f"[aireply] handler err: {e}")


# ═══════════════════════════════════════════════════════════════
#  FLOW SELF-CONTINUATION LOOP (v3.6)
# ═══════════════════════════════════════════════════════════════

async def flow_self_continue_loop():
    """Every 20s, check if bot should self-continue on quiet rooms."""
    await asyncio.sleep(25)
    while True:
        try:
            if not FLOW_ENABLED:
                await asyncio.sleep(20)
                continue
            fp_all = DB.get("flow_pending", {})
            now = time.time()
            for cid_str in list(fp_all.keys()):
                fp = fp_all[cid_str]
                if fp.get("replied"):
                    continue
                age = now - fp.get("ts", 0)
                if age < FLOW_FOLLOWUP_WINDOW_SEC:
                    continue
                if age > 300:
                    clear_flow_pending(int(cid_str))
                    continue

                cid = int(cid_str)
                if not is_whitelisted(cid):
                    clear_flow_pending(cid)
                    continue
                if not _can_fire_ceiling(cid):
                    continue

                # Check if anyone spoke after bot's last msg
                gm = DB.get("group_messages", {}).get(cid_str, [])
                bot_ts = fp.get("ts", 0)
                human_after = [m for m in gm if m.get("ts", 0) > bot_ts]
                if human_after:
                    fp["replied"] = True
                    save_db(DB)
                    continue

                if random.random() > FLOW_FOLLOWUP_CHANCE:
                    clear_flow_pending(cid)
                    continue

                # Generate a soft opener to revive the room
                room_mode = read_room(cid)
                context_block = get_context(cid, limit=100)
                last_bot_msg = None
                replies = DB.get("replies", [])
                for r in reversed(replies):
                    if r.get("group_id") == cid and r.get("sent_msg_id") == fp.get("bot_msg_id"):
                        last_bot_msg = r.get("bot_reply")
                        break

                opener = await generate_pressure_line(
                    context_block,
                    "(no new message — you want to keep the vibe going)",
                    last_bot_msg or "hey",
                    [], cid
                )
                if not opener:
                    clear_flow_pending(cid)
                    continue

                try:
                    await CipherElite.send_message(cid, opener)
                    dbg(f"flow self-continued in {cid}: '{opener}'")
                    record_individual(cid, (await CipherElite.get_me()).id, "KCE")
                    _mark_hourly_fire(cid)
                except Exception as e:
                    dbg(f"flow self-cont err: {e}")

                clear_flow_pending(cid)

            await asyncio.sleep(20)
        except Exception as e:
            print(f"[aireply] flow loop err: {e}")
            await asyncio.sleep(30)


print("[aireply] MODULE LOADED — chunk 9")

# ═══ END OF CHUNK 9 ═══
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
#  DELETE WATCHER
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
#  REACTION WATCHER
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
#  OWNER FOLLOW-UP WATCHER
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


# ═══════════════════════════════════════════════════════════════
#  FEEDBACK WATCHER
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
#  DM WATCHER
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

            # v3.6: prune pidgin rooms older than window
            pr = DB.get("pidgin_rooms", {})
            pc = time.time() - PIDGIN_WINDOW_SEC
            pr_changed = False
            for cid in list(pr.keys()):
                if pr[cid] < pc:
                    del pr[cid]
                    pr_changed = True
            if pr_changed:
                DB["pidgin_rooms"] = pr
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
        pressure = sum(1 for r in today_replies if r.get("pressure_lines"))
        askbacks = sum(1 for r in today_replies if r.get("ask_back"))

        lines = [
            "╔══════════════════════════════════════╗",
            f"║  📊  KCE DAILY SUMMARY — {today}",
            "║  ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━",
            "╚══════════════════════════════════════╝",
            "",
            f"💬 Replies today: `{len(today_replies)}`",
            f"👍 Good: `{good}`  👎 Bad: `{bad}`  🗑️ Deleted: `{deleted}`",
            f"💥 Pressure bursts: `{pressure}`",
            f"❓ Ask-backs: `{askbacks}`",
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
        try:
            asyncio.create_task(flow_self_continue_loop())
            dbg("flow self-continue loop started")
        except Exception as e:
            print(f"[aireply] flow start err: {e}")
        dbg("bootstrap complete")
    except Exception as e:
        print(f"[aireply] bootstrap err: {e}")


try:
    asyncio.create_task(_plugin_bootstrap())
except Exception as e:
    print(f"[aireply] bootstrap init err: {e}")


print("[aireply] MODULE LOADED SUCCESSFULLY — v3.6 ready")


# ╔══════════════════════════════════════════════════════════════╗
# ║  === END OF AIRREPLY v3.6 — FLOW MODE ===                    ║
# ║                                                              ║
# ║  Personality: CALM / WARM / KIND                             ║
# ║                                                              ║
# ║  v3.6 Additions:                                             ║
# ║  • 🔥 Aggressive initiation (5th trigger path)               ║
# ║  • 💥 Voice Pressure — up to 3 back-to-back lines            ║
# ║  • 🌊 Flow Mode — self-continues if room goes quiet          ║
# ║  • ❓ Ask-back — 35% chance for warm follow-up question      ║
# ║  • 🗣️ Pidgin Matcher — auto-switches voice in pidgin rooms   ║
# ║  • 🕐 Hourly ceiling 400 / floor 6                           ║
# ║  • 🎛️ Toggles: aggressive / pressure / pidgin / flow         ║
# ║                                                              ║
# ║  Learning signals (unchanged):                               ║
# ║  • Reply `good` / `bad` to log → persona / stats             ║
# ║  • EDIT bot's reply → persona learns your version            ║
# ║  • DELETE bot's reply → banned_phrases                       ║
# ║  • REACT ❤️/🤝/💛/🫡/😊/🔥 → persona learns good             ║
# ║  • Owner follows up after bot → persona learns style         ║
# ╚══════════════════════════════════════════════════════════════╝
