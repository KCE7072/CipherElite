# plugins/tg_contest_scanner.py
# CipherElite Plugin: Telegram Contest Scanner
# Searches all chats for contest/raid keywords and alerts you.

import asyncio
import json
import os
import html
from datetime import datetime, timezone, timedelta

from telethon import events
from utils.utils import CipherElite
from utils.decorators import rishabh
from plugins.bot import add_handler

# ─── Configuration ───────────────────────────────────────────────
# Edit these to match your setup
KEYWORDS = [
    "raid contest", "raid army", "shill contest",
    "meme raid", "activity contest", "invite contest",
    "giveaway", "airdrop", "prize pool", "how to join",
    "whitelist spot", "WL spot"
]

ALERT_CHAT_ID = None  # Set to your user ID or a group ID; None = send to "Saved Messages"
SEARCH_INTERVAL_MINUTES = 10
MAX_RESULTS_PER_KEYWORD = 50
SEEN_FILE = "tg_seen_ids.json"
# ─────────────────────────────────────────────────────────────────

CATEGORY = "utilities"  # groups plugin under "utilities" in .help

# ─── State ───────────────────────────────────────────────────────
seen_ids = set()
_search_task = None


def load_seen():
    global seen_ids
    if os.path.exists(SEEN_FILE):
        try:
            with open(SEEN_FILE, "r", encoding="utf-8") as f:
                seen_ids = set(json.load(f))
        except Exception:
            seen_ids = set()


def save_seen():
    try:
        with open(SEEN_FILE, "w", encoding="utf-8") as f:
            json.dump(list(seen_ids), f)
    except Exception as e:
        print(f"[tg_scanner] Failed to save seen IDs: {e}")


def format_alert(message, keyword):
    """Build a Telegram-friendly alert string."""
    chat = getattr(message, "chat", None)
    chat_title = getattr(chat, "title", None) or getattr(chat, "username", "Unknown")

    text = message.text or ""
    if len(text) > 350:
        text = text[:350] + "..."

    # Get sender info
    sender = getattr(message, "sender", None)
    sender_name = "Unknown"
    if sender:
        sender_name = getattr(sender, "first_name", None) or getattr(sender, "username", "Unknown")

    date = message.date.strftime("%Y-%m-%d %H:%M") if message.date else "Unknown"

    return (
        f"🎯 <b>Contest keyword found</b>\n"
        f"🏷 <i>{html.escape(keyword)}</i>\n"
        f"💬 <b>Chat:</b> {html.escape(chat_title)}\n"
        f"👤 <b>From:</b> {html.escape(sender_name)}\n"
        f"🕒 {date}\n"
        f"📝 {html.escape(text)}\n"
        f"🔗 <a href='https://t.me/c/{message.chat_id}/{message.id}'>Open Message</a>"
    )


async def send_alert(client, message, keyword):
    """Send an alert to the configured chat."""
    target = ALERT_CHAT_ID if ALERT_CHAT_ID else "me"
    try:
        text = format_alert(message, keyword)
        await client.send_message(target, text, parse_mode="html", link_preview=False)
        print(f"[tg_scanner] Alert sent: {message.id} ({keyword})")
    except Exception as e:
        print(f"[tg_scanner] Failed to send alert for {message.id}: {e}")


