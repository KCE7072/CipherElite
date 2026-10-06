# =============================================================================
#  CipherElite Plugin - cryptoraid v7.1
#  Multi-source link extraction + recency fallback + one-DM edited flow
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

print("[cryptoraid] IMPORTING v7.1")

VERSION = "7.1.0"
CATEGORY = "utilities"

RAID_WAT = timezone(timedelta(hours=1))

def raid_now():
    return datetime.now(RAID_WAT)

# ═══════════════════════════════════════════════════════════════
#  CONFIG
# ═══════════════════════════════════════════════════════════════

SMASH_LOG_ID = -1004453857887
RAIDAR_USER_ID = 5994885234
OWNER_USER_ID = 7616645514

RAID_KEYWORDS = ['raid', 'smash', 'retweet', 'raid tweet', 'reply on x', 'lfg raid']
SMASH_BUTTON = '👊'
OTHER_TARGETS = ['🤛', '✊', '🤜', 'Verify', 'Verified', '✅', 'Confirmed']

VERIFY_WAIT_AFTER_DONE = 10
DM2_WAIT_SECONDS = 60
MANUAL_DONE_TIMEOUT = 900
RECENCY_MATCH_WINDOW = 60
DEBUG = True
RAID_DM_KEEP = 30


def rdbg(msg):
    if DEBUG:
        print(f"[cryptoraid] {msg}")


# ═══════════════════════════════════════════════════════════════
#  STORAGE
# ═══════════════════════════════════════════════════════════════

RAID_ROOT = Path(__file__).parent.parent
RAID_DB_DIR = RAID_ROOT / "DB"
RAID_DB_DIR.mkdir(exist_ok=True)
RAID_DB_FILE = RAID_DB_DIR / "cryptoraid_v7.json"
QUEUE_BOT_FILE = RAID_DB_DIR / "queue_bot_config.json"
QUEUE_BOT_SESSION = RAID_DB_DIR / "queue_bot_raid"


