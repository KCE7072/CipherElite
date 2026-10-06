# =============================================================================
#  CipherElite Plugin - cryptoraid v6.0
#  Smash all groups + reply flow for whitelisted + queue bot DM + NL commands
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
import aiohttp
from datetime import datetime, timedelta, timezone
from pathlib import Path

print("[cryptoraid] IMPORTING v6.0")

VERSION = "6.0.0"
CATEGORY = "utilities"

# ═══════════════════════════════════════════════════════════════
#  TIMEZONE
# ═══════════════════════════════════════════════════════════════

RAID_WAT = timezone(timedelta(hours=1))

def raid_now():
    return datetime.now(RAID_WAT)

# ═══════════════════════════════════════════════════════════════
#  CONFIG
# ═══════════════════════════════════════════════════════════════

SMASH_LOG_ID = -1004453857887
REPLY_LOG_ID = -1004374819145
RAIDAR_USER_ID = 5994885234
OWNER_USER_ID = 7616645514

RAID_KEYWORDS = ['raid', 'smash', 'retweet', 'raid tweet', 'reply on x', 'lfg raid']
SMASH_BUTTON = '👊'
OTHER_TARGETS = ['🤛', '✊', '🤜', 'Verify', 'Verified', '✅', 'Confirmed']

VERIFY_WAIT_AFTER_DONE = 30
DM2_WAIT_SECONDS = 60
DM1_WAIT_SECONDS = 15
MANUAL_DONE_TIMEOUT = 600      # 10 min wait for user to tap Done
DEBUG = True
RAID_DM_KEEP = 20


def rdbg(msg):
    if DEBUG:
        print(f"[cryptoraid] {msg}")


# ═══════════════════════════════════════════════════════════════
#  STORAGE
# ═══════════════════════════════════════════════════════════════

RAID_ROOT = Path(__file__).parent.parent
RAID_DB_DIR = RAID_ROOT / "DB"
RAID_DB_DIR.mkdir(exist_ok=True)
RAID_DB_FILE = RAID_DB_DIR / "cryptoraid_v6.json"
QUEUE_BOT_FILE = RAID_DB_DIR / "queue_bot_config.json"
QUEUE_BOT_SESSION = RAID_DB_DIR / "queue_bot_raid"


def raid_load_db():
    try:
        if RAID_DB_FILE.exists():
            return json.loads(RAID_DB_FILE.read_text(encoding="utf-8"))
    except Exception as e:
        print(f"[cryptoraid] load err: {e}")
    return {
        "smashed": {},
        "count": 0,
        "whitelist": [],
        "queue": [],
        "current_raid": None,
        "completed": [],
        "failed": [],
        "raidar_dms_wl": [],     # only whitelisted raid links
        "paused": False,
        "started": raid_now().strftime("%Y-%m-%d %H:%M:%S"),
    }


def raid_save_db(data):
    try:
        RAID_DB_FILE.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
    except Exception as e:
        print(f"[cryptoraid] save err: {e}")


RAID_DB = raid_load_db()
PROCESSING = {"active": False}


def raid_is_wl(chat_id):
    return chat_id in RAID_DB.get("whitelist", [])


# ═══════════════════════════════════════════════════════════════
#  TOKEN LOADER — env var first, file fallback
# ═══════════════════════════════════════════════════════════════

def raid_load_token():
    # 1) env var
    tok = os.getenv("KCE_QUEUE_BOT_TOKEN", "").strip()
    if tok and ":" in tok and len(tok) > 40:
        rdbg(f"token from env (len={len(tok)})")
        return tok
    # 2) file
    try:
        if QUEUE_BOT_FILE.exists():
            data = json.loads(QUEUE_BOT_FILE.read_text(encoding="utf-8"))
            tok = data.get("token", "").strip()
            if tok and ":" in tok and len(tok) > 40:
                rdbg(f"token from file (len={len(tok)})")
                return tok
    except Exception as e:
        print(f"[cryptoraid] token file err: {e}")
    rdbg("NO VALID TOKEN FOUND")
    return ""


# ═══════════════════════════════════════════════════════════════
#  HELPERS
# ═══════════════════════════════════════════════════════════════

def raid_norm_url(url):
    url = re.sub(r'\?.*$', '', url)
    url = re.sub(r'/$', '', url)
    url = re.sub(r'^https?://(?:mobile\.|www\.)?', '', url)
    return url.lower()


def raid_extract_x_urls(text):
    raw = re.findall(r'https?://(?:mobile\.)?(?:twitter\.com|x\.com)/\S+', text or "")
    return [raid_norm_url(u) for u in raw]


def raid_has_intent(text):
    lower = (text or "").lower()
    return any(k in lower for k in RAID_KEYWORDS)


def raid_now_dict():
    n = raid_now()
    return {
        "date": n.strftime("%Y-%m-%d"),
        "time": n.strftime("%H:%M:%S"),
        "time12": n.strftime("%I:%M:%S %p"),
        "ts": n.timestamp(),
    }


async def raid_send_log(text, chat_id=None):
    target = chat_id or SMASH_LOG_ID
    try:
        return await CipherElite.send_message(target, text)
    except Exception as e:
        print(f"[cryptoraid] log err: {e}")
        return None


