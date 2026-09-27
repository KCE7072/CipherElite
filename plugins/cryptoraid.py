# cryptoraid.py - Crypto Raid Clicker Plugin
# Ported from custom Render raid bot
# Detects X/Twitter raid posts and auto-clicks the confirmation button

from telethon import events
from utils.utils import CipherElite
from plugins.bot import add_handler
import re

VERSION = "1.0.0"
CATEGORY = "utilities"

# Track processed links to avoid double-clicking
processed_links = set()

RAID_KEYWORDS = ['raid', 'smash', 'retweet', 'raid tweet', 'reply on x']
BUTTON_TARGETS = ['👊', '🤛', '✊', '🤝', 'Verify', '✅']


def extract_x_urls(text):
    """Find X/Twitter status URLs and normalize them."""
    raw = re.findall(r'https?://(?:mobile\.)?(?:twitter\.com|x\.com)/\S+', text or "")
    # Strip query strings and trailing slashes for dedup
    return [re.sub(r'[?/].*$', '', u).lower() for u in raw]


def init(client_instance):
    commands = [
        ".cryptoraid - Show raid clicker status",
        ".cryptoraid_stats - Show how many raids were clicked"
    ]
    description = "🎯 Crypto Raid - Auto-click raid buttons in X posts"
    add_handler("cryptoraid", commands, description)


async def register_commands():
    # --- STATUS COMMAND ---
    @CipherElite.on(events.NewMessage(pattern=r"^\.cryptoraid$"))
    async def status_handler(event):
        await event.reply(
            "🎯 **Crypto Raid Clicker**\n\n"
            "✅ Active\n"
            f"📊 Links processed: {len(processed_links)}\n"
            "🎯 Keywords: " + ", ".join(RAID_KEYWORDS) + "\n"
            "👊 Targets: " + ", ".join(BUTTON_TARGETS)
        )

    @CipherElite.on(events.NewMessage(pattern=r"^\.cryptoraid_stats$"))
    async def stats_handler(event):
        await event.reply(f"📊 **Stats**\n\nProcessed links: {len(processed_links)}")

    # --- THE ACTUAL RAID CLICKER ---
    @CipherElite.on(events.NewMessage())
    async def raid_detector(event):
        try:
            text = event.raw_text or ""
            if not text:
                return

            lower = text.lower()
            if not any(k in lower for k in RAID_KEYWORDS):
                return

            urls = extract_x_urls(text)
            if not urls:
                return

            # Only click if we have a NEW link
            new_urls = [u for u in urls if u not in processed_links]
            if not new_urls:
                return

            # Look for the raid button
            if not event.buttons:
                return

            clicked = False
            for r_idx, row in enumerate(event.buttons):
                for c_idx, btn in enumerate(row):
                    btn_text = getattr(btn, "text", "") or ""
                    if any(t in btn_text for t in BUTTON_TARGETS):
                        try:
                            await event.click(r_idx, c_idx)
                            clicked = True
                            for u in new_urls:
                                processed_links.add(u)
                            # Optional: reply confirmation
                            await event.reply(f"👊 **Raided!** ({len(new_urls)} link(s))")
                            break
                        except Exception as e:
                            print(f"[cryptoraid] click error: {e}")
                if clicked:
                    break
        except Exception as e:
            print(f"[cryptoraid] handler error: {e}")
