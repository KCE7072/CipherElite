
# =============================================================================
#  CipherElite Userbot Plugin - aireply.py v3.2
#  Full learning: group memory + room reading + persona + aggressive + slow
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

print("[aireply] IMPORTING v3.2")

VERSION = "3.2.0"
CATEGORY = "utilities"

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

# Aggressive mode overrides
AGGRESSIVE_SPEED = (1, 2)
AGGRESSIVE_GAP = 5
AGGRESSIVE_HOURLY = 60
AGGRESSIVE_REACT_PROB = 0.6
AGGRESSIVE_MIN_WORDS = 3      # any message with 3+ words triggers

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

WALLET_PATTERNS = {
    'sol': re.compile(r'\b[1-9A-HJ-NP-Za-km-z]{32,44}\b'),
    'evm': re.compile(r'\b0x[a-fA-F0-9]{40}\b'),
    'sui': re.compile(r'\b0x[a-fA-F0-9]{64}\b'),
}

# ── Learning config
LEARN_BATCH_SECONDS = 60       # group memory batches
LEARN_MAX_PHRASES = 30
LEARN_MAX_TOPICS = 20
ACTIVITY_WINDOW = 300          # seconds rolling
SLOW_MODE_THRESHOLD = 5        # distinct typers
SLOW_MODE_EXTRA_DELAY = 10     # seconds
SLOW_MODE_RESET = 3            # drop below this resets

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
        "aggressive": False,
        "slow_mode_until": 0,
        "admin_last_seen": {},
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


def reset_daily_if_needed():
    if DB.get("daily", {}).get("date") != today_str():
        DB["daily"] = {"date": today_str(), "count": 0}
        save_db(DB)


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


def aggressive_trigger(text):
    """Aggressive mode: reply to any message with 3+ words."""
    if not text:
        return False
    words = text.strip().split()
    return len(words) >= AGGRESSIVE_MIN_WORDS


def can_reply_to_user(user_id):
    gap = AGGRESSIVE_GAP if is_aggressive() else MIN_GAP_SAME_USER
    if gap <= 0:
        return True
    last = DB.get("replied_users", {}).get(str(user_id), 0)
    return (wat_now().timestamp() - last) >= gap


def can_reply_in_group(group_id):
    limit = AGGRESSIVE_HOURLY if is_aggressive() else RATE_LIMIT_HOURLY
    now = wat_now().timestamp()
    hour_ago = now - 3600
    timestamps = DB.get("hourly", {}).get(str(group_id), [])
    recent = [t for t in timestamps if t > hour_ago]
    return len(recent) < limit


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
    if is_aggressive():
        lo, hi = AGGRESSIVE_SPEED
    else:
        lo, hi = SPEED_MODES.get(CURRENT_SPEED, SPEED_MODES["normal"])
    return random.randint(lo, hi)


def get_slow_mode_extra():
    """Extra delay if slow mode active."""
    until = DB.get("slow_mode_until", 0)
    if until and wat_now().timestamp() < until:
        return SLOW_MODE_EXTRA_DELAY
    return 0


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


# ═══════════════════════════════════════════════════════════════
#  GROUP MEMORY — helpers
# ═══════════════════════════════════════════════════════════════

_mem_buffer = {}  # {chat_id: {"messages": [], "last_flush": ts}}


def record_message(chat_id, text, sender_id):
    """Buffer a message for the 60s batched memory update."""
    if not text or len(text) < 2:
        return
    if text.startswith((".", "..")):
        return
    buf = _mem_buffer.setdefault(chat_id, {"messages": [], "last_flush": time.time()})
    buf["messages"].append({
        "text": text[:300],
        "sender_id": sender_id,
        "ts": time.time(),
    })
    # cap buffer
    if len(buf["messages"]) > 500:
        buf["messages"] = buf["messages"][-500:]


def _extract_phrases(messages):
    """Top phrases from a batch of messages."""
    counter = {}
    stop = {"the", "a", "an", "and", "or", "to", "of", "in", "on", "at",
            "is", "am", "are", "was", "were", "be", "been", "being",
            "it", "its", "this", "that", "these", "those", "so", "for",
            "with", "from", "by", "as", "if", "then", "than", "but"}
    for m in messages:
        t = (m.get("text") or "").lower()
        # words
        for w in re.findall(r"[a-z0-9$]{3,}", t):
            if w in stop:
                continue
            counter[w] = counter.get(w, 0) + 1
    top = sorted(counter.items(), key=lambda kv: -kv[1])[:LEARN_MAX_PHRASES]
    return [w for w, _ in top]