async def raid_edit_log(msg_id, text, chat_id=None):
    target = chat_id or SMASH_LOG_ID
    try:
        await CipherElite.edit_message(target, msg_id, text)
    except Exception as e:
        print(f"[cryptoraid] edit err: {e}")


def raid_build_card(raid_id, chat_name, link, steps, status="processing"):
    emoji = {"done": "✅", "failed": "❌", "queued": "⏸️", "waiting": "⏳"}.get(status, "🎯")
    lines = [f"{emoji} RAID #{raid_id} — {chat_name}", "━━━━━━━━━━━━━━━━━━━━━━━━━━━", ""]
    for s in steps:
        lines.append(s)
        lines.append("")
    lines.append("━━━━━━━━━━━━━━━━━━━━━━━━━━━")
    lines.append(f"🔗 {link}")
    lines.append(f"💬 {chat_name}")
    lines.append(f"⏰ {raid_now().strftime('%I:%M:%S %p')} — {raid_now().strftime('%d/%m/%Y')} WAT")
    return "\n".join(lines)


# ═══════════════════════════════════════════════════════════════
#  RAIDAR DM LINK STORAGE — whitelisted raids only
# ═══════════════════════════════════════════════════════════════

def raid_store_dm_link(link, chat_id, raid_id):
    dms = RAID_DB.get("raidar_dms_wl", [])
    dms.append({
        "link": link,
        "chat_id": chat_id,
        "raid_id": raid_id,
        "ts": raid_now().timestamp(),
    })
    RAID_DB["raidar_dms_wl"] = dms[-RAID_DM_KEEP:]
    raid_save_db(RAID_DB)


def raid_find_dm_link(link):
    for dm in RAID_DB.get("raidar_dms_wl", []):
        if dm.get("link") == link:
            return dm
    return None


# ═══════════════════════════════════════════════════════════════
#  QUEUE BOT
# ═══════════════════════════════════════════════════════════════

QUEUE_BOT = None
QUEUE_BOT_TOKEN = ""


async def raid_start_bot():
    global QUEUE_BOT, QUEUE_BOT_TOKEN
    if QUEUE_BOT and QUEUE_BOT.is_connected():
        return
    QUEUE_BOT_TOKEN = raid_load_token()
    if not QUEUE_BOT_TOKEN:
        rdbg("queue bot: NO TOKEN")
        return
    try:
        bot = TelegramClient(str(QUEUE_BOT_SESSION), 6, "eb06d4abfb49dc3eeb1aeb98ae0f581e")
        await bot.start(bot_token=QUEUE_BOT_TOKEN)

        @bot.on(events.CallbackQuery)
        async def _cb(event):
            try:
                data = event.data.decode() if isinstance(event.data, bytes) else str(event.data)
                await raid_handle_cb(event, data)
            except Exception as e:
                print(f"[cryptoraid] cb err: {e}")
                try:
                    await event.answer("Error")
                except Exception:
                    pass

        QUEUE_BOT = bot
        me = await bot.get_me()
        rdbg(f"queue bot ONLINE @{me.username}")
    except Exception as e:
        print(f"[cryptoraid] bot start err: {e}")
        QUEUE_BOT = None


async def raid_dm_owner(text, buttons=None):
    if not QUEUE_BOT or not QUEUE_BOT.is_connected():
        rdbg("dm: bot not connected")
        return None
    try:
        return await QUEUE_BOT.send_message(OWNER_USER_ID, text, buttons=buttons)
    except Exception as e:
        print(f"[cryptoraid] dm err: {e}")
        return None


# ═══════════════════════════════════════════════════════════════
#  INIT
# ═══════════════════════════════════════════════════════════════

def init(client_instance):
    print("[cryptoraid] init called")
    commands = [
        ".cryptoraid - status",
        ".cryptoraid_stats - stats",
        ".cryptoraid_queue - queue",
        ".cryptoraid_reset - reset records",
        ".cryptoraid_pause - pause",
        ".cryptoraid_resume - resume",
        ".commands - cheat sheet",
        "..wl - whitelist current group",
        "..wl off - remove whitelist",
        "..wl list - list whitelisted",
    ]
    add_handler("cryptoraid", commands, "🎯 Raid v6.0 — smash + reply + NL")
    print("[cryptoraid] commands registered")

print("[cryptoraid] MODULE LOADED — chunk 1")

# ═══ END OF CHUNK 1 ═══
# ═══════════════════════════════════════════════════════════════
#  GEMINI — 4 reply variants
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


