# =============================================================================
#  KCE Quiz Hot-Fix v5.0 — admin-only trigger, self-reporting, Groq chain
# =============================================================================

from telethon import events
from telethon.tl import functions
from utils.utils import CipherElite
from utils.decorators import rishabh
from plugins.bot import add_handler
from plugins.ai_setup import ai_config
import asyncio
import json
import re
import time
import aiohttp
from datetime import datetime, timedelta, timezone
from pathlib import Path
from google import genai
from google.genai import types

print("[quizhot] IMPORTING v5.0")

# ═══════════════════════════════════════════════════════════════
#  TIMEZONE (unique names — no collision)
# ═══════════════════════════════════════════════════════════════

QUIZ_WAT = timezone(timedelta(hours=1))

def quiz_now():
    return datetime.now(QUIZ_WAT)

# ═══════════════════════════════════════════════════════════════
#  CONFIG
# ═══════════════════════════════════════════════════════════════

QUIZ_LOG_ID = -1004374819145
QUIZ_DEBUG = True
QUIZ_GEMINI_MODEL = "gemini-3.5-flash-lite"

QUIZ_ONLINE_PING = False
QUIZ_TYPING_SIM = False
QUIZ_AUTO_REFRESH_HOURS = 6

QUIZ_CORRECT_SIGNALS = ['correct', '✅', 'right', 'yes', 'winner', 'win', 'accurate', '✔']

# Groq fallback chain — auto-picks first working
GROQ_FALLBACK_MODELS = [
    "openai/gpt-oss-20b",
    "openai/gpt-oss-120b",
    "qwen/qwen3.8-27b",
]


def qdbg(msg):
    if QUIZ_DEBUG:
        print(f"[quizhot] {msg}")


# ═══════════════════════════════════════════════════════════════
#  STORAGE
# ═══════════════════════════════════════════════════════════════

QUIZ_ROOT = Path(__file__).parent.parent
QUIZ_DB_DIR = QUIZ_ROOT / "DB"
QUIZ_DB_DIR.mkdir(exist_ok=True)
QUIZ_DB_FILE = QUIZ_DB_DIR / "quizhot.json"
QUIZ_GROQ_FILE = QUIZ_DB_DIR / "groq_config.json"


def quiz_load_db():
    try:
        if QUIZ_DB_FILE.exists():
            return json.loads(QUIZ_DB_FILE.read_text(encoding="utf-8"))
    except Exception as e:
        print(f"[quizhot] load error: {e}")
    return {
        "groups": [],
        "qa_cache": {},
        "sources": {},
        "trusted_mods": {},
    }


def quiz_save_db(data):
    try:
        QUIZ_DB_FILE.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
    except Exception as e:
        print(f"[quizhot] save error: {e}")


QUIZ_DB = quiz_load_db()
QUIZ_LEARN = {}


def quiz_load_groq_key():
    try:
        if QUIZ_GROQ_FILE.exists():
            data = json.loads(QUIZ_GROQ_FILE.read_text(encoding="utf-8"))
            return data.get("key", "").strip()
    except Exception as e:
        print(f"[quizhot] groq config load error: {e}")
    return ""


QUIZ_GROQ_KEY = quiz_load_groq_key()
QUIZ_GROQ_URL = "https://api.groq.com/openai/v1/chat/completions"
QUIZ_GROQ_MODELS_URL = "https://api.groq.com/openai/v1/models"
QUIZ_GROQ_ACTIVE_MODEL = GROQ_FALLBACK_MODELS[0]


# ═══════════════════════════════════════════════════════════════
#  GROUP MGMT
# ═══════════════════════════════════════════════════════════════

def quiz_is_group(chat_id):
    return chat_id in QUIZ_DB.get("groups", [])


def quiz_add_group(chat_id):
    g = QUIZ_DB.get("groups", [])
    if chat_id not in g:
        g.append(chat_id)
        QUIZ_DB["groups"] = g
        quiz_save_db(QUIZ_DB)
        return True
    return False


def quiz_remove_group(chat_id):
    g = QUIZ_DB.get("groups", [])
    if chat_id in g:
        g.remove(chat_id)
        QUIZ_DB["groups"] = g
        quiz_save_db(QUIZ_DB)
        return True
    return False


# ═══════════════════════════════════════════════════════════════
#  ADMIN / MOD CHECK — the fix
# ═══════════════════════════════════════════════════════════════

async def quiz_is_admin_or_mod(chat_id, user_id):
    """Check if user is Telegram admin OR in trusted_mods list."""
    # trusted mods first (includes quiz-master bots)
    tm = QUIZ_DB.get("trusted_mods", {})
    if user_id in tm.get(str(chat_id), []):
        return True
    # telegram admin check
    try:
        perms = await CipherElite.get_permissions(chat_id, user_id)
        return bool(getattr(perms, "is_admin", False) or getattr(perms, "is_creator", False))
    except Exception:
        return False


# ═══════════════════════════════════════════════════════════════
#  SOURCES
# ═══════════════════════════════════════════════════════════════

def quiz_get_sources(chat_id):
    return QUIZ_DB.get("sources", {}).get(str(chat_id), [])


def quiz_set_sources(chat_id, sources):
    s = QUIZ_DB.get("sources", {})
    s[str(chat_id)] = sources
    QUIZ_DB["sources"] = s
    quiz_save_db(QUIZ_DB)


def quiz_add_source(chat_id, stype, value):
    sources = quiz_get_sources(chat_id)
    for s in sources:
        if s.get("type") == stype and s.get("value") == value:
            return False
    sources.append({"type": stype, "value": value, "text": "", "fetched_at": 0})
    quiz_set_sources(chat_id, sources)
    return True


def quiz_remove_source(chat_id, idx):
    sources = quiz_get_sources(chat_id)
    if 0 <= idx < len(sources):
        sources.pop(idx)
        quiz_set_sources(chat_id, sources)
        return True
    return False


