# =============================================================================
#  KCE Quiz Hot-Fix v4.0 — GROQ + cache + sources + MAD SPEED
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

WAT = timezone(timedelta(hours=1))

def wat_now():
    return datetime.now(WAT)

# ═══════════════════════════════════════════════════════════════
#  CONFIG
# ═══════════════════════════════════════════════════════════════

AI_LOG_CHAT_ID = -1004374819145
DEBUG = True
QUIZ_MODEL = "gemini-3.5-flash-lite"

ENABLE_ONLINE_PING = False
ENABLE_TYPING_SIM = False
ENABLE_ANSWER_COOLDOWN = False
COOLDOWN_SEC = 1
AUTO_REFRESH_HOURS = 6

CORRECT_SIGNALS = ['correct', '✅', 'right', 'yes', 'winner', 'win', 'accurate', '✔']


def dbg(msg):
    if DEBUG:
        print(f"[quizhot] {msg}")


# ═══════════════════════════════════════════════════════════════
#  STORAGE
# ═══════════════════════════════════════════════════════════════

PROJECT_ROOT = Path(__file__).parent.parent
DB_DIR = PROJECT_ROOT / "DB"
DB_DIR.mkdir(exist_ok=True)
DB_FILE = DB_DIR / "quizhot.json"
GROQ_CONFIG_FILE = DB_DIR / "groq_config.json"


def load_db():
    try:
        if DB_FILE.exists():
            return json.loads(DB_FILE.read_text(encoding="utf-8"))
    except Exception as e:
        print(f"[quizhot] load error: {e}")
    return {
        "groups": [],
        "history": [],
        "qa_cache": {},
        "sources": {},
    }


def save_db(data):
    try:
        DB_FILE.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
    except Exception as e:
        print(f"[quizhot] save error: {e}")


DB = load_db()
LEARN = {}


def _load_groq_key():
    try:
        if GROQ_CONFIG_FILE.exists():
            data = json.loads(GROQ_CONFIG_FILE.read_text(encoding="utf-8"))
            return data.get("key", "").strip()
    except Exception as e:
        print(f"[quizhot] groq config load error: {e}")
    return ""


GROQ_API_KEY = _load_groq_key()
GROQ_URL = "https://api.groq.com/openai/v1/chat/completions"
GROQ_MODEL = "openai/gpt-oss-20b"


# ═══════════════════════════════════════════════════════════════
#  GROUP MGMT
# ═══════════════════════════════════════════════════════════════

def is_quiz_group(chat_id):
    return chat_id in DB.get("groups", [])


def add_group(chat_id):
    g = DB.get("groups", [])
    if chat_id not in g:
        g.append(chat_id)
        DB["groups"] = g
        save_db(DB)
        return True
    return False


def remove_group(chat_id):
    g = DB.get("groups", [])
    if chat_id in g:
        g.remove(chat_id)
        DB["groups"] = g
        save_db(DB)
        return True
    return False


# ═══════════════════════════════════════════════════════════════
#  SOURCES
# ═══════════════════════════════════════════════════════════════

def get_sources(chat_id):
    return DB.get("sources", {}).get(str(chat_id), [])


def set_sources(chat_id, sources):
    s = DB.get("sources", {})
    s[str(chat_id)] = sources
    DB["sources"] = s
    save_db(DB)


def add_source(chat_id, stype, value):
    sources = get_sources(chat_id)
    for s in sources:
        if s.get("type") == stype and s.get("value") == value:
            return False
    sources.append({
        "type": stype,
        "value": value,
        "text": "",
        "fetched_at": 0,
    })
    set_sources(chat_id, sources)
    return True


def remove_source(chat_id, idx):
    sources = get_sources(chat_id)
    if 0 <= idx < len(sources):
        sources.pop(idx)
        set_sources(chat_id, sources)
        return True
    return False


def clear_sources(chat_id):
    set_sources(chat_id, [])


def build_knowledge_block(chat_id):
    sources = get_sources(chat_id)
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


async def fetch_website(url):
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
                    dbg(f"fetch {url}: HTTP {resp.status}")
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
        dbg(f"fetch error: {e}")
        return None