async def raid_gen_replies(link, chat_name):
    fallback = ["gm fam 🔥", "nice one 👀", "keep grinding 💪", "wagmi 🚀"]
    if not ai_config.is_enabled():
        return fallback
    client = raid_gemini_client()
    if client is None:
        return fallback

    prompt = f"""Generate 4 DIFFERENT short casual replies (max 5 words each) to a crypto raid tweet.

Link: {link}
Group: {chat_name}

Rules:
- lowercase
- 1 emoji max per reply
- casual crypto/nigerian vibe
- 4 DIFFERENT replies (not variations of same)
- friendly, real, not spammy

Output exactly 4 lines. Just the replies, no numbers."""

    try:
        from google.genai import types
        resp = await client.aio.models.generate_content(
            model="gemini-3.5-flash-lite",
            contents=[types.Content(role="user", parts=[types.Part(text=prompt)])],
            config=types.GenerateContentConfig(max_output_tokens=100, temperature=1.2),
        )
        text = (resp.text or "").strip()
        lines = [l.strip().strip('"').strip("'") for l in text.split("\n") if l.strip()]
        lines = [re.sub(r'^[\d\.\)\-\s]+', '', l) for l in lines]
        lines = [l for l in lines if 2 < len(l) < 80][:4]
        while len(lines) < 4:
            lines.append(random.choice(fallback))
        rdbg(f"replies: {lines}")
        return lines[:4]
    except Exception as e:
        print(f"[cryptoraid] gemini err: {e}")
        return fallback


# ═══════════════════════════════════════════════════════════════
#  COMMANDS
# ═══════════════════════════════════════════════════════════════

@CipherElite.on(events.NewMessage(pattern=r"\.cryptoraid$"))
@rishabh()
async def cmd_status(event):
    try:
        wl = RAID_DB.get("whitelist", [])
        q = RAID_DB.get("queue", [])
        cur = RAID_DB.get("current_raid")
        completed = RAID_DB.get("completed", [])
        failed = RAID_DB.get("failed", [])
        today = raid_now().strftime("%Y-%m-%d")
        today_done = sum(1 for r in completed if r.get("date", "").startswith(today))
        paused = RAID_DB.get("paused", False)
        bot_st = "✅ online" if (QUEUE_BOT and QUEUE_BOT.is_connected()) else "❌ offline"
        msg = (
            f"🎯 **Crypto Raid v6.0**\n"
            f"━━━━━━━━━━━━━━━━━━━━\n"
            f"{'⏸️ PAUSED' if paused else '✅ Active'}\n"
            f"👊 Smashes: `{RAID_DB.get('count', 0)}`\n"
            f"✅ Done: `{len(completed)}` (today: `{today_done}`)\n"
            f"❌ Failed: `{len(failed)}`\n"
            f"📝 Whitelisted: `{len(wl)}`\n"
            f"📦 Queue: `{len(q)}`\n"
            f"⚙️ Processing: `{cur['raid_id'] if cur else 'None'}`\n"
            f"🤖 Queue bot: {bot_st}"
        )
        await event.reply(msg)
    except Exception as e:
        await event.reply(f"❌ {e}")


@CipherElite.on(events.NewMessage(pattern=r"\.cryptoraid_stats$"))
@rishabh()
async def cmd_stats(event):
    try:
        c = RAID_DB.get("completed", [])
        f = RAID_DB.get("failed", [])
        today = raid_now().strftime("%Y-%m-%d")
        tc = sum(1 for r in c if r.get("date", "").startswith(today))
        tf = sum(1 for r in f if r.get("date", "").startswith(today))
        lines = [
            "📊 **Raid Stats**", "━━━━━━━━━━━━━━━━━━━━",
            f"✅ Done: `{len(c)}` (today: `{tc}`)",
            f"❌ Failed: `{len(f)}` (today: `{tf}`)",
            f"👊 Smashes: `{RAID_DB.get('count', 0)}`",
        ]
        if c:
            lines.append("\n**Last 3:**")
            for r in c[-3:]:
                lines.append(f"• #{r.get('raid_id')} — {r.get('time12', '?')}")
        await event.reply("\n".join(lines))
    except Exception as e:
        await event.reply(f"❌ {e}")


@CipherElite.on(events.NewMessage(pattern=r"\.cryptoraid_queue$"))
@rishabh()
async def cmd_queue(event):
    try:
        q = RAID_DB.get("queue", [])
        cur = RAID_DB.get("current_raid")
        lines = ["📦 **Queue**", "━━━━━━━━━━━━━━━━━━━━"]
        if cur:
            lines.append(f"⚙️ Processing: #{cur.get('raid_id')} — {cur.get('chat_name', '?')}")
        if q:
            lines.append(f"\nWaiting ({len(q)}):")
            for r in q[:10]:
                lines.append(f"⏸️ #{r.get('raid_id')} — {r.get('chat_name', '?')}")
        else:
            lines.append("✅ Queue empty")
        await event.reply("\n".join(lines))
    except Exception as e:
        await event.reply(f"❌ {e}")


@CipherElite.on(events.NewMessage(pattern=r"\.cryptoraid_reset$"))
@rishabh()
async def cmd_reset(event):
    RAID_DB["queue"] = []
    RAID_DB["current_raid"] = None
    RAID_DB["completed"] = []
    RAID_DB["failed"] = []
    raid_save_db(RAID_DB)
    await event.reply("🔄 Reset.")


@CipherElite.on(events.NewMessage(pattern=r"\.cryptoraid_pause$"))
@rishabh()
async def cmd_pause(event):
    RAID_DB["paused"] = True
    raid_save_db(RAID_DB)
    await event.reply("⏸️ Raid replies PAUSED")