def quiz_clear_sources(chat_id):
    quiz_set_sources(chat_id, [])


def quiz_knowledge_block(chat_id):
    sources = quiz_get_sources(chat_id)
    if not sources:
        return ""
    chunks = []
    for s in sources:
        text = s.get("text", "").strip()
        if text:
            chunks.append(text)
        elif s.get("type") == "note":
            chunks.append(s.get("value", ""))
    return "\n\n".join(chunks)[:3000]


async def quiz_fetch_website(url):
    try:
        if not url.startswith("http"):
            url = "https://" + url
        headers = {
            "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
                          "(KHTML, like Gecko) Chrome/120.0 Safari/537.36"
        }
        timeout = aiohttp.ClientTimeout(total=15)
        async with aiohttp.ClientSession(timeout=timeout, headers=headers) as session:
            async with session.get(url) as resp:
                if resp.status != 200:
                    qdbg(f"fetch {url}: HTTP {resp.status}")
                    return None
                html = await resp.text()
        html = re.sub(r'<script[^>]*>.*?</script>', ' ', html, flags=re.DOTALL | re.IGNORECASE)
        html = re.sub(r'<style[^>]*>.*?</style>', ' ', html, flags=re.DOTALL | re.IGNORECASE)
        text = re.sub(r'<[^>]+>', ' ', html)
        text = text.replace('&nbsp;', ' ').replace('&amp;', '&')
        text = text.replace('&lt;', '<').replace('&gt;', '>')
        text = text.replace('&quot;', '"').replace('&#39;', "'")
        text = re.sub(r'\s+', ' ', text).strip()
        return text[:5000]
    except Exception as e:
        qdbg(f"fetch error: {e}")
        return None


async def quiz_refresh_sources(chat_id):
    sources = quiz_get_sources(chat_id)
    updated = 0
    for s in sources:
        if s.get("type") == "web":
            txt = await quiz_fetch_website(s.get("value", ""))
            if txt:
                s["text"] = txt
                s["fetched_at"] = time.time()
                updated += 1
    if updated:
        quiz_set_sources(chat_id, sources)
    return updated


async def quiz_auto_refresh():
    await asyncio.sleep(60)
    while True:
        try:
            for cid_str in list(QUIZ_DB.get("sources", {}).keys()):
                try:
                    cid = int(cid_str)
                    sources = quiz_get_sources(cid)
                    stale = any(
                        s.get("type") == "web" and
                        time.time() - s.get("fetched_at", 0) > QUIZ_AUTO_REFRESH_HOURS * 3600
                        for s in sources
                    )
                    if stale:
                        qdbg(f"auto-refresh {cid}")
                        await quiz_refresh_sources(cid)
                except Exception as e:
                    qdbg(f"auto-refresh {cid_str}: {e}")
        except Exception as e:
            print(f"[quizhot] auto-refresh error: {e}")
        await asyncio.sleep(3600)


# ═══════════════════════════════════════════════════════════════
#  QA CACHE
# ═══════════════════════════════════════════════════════════════

def quiz_norm_q(text):
    t = (text or "").lower().strip()
    t = re.sub(r'[^\w\s]', '', t)
    t = re.sub(r'\s+', ' ', t)
    return t[:200]


def quiz_cache_lookup(question):
    cache = QUIZ_DB.get("qa_cache", {})
    nq = quiz_norm_q(question)
    if not nq:
        return None
    if nq in cache:
        entry = cache[nq]
        entry["hits"] = entry.get("hits", 0) + 1
        quiz_save_db(QUIZ_DB)
        qdbg(f"cache HIT exact: '{entry['answer']}'")
        return entry["answer"]
    nq_words = set(nq.split())
    if len(nq_words) < 3:
        return None
    best, best_score = None, 0
    for k, v in cache.items():
        k_words = set(k.split())
        if not k_words:
            continue
        overlap = len(nq_words & k_words)
        score = overlap / max(len(nq_words), len(k_words))
        if score > best_score and score >= 0.75:
            best_score = score
            best = v
    if best:
        best["hits"] = best.get("hits", 0) + 1
        quiz_save_db(QUIZ_DB)
        qdbg(f"cache HIT fuzzy {best_score:.2f}: '{best['answer']}'")
        return best["answer"]
    return None


def quiz_cache_store(question, answer):
    if not question or not answer:
        return
    nq = quiz_norm_q(question)
    if len(nq) < 5 or len(answer) > 100:
        return
    cache = QUIZ_DB.get("qa_cache", {})
    cache[nq] = {"answer": answer.strip()[:100], "hits": 0, "ts": time.time()}
    if len(cache) > 500:
        items = sorted(cache.items(), key=lambda kv: kv[1].get("ts", 0))
        cache = dict(items[-500:])
    QUIZ_DB["qa_cache"] = cache
    quiz_save_db(QUIZ_DB)
    qdbg(f"cache STORE: '{answer[:50]}'")


# ═══════════════════════════════════════════════════════════════
#  HELPERS
# ═══════════════════════════════════════════════════════════════

async def quiz_safe_reply(event, text):
    try:
        if event.is_private:
            await event.reply(text)
        else:
            await CipherElite.send_message(QUIZ_LOG_ID, text)
    except Exception as e:
        print(f"[quizhot] reply error: {e}")


async def quiz_is_owner(event):
    try:
        me = await CipherElite.get_me()
        return event.sender_id == me.id
    except Exception:
        return False


async def quiz_resolve_id(link):
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
        try:
            entity = await CipherElite.get_entity(link)
            return entity.id
        except Exception:
            return None
    except Exception:
        return None