def raid_load_db():
    try:
        if RAID_DB_FILE.exists():
            return json.loads(RAID_DB_FILE.read_text(encoding="utf-8"))
    except Exception as e:
        print(f"[cryptoraid] load err: {e}")
    return {
        "smashed": {}, "count": 0, "whitelist": [],
        "awaiting_dm": [],
        "current_raid": None,
        "completed": [], "failed": [],
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
#  TOKEN
# ═══════════════════════════════════════════════════════════════

def raid_load_token():
    tok = os.getenv("KCE_QUEUE_BOT_TOKEN", "").strip()
    if tok and ":" in tok and len(tok) > 40:
        rdbg(f"token from env (len={len(tok)})")
        return tok
    try:
        if QUEUE_BOT_FILE.exists():
            data = json.loads(QUEUE_BOT_FILE.read_text(encoding="utf-8"))
            tok = data.get("token", "").strip()
            if tok and ":" in tok and len(tok) > 40:
                rdbg(f"token from file (len={len(tok)})")
                return tok
    except Exception as e:
        print(f"[cryptoraid] token file err: {e}")
    rdbg("NO VALID TOKEN")
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


def raid_tweet_id(url):
    m = re.search(r'/status/(\d+)', url or "")
    return m.group(1) if m else None


def raid_extract_link_from_msg(msg):
    """Try MULTIPLE sources for x/twitter link from a message object."""
    if not msg:
        return None

    # 1) text body
    try:
        text = getattr(msg, "raw_text", None) or getattr(msg, "message", None) or ""
        urls = raid_extract_x_urls(text)
        if urls:
            return urls[0]
    except Exception:
        pass

    # 2) web preview
    try:
        wp = getattr(msg, "web_preview", None)
        if wp:
            for attr in ("url", "display_url"):
                val = getattr(wp, attr, None)
                if val and ("x.com" in val or "twitter.com" in val):
                    return raid_norm_url(val)
    except Exception:
        pass

    # 3) entities (URL entities)
    try:
        entities = getattr(msg, "entities", None) or []
        for ent in entities:
            ent_url = getattr(ent, "url", None)
            if ent_url and ("x.com" in ent_url or "twitter.com" in ent_url):
                return raid_norm_url(ent_url)
    except Exception:
        pass

    # 4) button URLs
    try:
        buttons = getattr(msg, "buttons", None)
        if buttons:
            for row in buttons:
                for btn in row:
                    burl = getattr(btn, "url", None)
                    if burl and ("x.com" in burl or "twitter.com" in burl):
                        return raid_norm_url(burl)
    except Exception:
        pass

    # 5) reply_to_msg_id chain — check if the message replies to one with a link
    return None


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


def raid_short_preview(text, max_len=60):
    if not text:
        return ""
    t = " ".join(text.split())
    if len(t) > max_len:
        return t[:max_len].rstrip() + "..."
    return t


async def raid_fetch_tweet(url):
    try:
        m = re.search(r'(?:twitter\.com|x\.com)/([^/]+)/status/(\d+)', url)
        if not m:
            return None
        user, tweet_id = m.group(1), m.group(2)
        api = f"https://api.fxtwitter.com/{user}/status/{tweet_id}"
        timeout = aiohttp.ClientTimeout(total=10)
        async with aiohttp.ClientSession(timeout=timeout) as s:
            async with s.get(api) as r:
                if r.status != 200:
                    rdbg(f"fxtwitter HTTP {r.status}")
                    return None
                data = await r.json()
        tweet = data.get("tweet", {}) or {}
        author = tweet.get("author", {}) or {}
        return {
            "text": (tweet.get("text") or "")[:600],
            "author": author.get("screen_name", "?"),
            "name": author.get("name", "?"),
            "likes": tweet.get("likes", 0),
            "retweets": tweet.get("retweets", 0),
            "replies": tweet.get("replies", 0),
        }
    except Exception as e:
        rdbg(f"fetch_tweet err: {e}")
        return None


# ═══════════════════════════════════════════════════════════════
#  LOG SENDERS
# ═══════════════════════════════════════════════════════════════

async def raid_send_log(text):
    try:
        return await CipherElite.send_message(SMASH_LOG_ID, text)
    except Exception as e:
        print(f"[cryptoraid] log err: {e}")
        return None


async def raid_edit_log(msg_id, text):
    try:
        await CipherElite.edit_message(SMASH_LOG_ID, msg_id, text)
    except Exception as e:
        print(f"[cryptoraid] edit err: {e}")


# ═══════════════════════════════════════════════════════════════
#  LOG CARD
# ═══════════════════════════════════════════════════════════════

def raid_build_card(raid_id, chat_name, link, steps, status="processing"):
    emoji = {
        "done": "✅", "failed": "❌", "queued": "⏸️",
        "waiting": "⏳", "processing": "🎯", "skip": "⏭️",
    }.get(status, "🎯")
    result_label = {
        "done": "SUCCESS", "failed": "FAILED",
        "queued": "QUEUED", "waiting": "YOUR TURN",
        "processing": "PROCESSING", "skip": "SMASH ONLY",
    }.get(status, "PROCESSING")

    next_step = {
        "skip": "⏭️ Not whitelisted — smash logged only.",
        "queued": "📩 Waiting for Raidar DM...",
        "waiting": "👤 Check your DM — pick → paste → tap Done.",
        "processing": "⚙️ Verifying... sit tight.",
        "done": "🎉 XP confirmed. All done.",
        "failed": "🚨 Failed — see steps above.",
    }.get(status, "⏳ Processing...")

    header = (
        "╔══════════════════════════════════════╗\n"
        f"║  {emoji}  RAID {raid_id}\n"
        f"║  📍  {chat_name[:32]}\n"
        f"║  🕐  {raid_now().strftime('%I:%M:%S %p')} WAT\n"
        "╚══════════════════════════════════════╝"
    )

    body = ""
    for s in steps:
        if "ORIGINAL POST" in s and "▸" in s:
            lines = s.split("\n")
            new_lines = []
            for ln in lines:
                if ln.strip().startswith("▸"):
                    m = re.search(r'"(.*)"', ln)
                    if m:
                        short = raid_short_preview(m.group(1), 60)
                        new_lines.append(f'   ▸ "{short}"')
                    else:
                        new_lines.append(ln[:90])
                else:
                    new_lines.append(ln)
            s = "\n".join(new_lines)
        body += "\n" + s + "\n"

    footer = (
        "\n━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        f"🎯 {next_step}\n"
        "━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        f"🔗 {link}\n"
        f"📊 {result_label}  •  {emoji} END"
    )
    return header + body + footer


# ═══════════════════════════════════════════════════════════════
#  DM BUILDER — one DM, edited at each step
# ═══════════════════════════════════════════════════════════════

def dm_step_header(raid_id, chat_name, step_num, total_steps=5):
    filled = "●" * step_num
    empty = "○" * (total_steps - step_num)
    return (
        "╔══════════════════════════════════════╗\n"
        f"║  🎯  RAID #{raid_id}\n"
        f"║  📍  {chat_name[:30]}\n"
        f"║  🕐  {raid_now().strftime('%I:%M:%S %p')} WAT\n"
        f"║  {filled}{empty}  step {step_num}/{total_steps}\n"
        "╚══════════════════════════════════════╝"
    )


def dm_tweet_block(tweet_data, tweet_text, tweet_author, max_len=400):
    if not tweet_text:
        return "📝 ORIGINAL POST\n▸ (content unavailable)\n"
    return (
        "━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        f"📝 @{tweet_author}\n"
        f"💬 {tweet_text[:max_len]}\n"
        f"❤️ {tweet_data.get('likes', 0)}  🔁 {tweet_data.get('retweets', 0)}\n"
    )


def dm_build_step1(raid_id, chat_name, tweet_data, tweet_text, tweet_author, replies):
    header = dm_step_header(raid_id, chat_name, 1)
    tweet = dm_tweet_block(tweet_data, tweet_text, tweet_author)
    reply_list = "\n".join([f"**{i+1}.** {r}" for i, r in enumerate(replies)])
    return (
        f"{header}\n"
        f"{tweet}"
        "\n🎯 **PICK A REPLY**\n\n"
        f"{reply_list}\n\n"
        "━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        "  👇 Tap a number to select"
    )


def dm_build_step2(raid_id, chat_name, tweet_data, tweet_text, tweet_author, idx, chosen):
    header = dm_step_header(raid_id, chat_name, 2)
    tweet = dm_tweet_block(tweet_data, tweet_text, tweet_author, max_len=250)
    return (
        f"{header}\n"
        f"{tweet}"
        f"\n📋 **REPLY #{idx+1}** — tap to copy\n\n"
        f"`{chosen}`\n\n"
        "━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        "  1️⃣ Copy the reply above\n"
        "  2️⃣ Tap 🔗 to open the post\n"
        "  3️⃣ Paste on X\n"
        "  4️⃣ Come back → tap ✅ Done"
    )


def dm_build_step3(raid_id, chat_name, chosen):
    header = dm_step_header(raid_id, chat_name, 3)
    return (
        f"{header}\n"
        "━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        "⏳ **WAITING TO VERIFY**\n"
        "━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
        f"📋 Your reply:\n`{chosen}`\n\n"
        f"🕐 Waiting {VERIFY_WAIT_AFTER_DONE}s for X to register...\n\n"
        "━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        "  ⏳ Then I'll click Verify on Raidar"
    )


def dm_build_step4(raid_id, chat_name, verify_ok):
    header = dm_step_header(raid_id, chat_name, 4)
    status_line = (
        "✅ **VERIFY CLICKED**\n"
        "▸ Waiting for Raidar DM #2..."
        if verify_ok else
        "⚠️ **VERIFY BUTTON NOT FOUND**\n"
        "▸ Waiting for Raidar DM #2 anyway..."
    )
    return (
        f"{header}\n"
        "━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        f"{status_line}\n"
        "━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
        f"🕐 Waiting up to {DM2_WAIT_SECONDS}s for XP confirmation...\n\n"
        "━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        "  ⏳ Sit tight — final result coming"
    )


def dm_build_step5_success(raid_id, chat_name, chosen, tweet_data, tweet_text, tweet_author):
    header = dm_step_header(raid_id, chat_name, 5)
    tweet = dm_tweet_block(tweet_data, tweet_text, tweet_author, max_len=200)
    return (
        f"{header}\n"
        f"{tweet}"
        f"\n📋 **YOUR REPLY**\n\n"
        f"`{chosen}`\n\n"
        "━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        "✅ **XP CONFIRMED**\n"
        "━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
        "▸ Raidar verified your reply\n"
        "▸ +3 XP added to your account\n\n"
        "━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        "🎉 All done — watching for next raid"
    )


def dm_build_step5_fail(raid_id, chat_name, chosen, fail_reasons):
    header = dm_step_header(raid_id, chat_name, 5)
    return (
        f"{header}\n"
        f"\n📋 **YOUR REPLY**\n\n"
        f"`{chosen or '(not selected)'}`\n\n"
        "━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        "🚨 **WHY IT FAILED**\n"
        "━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
        f"{fail_reasons}\n\n"
        "━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        "🎯 **WHAT TO DO NEXT**\n"
        "━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
        "• Check the post on X — is your reply visible?\n"
        "• If yes, Raidar may have lagged\n"
        "• Bot continues with the next raid automatically\n\n"
        "━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        "  ❌ No XP earned this raid"
    )


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
        rdbg("no token")
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


async def raid_edit_dm(msg_id, text, buttons=None):
    if not QUEUE_BOT or not QUEUE_BOT.is_connected():
        return None
    try:
        return await QUEUE_BOT.edit_message(OWNER_USER_ID, msg_id, text, buttons=buttons)
    except Exception as e:
        rdbg(f"edit dm err: {e}")
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
        ".cryptoraid_reset - reset",
        ".cryptoraid_pause - pause",
        ".cryptoraid_resume - resume",
        ".commands - cheat sheet",
        "..wl - whitelist current group",
        "..wl off - remove whitelist",
        "..wl list - list whitelisted",
    ]
    add_handler("cryptoraid", commands, "🎯 Raid v7.1 — multi-source match")
    print("[cryptoraid] commands registered")