@CipherElite.on(events.NewMessage(pattern=r"\.cryptoraid_resume$"))
@rishabh()
async def cmd_resume(event):
    RAID_DB["paused"] = False
    raid_save_db(RAID_DB)
    await event.reply("▶️ RESUMED")


@CipherElite.on(events.NewMessage(pattern=r"\.\.wl$"))
async def cmd_wl_add(event):
    try:
        try: await event.delete()
        except: pass
        chat = await event.get_chat()
        cid = event.chat_id
        name = getattr(chat, "title", "Unknown")
        wl = RAID_DB.get("whitelist", [])
        if cid in wl:
            return await raid_send_log(f"ℹ️ Already whitelisted: **{name}**")
        wl.append(cid)
        RAID_DB["whitelist"] = wl
        raid_save_db(RAID_DB)
        await raid_send_log(f"✅ Whitelisted **{name}** (`{cid}`)\nTotal: `{len(wl)}`")
    except Exception as e:
        await raid_send_log(f"❌ {e}")


@CipherElite.on(events.NewMessage(pattern=r"\.\.wl\s+off$"))
async def cmd_wl_off(event):
    try:
        try: await event.delete()
        except: pass
        chat = await event.get_chat()
        cid = event.chat_id
        name = getattr(chat, "title", "Unknown")
        wl = RAID_DB.get("whitelist", [])
        if cid not in wl:
            return await raid_send_log(f"ℹ️ Not whitelisted: **{name}**")
        wl.remove(cid)
        RAID_DB["whitelist"] = wl
        raid_save_db(RAID_DB)
        await raid_send_log(f"🗑️ Removed: **{name}** (`{cid}`)")
    except Exception as e:
        await raid_send_log(f"❌ {e}")


@CipherElite.on(events.NewMessage(pattern=r"\.\.wl\s+list$"))
@rishabh()
async def cmd_wl_list(event):
    try:
        wl = RAID_DB.get("whitelist", [])
        if not wl:
            return await event.reply("📭 No whitelisted groups.")
        lines = ["📋 **Whitelisted**\n"]
        for cid in wl:
            try:
                e = await CipherElite.get_entity(cid)
                name = getattr(e, "title", "Unknown")
            except Exception:
                name = "Unknown"
            lines.append(f"• **{name}** (`{cid}`)")
        await event.reply("\n".join(lines))
    except Exception as e:
        await event.reply(f"❌ {e}")


@CipherElite.on(events.NewMessage(pattern=r"\.commands$"))
@rishabh()
async def cmd_commands(event):
    await event.reply(
        "📖 **RAID CHEAT SHEET**\n"
        "━━━━━━━━━━━━━━━━━━━━\n"
        "`.cryptoraid` — status\n"
        "`.cryptoraid_stats` — stats\n"
        "`.cryptoraid_queue` — queue\n"
        "`.cryptoraid_pause` / `_resume`\n"
        "`.cryptoraid_reset`\n"
        "`..wl` — whitelist current\n"
        "`..wl off` — unwhitelist\n"
        "`..wl list` — list groups\n\n"
        "**Natural language (DM only):**\n"
        "• whats our raid status\n"
        "• pause all raids\n"
        "• resume all raids\n"
        "• whitelist this group\n"
        "• show me all groups for raid replies\n"
        "• whats our raid queue\n"
        "• whats our raid stats"
    )


# ═══════════════════════════════════════════════════════════════
#  CALLBACK HANDLERS (buttons)
# ═══════════════════════════════════════════════════════════════

async def raid_handle_cb(event, data):
    parts = data.split(":")
    action = parts[0]

    # ── reply pick
    if action == "copy":
        try:
            idx = int(parts[1])
            cur = RAID_DB.get("current_raid")
            if not cur:
                return await event.answer("No active raid", alert=True)
            opts = cur.get("reply_options", [])
            if idx >= len(opts):
                return await event.answer("Invalid", alert=True)
            chosen = opts[idx]
            cur["chosen_reply"] = chosen
            RAID_DB["current_raid"] = cur
            raid_save_db(RAID_DB)
            await event.answer(f"✅ Reply #{idx+1} selected")
            new_text = (
                f"🎯 **RAID #{cur['raid_id']}**\n"
                f"📍 {cur['chat_name']}\n"
                f"━━━━━━━━━━━━━━━━━━━━\n"
                f"📋 **Selected reply #{idx+1}:**\n\n"
                f"`{chosen}`\n\n"
                f"**Long-press the reply above to copy**\n"
                f"Then tap 🔗 to open and paste."
            )
            deeplink = cur.get("link_deeplink") or f"https://{cur['link']}"
            buttons = [
                [Button.inline("🔗 Open X post", url=deeplink)],
                [Button.inline("✅ Done — I posted it", f"done:{cur['raid_id']}".encode())],
            ]
            try:
                await event.edit(new_text, buttons=buttons)
            except Exception as e:
                rdbg(f"edit err: {e}")
        except Exception as e:
            await event.answer(f"err: {e}", alert=True)
        return

    # ── done
    if action == "done":
        try:
            rid = parts[1]
            cur = RAID_DB.get("current_raid")
            if not cur or str(cur.get("raid_id")) != rid:
                return await event.answer("Not current raid", alert=True)
            cur["manual_done"] = True
            cur["manual_done_ts"] = raid_now().timestamp()
            cur["steps"].append(
                f"5️⃣ ✅ YOU POSTED IT\n"
                f"   ▸ Waiting {VERIFY_WAIT_AFTER_DONE}s then verify\n"
                f"   ▸ Time: {raid_now().strftime('%I:%M:%S %p')}"
            )
            RAID_DB["current_raid"] = cur
            raid_save_db(RAID_DB)
            if cur.get("log_msg_id"):
                await raid_edit_log(
                    cur["log_msg_id"],
                    raid_build_card(cur["raid_id"], cur["chat_name"],
                                    f"https://{cur['link']}", cur["steps"], "processing"),
                    cur.get("log_chat_id")
                )
            await event.answer("✅ Marked done")
        except Exception as e:
            await event.answer(f"err: {e}", alert=True)
        return

    await event.answer("unknown")