def quiz_is_question(text):
    if not text:
        return False
    t = text.strip()
    if len(t) < 8:
        return False
    has_q_mark = "?" in t[:200]
    lower = t.lower()
    q_words = (
        "what", "which", "who", "when", "where", "why", "how",
        "name", "pick", "select", "choose", "identify",
        "complete the", "fill in", "guess the"
    )
    starts_q = any(lower.startswith(w) for w in q_words)
    skip_signals = (
        "rules:", "prize:", "winner is", "stay active",
        "leaderboard", "leader board", "round ", "point",
        "congratulations", "good job", "well done", "shoutout",
        "http://", "https://", "t.me/"
    )
    if any(s in lower for s in skip_signals):
        return False
    stripped = re.sub(r'[@#\w]+', '', t)
    if len(stripped) < 5 and not has_q_mark:
        return False
    return has_q_mark or starts_q


# ═══════════════════════════════════════════════════════════════
#  INIT
# ═══════════════════════════════════════════════════════════════

def init(client_instance):
    print("[quizhot] init called")
    commands = [
        ".q on <link|id> - watch group",
        ".q here - watch current group",
        ".q off <link|id> - stop watching",
        ".q list - list watched",
        ".q cache - show cached Q&A",
        ".q clear - reset cache",
        ".q learn \"q\" \"a\" - pre-cache",
        ".q admin on <link> - admin-only mode",
        ".q admin off <link> - anyone can trigger",
        ".kq add web <url> - add website",
        ".kq add note <text> - add fact",
        ".kq add mod <id> - trust a mod",
        ".kq remove mod <id> - untrust",
        ".kq mods - list trusted mods",
        ".kq list - show sources",
        ".kq remove <n> - remove source",
        ".kq clear - wipe sources",
        ".kq fetch - re-scrape",
        ".kq show - preview knowledge",
        ".kq setgroq <key> - save Groq key",
        ".kq groqtest - test Groq",
        ".kq models - list available models",
        ".kq raw - raw Groq response",
        ".kq selftest - full diagnostics",
    ]
    add_handler("quizhot", commands, "🎯 Quiz v5.0 — admin-only")
    print("[quizhot] commands registered")

print("[quizhot] MODULE LOADED — chunk 1 done")

# ═══ END OF CHUNK 1 ═══
# ═══════════════════════════════════════════════════════════════
#  .q COMMANDS
# ═══════════════════════════════════════════════════════════════

@CipherElite.on(events.NewMessage(pattern=r"\.q\s+on\s+(\S+)$"))
@rishabh()
async def cmd_q_on(event):
    if not await quiz_is_owner(event):
        return
    try:
        cid = await quiz_resolve_id(event.pattern_match.group(1))
        if cid is None:
            return await quiz_safe_reply(event, "❌ Could not resolve. Try `.q here`.")
        if quiz_add_group(cid):
            await quiz_safe_reply(event, f"✅ Quiz watch ON for `{cid}`")
        else:
            await quiz_safe_reply(event, f"ℹ️ Already watching `{cid}`")
    except Exception as e:
        await quiz_safe_reply(event, f"❌ error: `{e}`")


@CipherElite.on(events.NewMessage(pattern=r"\.q\s+here$"))
async def cmd_q_here(event):
    if not await quiz_is_owner(event):
        return
    try:
        try: await event.delete()
        except: pass
        chat = await event.get_chat()
        cid = event.chat_id
        name = getattr(chat, "title", "Unknown")
        if quiz_add_group(cid):
            await CipherElite.send_message(QUIZ_LOG_ID, f"✅ Quiz ON for **{name}** (`{cid}`)")
        else:
            await CipherElite.send_message(QUIZ_LOG_ID, f"ℹ️ Already watching **{name}**")
    except Exception as e:
        await CipherElite.send_message(QUIZ_LOG_ID, f"❌ error: `{e}`")


@CipherElite.on(events.NewMessage(pattern=r"\.q\s+off\s+(\S+)$"))
@rishabh()
async def cmd_q_off(event):
    if not await quiz_is_owner(event):
        return
    try:
        cid = await quiz_resolve_id(event.pattern_match.group(1))
        if cid is None:
            return await quiz_safe_reply(event, "❌ Could not resolve.")
        if quiz_remove_group(cid):
            await quiz_safe_reply(event, f"⏹️ Stopped watching `{cid}`")
        else:
            await quiz_safe_reply(event, f"ℹ️ Not watching `{cid}`")
    except Exception as e:
        await quiz_safe_reply(event, f"❌ error: `{e}`")


@CipherElite.on(events.NewMessage(pattern=r"\.q\s+list$"))
@rishabh()
async def cmd_q_list(event):
    if not await quiz_is_owner(event):
        return
    try:
        groups = QUIZ_DB.get("groups", [])
        if not groups:
            return await quiz_safe_reply(event, "📭 No groups watched.")
        lines = [f"🎯 **Watched** ({len(groups)})\n"]
        for cid in groups:
            try:
                e = await CipherElite.get_entity(cid)
                name = getattr(e, "title", str(cid))
            except Exception:
                name = "Unknown"
            admins_only = QUIZ_DB.get("admin_only", {}).get(str(cid), True)
            tag = "🔒 admin-only" if admins_only else "🌐 anyone"
            lines.append(f"• **{name}** (`{cid}`) — {len(quiz_get_sources(cid))} src — {tag}")
        await quiz_safe_reply(event, "\n".join(lines))
    except Exception as e:
        await quiz_safe_reply(event, f"❌ error: `{e}`")


@CipherElite.on(events.NewMessage(pattern=r"\.q\s+cache$"))
@rishabh()
async def cmd_q_cache(event):
    if not await quiz_is_owner(event):
        return
    try:
        cache = QUIZ_DB.get("qa_cache", {})
        top = sorted(cache.items(), key=lambda kv: kv[1].get("hits", 0), reverse=True)[:10]
        lines = [f"💾 **Cache: {len(cache)} entries**\n"]
        for q, v in top:
            lines.append(f"• ({v.get('hits', 0)}×) \"{q[:40]}\" → \"{v.get('answer', '')[:30]}\"")
        await quiz_safe_reply(event, "\n".join(lines))
    except Exception as e:
        await quiz_safe_reply(event, f"❌ error: `{e}`")