async def refresh_all_sources(chat_id):
    sources = get_sources(chat_id)
    updated = 0
    for s in sources:
        if s.get("type") == "web":
            txt = await fetch_website(s.get("value", ""))
            if txt:
                s["text"] = txt
                s["fetched_at"] = time.time()
                updated += 1
    if updated:
        set_sources(chat_id, sources)
    return updated


async def auto_refresh_loop():
    await asyncio.sleep(60)
    while True:
        try:
            for cid_str in list(DB.get("sources", {}).keys()):
                try:
                    cid = int(cid_str)
                    sources = get_sources(cid)
                    stale = any(
                        s.get("type") == "web" and
                        time.time() - s.get("fetched_at", 0) > AUTO_REFRESH_HOURS * 3600
                        for s in sources
                    )
                    if stale:
                        dbg(f"auto-refresh for {cid}")
                        await refresh_all_sources(cid)
                except Exception as e:
                    dbg(f"auto-refresh {cid_str} error: {e}")
        except Exception as e:
            print(f"[quizhot] auto-refresh loop error: {e}")
        await asyncio.sleep(3600)


# ═══════════════════════════════════════════════════════════════
#  QA CACHE
# ═══════════════════════════════════════════════════════════════

def normalize_q(text):
    t = (text or "").lower().strip()
    t = re.sub(r'[^\w\s]', '', t)
    t = re.sub(r'\s+', ' ', t)
    return t[:200]


def cache_lookup(question):
    cache = DB.get("qa_cache", {})
    nq = normalize_q(question)
    if not nq:
        return None
    if nq in cache:
        entry = cache[nq]
        entry["hits"] = entry.get("hits", 0) + 1
        save_db(DB)
        dbg(f"cache HIT (exact): '{entry['answer']}'")
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
        save_db(DB)
        dbg(f"cache HIT (fuzzy {best_score:.2f}): '{best['answer']}'")
        return best["answer"]
    return None


def cache_store(question, answer):
    if not question or not answer:
        return
    nq = normalize_q(question)
    if len(nq) < 5 or len(answer) > 100:
        return
    cache = DB.get("qa_cache", {})
    cache[nq] = {"answer": answer.strip()[:100], "hits": 0, "ts": time.time()}
    if len(cache) > 500:
        items = sorted(cache.items(), key=lambda kv: kv[1].get("ts", 0))
        cache = dict(items[-500:])
    DB["qa_cache"] = cache
    save_db(DB)
    dbg(f"cache STORE: '{answer[:50]}'")


# ═══════════════════════════════════════════════════════════════
#  HELPERS
# ═══════════════════════════════════════════════════════════════

async def _safe_reply(event, text):
    try:
        if event.is_private:
            await event.reply(text)
        else:
            await CipherElite.send_message(AI_LOG_CHAT_ID, text)
    except Exception as e:
        print(f"[quizhot] reply error: {e}")


async def _is_owner(event):
    try:
        me = await CipherElite.get_me()
        return event.sender_id == me.id
    except Exception:
        return False


async def _resolve_id(link):
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


def is_question(text):
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
    commands = [
        ".q on <link|id> - watch group",
        ".q here - watch current group",
        ".q off <link|id> - stop watching",
        ".q list - list watched",
        ".q cache - show cached Q&A",
        ".q clear - reset cache",
        ".q learn \"q\" \"a\" - pre-cache Q&A",
        ".kq add web <url> - add website source",
        ".kq add note <text> - add manual fact",
        ".kq list - show sources",
        ".kq remove <n> - remove source",
        ".kq clear - wipe sources",
        ".kq fetch - re-scrape web",
        ".kq show - preview knowledge",
        ".kq setgroq <key> - save Groq API key",
        ".kq groqtest - test Groq",
    ]
    add_handler("quizhot", commands, "🎯 Quiz v4.0 — Groq + cache + sources")

# ═══ END OF CHUNK 1 ═══
# ═══════════════════════════════════════════════════════════════
#  .q COMMANDS
# ═══════════════════════════════════════════════════════════════