# ═══════════════════════════════════════════════════════════════
#  NATURAL LANGUAGE HANDLERS
# ═══════════════════════════════════════════════════════════════

NL_MAP = [
    (r"(what'?s?\s+)?(our\s+)?raid\s+status", ".cryptoraid"),
    (r"pause\s+(all\s+)?raids?", ".cryptoraid_pause"),
    (r"resume\s+(all\s+)?raids?", ".cryptoraid_resume"),
    (r"whitelist\s+this\s+group", "..wl"),
    (r"remove\s+this\s+group", "..wl off"),
    (r"unwhitelist", "..wl off"),
    (r"(show|list)\s+(me\s+)?(all\s+)?groups?\s+for\s+raid", "..wl list"),
    (r"show\s+whitelist", "..wl list"),
    (r"(what'?s?\s+)?(our\s+)?raid\s+queue", ".cryptoraid_queue"),
    (r"(what'?s?\s+)?(our\s+)?raid\s+stats?", ".cryptoraid_stats"),
]


async def raid_nl_match(text):
    t = (text or "").lower().strip()
    for pat, cmd in NL_MAP:
        if re.search(pat, t):
            return cmd, "regex"
    if not ai_config.is_enabled():
        return None, None
    client = raid_gemini_client()
    if client is None:
        return None, None
    commands = [
        ".cryptoraid - status",
        ".cryptoraid_stats - stats",
        ".cryptoraid_queue - queue",
        ".cryptoraid_pause - pause raids",
        ".cryptoraid_resume - resume raids",
        "..wl - whitelist current group",
        "..wl off - remove whitelist",
        "..wl list - list whitelisted",
    ]
    prompt = (
        f'User said: "{text}"\n\n'
        f"Available commands:\n" + "\n".join(commands) +
        "\n\nReply with ONLY the exact command, or NONE if nothing matches."
    )
    try:
        from google.genai import types
        resp = await client.aio.models.generate_content(
            model="gemini-3.5-flash-lite",
            contents=[types.Content(role="user", parts=[types.Part(text=prompt)])],
            config=types.GenerateContentConfig(max_output_tokens=20, temperature=0.1),
        )
        out = (resp.text or "").strip().strip("`")
        if out.startswith(".") or out.startswith(".."):
            return out, "gemini"
    except Exception as e:
        rdbg(f"NL err: {e}")
    return None, None


@CipherElite.on(events.NewMessage(func=lambda e: e.is_private and not e.out))
async def raid_nl_handler(event):
    try:
        text = (event.raw_text or "").strip()
        if not text or text.startswith((".", "..")):
            return
        if event.sender_id == RAIDAR_USER_ID:
            return
        if len(text) < 4 or len(text) > 200:
            return
        me = await CipherElite.get_me()
        if event.sender_id != me.id:
            return
        cmd, source = await raid_nl_match(text)
        if not cmd:
            return
        rdbg(f"NL ({source}): '{text}' → '{cmd}'")
        await CipherElite.send_message("me", cmd)
    except Exception as e:
        print(f"[cryptoraid] NL err: {e}")

print("[cryptoraid] MODULE LOADED — chunk 2")

# ═══ END OF CHUNK 2 ═══
# ═══════════════════════════════════════════════════════════════
#  SMASH DETECTOR — ALL groups
# ═══════════════════════════════════════════════════════════════