@CipherElite.on(events.NewMessage(pattern=r"\.q\s+clear$"))
@rishabh()
async def cmd_q_clear(event):
    if not await quiz_is_owner(event):
        return
    try:
        QUIZ_DB["qa_cache"] = {}
        quiz_save_db(QUIZ_DB)
        QUIZ_LEARN.clear()
        await quiz_safe_reply(event, "🔄 Cache + learning cleared.")
    except Exception as e:
        await quiz_safe_reply(event, f"❌ error: `{e}`")


@CipherElite.on(events.NewMessage(pattern=r'\.q\s+learn\s+"([^"]+)"\s+"([^"]+)"$'))
@rishabh()
async def cmd_q_learn(event):
    if not await quiz_is_owner(event):
        return
    try:
        q = event.pattern_match.group(1).strip()
        a = event.pattern_match.group(2).strip()
        try: await event.delete()
        except: pass
        quiz_cache_store(q, a)
        await quiz_safe_reply(event, f"✅ Pre-cached: Q=\"{q[:50]}\" A=\"{a}\"")
    except Exception as e:
        await quiz_safe_reply(event, f"❌ error: `{e}`")


@CipherElite.on(events.NewMessage(pattern=r"\.q\s+admin\s+(on|off)\s+(\S+)$"))
@rishabh()
async def cmd_q_admin(event):
    if not await quiz_is_owner(event):
        return
    try:
        mode = event.pattern_match.group(1).lower()
        cid = await quiz_resolve_id(event.pattern_match.group(2))
        if cid is None:
            return await quiz_safe_reply(event, "❌ Could not resolve.")
        ao = QUIZ_DB.get("admin_only", {})
        ao[str(cid)] = (mode == "on")
        QUIZ_DB["admin_only"] = ao
        quiz_save_db(QUIZ_DB)
        state = "🔒 admin-only" if mode == "on" else "🌐 anyone can trigger"
        await quiz_safe_reply(event, f"✅ `{cid}` → {state}")
    except Exception as e:
        await quiz_safe_reply(event, f"❌ error: `{e}`")


# ═══════════════════════════════════════════════════════════════
#  .kq COMMANDS
# ═══════════════════════════════════════════════════════════════

@CipherElite.on(events.NewMessage(pattern=r"\.kq\s+setgroq\s+(\S+)$"))
@rishabh()
async def cmd_kq_setgroq(event):
    if not await quiz_is_owner(event):
        return
    try:
        global QUIZ_GROQ_KEY
        key = event.pattern_match.group(1).strip()
        if not key.startswith("gsk_"):
            return await quiz_safe_reply(event, "❌ Groq key should start with `gsk_`")
        if len(key) < 40:
            return await quiz_safe_reply(event, f"❌ Key too short ({len(key)} chars)")
        try: await event.delete()
        except: pass
        QUIZ_GROQ_FILE.write_text(
            json.dumps({"key": key, "saved_at": quiz_now().strftime("%Y-%m-%d %H:%M:%S")}, indent=2),
            encoding="utf-8"
        )
        QUIZ_GROQ_KEY = key
        await quiz_safe_reply(event, f"✅ Groq key saved ({len(key)} chars)")
    except Exception as e:
        await quiz_safe_reply(event, f"❌ error: `{e}`")


@CipherElite.on(events.NewMessage(pattern=r"\.kq\s+groqtest$"))
@rishabh()
async def cmd_kq_groqtest(event):
    if not await quiz_is_owner(event):
        return
    try:
        if not QUIZ_GROQ_KEY:
            return await quiz_safe_reply(event, "❌ No Groq key set.")
        await quiz_safe_reply(event, "⏳ Testing Groq...")
        t0 = time.time()
        ans = await quiz_groq_answer("What is 2+2?")
        elapsed = int((time.time() - t0) * 1000)
        if ans:
            await quiz_safe_reply(event, f"✅ Groq OK — {elapsed}ms\nModel: `{QUIZ_GROQ_ACTIVE_MODEL}`\nAnswer: \"{ans}\"")
        else:
            await quiz_safe_reply(event, f"❌ Groq failed ({elapsed}ms). Run `.kq raw` for details.")
    except Exception as e:
        await quiz_safe_reply(event, f"❌ error: `{e}`")


@CipherElite.on(events.NewMessage(pattern=r"\.kq\s+models$"))
@rishabh()
async def cmd_kq_models(event):
    if not await quiz_is_owner(event):
        return
    try:
        if not QUIZ_GROQ_KEY:
            return await quiz_safe_reply(event, "❌ No Groq key")
        async with aiohttp.ClientSession() as session:
            async with session.get(
                QUIZ_GROQ_MODELS_URL,
                headers={"Authorization": f"Bearer {QUIZ_GROQ_KEY}"}
            ) as resp:
                if resp.status != 200:
                    return await quiz_safe_reply(event, f"❌ HTTP {resp.status}")
                data = await resp.json()
        ids = [m["id"] for m in data.get("data", [])]
        await quiz_safe_reply(event, f"**Models ({len(ids)}):**\n" + "\n".join(f"`{i}`" for i in ids))
    except Exception as e:
        await quiz_safe_reply(event, f"❌ error: `{e}`")