@CipherElite.on(events.NewMessage(pattern=r"\.q\s+on\s+(\S+)$"))
@rishabh()
async def cmd_q_on(event):
    if not await _is_owner(event):
        return
    try:
        cid = await _resolve_id(event.pattern_match.group(1))
        if cid is None:
            return await _safe_reply(event, "❌ Could not resolve. Try `.q here`.")
        if add_group(cid):
            await _safe_reply(event, f"✅ Quiz watch ON for `{cid}`")
        else:
            await _safe_reply(event, f"ℹ️ Already watching `{cid}`")
    except Exception as e:
        await _safe_reply(event, f"❌ error: `{e}`")


@CipherElite.on(events.NewMessage(pattern=r"\.q\s+here$"))
async def cmd_q_here(event):
    if not await _is_owner(event):
        return
    try:
        try: await event.delete()
        except: pass
        chat = await event.get_chat()
        cid = event.chat_id
        name = getattr(chat, "title", "Unknown")
        if add_group(cid):
            await CipherElite.send_message(AI_LOG_CHAT_ID, f"✅ Quiz ON for **{name}** (`{cid}`)")
        else:
            await CipherElite.send_message(AI_LOG_CHAT_ID, f"ℹ️ Already watching **{name}**")
    except Exception as e:
        await CipherElite.send_message(AI_LOG_CHAT_ID, f"❌ error: `{e}`")


@CipherElite.on(events.NewMessage(pattern=r"\.q\s+off\s+(\S+)$"))
@rishabh()
async def cmd_q_off(event):
    if not await _is_owner(event):
        return
    try:
        cid = await _resolve_id(event.pattern_match.group(1))
        if cid is None:
            return await _safe_reply(event, "❌ Could not resolve.")
        if remove_group(cid):
            await _safe_reply(event, f"⏹️ Stopped watching `{cid}`")
        else:
            await _safe_reply(event, f"ℹ️ Not watching `{cid}`")
    except Exception as e:
        await _safe_reply(event, f"❌ error: `{e}`")


@CipherElite.on(events.NewMessage(pattern=r"\.q\s+list$"))
@rishabh()
async def cmd_q_list(event):
    if not await _is_owner(event):
        return
    try:
        groups = DB.get("groups", [])
        if not groups:
            return await _safe_reply(event, "📭 No groups watched.")
        lines = [f"🎯 **Watched** ({len(groups)})\n"]
        for cid in groups:
            try:
                e = await CipherElite.get_entity(cid)
                name = getattr(e, "title", str(cid))
            except Exception:
                name = "Unknown"
            lines.append(f"• **{name}** (`{cid}`) — {len(get_sources(cid))} sources")
        await _safe_reply(event, "\n".join(lines))
    except Exception as e:
        await _safe_reply(event, f"❌ error: `{e}`")


@CipherElite.on(events.NewMessage(pattern=r"\.q\s+cache$"))
@rishabh()
async def cmd_q_cache(event):
    if not await _is_owner(event):
        return
    try:
        cache = DB.get("qa_cache", {})
        top = sorted(cache.items(), key=lambda kv: kv[1].get("hits", 0), reverse=True)[:10]
        lines = [f"💾 **Cache: {len(cache)} entries**\n"]
        for q, v in top:
            lines.append(f"• ({v.get('hits', 0)}×) \"{q[:40]}\" → \"{v.get('answer', '')[:30]}\"")
        await _safe_reply(event, "\n".join(lines))
    except Exception as e:
        await _safe_reply(event, f"❌ error: `{e}`")


@CipherElite.on(events.NewMessage(pattern=r"\.q\s+clear$"))
@rishabh()
async def cmd_q_clear(event):
    if not await _is_owner(event):
        return
    try:
        DB["history"] = []
        DB["qa_cache"] = {}
        save_db(DB)
        LEARN.clear()
        await _safe_reply(event, "🔄 Cache + learning cleared.")
    except Exception as e:
        await _safe_reply(event, f"❌ error: `{e}`")


@CipherElite.on(events.NewMessage(pattern=r'\.q\s+learn\s+"([^"]+)"\s+"([^"]+)"$'))
@rishabh()
async def cmd_q_learn(event):
    if not await _is_owner(event):
        return
    try:
        q = event.pattern_match.group(1).strip()
        a = event.pattern_match.group(2).strip()
        try: await event.delete()
        except: pass
        cache_store(q, a)
        await _safe_reply(event, f"✅ Pre-cached: Q=\"{q[:50]}\" A=\"{a}\"")
    except Exception as e:
        await _safe_reply(event, f"❌ error: `{e}`")