@CipherElite.on(events.NewMessage)
async def raid_detector(event):
    try:
        if RAID_DB.get("paused"):
            return
        text = event.raw_text or ""
        if text.startswith(".") or text.startswith(".."):
            return
        if not raid_has_intent(text):
            return
        urls = raid_extract_x_urls(text)
        if not urls:
            return
        smashed = RAID_DB.get("smashed", {})
        new_urls = [u for u in urls if u not in smashed]
        if not new_urls:
            return
        if not event.buttons:
            return

        # find smash button
        clicked_row, clicked_col, clicked_text = None, None, None
        for r_idx, row in enumerate(event.buttons):
            for c_idx, btn in enumerate(row):
                btn_text = (getattr(btn, "text", "") or "").strip()
                if SMASH_BUTTON in btn_text:
                    clicked_row, clicked_col, clicked_text = r_idx, c_idx, btn_text
                    break
            if clicked_row is not None:
                break
        if clicked_row is None:
            for r_idx, row in enumerate(event.buttons):
                for c_idx, btn in enumerate(row):
                    btn_text = (getattr(btn, "text", "") or "").strip()
                    if any(t in btn_text for t in OTHER_TARGETS):
                        clicked_row, clicked_col, clicked_text = r_idx, c_idx, btn_text
                        break
                if clicked_row is not None:
                    break
        if clicked_row is None:
            return

        # click
        try:
            await event.click(clicked_row, clicked_col)
        except FloodWaitError as e:
            await asyncio.sleep(e.seconds)
            try: await event.click(clicked_row, clicked_col)
            except: return
        except Exception as e:
            print(f"[cryptoraid] click err: {e}")
            return

        chat = await event.get_chat()
        chat_name = getattr(chat, "title", "Unknown")
        chat_id = event.chat_id
        stamp = raid_now_dict()

        for url in new_urls:
            smashed[url] = {
                "date": stamp["date"], "time": stamp["time"],
                "time12": stamp["time12"], "ts": stamp["ts"],
                "chat": chat_name, "chat_id": chat_id, "button": clicked_text,
            }
        RAID_DB["smashed"] = smashed
        RAID_DB["count"] = RAID_DB.get("count", 0) + len(new_urls)
        raid_num = RAID_DB["count"]
        raid_id = f"{raid_num}_{int(stamp['ts'])}"
        raid_save_db(RAID_DB)

        is_wl = raid_is_wl(chat_id)

        steps = [f"1️⃣ 👊 SMASH DONE ✅\n   ▸ Clicked `{clicked_text}`"]

        if not is_wl:
            steps.append(f"2️⃣ ⛔ NOT WHITELISTED\n   ▸ `{chat_name}` — smash only, no reply flow")
            card = raid_build_card(raid_id, chat_name, f"https://{new_urls[0]}", steps, "done")
            await raid_send_log(card)
            return

        steps.append(f"2️⃣ ✅ WHITELISTED\n   ▸ Reply flow initiated")
        steps.append(f"3️⃣ ⏳ WAITING FOR RAIDAR DM #1...")

        raid_obj = {
            "raid_id": raid_id,
            "chat_id": chat_id,
            "chat_name": chat_name,
            "msg_id": event.message.id,
            "link": new_urls[0],
            "link_deeplink": f"https://{new_urls[0]}",
            "ts": stamp["ts"],
            "date": stamp["date"],
            "time12": stamp["time12"],
            "clicked_button": clicked_text,
            "status": "queued",
            "steps": steps,
            "log_msg_id": None,
            "log_chat_id": REPLY_LOG_ID,
            "reply_options": [],
            "chosen_reply": None,
            "manual_done": False,
            "manual_done_ts": None,
            "dm1_received": False,
            "dm1_time": None,
            "dm2_received": False,
            "dm2_time": None,
            "verify_clicked": False,
        }
        queue = RAID_DB.get("queue", [])
        queue.append(raid_obj)
        RAID_DB["queue"] = queue
        raid_save_db(RAID_DB)

        card = raid_build_card(raid_id, chat_name, f"https://{new_urls[0]}", steps, "queued")
        log_msg = await raid_send_log(card, REPLY_LOG_ID)
        if log_msg:
            raid_obj["log_msg_id"] = log_msg.id
            for i, r in enumerate(queue):
                if r["raid_id"] == raid_id:
                    queue[i]["log_msg_id"] = log_msg.id
                    break
            RAID_DB["queue"] = queue
            raid_save_db(RAID_DB)

        if not PROCESSING["active"]:
            asyncio.create_task(raid_process_queue())
    except Exception as e:
        print(f"[cryptoraid] detector err: {e}")


# ═══════════════════════════════════════════════════════════════
#  RAIDAR DM WATCHER
# ═══════════════════════════════════════════════════════════════