@CipherElite.on(events.NewMessage(pattern=r"\.kq\s+raw$"))
@rishabh()
async def cmd_kq_raw(event):
    if not await quiz_is_owner(event):
        return
    try:
        if not QUIZ_GROQ_KEY:
            return await quiz_safe_reply(event, "❌ no key")
        await quiz_safe_reply(event, f"**Model:** `{QUIZ_GROQ_ACTIVE_MODEL}`\n**Key:** `{QUIZ_GROQ_KEY[:10]}...{QUIZ_GROQ_KEY[-4:]}`\n\nSending...")
        payload = {
            "model": QUIZ_GROQ_ACTIVE_MODEL,
            "messages": [{"role": "user", "content": "reply with the word OK"}],
            "max_tokens": 10,
        }
        headers = {
            "Authorization": f"Bearer {QUIZ_GROQ_KEY}",
            "Content-Type": "application/json",
        }
        timeout = aiohttp.ClientTimeout(total=15)
        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.post(QUIZ_GROQ_URL, json=payload, headers=headers) as resp:
                status = resp.status
                body = await resp.text()
        await quiz_safe_reply(event, f"**Status:** `{status}`\n\n**Body:**\n{body[:1500]}")
    except Exception as e:
        await quiz_safe_reply(event, f"❌ exception: `{e}`")


@CipherElite.on(events.NewMessage(pattern=r"\.kq\s+selftest$"))
@rishabh()
async def cmd_kq_selftest(event):
    if not await quiz_is_owner(event):
        return
    try:
        lines = ["🧪 **SELF TEST**", "━━━━━━━━━━━━━━━━━━━━"]
        lines.append(f"✅ Plugin loaded")
        lines.append(f"{'✅' if QUIZ_GROQ_KEY else '❌'} Groq key: {'set ('+str(len(QUIZ_GROQ_KEY))+' chars)' if QUIZ_GROQ_KEY else 'empty'}")
        lines.append(f"⚙️ Active model: `{QUIZ_GROQ_ACTIVE_MODEL}`")
        lines.append(f"📝 Groups: `{len(QUIZ_DB.get('groups', []))}`")
        lines.append(f"💾 Cache: `{len(QUIZ_DB.get('qa_cache', {}))}`")
        lines.append(f"📚 Sources: `{sum(len(v) for v in QUIZ_DB.get('sources', {}).values())}`")
        if QUIZ_GROQ_KEY:
            t0 = time.time()
            ans = await quiz_groq_answer("test")
            elapsed = int((time.time() - t0) * 1000)
            if ans:
                lines.append(f"✅ Groq test: {elapsed}ms → \"{ans}\"")
            else:
                lines.append(f"❌ Groq test: FAILED ({elapsed}ms)")
        await quiz_safe_reply(event, "\n".join(lines))
    except Exception as e:
        await quiz_safe_reply(event, f"❌ error: `{e}`")


@CipherElite.on(events.NewMessage(pattern=r"\.kq\s+add\s+(web|note)\s+(.+)$"))
async def cmd_kq_add(event):
    if not await quiz_is_owner(event):
        return
    try:
        stype = event.pattern_match.group(1).lower()
        value = event.pattern_match.group(2).strip()
        try: await event.delete()
        except: pass
        chat = await event.get_chat()
        cid = event.chat_id
        name = getattr(chat, "title", "Unknown")

        if not quiz_add_source(cid, stype, value):
            await CipherElite.send_message(QUIZ_LOG_ID, "ℹ️ Source already exists")
            return

        msg = f"✅ **{stype}** added to **{name}**"
        if stype == "web":
            txt = await quiz_fetch_website(value)
            if txt:
                sources = quiz_get_sources(cid)
                for s in sources:
                    if s.get("type") == "web" and s.get("value") == value:
                        s["text"] = txt
                        s["fetched_at"] = time.time()
                        break
                quiz_set_sources(cid, sources)
                msg += f"\n📄 Fetched {len(txt)} chars"
            else:
                msg += "\n⚠️ Fetch failed — try `.kq fetch`"
        elif stype == "note":
            sources = quiz_get_sources(cid)
            for s in sources:
                if s.get("type") == "note" and s.get("value") == value:
                    s["text"] = value
                    break
            quiz_set_sources(cid, sources)
            msg += f"\n📝 Note saved"

        await CipherElite.send_message(QUIZ_LOG_ID, msg)
    except Exception as e:
        await CipherElite.send_message(QUIZ_LOG_ID, f"❌ kq add error: `{e}`")


@CipherElite.on(events.NewMessage(pattern=r"\.kq\s+add\s+mod\s+(\S+)$"))
@rishabh()
async def cmd_kq_add_mod(event):
    if not await quiz_is_owner(event):
        return
    try:
        uid_str = event.pattern_match.group(1).strip().lstrip("@")
        try:
            uid = int(uid_str)
        except ValueError:
            try:
                entity = await CipherElite.get_entity(uid_str)
                uid = entity.id
            except Exception:
                return await quiz_safe_reply(event, f"❌ Could not resolve `{uid_str}`")
        # add to all quiz groups
        tm = QUIZ_DB.get("trusted_mods", {})
        added = 0
        for cid in QUIZ_DB.get("groups", []):
            lst = tm.get(str(cid), [])
            if uid not in lst:
                lst.append(uid)
                tm[str(cid)] = lst
                added += 1
        QUIZ_DB["trusted_mods"] = tm
        quiz_save_db(QUIZ_DB)
        await quiz_safe_reply(event, f"✅ Added mod `{uid}` to {added} group(s)")
    except Exception as e:
        await quiz_safe_reply(event, f"❌ error: `{e}`")