# ═══════════════════════════════════════════════════════════════
#  .kq COMMANDS
# ═══════════════════════════════════════════════════════════════

@CipherElite.on(events.NewMessage(pattern=r"\.kq\s+setgroq\s+(\S+)$"))
@rishabh()
async def cmd_kq_setgroq(event):
    if not await _is_owner(event):
        return
    try:
        global GROQ_API_KEY
        key = event.pattern_match.group(1).strip()
        if not key.startswith("gsk_"):
            return await _safe_reply(event, "❌ Groq key should start with `gsk_`")
        if len(key) < 40:
            return await _safe_reply(event, f"❌ Key too short ({len(key)} chars)")
        try: await event.delete()
        except: pass
        GROQ_CONFIG_FILE.write_text(
            json.dumps({"key": key, "saved_at": wat_now().strftime("%Y-%m-%d %H:%M:%S")}, indent=2),
            encoding="utf-8"
        )
        GROQ_API_KEY = key
        await _safe_reply(event, f"✅ Groq key saved ({len(key)} chars)")
    except Exception as e:
        await _safe_reply(event, f"❌ error: `{e}`")


@CipherElite.on(events.NewMessage(pattern=r"\.kq\s+groqtest$"))
@rishabh()
async def cmd_kq_groqtest(event):
    if not await _is_owner(event):
        return
    try:
        if not GROQ_API_KEY:
            return await _safe_reply(event, "❌ No Groq key set. Run `.kq setgroq <key>`.")
        await _safe_reply(event, "⏳ Testing Groq...")
        t0 = time.time()
        ans = await _groq_answer("What is 2+2?", event.chat_id)
        elapsed = int((time.time() - t0) * 1000)
        if ans:
            await _safe_reply(event, f"✅ Groq OK — {elapsed}ms\nAnswer: \"{ans}\"")
        else:
            await _safe_reply(event, f"❌ Groq failed ({elapsed}ms). Check console.")
    except Exception as e:
        await _safe_reply(event, f"❌ error: `{e}`")


@CipherElite.on(events.NewMessage(pattern=r"\.kq\s+add\s+(web|note)\s+(.+)$"))
async def cmd_kq_add(event):
    if not await _is_owner(event):
        return
    try:
        stype = event.pattern_match.group(1).lower()
        value = event.pattern_match.group(2).strip()
        try: await event.delete()
        except: pass
        chat = await event.get_chat()
        cid = event.chat_id
        name = getattr(chat, "title", "Unknown")

        if not add_source(cid, stype, value):
            await CipherElite.send_message(AI_LOG_CHAT_ID, f"ℹ️ Source already exists")
            return

        msg = f"✅ **{stype}** added to **{name}**"
        if stype == "web":
            txt = await fetch_website(value)
            if txt:
                sources = get_sources(cid)
                for s in sources:
                    if s.get("type") == "web" and s.get("value") == value:
                        s["text"] = txt
                        s["fetched_at"] = time.time()
                        break
                set_sources(cid, sources)
                msg += f"\n📄 Fetched {len(txt)} chars"
            else:
                msg += "\n⚠️ Fetch failed — try `.kq fetch`"
        elif stype == "note":
            sources = get_sources(cid)
            for s in sources:
                if s.get("type") == "note" and s.get("value") == value:
                    s["text"] = value
                    break
            set_sources(cid, sources)
            msg += f"\n📝 Note: \"{value[:80]}\""

        await CipherElite.send_message(AI_LOG_CHAT_ID, msg)
    except Exception as e:
        await CipherElite.send_message(AI_LOG_CHAT_ID, f"❌ kq add error: `{e}`")


@CipherElite.on(events.NewMessage(pattern=r"\.kq\s+list$"))
@rishabh()
async def cmd_kq_list(event):
    if not await _is_owner(event):
        return
    try:
        cid = event.chat_id
        sources = get_sources(cid)
        if not sources:
            return await _safe_reply(event, "📭 No sources for this group.")
        lines = [f"📚 **Sources** ({len(sources)})\n"]
        for i, s in enumerate(sources):
            lines.append(
                f"`{i}` **{s['type']}**: {s.get('value', '')[:60]}\n"
                f"   └ {len(s.get('text', ''))} chars"
            )
        await _safe_reply(event, "\n".join(lines))
    except Exception as e:
        await _safe_reply(event, f"❌ error: `{e}`")