@CipherElite.on(events.NewMessage(from_users=RAIDAR_USER_ID))
async def raidar_watcher(event):
    try:
        text = event.raw_text or ""
        stamp = raid_now_dict()
        urls = raid_extract_x_urls(text)
        dm_link = urls[0] if urls else None

        # ── DM #1: smash confirmed
        if "How to earn reply XP" in text or "Raid Tweet" in text:
            cur = RAID_DB.get("current_raid")
            if cur and dm_link and dm_link == cur.get("link"):
                cur["dm1_received"] = True
                cur["dm1_time"] = stamp["time12"]
                cur["steps"].append(
                    f"4️⃣ 📩 RAIDAR DM #1 ✅\n"
                    f"   ▸ Matched link\n   ▸ Time: {stamp['time12']}"
                )
                raid_store_dm_link(dm_link, cur.get("chat_id"), cur.get("raid_id"))
                RAID_DB["current_raid"] = cur
                raid_save_db(RAID_DB)
                if cur.get("log_msg_id"):
                    await raid_edit_log(
                        cur["log_msg_id"],
                        raid_build_card(cur["raid_id"], cur["chat_name"],
                                        f"https://{cur['link']}", cur["steps"], "processing"),
                        cur.get("log_chat_id")
                    )
                rdbg(f"DM#1 matched raid {cur['raid_id']}")
            else:
                rdbg(f"DM#1 no match (link={dm_link})")
            return

        # ── DM #2: XP confirmed
        if "Reply verified" in text or "Received 3 XP" in text or "XP" in text:
            cur = RAID_DB.get("current_raid")
            if cur and cur.get("manual_done"):
                cur["dm2_received"] = True
                cur["dm2_time"] = stamp["time12"]
                cur["steps"].append(
                    f"8️⃣ 🎉 RAIDAR DM #2 — XP CONFIRMED ✅\n"
                    f"   ▸ \"{text[:100]}\"\n   ▸ Time: {stamp['time12']}"
                )
                if cur.get("log_msg_id"):
                    await raid_edit_log(
                        cur["log_msg_id"],
                        raid_build_card(cur["raid_id"], cur["chat_name"],
                                        f"https://{cur['link']}", cur["steps"], "done"),
                        cur.get("log_chat_id")
                    )
                await raid_send_log(
                    f"🎉 **RAID #{cur['raid_id']} WON** — {cur['chat_name']}\n"
                    f"🔗 {cur['link']}\n🕐 {stamp['time12']}",
                    SMASH_LOG_ID
                )
                completed = RAID_DB.get("completed", [])
                completed.append({
                    "raid_id": cur["raid_id"], "chat": cur["chat_name"],
                    "link": cur["link"], "date": stamp["date"],
                    "time12": stamp["time12"], "status": "done",
                })
                RAID_DB["completed"] = completed[-100:]
                RAID_DB["current_raid"] = None
                raid_save_db(RAID_DB)
                await raid_dm_owner(f"🎉 Raid #{cur['raid_id']} WON — XP confirmed!")
            return

        rdbg(f"raidar unknown: {text[:100]}")
    except Exception as e:
        print(f"[cryptoraid] raidar watcher err: {e}")


# ═══════════════════════════════════════════════════════════════
#  PROCESS QUEUE
# ═══════════════════════════════════════════════════════════════