@CipherElite.on(events.NewMessage(pattern=r"\.kq\s+remove\s+mod\s+(\S+)$"))
@rishabh()
async def cmd_kq_remove_mod(event):
    if not await quiz_is_owner(event):
        return
    try:
        uid_str = event.pattern_match.group(1).strip().lstrip("@")
        try:
            uid = int(uid_str)
        except ValueError:
            try:
                entity = await CipherElite.get_entity(uid_str)
                uid = entity.id
            except Exception:
                return await quiz_safe_reply(event, f"❌ Could not resolve `{uid_str}`")
        tm = QUIZ_DB.get("trusted_mods", {})
        removed = 0
        for cid in list(tm.keys()):
            if uid in tm[cid]:
                tm[cid].remove(uid)
                removed += 1
        QUIZ_DB["trusted_mods"] = tm
        quiz_save_db(QUIZ_DB)
        await quiz_safe_reply(event, f"🗑️ Removed mod `{uid}` from {removed} group(s)")
    except Exception as e:
        await quiz_safe_reply(event, f"❌ error: `{e}`")


@CipherElite.on(events.NewMessage(pattern=r"\.kq\s+mods$"))
@rishabh()
async def cmd_kq_mods(event):
    if not await quiz_is_owner(event):
        return
    try:
        tm = QUIZ_DB.get("trusted_mods", {})
        if not tm:
            return await quiz_safe_reply(event, "📭 No trusted mods.")
        lines = ["👑 **Trusted Mods**\n"]
        for cid, uids in tm.items():
            if uids:
                lines.append(f"**Group `{cid}`:**")
                for uid in uids:
                    try:
                        e = await CipherElite.get_entity(uid)
                        name = getattr(e, "first_name", "") or getattr(e, "username", "") or "?"
                    except Exception:
                        name = "?"
                    lines.append(f"  • {name} (`{uid}`)")
        await quiz_safe_reply(event, "\n".join(lines))
    except Exception as e:
        await quiz_safe_reply(event, f"❌ error: `{e}`")


@CipherElite.on(events.NewMessage(pattern=r"\.kq\s+list$"))
@rishabh()
async def cmd_kq_list(event):
    if not await quiz_is_owner(event):
        return
    try:
        cid = event.chat_id
        sources = quiz_get_sources(cid)
        if not sources:
            return await quiz_safe_reply(event, "📭 No sources.")
        lines = [f"📚 **Sources** ({len(sources)})\n"]
        for i, s in enumerate(sources):
            lines.append(f"`{i}` **{s['type']}**: {s.get('value', '')[:60]} — {len(s.get('text', ''))} chars")
        await quiz_safe_reply(event, "\n".join(lines))
    except Exception as e:
        await quiz_safe_reply(event, f"❌ error: `{e}`")


@CipherElite.on(events.NewMessage(pattern=r"\.kq\s+remove\s+(\d+)$"))
@rishabh()
async def cmd_kq_remove(event):
    if not await quiz_is_owner(event):
        return
    try:
        idx = int(event.pattern_match.group(1))
        if quiz_remove_source(event.chat_id, idx):
            await quiz_safe_reply(event, f"🗑️ Removed source `{idx}`")
        else:
            await quiz_safe_reply(event, f"❌ Invalid index `{idx}`")
    except Exception as e:
        await quiz_safe_reply(event, f"❌ error: `{e}`")


@CipherElite.on(events.NewMessage(pattern=r"\.kq\s+clear$"))
@rishabh()
async def cmd_kq_clear(event):
    if not await quiz_is_owner(event):
        return
    try:
        quiz_clear_sources(event.chat_id)
        await quiz_safe_reply(event, "🔄 Sources cleared.")
    except Exception as e:
        await quiz_safe_reply(event, f"❌ error: `{e}`")


@CipherElite.on(events.NewMessage(pattern=r"\.kq\s+fetch$"))
@rishabh()
async def cmd_kq_fetch(event):
    if not await quiz_is_owner(event):
        return
    try:
        await quiz_safe_reply(event, "⏳ Fetching...")
        n = await quiz_refresh_sources(event.chat_id)
        await quiz_safe_reply(event, f"✅ Refreshed {n} web source(s)")
    except Exception as e:
        await quiz_safe_reply(event, f"❌ error: `{e}`")


@CipherElite.on(events.NewMessage(pattern=r"\.kq\s+show$"))
@rishabh()
async def cmd_kq_show(event):
    if not await quiz_is_owner(event):
        return
    try:
        block = quiz_knowledge_block(event.chat_id)
        if not block:
            return await quiz_safe_reply(event, "📭 No knowledge yet.")
        await quiz_safe_reply(event, f"📚 **Knowledge** ({len(block)} chars)\n\n{block[:1500]}")
    except Exception as e:
        await quiz_safe_reply(event, f"❌ error: `{e}`")

print("[quizhot] MODULE LOADED — chunk 2 done")

# ═══ END OF CHUNK 2 ═══
# ═══════════════════════════════════════════════════════════════
#  GROQ — with auto-model-detection + error reporting
# ═══════════════════════════════════════════════════════════════