@CipherElite.on(events.NewMessage(pattern=r"\.kq\s+remove\s+(\d+)$"))
@rishabh()
async def cmd_kq_remove(event):
    if not await _is_owner(event):
        return
    try:
        idx = int(event.pattern_match.group(1))
        if remove_source(event.chat_id, idx):
            await _safe_reply(event, f"🗑️ Removed source `{idx}`")
        else:
            await _safe_reply(event, f"❌ Invalid index `{idx}`")
    except Exception as e:
        await _safe_reply(event, f"❌ error: `{e}`")


@CipherElite.on(events.NewMessage(pattern=r"\.kq\s+clear$"))
@rishabh()
async def cmd_kq_clear(event):
    if not await _is_owner(event):
        return
    try:
        clear_sources(event.chat_id)
        await _safe_reply(event, "🔄 Sources cleared.")
    except Exception as e:
        await _safe_reply(event, f"❌ error: `{e}`")


@CipherElite.on(events.NewMessage(pattern=r"\.kq\s+fetch$"))
@rishabh()
async def cmd_kq_fetch(event):
    if not await _is_owner(event):
        return
    try:
        await _safe_reply(event, "⏳ Fetching...")
        n = await refresh_all_sources(event.chat_id)
        await _safe_reply(event, f"✅ Refreshed {n} web source(s)")
    except Exception as e:
        await _safe_reply(event, f"❌ error: `{e}`")


@CipherElite.on(events.NewMessage(pattern=r"\.kq\s+show$"))
@rishabh()
async def cmd_kq_show(event):
    if not await _is_owner(event):
        return
    try:
        block = build_knowledge_block(event.chat_id)
        if not block:
            return await _safe_reply(event, "📭 No knowledge yet.")
        await _safe_reply(event, f"📚 **Knowledge** ({len(block)} chars)\n\n{block[:1500]}")
    except Exception as e:
        await _safe_reply(event, f"❌ error: `{e}`")

# ═══ END OF CHUNK 2 ═══
# ═══════════════════════════════════════════════════════════════
#  GROQ — ULTRA FAST
# ═══════════════════════════════════════════════════════════════

async def _groq_answer(question, cid):
    if not GROQ_API_KEY:
        return None

    knowledge = build_knowledge_block(cid)
    knowledge_section = f"Known facts:\n{knowledge[:1500]}\n" if knowledge else ""

    prompt = f"""{knowledge_section}Answer this quiz question in 1-3 words, lowercase, no punctuation, no emoji, no explanation:
{question[:250]}
Answer:"""

    try:
        payload = {
            "model": GROQ_MODEL,
            "messages": [
                {"role": "system", "content": "You answer quiz questions with 1-3 word answers only. No explanation."},
                {"role": "user", "content": prompt},
            ],
            "temperature": 0.1,
            "max_tokens": 15,
        }
        headers = {
            "Authorization": f"Bearer {GROQ_API_KEY}",
            "Content-Type": "application/json",
        }
        timeout = aiohttp.ClientTimeout(total=5)
        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.post(GROQ_URL, json=payload, headers=headers) as resp:
                if resp.status != 200:
                    body = await resp.text()
                    dbg(f"groq HTTP {resp.status}: {body[:200]}")
                    return None
                data = await resp.json()
        text = data.get("choices", [{}])[0].get("message", {}).get("content", "").strip()
        text = text.replace("\n", " ").replace("*", "").replace("_", "").strip('"').strip("'")
        text = re.sub(r'^(answer|ans|reply|the answer is)[:\s]*', '', text, flags=re.IGNORECASE)
        text = text.strip(".,!?;:")
        if len(text) < 1 or len(text) > 60:
            return None
        dbg(f"groq answer: '{text}'")
        return text
    except Exception as e:
        print(f"[quizhot] groq error: {e}")
        return None


# ═══════════════════════════════════════════════════════════════
#  GEMINI — FALLBACK
# ═══════════════════════════════════════════════════════════════