print("[cryptoraid] MODULE LOADED — chunk 1")

# ═══ END OF CHUNK 1 ═══
# ═══════════════════════════════════════════════════════════════
#  GEMINI — 4 TONE-MATCHED replies
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


async def raid_gen_replies(tweet_text, tweet_author):
    fallback = ["we outside 🚀", "nice one 🔥", "lfg fam 💪", "clean 🎯"]
    if not ai_config.is_enabled():
        return fallback
    client = raid_gemini_client()
    if client is None:
        return fallback

    prompt = f"""Generate 4 SHORT casual replies (max 5 words each) to this crypto raid tweet.

TWEET by @{tweet_author or '?'}:
\"{tweet_text[:300] if tweet_text else '(content unavailable)'}\"

Rules:
- lowercase
- 1 emoji max per reply
- 4 DIFFERENT replies
- friendly, real, not spammy
- Match the TONE of the tweet:
  • Formal/professional → clean English reply
  • Casual/informal → casual English reply
  • Nigerian/Pidgin tweet → Pidgin reply
  • Do NOT force pidgin unless the tweet is pidgin
- Do NOT mention the token name
- Sound like a real community member, not a bot

Output exactly 4 lines. Just the replies."""
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
        awaiting = RAID_DB.get("awaiting_dm", [])
        cur = RAID_DB.get("current_raid")
        completed = RAID_DB.get("completed", [])
        failed = RAID_DB.get("failed", [])
        today = raid_now().strftime("%Y-%m-%d")
        today_done = sum(1 for r in completed if r.get("date", "").startswith(today))
        paused = RAID_DB.get("paused", False)
        bot_st = "✅ online" if (QUEUE_BOT and QUEUE_BOT.is_connected()) else "❌ offline"
        msg = (
            f"🎯 **Crypto Raid v7.1**\n"
            f"━━━━━━━━━━━━━━━━━━━━\n"
            f"{'⏸️ PAUSED' if paused else '✅ Active'}\n"
            f"👊 Smashes: `{RAID_DB.get('count', 0)}`\n"
            f"✅ Done: `{len(completed)}` (today: `{today_done}`)\n"
            f"❌ Failed: `{len(failed)}`\n"
            f"📝 Whitelisted: `{len(wl)}`\n"
            f"📩 Awaiting DM: `{len(awaiting)}`\n"
            f"⚙️ Active: `{cur['raid_id'] if cur else 'None'}`\n"
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
        awaiting = RAID_DB.get("awaiting_dm", [])
        cur = RAID_DB.get("current_raid")
        lines = ["📦 **Queue**", "━━━━━━━━━━━━━━━━━━━━"]
        if cur:
            lines.append(f"⚙️ Active: #{cur.get('raid_id')} — {cur.get('chat_name', '?')}")
        if awaiting:
            lines.append(f"\nAwaiting Raidar DM ({len(awaiting)}):")
            for r in awaiting[:10]:
                lines.append(f"⏸️ #{r.get('raid_id')} — {r.get('chat_name', '?')}")
        else:
            lines.append("✅ No waiting raids")
        await event.reply("\n".join(lines))
    except Exception as e:
        await event.reply(f"❌ {e}")


@CipherElite.on(events.NewMessage(pattern=r"\.cryptoraid_reset$"))
@rishabh()
async def cmd_reset(event):
    RAID_DB["awaiting_dm"] = []
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
    await event.reply("⏸️ PAUSED")


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
        "`..wl list` — list\n\n"
        "**Natural language (DM only):**\n"
        "• whats our raid status\n"
        "• pause all raids / resume all raids\n"
        "• whitelist this group\n"
        "• show me all groups for raid replies\n"
        "• whats our raid queue\n"
        "• whats our raid stats"
    )