async def quiz_groq_answer(question, cid=None):
    """Groq call with auto-fallback across models."""
    if not QUIZ_GROQ_KEY:
        return None

    global QUIZ_GROQ_ACTIVE_MODEL

    knowledge = quiz_knowledge_block(cid) if cid else ""
    knowledge_section = f"Known facts:\n{knowledge[:1500]}\n" if knowledge else ""

    prompt = f"""{knowledge_section}Answer this quiz question in 1-3 words, lowercase, no punctuation, no emoji, no explanation:
{question[:250]}
Answer:"""

    headers = {
        "Authorization": f"Bearer {QUIZ_GROQ_KEY}",
        "Content-Type": "application/json",
    }
    payload_base = {
        "messages": [
            {"role": "system", "content": "Answer quiz questions with 1-3 word answers only."},
            {"role": "user", "content": prompt},
        ],
        "temperature": 0.1,
        "max_tokens": 15,
    }

    models_to_try = [QUIZ_GROQ_ACTIVE_MODEL] + [m for m in GROQ_FALLBACK_MODELS if m != QUIZ_GROQ_ACTIVE_MODEL]

    for model in models_to_try:
        payload = dict(payload_base)
        payload["model"] = model
        try:
            timeout = aiohttp.ClientTimeout(total=8)
            async with aiohttp.ClientSession(timeout=timeout) as session:
                async with session.post(QUIZ_GROQ_URL, json=payload, headers=headers) as resp:
                    status = resp.status
                    body_text = await resp.text()
                    if status != 200:
                        qdbg(f"groq {model} HTTP {status}: {body_text[:300]}")
                        # if 404 (model gone), try next
                        if status == 404:
                            continue
                        # 401, 429 etc — don't retry, report
                        await quiz_report_error(f"Groq `{model}` HTTP {status}", body_text[:400])
                        return None
                    data = json.loads(body_text)
            text = data.get("choices", [{}])[0].get("message", {}).get("content", "").strip()
            text = text.replace("\n", " ").replace("*", "").replace("_", "").strip('"').strip("'")
            text = re.sub(r'^(answer|ans|reply|the answer is)[:\s]*', '', text, flags=re.IGNORECASE)
            text = text.strip(".,!?;:")
            if len(text) < 1 or len(text) > 60:
                qdbg(f"groq {model}: bad length '{text}'")
                continue
            QUIZ_GROQ_ACTIVE_MODEL = model
            qdbg(f"groq {model}: '{text}'")
            return text
        except Exception as e:
            qdbg(f"groq {model} exception: {type(e).__name__}: {e}")
            continue

    return None


async def quiz_report_error(title, detail=""):
    """Send error report to log group."""
    try:
        msg = f"🚨 **QUIZ ERROR**\n{title}"
        if detail:
            msg += f"\n\n`{detail[:600]}`"
        await CipherElite.send_message(QUIZ_LOG_ID, msg)
    except Exception:
        pass


# ═══════════════════════════════════════════════════════════════
#  GEMINI FALLBACK
# ═══════════════════════════════════════════════════════════════

QUIZ_GEMINI_CLIENT = None


def quiz_get_gemini_client():
    global QUIZ_GEMINI_CLIENT
    if QUIZ_GEMINI_CLIENT is None:
        api_key = ai_config.get_api_key()
        if not api_key:
            return None
        QUIZ_GEMINI_CLIENT = genai.Client(api_key=api_key)
    return QUIZ_GEMINI_CLIENT


async def quiz_gemini_answer(question, cid=None):
    if not ai_config.is_enabled():
        return None
    client = quiz_get_gemini_client()
    if client is None:
        return None

    knowledge = quiz_knowledge_block(cid) if cid else ""
    knowledge_section = f"\nKnown facts:\n{knowledge[:2000]}\n" if knowledge else ""

    prompt = f"""{knowledge_section}Answer this quiz question in 1-3 words, lowercase, no punctuation, no emoji:
{question[:250]}
Answer:"""

    try:
        config = types.GenerateContentConfig(
            max_output_tokens=15,
            temperature=0.1,
            top_p=0.9,
        )
        resp = await client.aio.models.generate_content(
            model=QUIZ_GEMINI_MODEL,
            contents=[types.Content(role="user", parts=[types.Part(text=prompt)])],
            config=config,
        )
        text = (resp.text or "").strip()
        text = text.replace("\n", " ").replace("*", "").replace("_", "").strip('"').strip("'")
        text = re.sub(r'^(answer|ans|reply|the answer is)[:\s]*', '', text, flags=re.IGNORECASE)
        text = text.strip(".,!?;:")
        if len(text) < 1 or len(text) > 60:
            return None
        qdbg(f"gemini: '{text}'")
        return text
    except Exception as e:
        print(f"[quizhot] gemini error: {e}")
        return None


async def quiz_get_answer(question, cid=None):
    """Groq first, then Gemini."""
    if QUIZ_GROQ_KEY:
        ans = await quiz_groq_answer(question, cid)
        if ans:
            return ans
        qdbg("groq failed → gemini")
    return await quiz_gemini_answer(question, cid)


# ═══════════════════════════════════════════════════════════════
#  MAIN WATCHER
# ═══════════════════════════════════════════════════════════════