async def raid_process_queue():
    if PROCESSING["active"]:
        return
    PROCESSING["active"] = True
    try:
        while True:
            queue = RAID_DB.get("queue", [])
            if not queue:
                break
            raid = queue.pop(0)
            RAID_DB["queue"] = queue
            RAID_DB["current_raid"] = raid
            raid_save_db(RAID_DB)

            raid_id = raid["raid_id"]
            chat_name = raid["chat_name"]
            link = raid["link"]
            log_msg_id = raid.get("log_msg_id")
            log_chat_id = raid.get("log_chat_id")

            try:
                # wait for raidar DM #1 (max 15s)
                for _ in range(DM1_WAIT_SECONDS * 2):
                    await asyncio.sleep(0.5)
                    cur = RAID_DB.get("current_raid")
                    if cur and cur.get("dm1_received"):
                        raid = cur
                        break

                raid = RAID_DB.get("current_raid", raid)
                steps = raid["steps"]

                # generate replies
                steps.append(f"5️⃣ 🧠 GENERATING 4 REPLIES...")
                if log_msg_id:
                    await raid_edit_log(log_msg_id, raid_build_card(raid_id, chat_name, f"https://{link}", steps, "processing"), log_chat_id)

                replies = await raid_gen_replies(link, chat_name)
                raid["reply_options"] = replies
                steps[-1] = f"5️⃣ 🧠 4 REPLIES READY ✅"
                RAID_DB["current_raid"] = raid
                raid_save_db(RAID_DB)
                if log_msg_id:
                    await raid_edit_log(log_msg_id, raid_build_card(raid_id, chat_name, f"https://{link}", steps, "processing"), log_chat_id)

                # DM owner
                steps.append(f"6️⃣ 📱 SENDING DM...")
                if log_msg_id:
                    await raid_edit_log(log_msg_id, raid_build_card(raid_id, chat_name, f"https://{link}", steps, "processing"), log_chat_id)

                dm_text = (
                    f"🎯 **RAID #{raid_id}**\n"
                    f"📍 {chat_name}\n"
                    f"━━━━━━━━━━━━━━━━━━━━\n"
                    f"**Pick a reply:**\n\n"
                    + "\n".join([f"**{i+1}.** {r}" for i, r in enumerate(replies)])
                    + f"\n\n━━━━━━━━━━━━━━━━━━━━\n"
                    f"Tap a number → you'll get the reply + link + Done button."
                )
                dm_buttons = [[
                    Button.inline("1️⃣", b"copy:0"),
                    Button.inline("2️⃣", b"copy:1"),
                    Button.inline("3️⃣", b"copy:2"),
                    Button.inline("4️⃣", b"copy:3"),
                ]]
                dm = await raid_dm_owner(dm_text, dm_buttons)
                if dm:
                    steps[-1] = f"6️⃣ 📱 DM SENT ✅"
                else:
                    steps[-1] = f"6️⃣ ❌ DM FAILED"
                RAID_DB["current_raid"] = raid
                raid_save_db(RAID_DB)
                if log_msg_id:
                    await raid_edit_log(log_msg_id, raid_build_card(raid_id, chat_name, f"https://{link}", steps, "waiting"), log_chat_id)

                if not dm:
                    steps.append("⛔ Queue bot offline — aborting reply flow")
                    if log_msg_id:
                        await raid_edit_log(log_msg_id, raid_build_card(raid_id, chat_name, f"https://{link}", steps, "failed"), log_chat_id)
                    RAID_DB["current_raid"] = None
                    raid_save_db(RAID_DB)
                    continue

                # wait for Done tap (max 10 min)
                for _ in range(MANUAL_DONE_TIMEOUT * 2):
                    await asyncio.sleep(0.5)
                    cur = RAID_DB.get("current_raid")
                    if cur and cur.get("manual_done"):
                        raid = cur
                        break

                raid = RAID_DB.get("current_raid", raid)
                if not raid.get("manual_done"):
                    steps = raid["steps"]
                    steps.append(f"⏰ TIMEOUT — no Done tap")
                    if log_msg_id:
                        await raid_edit_log(log_msg_id, raid_build_card(raid_id, chat_name, f"https://{link}", steps, "failed"), log_chat_id)
                    RAID_DB["current_raid"] = None
                    raid_save_db(RAID_DB)
                    continue

                # 30s wait
                steps = raid["steps"]
                steps.append(f"7️⃣ ⏳ WAITING {VERIFY_WAIT_AFTER_DONE}s...")
                if log_msg_id:
                    await raid_edit_log(log_msg_id, raid_build_card(raid_id, chat_name, f"https://{link}", steps, "processing"), log_chat_id)

                await asyncio.sleep(VERIFY_WAIT_AFTER_DONE)

                # verify click
                verify_clicked = False
                try:
                    msg = await CipherElite.get_messages(raid["chat_id"], ids=raid["msg_id"])
                    if msg and msg.buttons:
                        for r_idx, row in enumerate(msg.buttons):
                            for c_idx, btn in enumerate(row):
                                btxt = (getattr(btn, "text", "") or "").strip()
                                if "Verify" in btxt or "✅" in btxt:
                                    await msg.click(r_idx, c_idx)
                                    verify_clicked = True
                                    break
                            if verify_clicked:
                                break
                except Exception as e:
                    print(f"[cryptoraid] verify err: {e}")

                steps[-1] = f"7️⃣ {'✅ VERIFY CLICKED' if verify_clicked else '⚠️ VERIFY NOT FOUND'}"
                raid["verify_clicked"] = verify_clicked
                RAID_DB["current_raid"] = raid
                raid_save_db(RAID_DB)
                if log_msg_id:
                    await raid_edit_log(log_msg_id, raid_build_card(raid_id, chat_name, f"https://{link}", steps, "processing"), log_chat_id)

                # wait for DM #2
                steps.append(f"⏳ WAITING FOR DM #2 ({DM2_WAIT_SECONDS}s)...")
                if log_msg_id:
                    await raid_edit_log(log_msg_id, raid_build_card(raid_id, chat_name, f"https://{link}", steps, "processing"), log_chat_id)

                for _ in range(DM2_WAIT_SECONDS * 2):
                    await asyncio.sleep(0.5)
                    cur = RAID_DB.get("current_raid")
                    if cur and cur.get("dm2_received"):
                        break

                raid = RAID_DB.get("current_raid", raid)
                if not raid.get("dm2_received"):
                    steps[-1] = f"❌ NO DM #2 IN {DM2_WAIT_SECONDS}s"
                    if log_msg_id:
                        await raid_edit_log(log_msg_id, raid_build_card(raid_id, chat_name, f"https://{link}", steps, "failed"), log_chat_id)
                    failed = RAID_DB.get("failed", [])
                    failed.append({
                        "raid_id": raid_id, "chat": chat_name, "link": link,
                        "date": raid.get("date"), "time12": raid.get("time12"),
                        "reason": "no_dm2",
                    })
                    RAID_DB["failed"] = failed[-50:]
                    RAID_DB["current_raid"] = None
                    raid_save_db(RAID_DB)
                    await raid_dm_owner(f"❌ Raid #{raid_id} — no XP")
            except Exception as e:
                print(f"[cryptoraid] proc err {raid_id}: {e}")
                RAID_DB["current_raid"] = None
                raid_save_db(RAID_DB)
    finally:
        PROCESSING["active"] = False
        RAID_DB["current_raid"] = None
        raid_save_db(RAID_DB)


# ═══════════════════════════════════════════════════════════════
#  BOOTSTRAP
# ═══════════════════════════════════════════════════════════════

async def raid_bootstrap():
    try:
        await asyncio.sleep(12)
        await raid_start_bot()
        rdbg("bootstrap complete")
    except Exception as e:
        print(f"[cryptoraid] bootstrap err: {e}")


try:
    asyncio.create_task(raid_bootstrap())
except Exception as e:
    print(f"[cryptoraid] bootstrap init err: {e}")

print("[cryptoraid] MODULE LOADED SUCCESSFULLY — v6.0 ready")


# ╔══════════════════════════════════════════════════════════════╗
# ║  === END OF CRYPTORAID v6.0 ===                              ║
# ╚══════════════════════════════════════════════════════════════╝
