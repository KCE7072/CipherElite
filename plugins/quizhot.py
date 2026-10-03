# =============================================================================
#  KCE Quiz Hot-Fix v2.0 — Fast quiz answerer (buttons + text)
#  Standalone — no dependency on aireply.py
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
import random
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
ANSWER_COOLDOWN_SEC = 30   # min gap between answers in same group

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


def load_db():
    try:
        if DB_FILE.exists():
            return json.loads(DB_FILE.read_text(encoding="utf-8"))
    except Exception as e:
        print(f"[quizhot] load error: {e}")
    return {"groups": [], "history": []}


def save_db(data):
    try:
        DB_FILE.write_text(json.dumps(data, indent=2), encoding="utf-8")
    except Exception as e:
        print(f"[quizhot] save error: {e}")


DB = load_db()

# runtime state — per group
LEARN = {}   # {chat_id: {"correct_options": [...], "last_question_id": ..., "last_answer_ts": ...}}


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


async def _fire_online():
    try:
        await CipherElite(functions.account.UpdateStatusRequest(offline=False))
    except Exception:
        pass


# ═══════════════════════════════════════════════════════════════
#  INIT — register commands
# ═══════════════════════════════════════════════════════════════

def init(client_instance):
    commands = [
        ".q on <link|id> - watch quiz group",
        ".q here - watch current group (run inside)",
        ".q off <link|id> - stop watching",
        ".q list - show watched groups",
        ".q clear - reset learned answers",
    ]
    add_handler("quizhot", commands, "🎯 Quiz hot-fix — auto-answers quizzes")


# ═══════════════════════════════════════════════════════════════
#  COMMANDS
# ═══════════════════════════════════════════════════════════════

@CipherElite.on(events.NewMessage(pattern=r"\.q\s+on\s+(\S+)$"))
@rishabh()
async def cmd_q_on(event):
    if not await _is_owner(event):
        return
    try:
        link = event.pattern_match.group(1)
        cid = await _resolve_id(link)
        if cid is None:
            return await _safe_reply(event, f"❌ Could not resolve `{link}`\nTry `.q here` inside the group.")
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
            await CipherElite.send_message(
                AI_LOG_CHAT_ID,
                f"✅ Quiz watch ON for **{name}**\n🆔 `{cid}`"
            )
        else:
            await CipherElite.send_message(
                AI_LOG_CHAT_ID,
                f"ℹ️ Already watching **{name}** (`{cid}`)"
            )
    except Exception as e:
        await CipherElite.send_message(AI_LOG_CHAT_ID, f"❌ error: `{e}`")


@CipherElite.on(events.NewMessage(pattern=r"\.q\s+off\s+(\S+)$"))
@rishabh()
async def cmd_q_off(event):
    if not await _is_owner(event):
        return
    try:
        link = event.pattern_match.group(1)
        cid = await _resolve_id(link)
        if cid is None:
            return await _safe_reply(event, f"❌ Could not resolve `{link}`")
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
        lines = [f"🎯 **Watched Quiz Groups** ({len(groups)})\n"]
        for cid in groups:
            try:
                e = await CipherElite.get_entity(cid)
                name = getattr(e, "title", str(cid))
            except Exception:
                name = "Unknown"
            lines.append(f"• **{name}** (`{cid}`)")
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
        save_db(DB)
        LEARN.clear()
        await _safe_reply(event, "🔄 Quiz learning cleared.")
    except Exception as e:
        await _safe_reply(event, f"❌ error: `{e}`")


# ═══════════════════════════════════════════════════════════════
#  FAST QUIZ ANSWER — optimized prompt, minimal tokens
# ═══════════════════════════════════════════════════════════════

FAST_QUIZ_PROMPT = """You answer Telegram quiz questions. Reply with ONLY the answer.
Rules:
- 1-3 words max
- lowercase
- no punctuation, no emoji, no explanation
- if it's a name/number, just the name/number
- if unsure, give best guess

Question: {q}

Answer:"""

_quiz_client = None

def _get_quiz_client():
    global _quiz_client
    if _quiz_client is None:
        api_key = ai_config.get_api_key()
        if not api_key:
            return None
        _quiz_client = genai.Client(api_key=api_key)
    return _quiz_client


async def _fast_quiz_answer(question):
    """Fast minimal-latency answer."""
    if not ai_config.is_enabled():
        return None
    client = _get_quiz_client()
    if client is None:
        return None

    try:
        config = types.GenerateContentConfig(
            max_output_tokens=15,
            temperature=0.2,
        )
        resp = await client.aio.models.generate_content(
            model=QUIZ_MODEL,
            contents=[types.Content(
                role="user",
                parts=[types.Part(text=FAST_QUIZ_PROMPT.format(q=question[:250]))]
            )],
            config=config,
        )
        text = (resp.text or "").strip()
        # clean aggressively
        text = text.replace("\n", " ").replace("*", "").replace("_", "").strip('"').strip("'")
        text = re.sub(r'^(answer|ans|reply|the answer is)[:\s]*', '', text, flags=re.IGNORECASE)
        text = text.strip(".,!?;:")
        if len(text) < 1 or len(text) > 60:
            return None
        return text
    except Exception as e:
        print(f"[quizhot] gemini error: {e}")
        return None


