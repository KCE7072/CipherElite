# cryptoraid.py - Crypto Raid Clicker Plugin
# Dynamic raid detection + button clicker + persistent logging
# CipherElite Plugin v1.0.0

from telethon import events
from telethon.errors import FloodWaitError
from utils.utils import CipherElite
from plugins.bot import add_handler
import re
import json
import os
import asyncio
from datetime import datetime

VERSION = "1.0.0"
CATEGORY = "utilities"

# --- Config ---
DB_FILE = "DB/cryptoraid.json"

RAID_KEYWORDS = [
    'raid', 'smash', 'retweet', 'raid tweet',
    'reply on x', 'like & retweet', 'lfg raid'
]

# The knuckle emoji + common raid button labels
BUTTON_TARGETS = [
    '👊', '🤛', '✊', '🤜', '🤝',  # punch/knuckle variants
    'Verify', 'Verified', '✅', 'Done', 'Confirmed',
    'LFG', 'Let\'s go', 'Raid', 'Smash', 'Claim'
]

# --- Persistent storage ---
def load_db():
    """Load persistent record of smashed raids."""
    try:
        if os.path.exists(DB_FILE):
            with open(DB_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
    except Exception as e:
        print(f"[cryptoraid] load_db error: {e}")
    return {"smashed": {}, "count": 0, "last": None}


def save_db(data):
    """Save persistent record."""
    try:
        os.makedirs(os.path.dirname(DB_FILE), exist_ok=True)
        with open(DB_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
    except Exception as e:
        print(f"[cryptoraid] save_db error: {e}")


DB = load_db()


# --- Helpers ---
def normalize_url(url):
    """Strip query strings/trailing slashes so duplicates are detected."""
    url = re.sub(r'\?.*$', '', url)
    url = re.sub(r'/$', '', url)
    url = re.sub(r'^https?://(?:mobile\.|www\.)?', '', url)
    return url.lower()


def extract_x_urls(text):
    """Find X/Twitter URLs and normalize them."""
    raw = re.findall(
        r'https?://(?:mobile\.)?(?:twitter\.com|x\.com)/\S+',
        text or ""
    )
    return [normalize_url(u) for u in raw]


def has_raid_intent(text):
    """Check if message looks like a raid post."""
    lower = (text or "").lower()
    return any(k in lower for k in RAID_KEYWORDS)


# --- Plugin init ---
def init(client_instance):
    commands = [
        ".cryptoraid - Show raid clicker status",
        ".cryptoraid_stats - Show smash statistics",
        ".cryptoraid_log [n] - Show last N smashed raids (default 10)",
        ".cryptoraid_reset - Reset the smash record (careful!)"
    ]
    description = "🎯 Crypto Raid — Detects X/Twitter raids and smashes the 👊 button"
    add_handler("cryptoraid", commands, description)


async def register_commands():

    # --- STATUS ---
    @CipherElite.on(events.NewMessage(pattern=r"\.cryptoraid$"))
    async def cmd_status(event):
        try:
            smashed = DB.get("smashed", {})
            total = DB.get("count", 0)
            last = DB.get("last") or "None yet"

            # Count today's raids
            today = datetime.utcnow().strftime("%Y-%m-%d")
            today_count = sum(
                1 for v in smashed.values()
                if isinstance(v, dict) and v.get("date", "").startswith(today)
            )

            await event.reply(
                "🎯 **Crypto Raid Clicker**\n\n"
                f"✅ Status: Active\n"
                f"📊 Total smashes: `{total}`\n"
                f"📅 Today: `{today_count}`\n"
                f"🕒 Last smash: `{last}`\n\n"
                f"**Keywords:** {', '.join(RAID_KEYWORDS)}\n"
                f"**Buttons:** {' '.join(BUTTON_TARGETS[:8])}"
            )
        except Exception as e:
            await event.reply(f"❌ Error: `{e}`")

    # --- STATS ---
    @CipherElite.on(events.NewMessage(pattern=r"\.cryptoraid_stats$"))
    async def cmd_stats(event):
        try:
            smashed = DB.get("smashed", {})
            total = DB.get("count", 0)

            today = datetime.utcnow().strftime("%Y-%m-%d")
            today_count = sum(
                1 for v in smashed.values()
                if isinstance(v, dict) and v.get("date", "").startswith(today)
            )

            # Get last 5
            sorted_items = sorted(
                smashed.items(),
                key=lambda x: x[1].get("ts", 0),
                reverse=True
            )[:5]

            lines = ["📊 **Raid Stats**\n"]
            lines.append(f"Total: `{total}`")
            lines.append(f"Today: `{today_count}`")
            lines.append(f"Unique: `{len(smashed)}`\n")
            lines.append("**Last 5:**")
            for url, info in sorted_items:
                lines.append(f"• `{url[:40]}...` @ {info.get('date', '?')}")

            await event.reply("\n".join(lines))
        except Exception as e:
            await event.reply(f"❌ Error: `{e}`")

    # --- LOG ---
    @CipherElite.on(events.NewMessage(pattern=r"\.cryptoraid_log(?:\s+(\d+))?$"))
    async def cmd_log(event):
        try:
            n = int(event.pattern_match.group(1) or 10)
            smashed = DB.get("smashed", {})
            sorted_items = sorted(
                smashed.items(),
                key=lambda x: x[1].get("ts", 0),
                reverse=True
            )[:n]

            if not sorted_items:
                return await event.reply("📭 No raids smashed yet.")

            lines = [f"📜 **Last {len(sorted_items)} smashes:**\n"]
            for url, info in sorted_items:
                lines.append(
                    f"✅ `{url[:50]}`\n"
                    f"   • {info.get('date', '?')} {info.get('time', '?')}\n"
                    f"   • Chat: {info.get('chat', '?')}"
                )
            await event.reply("\n".join(lines))
        except Exception as e:
            await event.reply(f"❌ Error: `{e}`")

    # --- RESET ---
    @CipherElite.on(events.NewMessage(pattern=r"\.cryptoraid_reset$"))
    async def cmd_reset(event):
        try:
            DB["smashed"] = {}
            DB["count"] = 0
            DB["last"] = None
            save_db(DB)
            await event.reply("🔄 Raid record reset.")
        except Exception as e:
            await event.reply(f"❌ Error: `{e}`")

    # --- THE ACTUAL RAID SMASHER ---
    @CipherElite.on(events.NewMessage())
    async def raid_detector(event):
        try:
            text = event.raw_text or ""
            if not text:
                return

            # Fast check first
            if not has_raid_intent(text):
                return

            urls = extract_x_urls(text)
            if not urls:
                return

            # Check if we already smashed this
            smashed = DB.get("smashed", {})
            new_urls = [u for u in urls if u not in smashed]
            if not new_urls:
                return

            # Need a button to click
            if not event.buttons:
                return

            # Look for a raid button
            clicked_row = None
            clicked_col = None
            clicked_text = None

            for r_idx, row in enumerate(event.buttons):
                for c_idx, btn in enumerate(row):
                    btn_text = (getattr(btn, "text", "") or "").strip()
                    # Check button text against targets
                    for target in BUTTON_TARGETS:
                        if target in btn_text:
                            clicked_row = r_idx
                            clicked_col = c_idx
                            clicked_text = btn_text
                            break
                    if clicked_row is not None:
                        break
                if clicked_row is not None:
                    break

            if clicked_row is None:
                return  # No raid button found

            # SMASH IT
            try:
                await event.click(clicked_row, clicked_col)
            except FloodWaitError as e:
                print(f"[cryptoraid] FloodWait {e.seconds}s")
                await asyncio.sleep(e.seconds)
                try:
                    await event.click(clicked_row, clicked_col)
                except Exception as e2:
                    print(f"[cryptoraid] retry failed: {e2}")
                    return
            except Exception as e:
                print(f"[cryptoraid] click failed: {e}")
                return

            # Record success
            chat = await event.get_chat()
            chat_title = getattr(chat, "title", "Unknown")

            now = datetime.utcnow()
            stamp = now.strftime("%Y-%m-%d %H:%M:%S")
            today = now.strftime("%Y-%m-%d")
            time_only = now.strftime("%H:%M:%S")

            for url in new_urls:
                smashed[url] = {
                    "date": today,
                    "time": time_only,
                    "ts": now.timestamp(),
                    "chat": chat_title,
                    "button": clicked_text
                }

            DB["smashed"] = smashed
            DB["count"] = DB.get("count", 0) + len(new_urls)
            DB["last"] = stamp
            save_db(DB)

            # Reply confirmation
            try:
                await event.reply(
                    f"👊 **Raid Smashed!**\n\n"
                    f"🔗 {len(new_urls)} link(s)\n"
                    f"💬 Chat: {chat_title}\n"
                    f"🔘 Button: `{clicked_text}`\n"
                    f"📊 Total: `{DB['count']}`"
                )
            except Exception:
                pass  # Don't fail if reply fails

        except Exception as e:
            print(f"[cryptoraid] handler error: {e}")