_gemini_client = None


def _get_gemini_client():
    global _gemini_client
    if _gemini_client is None:
        api_key = ai_config.get_api_key()
        if not api_key:
            return None
        _gemini_client = genai.Client(api_key=api_key)
    return _gemini_client


async def _gemini_answer(question, cid):
    if not ai_config.is_enabled():
        return None
    client = _get_gemini_client()
    if client is None:
        return None

    knowledge = build_knowledge_block(cid)
    knowledge_section = f"\nKnown facts:\n{knowledge[:2000]}\n" if knowledge else ""

    prompt = f"""{knowledge_section}Answer this quiz question in 1-3 words, lowercase, no punctuation, no emoji, no explanation:
{question[:250]}
Answer:"""

    try:
        config = types.GenerateContentConfig(
            max_output_tokens=15,
            temperature=0.1,
            top_p=0.9,
        )
        resp = await client.aio.models.generate_content(
            model=QUIZ_MODEL,
            contents=[types.Content(role="user", parts=[types.Part(text=prompt)])],
            config=config,
        )
        text = (resp.text or "").strip()
        text = text.replace("\n", " ").replace("*", "").replace("_", "").strip('"').strip("'")
        text = re.sub(r'^(answer|ans|reply|the answer is)[:\s]*', '', text, flags=re.IGNORECASE)
        text = text.strip(".,!?;:")
        if len(text) < 1 or len(text) > 60:
            return None
        dbg(f"gemini answer: '{text}'")
        return text
    except Exception as e:
        print(f"[quizhot] gemini error: {e}")
        return None


async def _get_answer(question, cid):
    """Groq first, then Gemini fallback."""
    if GROQ_API_KEY:
        ans = await _groq_answer(question, cid)
        if ans:
            return ans
        dbg("groq failed, falling back to gemini")
    return await _gemini_answer(question, cid)


# ═══════════════════════════════════════════════════════════════
#  MAIN WATCHER
# ═══════════════════════════════════════════════════════════════

@CipherElite.on(events.NewMessage)
async def quiz_watcher(event):
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

        chat_id = event.chat_id
        state = LEARN.setdefault(chat_id, {
            "correct_options": [],
            "last_question_id": None,
            "last_question_text": None,
            "last_answer_ts": 0,
        })

        if state.get("last_question_id") == event.message.id:
            return

        if ENABLE_ANSWER_COOLDOWN:
            now_ts = wat_now().timestamp()
            if now_ts - state.get("last_answer_ts", 0) < COOLDOWN_SEC:
                return

        lower = text.lower()

        # ── LEARNING: admin says "correct"
        if event.is_reply:
            try:
                replied = await event.get_reply_message()
            except Exception:
                replied = None
            if replied and replied.raw_text:
                has_signal = any(sig in lower for sig in CORRECT_SIGNALS)
                is_admin = False
                try:
                    perms = await CipherElite.get_permissions(chat_id, event.sender_id)
                    is_admin = bool(getattr(perms, "is_admin", False) or getattr(perms, "is_creator", False))
                except Exception:
                    pass
                if has_signal and is_admin:
                    correct = replied.raw_text.strip()[:100]
                    state["correct_options"].append(correct)
                    state["correct_options"] = state["correct_options"][-30:]
                    last_q = state.get("last_question_text")
                    if last_q:
                        cache_store(last_q, correct)
                    LEARN[chat_id] = state
                    dbg(f"learned: '{correct}'")
                    return

        # ── BUTTON QUIZ
        if event.buttons:
            flat = [b for row in event.buttons for b in row]
            if 2 <= len(flat) <= 8:
                if not is_question(text) and len(text) < 10:
                    return
                dbg(f"button quiz: {len(flat)} opts")
                state["last_question_id"] = event.message.id
                state["last_question_text"] = text[:200]
                state["last_answer_ts"] = wat_now().timestamp()
                LEARN[chat_id] = state

                cached = cache_lookup(text)
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
                    for r_idx, row in enumerate(event.buttons):
                        for c_idx, btn in enumerate(row):
                            btext = (getattr(btn, "text", "") or "").strip()
                            if re.match(r'^[Aa1]\b', btext):
                                target_row, target_col = r_idx, c_idx
                                break
                        if target_row is not None:
                            break
                if target_row is None:
                    target_row, target_col = 0, 0

                try:
                    await event.click(target_row, target_col)
                    dbg(f"CLICKED ({target_row},{target_col})")
                except Exception as e:
                    dbg(f"click error: {e}")
                return

        # ── TEXT QUIZ
        if not is_question(text):
            return

        dbg(f"question: '{text[:80]}'")
        state["last_question_id"] = event.message.id
        state["last_question_text"] = text[:200]
        state["last_answer_ts"] = wat_now().timestamp()
        LEARN[chat_id] = state

        # cache first
        cached = cache_lookup(text)
        if cached:
            dbg(f"FAST cache: '{cached}'")
            try:
                await event.reply(cached)
                dbg(f"REPLIED (cache): '{cached}'")
            except Exception as e:
                print(f"[quizhot] send err: {e}")
            return

        # Groq → Gemini
        t0 = time.time()
        answer = await _get_answer(text, chat_id)
        elapsed = int((time.time() - t0) * 1000)
        if not answer:
            dbg(f"no answer ({elapsed}ms)")
            return

        try:
            await event.reply(answer)
            dbg(f"REPLIED ({elapsed}ms): '{answer}'")
        except Exception as e:
            print(f"[quizhot] send err: {e}")
            return

        cache_store(text, answer)

        try:
            await CipherElite.send_message(
                AI_LOG_CHAT_ID,
                f"🎯 **QUIZ ANSWERED** ({elapsed}ms)\n📍 `{chat_id}`\n❓ \"{text[:150]}\"\n🤖 \"{answer}\"\n🕐 {wat_now().strftime('%I:%M:%S %p')} WAT"
            )
        except Exception:
            pass

    except Exception as e:
        print(f"[quizhot] watcher error: {e}")