# ═══════════════════════════════════════════════════════════════
#  BUTTON HANDLERS
# ═══════════════════════════════════════════════════════════════

async def raid_handle_cb(event, data):
    parts = data.split(":")
    action = parts[0]

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

            td = cur.get("tweet_data") or {}
            step2_text = dm_build_step2(
                cur["raid_id"], cur["chat_name"],
                td, cur.get("tweet_text", ""), cur.get("tweet_author", ""),
                idx, chosen
            )
            deeplink = cur.get("link_deeplink") or f"https://{cur['link']}"
            step2_buttons = [
                [Button.url("🔗 Open X post", deeplink)],
                [Button.inline("✅ Done — I posted it", f"done:{cur['raid_id']}".encode())],
            ]
            try:
                await event.edit(step2_text, buttons=step2_buttons)
                rdbg(f"edit DM → step 2")
            except Exception as e:
                rdbg(f"edit err: {e}, fallback new msg")
                try:
                    await QUEUE_BOT.send_message(event.sender_id, step2_text, buttons=step2_buttons)
                except Exception:
                    pass
        except Exception as e:
            print(f"[cryptoraid] copy cb err: {e}")
        return

    if action == "done":
        try:
            rid = parts[1]
            cur = RAID_DB.get("current_raid")
            if not cur or str(cur.get("raid_id")) != rid:
                return await event.answer("Not current raid", alert=True)
            if cur.get("manual_done"):
                return await event.answer("Already done ✅", alert=True)

            cur["manual_done"] = True
            cur["manual_done_ts"] = raid_now().timestamp()
            RAID_DB["current_raid"] = cur
            raid_save_db(RAID_DB)

            await event.answer("✅ Confirmed — verifying soon")

            step3_text = dm_build_step3(
                cur["raid_id"], cur["chat_name"],
                cur.get("chosen_reply", "")
            )
            try:
                await event.edit(step3_text, buttons=None)
                rdbg(f"edit DM → step 3")
            except Exception as e:
                rdbg(f"edit err step3: {e}")
        except Exception as e:
            print(f"[cryptoraid] done cb err: {e}")
        return

    await event.answer("unknown")