@CipherElite.on(events.NewMessage)
async def quiz_watcher(event):
    try:
        if event.out:
            return
        if not quiz_is_group(event.chat_id):
            return
        text = event.raw_text or ""
        if not text or text.startswith((".", "..")):
            return

        me = await CipherElite.get_me()
        sender = await event.get_sender()
        if sender and sender.id == me.id:
            return

        chat_id = event.chat_id
        state = QUIZ_LEARN.setdefault(chat_id, {
            "last_question_id": None,
            "last_question_text": None,
            "last_answer_ts": 0,
        })

        if state.get("last_question_id") == event.message.id:
            return

        lower = text.lower()

        # ── LEARNING: admin says "correct"
        if event.is_reply:
            try:
                replied = await event.get_reply_message()
            except Exception:
                replied = None
            if replied and replied.raw_text:
                has_signal = any(sig in lower for sig in QUIZ_CORRECT_SIGNALS)
                if has_signal:
                    is_mod = await quiz_is_admin_or_mod(chat_id, event.sender_id)
                    if is_mod:
                        correct = replied.raw_text.strip()[:100]
                        last_q = state.get("last_question_text")
                        if last_q:
                            quiz_cache_store(last_q, correct)
                        qdbg(f"learned: '{correct}'")
                        return

        # ── BUTTON QUIZ
        if event.buttons:
            flat = [b for row in event.buttons for b in row]
            if 2 <= len(flat) <= 8:
                is_mod = await quiz_is_admin_or_mod(chat_id, event.sender_id)
                admin_only = QUIZ_DB.get("admin_only", {}).get(str(chat_id), True)
                if admin_only and not is_mod:
                    return
                if not quiz_is_question(text) and len(text) < 10:
                    return
                qdbg(f"button quiz: {len(flat)} opts")
                state["last_question_id"] = event.message.id
                state["last_question_text"] = text[:200]
                state["last_answer_ts"] = quiz_now().timestamp()
                QUIZ_LEARN[chat_id] = state

                cached = quiz_cache_lookup(text)
                target_row, target_col = None, None
                if cached:
                    for r_idx, row in enumerate(event.buttons):
                        for c_idx, btn in enumerate(row):
                            btext = (getattr(btn, "text", "") or "").strip().lower()
                            if cached.lower() in btext or btext in cached.lower():
                                target_row, target_col = r_idx, c_idx
                                break
                        if target_row is not None:
                            break
                if target_row is None:
                    target_row, target_col = 0, 0
                try:
                    await event.click(target_row, target_col)
                    qdbg(f"CLICKED ({target_row},{target_col})")
                except Exception as e:
                    qdbg(f"click error: {e}")
                return

        # ── TEXT QUIZ — admin-only check is HERE
        if not quiz_is_question(text):
            return

        # check admin-only mode
        admin_only = QUIZ_DB.get("admin_only", {}).get(str(chat_id), True)
        if admin_only:
            is_mod = await quiz_is_admin_or_mod(chat_id, event.sender_id)
            if not is_mod:
                qdbg(f"skip — {event.sender_id} not admin/mod")
                return

        qdbg(f"question from {'mod' if admin_only else 'anyone'}: '{text[:80]}'")
        state["last_question_id"] = event.message.id
        state["last_question_text"] = text[:200]
        state["last_answer_ts"] = quiz_now().timestamp()
        QUIZ_LEARN[chat_id] = state

        # cache first
        cached = quiz_cache_lookup(text)
        if cached:
            qdbg(f"FAST cache: '{cached}'")
            try:
                await event.reply(cached)
                qdbg(f"REPLIED (cache): '{cached}'")
            except Exception as e:
                print(f"[quizhot] send err: {e}")
            return

        # Groq → Gemini
        t0 = time.time()
        answer = await quiz_get_answer(text, chat_id)
        elapsed = int((time.time() - t0) * 1000)
        if not answer:
            qdbg(f"no answer ({elapsed}ms)")
            return

        try:
            await event.reply(answer)
            qdbg(f"REPLIED ({elapsed}ms): '{answer}'")
        except Exception as e:
            print(f"[quizhot] send err: {e}")
            return

        quiz_cache_store(text, answer)

        try:
            await CipherElite.send_message(
                QUIZ_LOG_ID,
                f"🎯 **QUIZ ANSWERED** ({elapsed}ms)\n📍 `{chat_id}`\n❓ \"{text[:150]}\"\n🤖 \"{answer}\"\n⚙️ model: `{QUIZ_GROQ_ACTIVE_MODEL}`\n🕐 {quiz_now().strftime('%I:%M:%S %p')} WAT"
            )
        except Exception:
            pass

    except Exception as e:
        print(f"[quizhot] watcher error: {e}")
        await quiz_report_error("Watcher exception", f"{type(e).__name__}: {e}")


# ═══════════════════════════════════════════════════════════════
#  BOOTSTRAP — self-report + auto-refresh
# ═══════════════════════════════════════════════════════════════

async def quiz_startup_selftest():
    await asyncio.sleep(15)
    try:
        lines = ["🚀 **QUIZHOT v5.0 STARTUP**", "━━━━━━━━━━━━━━━━━━━━"]
        lines.append(f"✅ Plugin loaded")
        lines.append(f"{'✅' if QUIZ_GROQ_KEY else '❌'} Groq key: {'set ('+str(len(QUIZ_GROQ_KEY))+' chars)' if QUIZ_GROQ_KEY else 'empty'}")
        lines.append(f"⚙️ Model: `{QUIZ_GROQ_ACTIVE_MODEL}`")
        lines.append(f"📝 Groups: `{len(QUIZ_DB.get('groups', []))}`")
        lines.append(f"💾 Cache: `{len(QUIZ_DB.get('qa_cache', {}))}`")

        if QUIZ_GROQ_KEY:
            t0 = time.time()
            ans = await quiz_groq_answer("test")
            elapsed = int((time.time() - t0) * 1000)
            if ans:
                lines.append(f"✅ Groq live test: **{elapsed}ms** → \"{ans}\"")
            else:
                lines.append(f"❌ Groq live test FAILED ({elapsed}ms) — check `.kq raw`")
        else:
            lines.append("⚠️ Run `.kq setgroq <key>` to enable Groq")

        await CipherElite.send_message(QUIZ_LOG_ID, "\n".join(lines))
        print("[quizhot] startup self-report sent")
    except Exception as e:
        print(f"[quizhot] startup selftest error: {e}")


async def quiz_plugin_bootstrap():
    try:
        await asyncio.sleep(10)
        asyncio.create_task(quiz_auto_refresh())
        asyncio.create_task(quiz_startup_selftest())
        print("[quizhot] bootstrap complete")
    except Exception as e:
        print(f"[quizhot] bootstrap error: {e}")


try:
    asyncio.create_task(quiz_plugin_bootstrap())
except Exception as e:
    print(f"[quizhot] bootstrap init error: {e}")

print("[quizhot] MODULE LOADED SUCCESSFULLY — v5.0 ready")


# ╔══════════════════════════════════════════════════════════════╗
# ║  === END OF QUIZHOT v5.0 ===                                 ║
# ║                                                              ║
# ║  • Admin-only trigger (fix)                                  ║
# ║  • Groq auto-fallback chain                                  ║
# ║  • Startup self-report                                       ║
# ║  • Error auto-report to log                                  ║
# ║  • Unique variable names (no collision)                      ║
# ║  • Cache → Groq → Gemini                                     ║
# ║  • Web sources + notes                                       ║
# ║  • Trusted mods                                              ║
# ╚══════════════════════════════════════════════════════════════╝