# ═══════════════════════════════════════════════════════════════
#  BOOTSTRAP
# ═══════════════════════════════════════════════════════════════

async def _plugin_bootstrap():
    try:
        await asyncio.sleep(10)
        asyncio.create_task(auto_refresh_loop())
        dbg("bootstrap: auto-refresh started")
        if GROQ_API_KEY:
            dbg(f"bootstrap: groq key loaded ({len(GROQ_API_KEY)} chars)")
        else:
            dbg("bootstrap: NO groq key — use .kq setgroq <key>")
    except Exception as e:
        print(f"[quizhot] bootstrap error: {e}")


try:
    asyncio.create_task(_plugin_bootstrap())
except Exception as e:
    print(f"[quizhot] bootstrap init error: {e}")

@CipherElite.on(events.NewMessage(pattern=r"\.kq\s+models$"))
@rishabh()
async def cmd_kq_models(event):
    if not await _is_owner(event):
        return
    try:
        if not GROQ_API_KEY:
            return await _safe_reply(event, "❌ No Groq key")
        async with aiohttp.ClientSession() as session:
            async with session.get(
                "https://api.groq.com/openai/v1/models",
                headers={"Authorization": f"Bearer {GROQ_API_KEY}"}
            ) as resp:
                if resp.status != 200:
                    return await _safe_reply(event, f"❌ HTTP {resp.status}")
                data = await resp.json()
        ids = [m["id"] for m in data.get("data", [])]
        await _safe_reply(event, f"**Available models ({len(ids)}):**\n\n" + "\n".join(f"`{i}`" for i in ids))
    except Exception as e:
        await _safe_reply(event, f"❌ error: `{e}`")

# ╔══════════════════════════════════════════════════════════════╗
# ║  === END OF QUIZHOT v4.0 — GROQ EDITION ===                  ║
# ║                                                              ║
# ║  • Groq primary (300-500ms)                                  ║
# ║  • Gemini fallback (1-2s)                                    ║
# ║  • Cache hits (150ms)                                        ║
# ║  • Per-group sources (web + notes)                           ║
# ║  • Strict question filter                                    ║
# ║  • No typing/online sim                                      ║
# ║  • Auto-refresh sources every 6h                             ║
# ║  • Learns from admin "correct" replies                       ║
# ╚══════════════════════════════════════════════════════════════╝

                                  