def _extract_topics(messages):
    """Recurring $TOKEN or project mentions."""
    counter = {}
    for m in messages:
        t = m.get("text") or ""
        for tok in re.findall(r"\$[A-Za-z0-9_]{2,20}", t):
            counter[tok.upper()] = counter.get(tok.upper(), 0) + 1
    top = sorted(counter.items(), key=lambda kv: -kv[1])[:LEARN_MAX_TOPICS]
    return [w for w, _ in top]


def _infer_tone(messages):
    """Infer dominant tone from a batch."""
    pidgin_markers = ["omo", "na", "dey", "sha", "abi", "chale", "wahala",
                      "shey", "sabi", "jare", "sef", "gan"]
    formal_markers = ["please", "kindly", "regards", "sincerely", "apolog",
                      "however", "furthermore", "moreover"]
    casual_markers = ["lol", "lmao", "fr", "ngl", "tbh", "imo", "bro", "fam"]

    pidgin_score = 0
    formal_score = 0
    casual_score = 0
    total = 0
    for m in messages:
        t = (m.get("text") or "").lower()
        if not t:
            continue
        total += 1
        for k in pidgin_markers:
            if k in t:
                pidgin_score += 1
        for k in formal_markers:
            if k in t:
                formal_score += 1
        for k in casual_markers:
            if k in t:
                casual_score += 1
    if total == 0:
        return "casual"
    if pidgin_score > total * 0.15:
        return "pidgin"
    if formal_score > total * 0.1:
        return "formal"
    if casual_score > total * 0.2:
        return "casual"
    return "casual"


def flush_memory(chat_id):
    """Called every 60s — processes buffer into group memory."""
    buf = _mem_buffer.get(chat_id)
    if not buf or not buf["messages"]:
        return
    messages = buf["messages"]

    gm = DB.get("group_memory", {})
    existing = gm.get(str(chat_id), {})

    # merge phrases
    new_phrases = _extract_phrases(messages)
    old_phrases = existing.get("top_phrases", [])
    merged = old_phrases + new_phrases
    # count + sort
    cnt = {}
    for p in merged:
        cnt[p] = cnt.get(p, 0) + 1
    top_phrases = [k for k, _ in sorted(cnt.items(), key=lambda kv: -kv[1])[:LEARN_MAX_PHRASES]]

    # merge topics
    new_topics = _extract_topics(messages)
    old_topics = existing.get("topics", [])
    tcnt = {}
    for t in old_topics + new_topics:
        tcnt[t] = tcnt.get(t, 0) + 1
    top_topics = [k for k, _ in sorted(tcnt.items(), key=lambda kv: -kv[1])[:LEARN_MAX_TOPICS]]

    # tone
    tone = _infer_tone(messages)

    # activity rate (msgs/min)
    now_ts = time.time()
    recent = [m for m in messages if now_ts - m.get("ts", 0) < ACTIVITY_WINDOW]
    activity_rate = len(recent) / (ACTIVITY_WINDOW / 60)

    # mode
    if activity_rate > 5:
        mode = "hyped"
    elif activity_rate < 0.2:
        mode = "dead"
    else:
        mode = "normal"

    # check average message length for "serious"
    avg_len = sum(len(m.get("text", "")) for m in messages) / max(len(messages), 1)
    if avg_len > 80 and activity_rate < 3:
        mode = "serious"

    gm[str(chat_id)] = {
        "top_phrases": top_phrases,
        "topics": top_topics,
        "tone": tone,
        "mode": mode,
        "activity_rate": round(activity_rate, 2),
        "msg_count": existing.get("msg_count", 0) + len(messages),
        "last_updated": now_ts,
    }
    DB["group_memory"] = gm
    save_db(DB)
    dbg(f"memory flush {chat_id}: tone={tone} mode={mode} phrases={len(top_phrases)}")

    # clear buffer
    buf["messages"] = []
    buf["last_flush"] = now_ts


def get_group_context(chat_id):
    """Return a short context string for the prompt."""
    gm = DB.get("group_memory", {}).get(str(chat_id))
    if not gm:
        return ""
    parts = []
    if gm.get("tone"):
        parts.append(f"tone={gm['tone']}")
    if gm.get("mode"):
        parts.append(f"room={gm['mode']}")
    if gm.get("top_phrases"):
        parts.append(f"common words: {', '.join(gm['top_phrases'][:10])}")
    if gm.get("topics"):
        parts.append(f"hot topics: {', '.join(gm['topics'][:5])}")
    return " | ".join(parts)


def get_persona_block():
    pp = DB.get("persona_phrases", [])
    if not pp:
        return ""
    return f"Phrases you actually use: {', '.join(pp[-15:])}"


print("[aireply] MODULE LOADED — chunk 1")

# ═══ END OF BATCH 1 ═══
# ═══════════════════════════════════════════════════════════════
#  GEMINI — keyword replies with group memory + persona
# ═══════════════════════════════════════════════════════════════

