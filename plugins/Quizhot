# =============================================================================
#  KCE Quiz Hot-Fix v1.0 — Standalone quiz clicker
#  Watches quiz groups, learns from mods, clicks buttons fast
# =============================================================================

from telethon import events
from utils.utils import CipherElite
from utils.decorators import rishabh
from plugins.bot import add_handler
import asyncio
import json
import re
import random
from datetime import datetime, timedelta, timezone
from pathlib import Path

WAT = timezone(timedelta(hours=1))
def wat_now():
    return datetime.now(WAT)

# ═══════════════════════════════════════════════════════════════
#  CONFIG
# ═══════════════════════════════════════════════════════════════

AI_LOG_CHAT_ID = -1004374819145
DEBUG = True

# Correct signals from mods
CORRECT_SIGNALS = ['correct', '✅', 'right', 'yes', 'winner', 'win', 'accurate', '✔']

# Learn cache: {chat_id: {"correct_options": [...], "last_question_id": ..., "pending": {}}}
LEARN = {}

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


async def resolve_id(link):
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

# ═══════════════════════════════════════════════════════════════
#  INIT
# ═══════════════════════════════════════════════════════════════

def init(client_instance):
    commands = [
        ".q on <link|id> - watch quiz group",
        ".q off <link|id> - stop watching",
        ".q list - show watched groups",
        ".q clear - reset learned answers",
    ]
    add_handler("quizhot", commands, "🎯 Quiz hot-fix — auto-click quiz buttons")


@CipherElite.on(events.NewMessage(pattern=r"\.q\s+on\s+(\S+)$"))
@rishabh()
async def cmd_q_on(event):
    if not await _is_owner(event):
        return
    try:
        link = event.pattern_match.group(1)
        cid = await resolve_id(link)
        if cid is None:
            return await _safe_reply(event, f"❌ Could not resolve `{link}`")
        if add_group(cid):
            await _safe_reply(event, f"✅ Quiz watch **ON** for `{cid}`\nBot will click buttons on quiz questions.")
        else:
            await _safe_reply(event, f"ℹ️ Already watching `{cid}`")
    except Exception as e:
        await _safe_reply(event, f"❌ error: `{e}`")


@CipherElite.on(events.NewMessage(pattern=r"\.q\s+off\s+(\S+)$"))
@rishabh()
async def cmd_q_off(event):
    if not await _is_owner(event):
        return
    try:
        link = event.pattern_match.group(1)
        cid = await resolve_id(link)
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
#  QUIZ WATCHER — learn + auto-click buttons
# ═══════════════════════════════════════════════════════════════

@CipherElite.on(events.NewMessage)
async def quiz_watcher(event):
    try:
        if event.out:
            return
        if not is_quiz_group(event.chat_id):
            return

        text = event.raw_text or ""
        me = await CipherElite.get_me()
        sender = await event.get_sender()
        if sender and sender.id == me.id:
            return

        chat_id = event.chat_id
        state = LEARN.setdefault(chat_id, {
            "correct_options": [],   # learned correct answer texts
            "last_question_id": None,
            "last_question_text": None,
            "question_count": 0,
            "answer_count": 0,
        })

        # ── LEARNING: mod says "correct" as reply
        if event.is_reply:
            try:
                replied = await event.get_reply_message()
            except Exception:
                replied = None

            if replied and replied.raw_text:
                lower = text.lower()
                has_signal = any(sig in lower for sig in CORRECT_SIGNALS)

                # also check if sender is admin
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
                        dbg(f"learned correct: '{correct}' (total: {len(state['correct_options'])})")

        # ── BUTTON-QUIZ: detect message with inline buttons (A/B/C/D style)
        if event.buttons and not event.out:
            btns = event.buttons
            # count buttons
            flat = [b for row in btns for b in row]
            if len(flat) < 2 or len(flat) > 8:
                return

            # is it a question? has text and question words OR ends with ?
            lower = text.lower()
            is_question = (
                "?" in text
                or any(w in lower for w in ("what", "which", "who", "when", "where", "why", "how"))
            )

            if not is_question and len(text) < 8:
                return

            dbg(f"quiz with buttons detected: {len(flat)} options, question='{text[:60]}'")
            state["last_question_id"] = event.message.id
            state["last_question_text"] = text[:200]
            state["question_count"] += 1

            # decide which option to click
            target_row, target_col = None, None

            # if we have learned correct options, match against button text
            learned = state.get("correct_options", [])
            if learned:
                for r_idx, row in enumerate(btns):
                    for c_idx, btn in enumerate(row):
                        btn_text = (getattr(btn, "text", "") or "").strip().lower()
                        for correct in learned:
                            if correct.lower() in btn_text or btn_text in correct.lower():
                                target_row, target_col = r_idx, c_idx
                                dbg(f"matched learned answer '{correct}' → button '{btn_text}'")
                                break
                        if target_row is not None:
                            break
                    if target_row is not None:
                        break

            # fallback: pick FIRST button (A) if no learning
            if target_row is None:
                # look for a button that says A) / A. / 1) etc
                for r_idx, row in enumerate(btns):
                    for c_idx, btn in enumerate(row):
                        btn_text = (getattr(btn, "text", "") or "").strip()
                        # prioritize option A
                        if re.match(r'^[Aa1]\b', btn_text) or btn_text.startswith("A)"):
                            target_row, target_col = r_idx, c_idx
                            break
                    if target_row is not None:
                        break

            if target_row is None:
                # last resort: first button
                target_row, target_col = 0, 0

            # beast mode — click NOW
            try:
                await CipherElite(functions.account.UpdateStatusRequest(offline=False))
            except Exception:
                pass

            try:
                await event.click(target_row, target_col)
                dbg(f"CLICKED button ({target_row},{target_col})")
                state["answer_count"] += 1

                # log to AI REPLY LOG
                log = (
                    f"🎯 **QUIZ CLICKED**\n"
                    f"📍 chat: `{chat_id}`\n"
                    f"❓ \"{text[:150]}\"\n"
                    f"👆 clicked: ({target_row},{target_col})\n"
                    f"🕐 {wat_now().strftime('%I:%M:%S %p')} WAT"
                )
                try:
                    await CipherElite.send_message(AI_LOG_CHAT_ID, log)
                except Exception:
                    pass
            except Exception as e:
                dbg(f"click error: {e}")

        LEARN[chat_id] = state

    except Exception as e:
        print(f"[quizhot] watcher error: {e}")


# Forgot import
from telethon.tl import functions

# ═══ END OF QUIZHOT v1.0 ═══
