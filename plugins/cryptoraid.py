# =============================================================================
#  CipherElite Userbot Plugin - cryptoraid v2.1
#  Silent raid smasher with private log notifications
# =============================================================================

from telethon import events
from telethon.errors import FloodWaitError
from utils.utils import CipherElite
from utils.decorators import rishabh
from plugins.bot import add_handler
import asyncio
import json
import re
from datetime import datetime
from pathlib import Path

VERSION = "2.1.0"
CATEGORY = "utilities"

LOG_CHAT_ID = -1004453857887

PROJECT_ROOT = Path(__file__).parent.parent
DB_DIR = PROJECT_ROOT / "DB"
DB_DIR.mkdir(exist_ok=True)
DB_FILE = DB_DIR / "cryptoraid.json"

RAID_KEYWORDS = ['raid', 'smash', 'retweet', 'raid tweet', 'reply on x', 'lfg raid']
SMASH_BUTTON = '👊'
OTHER_TARGETS = ['🤛', '✊', '🤜', 'Verify', 'Verified', '✅', 'Confirmed']


def load_db():
    try:
        if DB_FILE.exists():
            return json.loads(DB_FILE.read_text(encoding="utf-8"))
    except Exception as e:
        print(f"[cryptoraid] load error: {e}")
    return {"smashed": {}, "count": 0, "last": None, "started": datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")}


def save_db(data):
    try:
        DB_FILE.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
    except Exception as e:
        print(f"[cryptoraid] save error: {e}")


DB = load_db()


def normalize_url(url):
    url = re.sub(r'\?.*$', '', url)
    url = re.sub(r'/$', '', url)
    url = re.sub(r'^https?://(?:mobile\.|www\.)?', '', url)
    return url.lower()


def extract_x_urls(text):
    raw = re.findall(r'https?://(?:mobile\.)?(?:twitter\.com|x\.com)/\S+', text or "")
    return [normalize_url(u) for u in raw]


def has_raid_intent(text):
    lower = (text or "").lower()
    return any(k in lower for k in RAID_KEYWORDS)


def format_12h(dt):
    return dt.strftime("%I:%M:%S %p")


def init(client_instance):
    commands = [
        ".cryptoraid - Show raid clicker status",
        ".cryptoraid_stats - Show full smash statistics",
        ".cryptoraid_log [n] - Show last N smashed raids",
        ".cryptoraid_today - Show today's smashes",
        ".cryptoraid_reset - Reset the smash record",
    ]
    description = "Crypto Raid v2.1 - Silent smasher with private logging"
    add_handler("cryptoraid", commands, description)


@CipherElite.on(events.NewMessage(pattern=r"\.cryptoraid$"))
@rishabh()
async def cmd_status(event):
    try:
        smashed = DB.get("smashed", {})
        total = DB.get("count", 0)
        last = DB.get("last") or "Never"
        started = DB.get("started", "Unknown")

        today = datetime.utcnow().strftime("%Y-%m-%d")
        today_count = sum(
            1 for v in smashed.values()
            if isinstance(v, dict) and v.get("date", "").startswith(today)
        )

        await event.reply(
            f"🎯 **Crypto Raid Clicker v2.1**\n"
            f"━━━━━━━━━━━━━━━━━━━━\n"
            f"✅ **Status:** Active (Silent)\n"
            f"👊 **Total smashes:** `{total}`\n"
            f"📅 **Today:** `{today_count}`\n"
            f"🔗 **Unique links:** `{len(smashed)}`\n"
            f"🕒 **Last smash:** `{last}`\n"
            f"🚀 **Bot started:** `{started}`\n"
            f"━━━━━━━━━━━━━━━━━━━━\n"
            f"📬 **Log group:** `{LOG_CHAT_ID}`"
        )
    except Exception as e:
        await event.reply(f"❌ Error: `{e}`")


@CipherElite.on(events.NewMessage(pattern=r"\.cryptoraid_stats$"))
@rishabh()
async def cmd_stats(event):
    try:
        smashed = DB.get("smashed", {})
        total = DB.get("count", 0)

        today = datetime.utcnow().strftime("%Y-%m-%d")
        today_count = sum(
            1 for v in smashed.values()
            if isinstance(v, dict) and v.get("date", "").startswith(today)
        )

        chats = {}
        for info in smashed.values():
            if isinstance(info, dict):
                c = info.get("chat", "Unknown")
                chats[c] = chats.get(c, 0) + 1

        top_chats = sorted(chats.items(), key=lambda x: x[1], reverse=True)[:5]

        lines = [
            f"📊 **Raid Statistics**",
            f"━━━━━━━━━━━━━━━━━━━━",
            f"👊 **Total smashes:** `{total}`",
            f"📅 **Today:** `{today_count}`",
            f"🔗 **Unique links:** `{len(smashed)}`",
            f"💬 **Chats raided:** `{len(chats)}`",
            "",
            f"🏆 **Top 5 Chats:**"
        ]
        for name, count in top_chats:
            lines.append(f"• {name[:30]} — `{count}`")
        lines.append("━━━━━━━━━━━━━━━━━━━━")

        await event.reply("\n".join(lines))
    except Exception as e:
        await event.reply(f"❌ Error: `{e}`")


@CipherElite.on(events.NewMessage(pattern=r"\.cryptoraid_today$"))
@rishabh()
async def cmd_today(event):
    try:
        smashed = DB.get("smashed", {})
        today = datetime.utcnow().strftime("%Y-%m-%d")

        today_items = [
            (url, info) for url, info in smashed.items()
            if isinstance(info, dict) and info.get("date", "").startswith(today)
        ]
        today_items.sort(key=lambda x: x[1].get("ts", 0), reverse=True)

        if not today_items:
            return await event.reply(f"📭 No raids smashed today ({today}) yet.")

        lines = [f"📅 **Today's Smashes** ({len(today_items)}):\n"]
        for url, info in today_items[:15]:
            lines.append(
                f"👊 `{url[:45]}`\n"
                f"   ⏰ {info.get('time12', info.get('time', '?'))} — {info.get('chat', '?')[:25]}"
            )
        await event.reply("\n".join(lines))
    except Exception as e:
        await event.reply(f"❌ Error: `{e}`")


@CipherElite.on(events.NewMessage(pattern=r"\.cryptoraid_log(?:\s+(\d+))?"))
@rishabh()
async def cmd_log(event):
    try:
        n = int(event.pattern_match.group(1) or 10)
        smashed = DB.get("smashed", {})
        sorted_items = sorted(
            smashed.items(),
            key=lambda x: x[1].get("ts", 0) if isinstance(x[1], dict) else 0,
            reverse=True
        )[:n]

        if not sorted_items:
            return await event.reply("📭 No raids smashed yet.")

        lines = [f"📜 **Last {len(sorted_items)} Smashes:**\n"]
        for url, info in sorted_items:
            if isinstance(info, dict):
                lines.append(
                    f"👊 `{url[:45]}`\n"
                    f"   📅 {info.get('date', '?')} ⏰ {info.get('time12', info.get('time', '?'))}\n"
                    f"   💬 {info.get('chat', '?')[:30]}"
                )
        await event.reply("\n".join(lines))
    except Exception as e:
        await event.reply(f"❌ Error: `{e}`")


@CipherElite.on(events.NewMessage(pattern=r"\.cryptoraid_reset$"))
@rishabh()
async def cmd_reset(event):
    try:
        DB["smashed"] = {}
        DB["count"] = 0
        DB["last"] = None
        DB["started"] = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")
        save_db(DB)
        await event.reply("🔄 Raid record reset. Starting fresh.")
    except Exception as e:
        await event.reply(f"❌ Error: `{e}`")


@CipherElite.on(events.NewMessage)
async def raid_detector(event):
    try:
        text = event.raw_text or ""

        if text.startswith("."):
            return

        if not has_raid_intent(text):
            return

        urls = extract_x_urls(text)
        if not urls:
            return

        smashed = DB.get("smashed", {})
        new_urls = [u for u in urls if u not in smashed]
        if not new_urls:
            return

        if not event.buttons:
            return

        clicked_row = None
        clicked_col = None
        clicked_text = None

        for r_idx, row in enumerate(event.buttons):
            for c_idx, btn in enumerate(row):
                btn_text = (getattr(btn, "text", "") or "").strip()
                if SMASH_BUTTON in btn_text:
                    clicked_row = r_idx
                    clicked_col = c_idx
                    clicked_text = btn_text
                    break
            if clicked_row is not None:
                break

        if clicked_row is None:
            for r_idx, row in enumerate(event.buttons):
                for c_idx, btn in enumerate(row):
                    btn_text = (getattr(btn, "text", "") or "").strip()
                    if any(t in btn_text for t in OTHER_TARGETS):
                        clicked_row = r_idx
                        clicked_col = c_idx
                        clicked_text = btn_text
                        break
                if clicked_row is not None:
                    break

        if clicked_row is None:
            return

        try:
            await event.click(clicked_row, clicked_col)
        except FloodWaitError as e:
            await asyncio.sleep(e.seconds)
            try:
                await event.click(clicked_row, clicked_col)
            except Exception:
                return
        except Exception as e:
            print(f"[cryptoraid] click error: {e}")
            return

        chat = await event.get_chat()
        chat_title = getattr(chat, "title", "Unknown")
        now = datetime.utcnow()

        for url in new_urls:
            smashed[url] = {
                "date": now.strftime("%Y-%m-%d"),
                "time": now.strftime("%H:%M:%S"),
                "time12": format_12h(now),
                "ts": now.timestamp(),
                "chat": chat_title,
                "button": clicked_text
            }

        DB["smashed"] = smashed
        DB["count"] = DB.get("count", 0) + len(new_urls)
        DB["last"] = now.strftime("%Y-%m-%d %H:%M:%S")
        save_db(DB)

        try:
            log_msg = (
                f"👊 **Raid Smashed**\n"
                f"━━━━━━━━━━━━━━━━━━━━\n"
                f"💬 **Chat:** {chat_title}\n"
                f"🔗 **Link:** https://{new_urls[0]}\n"
                f"📅 **Date:** {now.strftime('%d/%m/%Y')}\n"
                f"⏰ **Time:** {format_12h(now)}\n"
                f"📊 **Total:** {DB['count']}\n"
                f"━━━━━━━━━━━━━━━━━━━━"
            )
            await event.client.send_message(LOG_CHAT_ID, log_msg)
        except Exception as e:
            print(f"[cryptoraid] log send error: {e}")

    except Exception as e:
        print(f"[cryptoraid] detector error: {e}")