async def search_loop(client):
    """Background loop that searches for keywords periodically."""
    global seen_ids

    while True:
        try:
            print(f"[tg_scanner] Starting search cycle...")
            now = datetime.now(timezone.utc)

            for keyword in KEYWORDS:
                try:
                    # Global search across ALL chats the userbot is in
                    async for message in client.iter_messages(None, search=keyword, limit=MAX_RESULTS_PER_KEYWORD):
                        if message.id in seen_ids:
                            continue

                        # Only alert on messages from the last 24 hours
                        if message.date and (now - message.date.replace(tzinfo=timezone.utc)) > timedelta(hours=24):
                            continue

                        seen_ids.add(message.id)
                        await send_alert(client, message, keyword)
                        await asyncio.sleep(0.5)  # Be gentle

                except Exception as e:
                    print(f"[tg_scanner] Keyword '{keyword}' search failed: {e}")
                    await asyncio.sleep(2)

            save_seen()
            print(f"[tg_scanner] Cycle complete. Sleeping {SEARCH_INTERVAL_MINUTES} min...")
            await asyncio.sleep(SEARCH_INTERVAL_MINUTES * 60)

        except asyncio.CancelledError:
            print("[tg_scanner] Search loop cancelled.")
            break
        except Exception as e:
            print(f"[tg_scanner] Search loop error: {e}")
            await asyncio.sleep(60)


# ─── Plugin Registration ─────────────────────────────────────────
def init(client_instance):
    commands = [
        ".tgscan start   - Start the Telegram contest scanner",
        ".tgscan stop    - Stop the Telegram contest scanner",
        ".tgscan status  - Check scanner status",
        ".tgscan test    - Send a test alert",
        ".tgscan clear   - Clear seen IDs (will re-alert on old messages)",
    ]
    description = "Telegram Contest Scanner - Finds raid/contest keywords in all your chats"
    add_handler("tg_contest_scanner", commands, description)


async def register_commands():
    global _search_task, seen_ids

    @CipherElite.on(events.NewMessage(pattern=r"\.tgscan\s+start"))
    @rishabh()
    async def start_scanner(event):
        global _search_task
        if _search_task and not _search_task.done():
            await event.reply("⚠️ Scanner is already running.")
            return

        load_seen()
        _search_task = asyncio.create_task(search_loop(CipherElite))
        await event.reply(
            f"✅ <b>Telegram Contest Scanner started!</b>\n"
            f"• Keywords: {len(KEYWORDS)}\n"
            f"• Interval: {SEARCH_INTERVAL_MINUTES} min\n"
            f"• Alerts to: {'Saved Messages' if not ALERT_CHAT_ID else ALERT_CHAT_ID}",
            parse_mode="html"
        )

    @CipherElite.on(events.NewMessage(pattern=r"\.tgscan\s+stop"))
    @rishabh()
    async def stop_scanner(event):
        global _search_task
        if _search_task and not _search_task.done():
            _search_task.cancel()
            _search_task = None
            await event.reply("🛑 Scanner stopped.")
        else:
            await event.reply("⚠️ Scanner is not running.")

    @CipherElite.on(events.NewMessage(pattern=r"\.tgscan\s+status"))
    @rishabh()
    async def scanner_status(event):
        running = _search_task and not _search_task.done()
        status = "🟢 Running" if running else "🔴 Stopped"
        await event.reply(
            f"<b>TG Scanner Status</b>\n"
            f"• State: {status}\n"
            f"• Keywords: {len(KEYWORDS)}\n"
            f"• Seen messages: {len(seen_ids)}\n"
            f"• Interval: {SEARCH_INTERVAL_MINUTES} min",
            parse_mode="html"
        )

    @CipherElite.on(events.NewMessage(pattern=r"\.tgscan\s+test"))
    @rishabh()
    async def test_alert(event):
        target = ALERT_CHAT_ID if ALERT_CHAT_ID else "me"
        try:
            await CipherElite.send_message(
                target,
                "✅ <b>TG Scanner Test</b>\nTelegram alerts are working.",
                parse_mode="html"
            )
            await event.reply("✅ Test alert sent.")
        except Exception as e:
            await event.reply(f"❌ Test failed: {e}")

    @CipherElite.on(events.NewMessage(pattern=r"\.tgscan\s+clear"))
    @rishabh()
    async def clear_seen(event):
        global seen_ids
        seen_ids = set()
        save_seen()
        await event.reply("🗑️ Seen IDs cleared. Old messages will be re-alerted on next cycle.")