# ═══════════════════════════════════════════════════════════════
#  MAIN WATCHER — buttons + text questions
# ═══════════════════════════════════════════════════════════════

SKIP_PHRASES = [
    "rules:", "prize:", "round ", "winner", "stay active",
    "let's see", "we have", "i'll send", "point per",
    "quiz —", "quiz -", "questions lined up", "join here",
    "don't edit", "no edited", "keep your answers"
]


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
            "last_answer_ts": 0,
        })

        # dedupe — same message
        if state.get("last_question_id") == event.message.id:
            return

        now_ts = wat_now().timestamp()
        if now_ts - state.get("last_answer_ts", 0) < ANSWER_COOLDOWN_SEC:
            return

        lower = text.lower()

        # skip announcements / rules / intros
        if any(p in lower for p in SKIP_PHRASES):
            dbg(f"skip phrase detected, ignoring")
            return

        # ── LEARNING: mod replies "correct" to someone's answer
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
                    if correct not in state["correct_options"]:
                        state["correct_options"].append(correct)
                        state["correct_options"] = state["correct_options"][-20:]
                        dbg(f"learned: '{correct}'")

        # ── BUTTON QUIZ (A/B/C/D options)
        if event.buttons:
            flat = [b for row in event.buttons for b in row]
            if 2 <= len(flat) <= 8:
                is_q = "?" in text or any(
                    w in lower for w in ("what", "which", "who", "when", "where", "why", "how")
                )
                if not is_q and len(text) < 10:
                    return

                dbg(f"button quiz: {len(flat)} options, q='{text[:60]}'")
                state["last_question_id"] = event.message.id
                state["last_answer_ts"] = now_ts
                LEARN[chat_id] = state

                target_row, target_col = None, None
                learned = state.get("correct_options", [])
                if learned:
                    for r_idx, row in enumerate(event.buttons):
                        for c_idx, btn in enumerate(row):
                            btext = (getattr(btn, "text", "") or "").strip().lower()
                            for corr in learned:
                                if corr.lower() in btext or btext in corr.lower():
                                    target_row, target_col = r_idx, c_idx
                                    break
                            if target_row is not None:
                                break
                        if target_row is not None:
                            break

                if target_row is None:
                    for r_idx, row in enumerate(event.buttons):
                        for c_idx, btn in enumerate(row):
                            btext = (getattr(btn, "text", "") or "").strip()
                            if re.match(r'^[Aa1]\b', btext) or btext.startswith(("A)", "A.")):
                                target_row, target_col = r_idx, c_idx
                                break
                        if target_row is not None:
                            break

                if target_row is None:
                    target_row, target_col = 0, 0

                await _fire_online()
                try:
                    await event.click(target_row, target_col)
                    dbg(f"CLICKED ({target_row},{target_col})")
                    try:
                        await CipherElite.send_message(
                            AI_LOG_CHAT_ID,
                            f"🎯 **QUIZ BUTTON CLICKED**\n📍 `{chat_id}`\n❓ \"{text[:150]}\"\n👆 ({target_row},{target_col})\n🕐 {wat_now().strftime('%I:%M:%S %p')} WAT"
                        )
                    except Exception:
                        pass
                except Exception as e:
                    dbg(f"click error: {e}")
                return

        # ── TEXT-ANSWER QUIZ
        is_admin = False
        try:
            perms = await CipherElite.get_permissions(chat_id, event.sender_id)
            is_admin = bool(getattr(perms, "is_admin", False) or getattr(perms, "is_creator", False))
        except Exception:
            pass

        has_q_mark = "?" in text
        starts_q_word = any(
            lower.startswith(w) for w in
            ("what", "which", "who", "when", "where", "why", "how",
             "name", "pick", "complete", "the", "in", "on")
        )
        is_question = (is_admin or has_q_mark or starts_q_word) and len(text) >= 8

        if not is_question:
            return

        dbg(f"text quiz detected: '{text[:80]}'")
        state["last_question_id"] = event.message.id
        state["last_answer_ts"] = now_ts
        LEARN[chat_id] = state

        answer = await _fast_quiz_answer(text)
        if not answer:
            dbg("no answer generated")
            return

        await _fire_online()
        try:
            await event.reply(answer)
            dbg(f"ANSWERED: '{answer}'")
        except Exception as e:
            print(f"[quizhot] send error: {e}")
            return

        try:
            await CipherElite.send_message(
                AI_LOG_CHAT_ID,
                f"🎯 **TEXT QUIZ ANSWERED**\n📍 `{chat_id}`\n❓ \"{text[:150]}\"\n🤖 \"{answer}\"\n🕐 {wat_now().strftime('%I:%M:%S %p')} WAT"
            )
        except Exception:
            pass

    except Exception as e:
        print(f"[quizhot] watcher error: {e}")


# ╔══════════════════════════════════════════════════════════════╗
# ║  === END OF QUIZHOT v2.0 ===                                 ║
# ║  Fast text + button quiz answers, self-contained             ║
# ╚══════════════════════════════════════════════════════════════╝
