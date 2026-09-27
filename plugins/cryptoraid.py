# =============================================================================
#  CipherElite Userbot Plugin
#
#  Plugin Name:    cryptoraid
#  Version:        1.0.0
#  Author:         KCE7072
#  Description:    Auto-click raid buttons on X/Twitter raid posts
#  Created:        27/09/2026
# =============================================================================

from telethon import events
from telethon.errors import FloodWaitError
from utils.utils import CipherElite
from utils.decorators import rishabh
from plugins.bot import add_handler
import asyncio
import json
import os
import re
from datetime import datetime
from pathlib import Path

VERSION = "1.0.0"
CATEGORY = "utilities"

# ─── Config ──────────────────────────────────────────────────────────────────
PROJECT_ROOT = Path(__file__).parent.parent
DB_DIR = PROJECT_ROOT / "DB"
DB_DIR.mkdir(exist_ok=True)
DB_FILE = DB_DIR / "cryptoraid.json"

RAID_KEYWORDS = ['raid', 'smash', 'retweet', 'raid tweet', 'reply on x', 'lfg raid']
BUTTON_TARGETS = ['👊', '🤛', '✊', '🤜', '🤝', 'Verify', 'Verified', '✅', 'Confirmed']

# ─── Persistent storage ──────────────────────────────────────────────────────
def load_db():
    try:
        if DB_FILE.exists():
            return json.loads(DB_FILE.read_text(encoding="utf-8"))
    except Exception as e:
        print(f"[cryptoraid] load error: {e}")
    return {"smashed": {}, "count": 0, "last": None}


def save_db(data):
    try:
        DB_FILE.write_text(
            json.dumps(data, indent=2, ensure_ascii=False),
            encoding="utf-8"
        )
    except Exception as e:
        print(f"[cryptoraid] save error: {e}")


DB = load_db()


def normalize_url(url):
    url = re.sub(r'\?.*$', '', url)
    url = re.sub(r'/$', '', url)
    url = re.sub(r'^https?://(?:mobile\.|www\.)?', '', url)
    return url.lower()


def extract_x_urls(text):
    raw = re.findall(
        r'https?://(?:mobile\.)?(?:twitter\.com|x\.com)/\S+',
        text or ""
    )
    return [normalize_url(u) for u in raw]


def has_raid_intent(text):
    lower = (text or "").lower()
    return any(k in lower for k in RAID_KEYWORDS)


def init(client_instance):
    commands = [
        ".cryptoraid - Show raid clicker status",
        ".cryptoraid_stats - Show smash statistics",
        ".cryptoraid_log [n] - Show last N smashes",
        ".cryptoraid_reset - Reset the smash record",
    ]
    description = "🎯 Crypto Raid – Auto-clicks 👊 buttons on X raid posts | Created: 27/09/2026"
    add_handler("cryptoraid", commands, description)


# ─── Command handlers ────────────────────────────────────────────────────────
@CipherElite.on(events.NewMessage(pattern=r"\.cryptoraid$"))
@rishabh()
async def cmd_status(event):
    try:
        smashed = DB.get("smashed", {})
        total = DB.get("count", 0)
        last = DB.get("last") or "None"

        today = datetime.utcnow().strftime("%Y-%m-%d")
        today_count = sum(
            1 for v in smashed.values()
            if isinstance(v, dict) and v.get("date", "").startswith(today)
        )

        await event.reply(
            f"🎯 **Crypto Raid Clicker**\n\n"
            f"✅ Status: Active\n"
            f"📊 Total smashes: `{total}`\n"
            f"📅 Today: `{today_count}`\n"
            f"🕒 Last smash: `{last}`\n\n"
            f"**Tracked keywords:** {', '.join(RAID_KEYWORDS)}"
        )
        await event.delete()
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

        sorted_items = sorted(
            smashed.items(),
            key=lambda x: x[1].get("ts", 0) if isinstance(x[1], dict) else 0,
            reverse=True
        )[:5]

        lines = [
            "📊 **Raid Stats**\n",
            f"Total: `{total}`",
            f"Today: `{today_count}`",
            f"Unique URLs: `{len(smashed)}`\n",
            "**Last 5:**"
        ]
        for url, info in sorted_items:
            if isinstance(info, dict):
                lines.append(f"• `{url[:40]}` @ {info.get('date', '?')}")

        await event.reply("\n".join(lines))
        await event.delete()
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
            await event.reply("📭 No raids smashed yet.")
            return

        lines = [f"📜 **Last {len(sorted_items)} smashes:**\n"]
        for url, info in sorted_items:
            if isinstance(info, dict):
                lines.append(
                    f"✅ `{url[:50]}`\n"
                    f"   {info.get('date', '?')} {info.get('time', '?')} — {info.get('chat', '?')}"
                )
        await event.reply("\n".join(lines))
        await event.delete()
    except Exception as e:
        await event.reply(f"❌ Error: `{e}`")


@CipherElite.on(events.NewMessage(pattern=r"\.cryptoraid_reset$"))
@rishabh()
async def cmd_reset(event):
    try:
        DB["smashed"] = {}
        DB["count"] = 0
        DB["last"] = None
        save_db(DB)
        await event.reply("🔄 Raid record reset.")
        await event.delete()
    except Exception as e:
        await event.reply(f"❌ Error: `{e}`")


# ─── THE ACTUAL RAID SMASHER ─────────────────────────────────────────────────
@CipherElite.on(events.NewMessage)
@rishabh()
async def raid_detector(event):
    try:
        text = event.raw_text or ""
        if not text:
            return

        # Skip if command message
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

        # Check if the message has any buttons
        if not event.buttons:
            return

        clicked_row = None
        clicked_col = None
        clicked_text = None

        for r_idx, row in enumerate(event.buttons):
            for c_idx, btn in enumerate(row):
                btn_text = (getattr(btn, "text", "") or "").strip()
                if any(t in btn_text for t in BUTTON_TARGETS):
                    clicked_row = r_idx
                    clicked_col = c_idx
                    clicked_text = btn_text
                    break
            if clicked_row is not None:
                break

        if clicked_row is None:
            return

        # Click the button
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

        # Save to database
        chat = await event.get_chat()
        chat_title = getattr(chat, "title", "Unknown")

        now = datetime.utcnow()
        for url in new_urls:
            smashed[url] = {
                "date": now.strftime("%Y-%m-%d"),
                "time": now.strftime("%H:%M:%S"),
                "ts": now.timestamp(),
                "chat": chat_title,
                "button": clicked_text
            }

        DB["smashed"] = smashed
        DB["count"] = DB.get("count", 0) + len(new_urls)
        DB["last"] = now.strftime("%Y-%m-%d %H:%M:%S")
        save_db(DB)

        # Notify in chat
        try:
            await event.reply(
                f"👊 **Raid Smashed!**\n"
                f"🔗 {len(new_urls)} link(s)\n"
                f"💬 {chat_title}\n"
                f"📊 Total: `{DB['count']}`"
            )
        except Exception:
            pass

    except Exception as e:
        print(f"[cryptoraid] detector error: {e}")