def _build_room_instruction(chat_id):
    """Returns tone/room hints based on group memory."""
    gm = DB.get("group_memory", {}).get(str(chat_id))
    if not gm:
        return ""
    tone = gm.get("tone", "casual")
    mode = gm.get("mode", "normal")

    hints = []
    if tone == "pidgin":
        hints.append("- This group uses Nigerian Pidgin a lot — you can reply in pidgin")
    elif tone == "formal":
        hints.append("- This group is more formal — keep replies clean English, no slang")
    else:
        hints.append("- This group is casual — slang is fine")

    if mode == "hyped":
        hints.append("- Room is HYPED right now — match the energy, be quick")
    elif mode == "dead":
        hints.append("- Room is quiet right now — be more engaging, don't sound flat")
    elif mode == "serious":
        hints.append("- Room is serious right now — no jokes, no slang")

    return "\n".join(hints)


async def generate_reply(their_message, context_messages=None, chat_id=None):
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

    # room reading + persona
    room_hint = _build_room_instruction(chat_id) if chat_id else ""
    persona = get_persona_block()

    extra = ""
    if room_hint:
        extra += f"\n\nContext from this group:\n{room_hint}"
    if persona:
        extra += f"\n\n{persona}"

    user_prompt = f"""Recent context:
{context if context else "(no context)"}

Recent replies you already sent (DO NOT repeat these):
{banned}

Message to reply to:
\"{their_message[:200]}\"{extra}

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
                    f"Do NOT repeat it. Say something different, max {WORD_LIMIT} words."
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
        print(f"[aireply] Gemini err: {e}")
        return None


# ═══════════════════════════════════════════════════════════════
#  PERSONA BUILDER — extract phrases from good replies
# ═══════════════════════════════════════════════════════════════

def persona_add(reply_text):
    """Add words from a good reply to the persona list."""
    if not reply_text:
        return
    t = reply_text.lower().strip()
    if len(t) < 2 or len(t) > 60:
        return
    pp = DB.get("persona_phrases", [])
    # add whole phrase if it's short, else skip
    if t not in pp and len(t) <= 30:
        pp.append(t)
        DB["persona_phrases"] = pp[-50:]  # keep 50
        save_db(DB)
        dbg(f"persona added: '{t}'")


# ═══════════════════════════════════════════════════════════════
#  SENDERS
# ═══════════════════════════════════════════════════════════════

def build_reply_card(n, group_name, user_name, their_msg, bot_reply,
                     speed="normal", jump_link=None):
    mode_tag = " 🔥 AGGRO" if is_aggressive() else ""
    header = (
        "╔══════════════════════════════════════╗\n"
        "║  🎯⚡💥🔥  KCE AI REPLY  🎯⚡💥🔥\n"
        "║  ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        f"║  📍 {group_name[:30]}\n"
        f"║  👤 {user_name[:40]}\n"
        f"║  🕐 {wat_now().strftime('%I:%M:%S %p')} — {wat_now().strftime('%d/%m/%Y')} WAT\n"
        f"║  🎚️ {speed}{mode_tag}\n"
        "╚══════════════════════════════════════╝"
    )
    body = (
        f'\n📩 THEY SAID\n"{their_msg[:150]}"\n'
        f'\n🤖 KCE REPLIED\n"{bot_reply}"\n'
        f"\n✅ SENT  •  ⚡ {speed}\n"
        f"🔗 Auto-generated reply  •  #{n}\n"
    )
    if jump_link:
        body += f"🔗 Jump: {jump_link}\n"
    body += "━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
    body += "💡 Reply to this card with `good` or `bad` to teach KCE"
    return header + body


def build_wallet_card(n, group_name, user_name, dropped, chain, addr, jump_link=None):
    header = (
        "╔══════════════════════════════════════╗\n"
        "║  💰⚡💥🔥  KCE WALLET DROP  🔥💥⚡💰\n"
        "║  ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        f"║  📍 {group_name[:30]}\n"
        f"║  👤 {user_name[:40]}\n"
        f"║  🕐 {wat_now().strftime('%I:%M:%S %p')} — {wat_now().strftime('%d/%m/%Y')} WAT\n"
        "╚══════════════════════════════════════╝"
    )
    body = (
        f'\n💬 THEY DROPPED\n"{dropped[:150]}"\n'
        f'\n💰 KCE REPLIED ({chain.upper()})\n"{addr}"\n'
        f"\n⚡ BEAST MODE\n🔗 #{n}\n"
    )
    if jump_link:
        body += f"🔗 Jump: {jump_link}\n"
    body += "━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    return header + body


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
        ".kce tz - timezone",
        ".kce aggressive on/off",
        ".kce room - current room read",
        ".kce persona list",
        ".kce summary - trigger daily summary",
        ".kce dm block/unblock/list",
        ".kce wallet set sol|evm|sui <addr>",
        ".kce wallet list",
        ".kce wallet on|off <link|id>",
        ".kcew - whitelist current group",
        ".kcew off - remove whitelist",
        ".kcew list - list whitelisted",
    ]
    description = "🤖 KCE AI Reply v3.2 — learning + aggressive + persona"
    add_handler("aireply", commands, description)
    print("[aireply] commands registered")


# ═══════════════════════════════════════════════════════════════
#  STATUS / STATS / MEMORY / HELP / TZ
# ═══════════════════════════════════════════════════════════════

@CipherElite.on(events.NewMessage(pattern=r"\.kce$"))
@rishabh()
async def cmd_status(event):
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
        wg = DB.get("wallet_groups", [])
        aggro = "🔥 ON" if is_aggressive() else "off"
        slow_until = DB.get("slow_mode_until", 0)
        slow_st = "🟢 active" if slow_until and wat_now().timestamp() < slow_until else "off"
        msg = (
            "🤖 **KCE AI Reply v3.2**\n"
            "━━━━━━━━━━━━━━━━━━━━\n"
            f"🧠 Gemini: {'✅ Ready' if gemini_ok else '❌ Disabled'}\n"
            f"📝 Whitelisted: `{len(wl)}` groups\n"
            f"💰 Wallet groups: `{len(wg)}`\n"
            f"💬 Replies sent: `{len(replies)}`\n"
            f"📅 Today: `{today}/{RATE_LIMIT_DAILY}`\n"
            f"⚡ Speed: `{CURRENT_SPEED}`\n"
            f"🔥 Aggressive: `{aggro}`\n"
            f"🐢 Slow mode: `{slow_st}`\n"
            f"🧬 Persona phrases: `{len(DB.get('persona_phrases', []))}`\n"
            f"🕐 TZ: `WAT (UTC+1)`\n"
            f"🚫 DM blocked: `{len(bl)}`\n"
            f"🚀 Started: `{started}`\n"
            "━━━━━━━━━━━━━━━━━━━━\n"
            f"⚙️ Word limit: `{WORD_LIMIT}`"
        )
        await _safe_reply(event, msg)
    except Exception as e:
        await send_log(f"❌ status err: `{e}`")


@CipherElite.on(events.NewMessage(pattern=r"\.kce\s+stats$"))
@rishabh()
async def cmd_stats(event):
    if not await _is_owner(event):
        return
    try:
        reset_daily_if_needed()
        replies = DB.get("replies", [])
        today = today_str()
        today_count = sum(1 for r in replies if r.get("date") == today)
        wallet_count = sum(1 for r in replies if r.get("trigger") == "wallet")
        good = sum(1 for r in replies if r.get("feedback") == "good")
        bad = sum(1 for r in replies if r.get("feedback") == "bad")
        lines = [
            "📊 **KCE Stats**",
            "━━━━━━━━━━━━━━━━━━━━",
            f"💬 Total replies: `{len(replies)}`",
            f"📅 Today: `{today_count}`",
            f"💰 Wallet drops: `{wallet_count}`",
            f"👍 Good: `{good}`  👎 Bad: `{bad}`",
            f"⚡ Speed: `{CURRENT_SPEED}`",
            f"🔥 Aggressive: `{'ON' if is_aggressive() else 'off'}`",
        ]
        await _safe_reply(event, "\n".join(lines))
    except Exception as e:
        await send_log(f"❌ stats err: `{e}`")


@CipherElite.on(events.NewMessage(pattern=r"\.kce\s+memory$"))
@rishabh()
async def cmd_memory(event):
    if not await _is_owner(event):
        return
    try:
        replies = DB.get("replies", [])
        users = DB.get("replied_users", {})
        gm = DB.get("group_memory", {})
        lines = [
            "🧠 **KCE Memory**",
            "━━━━━━━━━━━━━━━━━━━━",
            f"💾 Replies: `{len(replies)}` / 500",
            f"👥 Users: `{len(users)}`",
            f"📁 Groups learned: `{len(gm)}`",
            f"🧬 Persona phrases: `{len(DB.get('persona_phrases', []))}`",
            f"📁 DB: `DB/aireply.json`",
        ]
        await _safe_reply(event, "\n".join(lines))
    except Exception as e:
        await send_log(f"❌ memory err: `{e}`")


@CipherElite.on(events.NewMessage(pattern=r"\.kce\s+room$"))
@rishabh()
async def cmd_room(event):
    if not await _is_owner(event):
        return
    try:
        cid = event.chat_id
        gm = DB.get("group_memory", {}).get(str(cid), {})
        if not gm:
            return await _safe_reply(event, "📭 No memory yet for this group.")
        lines = [
            "🏠 **Room read**",
            "━━━━━━━━━━━━━━━━━━━━",
            f"🎭 Tone: `{gm.get('tone', '?')}`",
            f"📊 Mode: `{gm.get('mode', '?')}`",
            f"⚡ Activity: `{gm.get('activity_rate', 0)}` msgs/min",
            f"📨 Messages seen: `{gm.get('msg_count', 0)}`",
            f"\n**Top phrases:**",
            ", ".join(gm.get("top_phrases", [])[:15]),
        ]
        if gm.get("topics"):
            lines.append(f"\n**Hot topics:**")
            lines.append(", ".join(gm.get("topics", [])[:10]))
        await _safe_reply(event, "\n".join(lines))
    except Exception as e:
        await send_log(f"❌ room err: `{e}`")


@CipherElite.on(events.NewMessage(pattern=r"\.kce\s+persona(?:\s+list)?$"))
@rishabh()
async def cmd_persona(event):
    if not await _is_owner(event):
        return
    try:
        pp = DB.get("persona_phrases", [])
        if not pp:
            return await _safe_reply(event, "📭 No persona phrases yet. Reply `good` to log cards to build persona.")
        lines = [f"🧬 **Persona Phrases ({len(pp)})**\n"]
        for p in pp[-30:]:
            lines.append(f"• `{p}`")
        await _safe_reply(event, "\n".join(lines))
    except Exception as e:
        await send_log(f"❌ persona err: `{e}`")


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
                "🔥 **AGGRESSIVE MODE ON**\n"
                f"• Trigger: any message ≥{AGGRESSIVE_MIN_WORDS} words\n"
                f"• Delay: `{AGGRESSIVE_SPEED[0]}-{AGGRESSIVE_SPEED[1]}s`\n"
                f"• Hourly cap: `{AGGRESSIVE_HOURLY}`\n"
                f"• Reaction chance: `{int(AGGRESSIVE_REACT_PROB*100)}%`"
            )
        else:
            await _safe_reply(event, "😌 **Aggressive mode OFF**")
    except Exception as e:
        await send_log(f"❌ aggressive err: `{e}`")


@CipherElite.on(events.NewMessage(pattern=r"\.kce\s+summary$"))
@rishabh()
async def cmd_summary(event):
    if not await _is_owner(event):
        return
    try:
        await _safe_reply(event, "⏳ Generating summary...")
        await send_daily_summary()
        await _safe_reply(event, "✅ Sent to log.")
    except Exception as e:
        await send_log(f"❌ summary err: `{e}`")


@CipherElite.on(events.NewMessage(pattern=r"\.kce\s+replies(?:\s+(\d+))?$"))
@rishabh()
async def cmd_replies(event):
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
        await send_log(f"❌ replies err: `{e}`")


@CipherElite.on(events.NewMessage(pattern=r"\.kce\s+reset$"))
@rishabh()
async def cmd_reset(event):
    if not await _is_owner(event):
        return
    try:
        DB["replies"] = []
        DB["replied_users"] = {}
        DB["hourly"] = {}
        DB["daily"] = {"date": today_str(), "count": 0}
        DB["group_memory"] = {}
        DB["persona_phrases"] = []
        save_db(DB)
        await _safe_reply(event, "🔄 Memory + learning cleared.")
    except Exception as e:
        await send_log(f"❌ reset err: `{e}`")


@CipherElite.on(events.NewMessage(pattern=r"\.kce\s+help$"))
@rishabh()
async def cmd_help(event):
    if not await _is_owner(event):
        return
    try:
        msg = (
            "🤖 **KCE AI Reply v3.2 — Commands**\n"
            "━━━━━━━━━━━━━━━━━━━━\n"
            "`.kce` — status\n"
            "`.kce stats` — reply stats\n"
            "`.kce memory` — memory info\n"
            "`.kce room` — current room read\n"
            "`.kce persona list` — learned phrases\n"
            "`.kce summary` — trigger daily summary\n"
            "`.kce replies [n]` — last N\n"
            "`.kce reset` — clear all\n"
            "`.kce speed fast|normal|slow`\n"
            "`.kce aggressive on|off` — 🔥 mode\n"
            "`.kce tz` — timezone\n"
            "\n**Whitelist:**\n"
            "`.kcew` / `.kcew off` / `.kcew list`\n"
            "\n**Wallet:**\n"
            "`.kce wallet set sol|evm|sui <addr>`\n"
            "`.kce wallet list`\n"
            "`.kce wallet on|off <link|id>`\n"
            "\n**DM blacklist:**\n"
            "`.kce dm block|unblock|list`\n"
            "\n**Feedback:**\n"
            "Reply `good` or `bad` to any log card"
        )
        await _safe_reply(event, msg)
    except Exception as e:
        await send_log(f"❌ help err: `{e}`")


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


print("[aireply] MODULE LOADED — chunk 2")

# ═══ END OF BATCH 2 ═══
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
#  DM BLACKLIST (.kce dm)
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
#  WALLET (.kce wallet)
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
            await _safe_reply(event, f"✅ Wallet drop **ON** for `{cid}`")
        else:
            if cid not in groups:
                return await _safe_reply(event, f"ℹ️ Wallet already OFF for `{cid}`")
            groups.remove(cid)
            DB["wallet_groups"] = groups
            save_db(DB)
            await _safe_reply(event, f"⏹️ Wallet drop **OFF** for `{cid}`")
    except Exception as e:
        await send_log(f"❌ wallet flag err: `{e}`")


# ═══════════════════════════════════════════════════════════════
#  GROUP MEMORY LEARNER — every message in whitelisted groups
# ═══════════════════════════════════════════════════════════════

@CipherElite.on(events.NewMessage)
async def group_memory_learner(event):
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
        record_message(event.chat_id, text, event.sender_id)
    except Exception as e:
        print(f"[aireply] memory learner err: {e}")


async def memory_flusher_loop():
    """Every 60s, flush buffered messages into group memory."""
    await asyncio.sleep(30)
    while True:
        try:
            for cid in list(_mem_buffer.keys()):
                try:
                    flush_memory(cid)
                except Exception as e:
                    print(f"[aireply] flush err for {cid}: {e}")
        except Exception as e:
            print(f"[aireply] flusher err: {e}")
        await asyncio.sleep(LEARN_BATCH_SECONDS)


# ═══════════════════════════════════════════════════════════════
#  TYPING WATCHER — slow mode detection
# ═══════════════════════════════════════════════════════════════

_typing_users = {}  # {chat_id: {user_id: last_ts}}


@CipherElite.on(events.Raw(events.UserUpdate))
async def typing_watcher(event):
    try:
        if not is_whitelisted(event.chat_id if hasattr(event, 'chat_id') else None):
            return
        from telethon.tl.types import (
            UpdateUserTyping, UpdateChatUserTyping,
            SendMessageTypingAction,
        )
        chat_id = None
        user_id = None

        if isinstance(event, UpdateUserTyping):
            user_id = event.user_id
            chat_id = user_id  # private
        elif isinstance(event, UpdateChatUserTyping):
            chat_id = event.chat_id
            user_id = event.from_id
        else:
            return

        if not is_whitelisted(chat_id):
            return

        # only count "typing" action
        action = getattr(event, "action", None)
        if not isinstance(action, SendMessageTypingAction):
            return

        users = _typing_users.setdefault(chat_id, {})
        users[user_id] = time.time()

        # purge old (>5s)
        now = time.time()
        users = {u: t for u, t in users.items() if now - t < 5}
        _typing_users[chat_id] = users

        count = len(users)
        if count >= SLOW_MODE_THRESHOLD:
            DB["slow_mode_until"] = now + SLOW_MODE_EXTRA_DELAY
            save_db(DB)
            dbg(f"slow mode ON in {chat_id} ({count} typers)")
        elif count <= SLOW_MODE_RESET:
            # if below threshold, let slow mode expire naturally
            pass
    except Exception as e:
        # silent — typing events are noisy
        pass


# ═══════════════════════════════════════════════════════════════
#  ADMIN ACTIVITY WATCHER
# ═══════════════════════════════════════════════════════════════

@CipherElite.on(events.NewMessage)
async def admin_activity_watcher(event):
    try:
        if event.out:
            return
        if not is_whitelisted(event.chat_id):
            return
        sender = await event.get_sender()
        if not sender:
            return
        # check if sender is admin
        try:
            perms = await CipherElite.get_permissions(event.chat_id, sender.id)
            is_admin = bool(getattr(perms, "is_admin", False) or getattr(perms, "is_creator", False))
        except Exception:
            is_admin = False
        if is_admin:
            al = DB.get("admin_last_seen", {})
            al[str(event.chat_id)] = time.time()
            DB["admin_last_seen"] = al
            save_db(DB)
    except Exception as e:
        pass  # silent


def is_admin_recently_active(chat_id, window=120):
    """True if admin was active in chat within window seconds."""
    al = DB.get("admin_last_seen", {})
    last = al.get(str(chat_id), 0)
    if not last:
        return False
    return (time.time() - last) < window


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
        # extract reply number from card — pattern: "#N" with  •  #N or  #N
        m = re.search(r'#(\d+)\s*$', card_text, re.MULTILINE) or re.search(r'#(\d+)', card_text)
        if not m:
            return
        n = int(m.group(1))

        # update feedback
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
        dbg(f"feedback recorded: #{n} = {text}")

        # if good → add to persona
        if text == "good":
            persona_add(target.get("bot_reply", ""))

        # react to confirm
        try:
            emoji = "👍" if text == "good" else "👎"
            await event.reply(f"{emoji} Logged #{n} as {text}")
        except Exception:
            pass
    except Exception as e:
        print(f"[aireply] feedback err: {e}")


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
        gm = DB.get("group_memory", {})

        lines = [
            "╔══════════════════════════════════════╗",
            f"║  📊  KCE DAILY SUMMARY — {today}",
            "║  ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━",
            "╚══════════════════════════════════════╝",
            "",
            f"💬 Replies today: `{len(today_replies)}`",
            f"👍 Good: `{good}`  👎 Bad: `{bad}`",
            f"📁 Groups learned: `{len(gm)}`",
            f"🧬 Persona phrases: `{len(DB.get('persona_phrases', []))}`",
            "",
        ]

        # top groups
        per_group = {}
        for r in today_replies:
            g = r.get("group_name", "?")
            per_group[g] = per_group.get(g, 0) + 1
        top = sorted(per_group.items(), key=lambda kv: -kv[1])[:3]
        if top:
            lines.append("**Top groups today:**")
            for g, c in top:
                lines.append(f"  • {g[:30]} — `{c}` replies")

        # sample replies
        if today_replies:
            lines.append("")
            lines.append("**Sample replies:**")
            for r in today_replies[-5:]:
                lines.append(f"  • \"{r.get('bot_reply', '')[:40]}\"  →  {r.get('user_name', '')[:20]}")

        card = "\n".join(lines)
        await send_log(card)
        dbg("daily summary sent")
    except Exception as e:
        print(f"[aireply] daily summary err: {e}")


async def daily_summary_loop():
    """Fire once at 23:59 WAT."""
    await asyncio.sleep(20)
    while True:
        try:
            now = wat_now()
            # target 23:59 WAT
            if now.hour == 23 and now.minute == 59:
                # check we haven't fired today
                last = DB.get("last_summary_date", "")
                if last != today_str():
                    DB["last_summary_date"] = today_str()
                    save_db(DB)
                    await send_daily_summary()
                await asyncio.sleep(60)  # wait past minute
            await asyncio.sleep(30)
        except Exception as e:
            print(f"[aireply] summary loop err: {e}")
            await asyncio.sleep(60)


print("[aireply] MODULE LOADED — chunk 3")

# ═══ END OF BATCH 3 ═══
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
        same_user = []
        for m in msgs:
            if m.id == event.message.id:
                continue
            if m.sender_id == sender_id and m.raw_text and not m.raw_text.startswith((".", "..")):
                same_user.append(f"[them]: {m.raw_text[:150]}")
        same_user = same_user[:3]
        ctx.extend(same_user)
    except Exception as e:
        dbg(f"context err: {e}")
    return ctx[-limit:]


async def _fire_online():
    try:
        await CipherElite(functions.account.UpdateStatusRequest(offline=False))
    except Exception as e:
        dbg(f"online ping err: {e}")


# ═══════════════════════════════════════════════════════════════
#  KEYWORD REPLY HANDLER (v3.2 — aggressive + slow mode + room)
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
        # aggressive: any 3+ word message
        if not triggered and is_aggressive() and aggressive_trigger(text):
            triggered, trigger_type = True, "aggressive"

        if not triggered:
            return

        dbg(f"trigger={trigger_type} aggro={is_aggressive()} chat={event.chat_id} text='{text[:50]}'")

        user_id = event.sender_id
        if not can_reply_to_user(user_id):
            dbg("block: user gap")
            return
        if not can_reply_in_group(event.chat_id):
            dbg("block: hourly cap")
            chat = await event.get_chat()
            await queue_item(f"⚠️ Hourly cap in **{getattr(chat, 'title', '?')}**")
            return
        if not can_reply_daily():
            dbg("block: daily cap")
            await queue_item("🚨 **Daily cap reached**", alert=True)
            return

        context = await _get_smart_context(event, me, limit=5)
        reply_text = await generate_reply(text, context, chat_id=event.chat_id)
        if not reply_text:
            chat = await event.get_chat()
            await queue_item(
                f"⚠️ **Gemini failed**\nGroup: `{getattr(chat, 'title', '?')}`\nSaid: \"{text[:100]}\""
            )
            return

        # delay — includes slow mode extra
        base_delay = get_delay()
        slow_extra = get_slow_mode_extra()
        total_delay = base_delay + slow_extra
        dbg(f"delay {base_delay}s + slow {slow_extra}s = {total_delay}s")

        try:
            await _fire_online()
            first_half = max(1, total_delay // 2)
            second_half = max(1, total_delay - first_half)
            async with CipherElite.action(event.chat_id, "typing"):
                await asyncio.sleep(first_half)
            await asyncio.sleep(random.uniform(0.5, 1.5))
            async with CipherElite.action(event.chat_id, "typing"):
                await asyncio.sleep(second_half)
        except Exception as e:
            dbg(f"typing failed: {e}")
            await asyncio.sleep(total_delay)

        try:
            sent = await event.reply(reply_text)
            dbg(f"sent: '{reply_text}'")
        except FloodWaitError as e:
            await asyncio.sleep(e.seconds + 1)
            sent = await event.reply(reply_text)
        except Exception as e:
            print(f"[aireply] send err: {e}")
            await queue_item(f"❌ **Reply failed** in `{event.chat_id}`: `{e}`", alert=True)
            return

        track_reply(event.chat_id, user_id)

        stamp = now_dict()
        chat = await event.get_chat()
        chat_name = getattr(chat, "title", "Unknown")
        user_name = format_user(sender)

        replies = DB.get("replies", [])
        reply_num = len(replies) + 1
        jump_link = build_jump_link(event.chat_id, event.message.id)

        speed_label = "aggressive" if is_aggressive() else CURRENT_SPEED
        if slow_extra:
            speed_label += "+slow"

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
            "speed": speed_label,
            "jump_link": jump_link,
            "feedback": None,
        }
        replies.append(record)
        DB["replies"] = replies[-500:]
        save_db(DB)

        card = build_reply_card(
            reply_num, chat_name, user_name, text, reply_text,
            speed=speed_label, jump_link=jump_link
        )
        await send_log(card)

        # reaction
        react_prob = AGGRESSIVE_REACT_PROB if is_aggressive() else REACT_PROBABILITY
        if REACT_TO_GM and random.random() < react_prob:
            try:
                await sent.react(random.choice(REACTION_EMOJIS))
            except Exception:
                pass

    except FloodWaitError as e:
        print(f"[aireply] FloodWait {e.seconds}s")
        await asyncio.sleep(e.seconds + 1)
    except Exception as e:
        print(f"[aireply] handler err: {e}")


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

        hits = []
        for chain, pat in WALLET_PATTERNS.items():
            if pat.findall(text):
                hits.append(chain)

        if not hits:
            return

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

        try:
            await _fire_online()
            async with CipherElite.action(event.chat_id, "typing"):
                await asyncio.sleep(0.5)
            await event.reply(addr)
        except Exception as e:
            print(f"[aireply] wallet send err: {e}")
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

        card = build_wallet_card(
            reply_num, chat_name, user_name, text, chain, addr, jump_link=jump_link
        )
        await send_log(card)
    except Exception as e:
        print(f"[aireply] wallet watcher err: {e}")


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
            dbg(f"suspicious DM from {sender_id} — blacklisted, skip")
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


async def _plugin_bootstrap():
    try:
        await asyncio.sleep(8)
        global HEARTBEAT_TASK
        if not HEARTBEAT_TASK or HEARTBEAT_TASK.done():
            HEARTBEAT_TASK = asyncio.create_task(_heartbeat_loop())
        # memory flusher
        try:
            asyncio.create_task(memory_flusher_loop())
            dbg("memory flusher started")
        except Exception as e:
            print(f"[aireply] flusher start err: {e}")
        # daily summary
        try:
            asyncio.create_task(daily_summary_loop())
            dbg("daily summary loop started")
        except Exception as e:
            print(f"[aireply] summary start err: {e}")
        dbg("bootstrap complete")
    except Exception as e:
        print(f"[aireply] bootstrap err: {e}")


try:
    asyncio.create_task(_plugin_bootstrap())
except Exception as e:
    print(f"[aireply] bootstrap init err: {e}")


print("[aireply] MODULE LOADED SUCCESSFULLY — v3.2 ready")


# ╔══════════════════════════════════════════════════════════════╗
# ║  === END OF AIRREPLY v3.2 — FULL LEARNING EDITION ===        ║
# ║                                                              ║
# ║  Features:                                                   ║
# ║  • Keyword AI replies (whitelisted groups)                   ║
# ║  • Group message learning (60s batches)                      ║
# ║  • Reading the room (hyped/dead/serious/normal)              ║
# ║  • Persona accumulation from 👍 feedback                     ║
# ║  • Aggressive mode toggle                                    ║
# ║  • Slow mode (typing detection)                              ║
# ║  • Admin activity awareness                                  ║
# ║  • Reply `good`/`bad` to log cards                           ║
# ║  • Daily summary at 23:59 WAT                                ║
# ║  • Wallet drop (SOL/EVM/SUI)                                 ║
# ║  • DM blacklist + suspicious alerts                          ║
# ║  • WAT timezone + beautiful cards                            ║
# ║  • Natural language commands (DM)                            ║
# ╚══════════════════════════════════════════════════════════════╝