# ═══════════════════════════════════════════════════════════════
#  NATURAL LANGUAGE
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
        ".cryptoraid_pause - pause",
        ".cryptoraid_resume - resume",
        "..wl - whitelist current group",
        "..wl off - remove whitelist",
        "..wl list - list whitelisted",
    ]
    prompt = (
        f'User said: "{text}"\n\nAvailable commands:\n' + "\n".join(commands) +
        "\n\nReply with ONLY the exact command, or NONE."
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
#  Multi-source link extraction (text + web_preview + entities + buttons)
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

        # ─── multi-source link extraction
        urls = raid_extract_x_urls(text)

        # fallback: web preview
        if not urls:
            try:
                wp = getattr(event.message, "web_preview", None)
                if wp:
                    for attr in ("url", "display_url"):
                        val = getattr(wp, attr, None)
                        if val and ("x.com" in val or "twitter.com" in val):
                            urls = [raid_norm_url(val)]
                            rdbg(f"link from web_preview: {val}")
                            break
            except Exception:
                pass

        # fallback: entities
        if not urls:
            try:
                for ent in (event.message.entities or []):
                    ent_url = getattr(ent, "url", None)
                    if ent_url and ("x.com" in ent_url or "twitter.com" in ent_url):
                        urls = [raid_norm_url(ent_url)]
                        rdbg(f"link from entity: {ent_url}")
                        break
            except Exception:
                pass

        # fallback: button URLs
        if not urls and event.buttons:
            try:
                for row in event.buttons:
                    for btn in row:
                        burl = getattr(btn, "url", None)
                        if burl and ("x.com" in burl or "twitter.com" in burl):
                            urls = [raid_norm_url(burl)]
                            rdbg(f"link from button: {burl}")
                            break
                    if urls:
                        break
            except Exception:
                pass

        if not urls:
            rdbg("no x link found in message")
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
        tweet_id = raid_tweet_id(new_urls[0])

        # ─── NOT whitelisted
        if not is_wl:
            tweet_data = await raid_fetch_tweet(new_urls[0])
            tweet_text = (tweet_data or {}).get("text", "")
            tweet_author = (tweet_data or {}).get("author", "")

            steps = [
                f"1️⃣ 👊 SMASH DONE ✅\n"
                f"   ▸ Detected raid + X link\n"
                f"   ▸ Clicked '{clicked_text}'"
            ]
            steps.append(
                f"2️⃣ ⛔ WHITELIST SKIP\n"
                f"   ▸ '{chat_name}' not in reply whitelist\n"
                f"   ▸ Smash logged only"
            )
            if tweet_text:
                short = raid_short_preview(tweet_text, 60)
                steps.append(f"📝 @{tweet_author}\n   ▸ \"{short}\"")
            else:
                steps.append(f"📝 ORIGINAL POST\n   ▸ (content unavailable)")
            card = raid_build_card(raid_id, chat_name, f"https://{new_urls[0]}", steps, "skip")
            await raid_send_log(card)
            return

        # ─── Whitelisted
        tweet_data = await raid_fetch_tweet(new_urls[0])
        tweet_text = (tweet_data or {}).get("text", "")
        tweet_author = (tweet_data or {}).get("author", "")

        steps = [
            f"1️⃣ 👊 SMASH DONE ✅\n"
            f"   ▸ Detected raid + X link\n"
            f"   ▸ Clicked '{clicked_text}'"
        ]
        steps.append(
            f"2️⃣ ✅ WHITELISTED\n"
            f"   ▸ Reply flow armed"
        )
        if tweet_text:
            short = raid_short_preview(tweet_text, 60)
            steps.append(f"📝 @{tweet_author}\n   ▸ \"{short}\"")
        else:
            steps.append(f"📝 ORIGINAL POST\n   ▸ (content unavailable)")
        steps.append(f"3️⃣ 📡 WAITING FOR RAIDAR DM...")

        raid_obj = {
            "raid_id": raid_id,
            "chat_id": chat_id,
            "chat_name": chat_name,
            "msg_id": event.message.id,
            "link": new_urls[0],
            "link_deeplink": f"https://{new_urls[0]}",
            "tweet_id": tweet_id,
            "ts": stamp["ts"],
            "date": stamp["date"],
            "time12": stamp["time12"],
            "clicked_button": clicked_text,
            "status": "awaiting_dm",
            "steps": steps,
            "log_msg_id": None,
            "dm_msg_id": None,
            "raidar_dm_msg_id": None,
            "reply_options": [],
            "chosen_reply": None,
            "manual_done": False,
            "manual_done_ts": None,
            "dm1_received": False,
            "dm1_time": None,
            "dm2_received": False,
            "dm2_time": None,
            "verify_clicked": False,
            "tweet_text": tweet_text,
            "tweet_author": tweet_author,
            "tweet_data": tweet_data or {},
        }
        awaiting = RAID_DB.get("awaiting_dm", [])
        awaiting.append(raid_obj)
        RAID_DB["awaiting_dm"] = awaiting[-50:]
        raid_save_db(RAID_DB)

        card = raid_build_card(raid_id, chat_name, f"https://{new_urls[0]}", steps, "queued")
        log_msg = await raid_send_log(card)
        if log_msg:
            raid_obj["log_msg_id"] = log_msg.id
            for i, r in enumerate(awaiting):
                if r["raid_id"] == raid_id:
                    awaiting[i]["log_msg_id"] = log_msg.id
                    break
            RAID_DB["awaiting_dm"] = awaiting
            raid_save_db(RAID_DB)

        rdbg(f"raid {raid_id} awaiting Raidar DM (tweet_id={tweet_id})")
    except Exception as e:
        print(f"[cryptoraid] detector err: {e}")

print("[cryptoraid] MODULE LOADED — chunk 3A")

# ═══ END OF CHUNK 3A ═══
# ═══════════════════════════════════════════════════════════════
#  RAIDAR DM WATCHER
#  DM #1 → activate raid (match by tweet_id OR recency)
#  DM #2 → XP confirmation
# ═══════════════════════════════════════════════════════════════

@CipherElite.on(events.NewMessage(from_users=RAIDAR_USER_ID))
async def raidar_watcher(event):
    try:
        text = event.raw_text or ""
        stamp = raid_now_dict()

        # ─── multi-source link extraction from the DM
        dm_link = raid_extract_link_from_msg(event.message)
        dm_tweet_id = raid_tweet_id(dm_link) if dm_link else None
        rdbg(f"raidar DM: link={dm_link} tid={dm_tweet_id}")

        # ── DM #1 (smash confirmed)
        if "How to earn reply XP" in text or "Raid Tweet" in text:
            awaiting = RAID_DB.get("awaiting_dm", [])
            match_idx = None
            match_reason = None

            # priority 1: exact tweet ID match
            if dm_tweet_id:
                for i, r in enumerate(awaiting):
                    if r.get("tweet_id") == dm_tweet_id:
                        match_idx = i
                        match_reason = f"tweet_id={dm_tweet_id}"
                        break

            # priority 2: recency — pick most recent awaiting raid within window
            if match_idx is None and awaiting:
                now_ts = raid_now().timestamp()
                for i in range(len(awaiting) - 1, -1, -1):
                    r = awaiting[i]
                    age = now_ts - r.get("ts", 0)
                    if age < RECENCY_MATCH_WINDOW:
                        match_idx = i
                        match_reason = f"recency (age={int(age)}s)"
                        break

            if match_idx is None:
                rdbg(f"DM#1 no match (tid={dm_tweet_id}, awaiting={len(awaiting)})")
                return

            raid = awaiting.pop(match_idx)
            RAID_DB["awaiting_dm"] = awaiting
            rdbg(f"DM#1 matched raid {raid['raid_id']} by {match_reason}")

            raid["dm1_received"] = True
            raid["dm1_time"] = stamp["time12"]
            raid["raidar_dm_msg_id"] = event.message.id
            raid["status"] = "active"
            raid["steps"].append(
                f"4️⃣ 📩 RAIDAR DM #1 ✅\n"
                f"   ▸ Matched: {match_reason}\n"
                f"   ▸ Time: {stamp['time12']}"
            )

            RAID_DB["current_raid"] = raid
            raid_save_db(RAID_DB)

            if raid.get("log_msg_id"):
                await raid_edit_log(
                    raid["log_msg_id"],
                    raid_build_card(raid["raid_id"], raid["chat_name"],
                                    f"https://{raid['link']}", raid["steps"], "processing")
                )

            if not PROCESSING["active"]:
                asyncio.create_task(raid_process_queue())
            return

        # ── DM #2 (XP confirmed)
        if "Reply verified" in text or "Received 3 XP" in text or "XP" in text:
            cur = RAID_DB.get("current_raid")
            if not cur:
                rdbg("DM#2: no active raid")
                return
            # tweet id match (if available)
            cur_tid = cur.get("tweet_id")
            if dm_tweet_id and cur_tid and dm_tweet_id != cur_tid:
                rdbg(f"DM#2 tid mismatch ({dm_tweet_id} != {cur_tid})")
                return
            if not cur.get("manual_done"):
                rdbg("DM#2 before Done tap — ignoring")
                return

            cur["dm2_received"] = True
            cur["dm2_time"] = stamp["time12"]
            cur["steps"].append(
                f"9️⃣ 🎉 RAIDAR DM #2 — XP CONFIRMED ✅\n"
                f"   ▸ \"{text[:80]}\"\n"
                f"   ▸ Time: {stamp['time12']}"
            )
            RAID_DB["current_raid"] = cur
            raid_save_db(RAID_DB)

            if cur.get("log_msg_id"):
                await raid_edit_log(
                    cur["log_msg_id"],
                    raid_build_card(cur["raid_id"], cur["chat_name"],
                                    f"https://{cur['link']}", cur["steps"], "done")
                )

            if cur.get("dm_msg_id"):
                success_text = dm_build_step5_success(
                    cur["raid_id"], cur["chat_name"],
                    cur.get("chosen_reply", ""),
                    cur.get("tweet_data") or {},
                    cur.get("tweet_text", ""),
                    cur.get("tweet_author", "")
                )
                await raid_edit_dm(cur["dm_msg_id"], success_text, buttons=None)

            completed = RAID_DB.get("completed", [])
            completed.append({
                "raid_id": cur["raid_id"], "chat": cur["chat_name"],
                "link": cur["link"], "date": stamp["date"],
                "time12": stamp["time12"], "status": "done",
            })
            RAID_DB["completed"] = completed[-100:]
            RAID_DB["current_raid"] = None
            raid_save_db(RAID_DB)
            rdbg(f"raid {cur['raid_id']} WON")
            return

        rdbg(f"raidar DM unknown pattern: {text[:80]}")
    except Exception as e:
        print(f"[cryptoraid] raidar watcher err: {e}")

print("[cryptoraid] MODULE LOADED — chunk 3B")

# ═══ END OF CHUNK 3B ═══
# ═══════════════════════════════════════════════════════════════
#  PROCESS QUEUE — flow runs when Raidar DM #1 matched
# ═══════════════════════════════════════════════════════════════

async def raid_process_queue():
    if PROCESSING["active"]:
        return
    PROCESSING["active"] = True
    try:
        while True:
            raid = RAID_DB.get("current_raid")
            if not raid:
                break
            if raid.get("status") != "active":
                break

            raid_id = raid["raid_id"]
            chat_name = raid["chat_name"]
            link = raid["link"]
            log_msg_id = raid.get("log_msg_id")

            try:
                # ─── generate 4 replies
                raid["steps"].append(f"5️⃣ 🧠 GENERATING 4 REPLIES...")
                RAID_DB["current_raid"] = raid
                raid_save_db(RAID_DB)
                if log_msg_id:
                    await raid_edit_log(
                        log_msg_id,
                        raid_build_card(raid_id, chat_name, f"https://{link}", raid["steps"], "processing")
                    )

                replies = await raid_gen_replies(
                    raid.get("tweet_text", ""),
                    raid.get("tweet_author", "")
                )
                raid["reply_options"] = replies
                raid["steps"][-1] = (
                    f"5️⃣ 🧠 4 REPLIES READY ✅\n"
                    + "\n".join([f"   {i+1}. {r}" for i, r in enumerate(replies)])
                )
                RAID_DB["current_raid"] = raid
                raid_save_db(RAID_DB)
                if log_msg_id:
                    await raid_edit_log(
                        log_msg_id,
                        raid_build_card(raid_id, chat_name, f"https://{link}", raid["steps"], "processing")
                    )

                # ─── send step 1 DM
                raid["steps"].append(f"6️⃣ 📱 SENDING DM...")
                RAID_DB["current_raid"] = raid
                raid_save_db(RAID_DB)
                if log_msg_id:
                    await raid_edit_log(
                        log_msg_id,
                        raid_build_card(raid_id, chat_name, f"https://{link}", raid["steps"], "processing")
                    )

                td = raid.get("tweet_data") or {}
                step1_text = dm_build_step1(
                    raid_id, chat_name,
                    td, raid.get("tweet_text", ""), raid.get("tweet_author", ""),
                    replies
                )
                dm_buttons = [[
                    Button.inline("1️⃣", b"copy:0"),
                    Button.inline("2️⃣", b"copy:1"),
                    Button.inline("3️⃣", b"copy:2"),
                    Button.inline("4️⃣", b"copy:3"),
                ]]

                dm_msg = await raid_dm_owner(step1_text, dm_buttons)
                if not dm_msg:
                    raid["steps"][-1] = f"6️⃣ ❌ DM FAILED — bot offline"
                    RAID_DB["current_raid"] = raid
                    raid_save_db(RAID_DB)
                    if log_msg_id:
                        await raid_edit_log(
                            log_msg_id,
                            raid_build_card(raid_id, chat_name, f"https://{link}", raid["steps"], "failed")
                        )
                    RAID_DB["current_raid"] = None
                    raid_save_db(RAID_DB)
                    continue

                raid["dm_msg_id"] = dm_msg.id
                raid["steps"][-1] = f"6️⃣ 📱 DM SENT ✅\n   ▸ Waiting for your pick..."
                RAID_DB["current_raid"] = raid
                raid_save_db(RAID_DB)
                if log_msg_id:
                    await raid_edit_log(
                        log_msg_id,
                        raid_build_card(raid_id, chat_name, f"https://{link}", raid["steps"], "waiting")
                    )

                # ─── WAIT for Done tap
                for _ in range(MANUAL_DONE_TIMEOUT * 2):
                    await asyncio.sleep(0.5)
                    cur = RAID_DB.get("current_raid")
                    if cur and cur.get("manual_done"):
                        raid = cur
                        break

                raid = RAID_DB.get("current_raid", raid)
                if not raid.get("manual_done"):
                    raid["steps"].append(f"⏰ TIMEOUT — no Done tap in {MANUAL_DONE_TIMEOUT//60} min")
                    if log_msg_id:
                        await raid_edit_log(
                            log_msg_id,
                            raid_build_card(raid_id, chat_name, f"https://{link}", raid["steps"], "failed")
                        )
                    RAID_DB["current_raid"] = None
                    raid_save_db(RAID_DB)
                    continue

                # ─── user tapped Done → wait 10s
                raid["steps"].append(
                    f"7️⃣ ✅ YOU POSTED IT\n"
                    f"   ▸ Reply: `{raid.get('chosen_reply', '?')[:60]}`\n"
                    f"   ▸ Time: {raid_now().strftime('%I:%M:%S %p')}"
                )
                raid["steps"].append(f"8️⃣ ⏳ WAITING {VERIFY_WAIT_AFTER_DONE}s...")
                RAID_DB["current_raid"] = raid
                raid_save_db(RAID_DB)
                if log_msg_id:
                    await raid_edit_log(
                        log_msg_id,
                        raid_build_card(raid_id, chat_name, f"https://{link}", raid["steps"], "processing")
                    )

                await asyncio.sleep(VERIFY_WAIT_AFTER_DONE)

                # ─── click Verify on the RAIDAR DM (stored earlier)
                verify_clicked = False
                try:
                    raidar_msg_id = raid.get("raidar_dm_msg_id")
                    if raidar_msg_id:
                        msg = await CipherElite.get_messages(RAIDAR_USER_ID, ids=raidar_msg_id)
                        if msg and msg.buttons:
                            for r_idx, row in enumerate(msg.buttons):
                                for c_idx, btn in enumerate(row):
                                    btxt = (getattr(btn, "text", "") or "").strip()
                                    if "Verify" in btxt or "✅" in btxt:
                                        await msg.click(r_idx, c_idx)
                                        verify_clicked = True
                                        rdbg(f"clicked Verify on Raidar DM ({raidar_msg_id})")
                                        break
                                if verify_clicked:
                                    break
                        else:
                            rdbg(f"no buttons on raidar msg {raidar_msg_id}")
                    else:
                        rdbg("no raidar_dm_msg_id stored")
                except Exception as e:
                    print(f"[cryptoraid] verify err: {e}")

                if verify_clicked:
                    raid["steps"][-1] = (
                        f"8️⃣ ✅ VERIFY CLICKED ✅\n"
                        f"   ▸ Time: {raid_now().strftime('%I:%M:%S %p')}"
                    )
                else:
                    raid["steps"][-1] = f"8️⃣ ⚠️ VERIFY NOT FOUND\n   ▸ Waiting for DM #2 anyway"
                raid["verify_clicked"] = verify_clicked
                RAID_DB["current_raid"] = raid
                raid_save_db(RAID_DB)
                if log_msg_id:
                    await raid_edit_log(
                        log_msg_id,
                        raid_build_card(raid_id, chat_name, f"https://{link}", raid["steps"], "processing")
                    )

                # ─── edit DM to step 4
                if raid.get("dm_msg_id"):
                    step4_text = dm_build_step4(raid_id, chat_name, verify_clicked)
                    await raid_edit_dm(raid["dm_msg_id"], step4_text, buttons=None)

                # ─── wait for DM #2
                raid["steps"].append(f"⏳ WAITING FOR RAIDAR DM #2 ({DM2_WAIT_SECONDS}s)...")
                RAID_DB["current_raid"] = raid
                raid_save_db(RAID_DB)
                if log_msg_id:
                    await raid_edit_log(
                        log_msg_id,
                        raid_build_card(raid_id, chat_name, f"https://{link}", raid["steps"], "processing")
                    )

                for _ in range(DM2_WAIT_SECONDS * 2):
                    await asyncio.sleep(0.5)
                    cur = RAID_DB.get("current_raid")
                    if cur and cur.get("dm2_received"):
                        raid = cur
                        break

                raid = RAID_DB.get("current_raid", raid)
                if not raid.get("dm2_received"):
                    reason_lines = []
                    if not raid.get("dm1_received"):
                        reason_lines.append("▸ Raidar DM #1 was never received")
                    if not raid.get("manual_done"):
                        reason_lines.append("▸ Done button was never tapped")
                    if not raid.get("verify_clicked"):
                        reason_lines.append("▸ Verify button was not found on Raidar DM")
                    if not raid.get("chosen_reply"):
                        reason_lines.append("▸ No reply was selected")
                    if not reason_lines:
                        reason_lines.append("▸ Reply posted + verify clicked")
                        reason_lines.append("▸ But Raidar didn't confirm XP")
                        reason_lines.append("▸ Possible causes:")
                        reason_lines.append("   • Reply not detected by Raidar")
                        reason_lines.append("   • X rate-limited the reply")
                        reason_lines.append("   • Reply removed or flagged")
                        reason_lines.append("   • Raidar bot lag")

                    fail_reasons = "\n".join(reason_lines)
                    raid["steps"].append(f"❌ NO DM #2 IN {DM2_WAIT_SECONDS}s\n{fail_reasons}")

                    if log_msg_id:
                        await raid_edit_log(
                            log_msg_id,
                            raid_build_card(raid_id, chat_name, f"https://{link}", raid["steps"], "failed")
                        )

                    failed = RAID_DB.get("failed", [])
                    failed.append({
                        "raid_id": raid_id, "chat": chat_name, "link": link,
                        "date": raid.get("date"), "time12": raid.get("time12"),
                        "reason": "no_dm2",
                    })
                    RAID_DB["failed"] = failed[-50:]

                    if raid.get("dm_msg_id"):
                        fail_text = dm_build_step5_fail(
                            raid_id, chat_name,
                            raid.get("chosen_reply", ""),
                            fail_reasons
                        )
                        await raid_edit_dm(raid["dm_msg_id"], fail_text, buttons=None)

                    RAID_DB["current_raid"] = None
                    raid_save_db(RAID_DB)

            except Exception as e:
                print(f"[cryptoraid] proc err {raid_id}: {e}")
                RAID_DB["current_raid"] = None
                raid_save_db(RAID_DB)
    finally:
        PROCESSING["active"] = False
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

print("[cryptoraid] MODULE LOADED SUCCESSFULLY — v7.1 ready")


# ╔══════════════════════════════════════════════════════════════╗
# ║  === END OF CRYPTORAID v7.1 ===                              ║
# ║                                                              ║
# ║  Flow:                                                       ║
# ║   1. Smash → store as awaiting_dm                            ║
# ║   2. Raidar DM arrives → multi-source link extract           ║
# ║      → match by tweet_id OR recency fallback                 ║
# ║   3. Activate raid → send ONE DM (step 1: pick a reply)      ║
# ║   4. You tap a number → DM EDIT → step 2 (copy + Open + Done)║
# ║   5. You tap Done → DM EDIT → step 3 (waiting 10s)           ║
# ║   6. Bot clicks Verify on Raidar DM                          ║
# ║   7. DM EDIT → step 4 (verify status)                        ║
# ║   8. DM #2 → DM EDIT → step 5 (WON / FAILED)                 ║
# ║                                                              ║
# ║  Fixes:                                                      ║
# ║   • Multi-source link extraction (text/preview/entities/btn) ║
# ║   • Recency fallback when link extraction fails              ║
# ║   • Verify on Raidar DM (correct message)                    ║
# ║   • One DM, edited 5 times                                   ║
# ║   • Progress dots ●●●○○                                       ║
# ║   • 10s wait, not 30s                                        ║
# ╚══════════════════════════════════════════════════════════════╝
