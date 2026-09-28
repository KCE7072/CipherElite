# =============================================================================
#  CipherElite Userbot Plugin - cryptoraid v3.0
#  Raid clicker + X reply via Cloudflare Worker + whitelist system
# =============================================================================

from telethon import events
from telethon.errors import FloodWaitError
from utils.utils import CipherElite
from utils.decorators import rishabh
from plugins.bot import add_handler
import asyncio
import json
import re
import aiohttp
from datetime import datetime
from pathlib import Path

VERSION = "3.0.0"
CATEGORY = "utilities"

# ═══════════════════════════════════════════════════════════════════════
#  CONFIG
# ═══════════════════════════════════════════════════════════════════════

WORKER_URL = "https://raid-reply-bot.kce7072.workers.dev/reply"
WORKER_SECRET = "kce-raid-secret-2009-kce"
LOG_CHAT_ID = -1004453857887

RAID_KEYWORDS = ['raid', 'smash', 'retweet', 'raid tweet', 'reply on x', 'lfg raid']
SMASH_BUTTON = '👊'
OTHER_TARGETS = ['🤛', '✊', '🤜', 'Verify', 'Verified', '✅', 'Confirmed']

REPLY_DELAY_SECONDS = 45  # Wait before clicking Verify

# ═══════════════════════════════════════════════════════════════════════
#  STORAGE
# ═══════════════════════════════════════════════════════════════════════

PROJECT_ROOT = Path(__file__).parent.parent
DB_DIR = PROJECT_ROOT / "DB"
DB_DIR.mkdir(exist_ok=True)
DB_FILE = DB_DIR / "cryptoraid_v3.json"


def load_db():
    try:
        if DB_FILE.exists():
            return json.loads(DB_FILE.read_text(encoding="utf-8"))
    except Exception as e:
        print(f"[cryptoraid] load error: {e}")
    return {
        "smashed": {},
        "count": 0,
        "last": None,
        "started": datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S"),
        "whitelist": [],           # list of group IDs allowed for replies
        "pending_replies": {},     # raid_id -> {link, chat_id, msg_id, ts, stage, log_msg_id, worker_reply_url}
    }


def save_db(data):
    try:
        DB_FILE.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
    except Exception as e:
        print(f"[cryptoraid] save error: {e}")


DB = load_db()


# ═══════════════════════════════════════════════════════════════════════
#  HELPERS
# ═══════════════════════════════════════════════════════════════════════

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


def now_stamp():
    n = datetime.utcnow()
    return {
        "date": n.strftime("%Y-%m-%d"),
        "time": n.strftime("%H:%M:%S"),
        "time12": n.strftime("%I:%M:%S %p"),
        "ts": n.timestamp()
    }


async def tg_send_log(text):
    """Send a message to the log group via the userbot."""
    try:
        await CipherElite.send_message(LOG_CHAT_ID, text, parse_mode="markdown")
    except Exception as e:
        print(f"[cryptoraid] log send error: {e}")


async def tg_edit_log(msg_id, text):
    """Edit an existing message in the log group."""
    try:
        await CipherElite.edit_message(LOG_CHAT_ID, msg_id, text, parse_mode="markdown")
    except Exception as e:
        print(f"[cryptoraid] log edit error: {e}")


async def call_worker(link, text, raid_id):
    """POST to the Cloudflare Worker /reply endpoint."""
    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(
                WORKER_URL,
                json={
                    "link": "https://" + link if not link.startswith("http") else link,
                    "text": text,
                    "secret": WORKER_SECRET,
                    "raid_id": raid_id
                },
                timeout=aiohttp.ClientTimeout(total=30)
            ) as resp:
                body = await resp.text()
                try:
                    return resp.status, json.loads(body)
                except Exception:
                    return resp.status, {"raw": body[:500]}
    except Exception as e:
        return 0, {"error": str(e)}


def format_log(raid_id, group_name, group_id, link, steps):
    """Build the growing 25-line log message from a dict of steps."""
    lines = [f"🎯 RAID #{raid_id} — {group_name}", "━━━━━━━━━━━━━━━━━━━━━━━━━━━", ""]
    for s in steps:
        lines.append(s)
        lines.append("")
    lines.append("━━━━━━━━━━━━━━━━━━━━━━━━━━━")
    lines.append(f"🔗 {link}")
    lines.append(f"💬 {group_name}")
    lines.append(f"⏰ {datetime.utcnow().strftime('%I:%M:%S %p')} — {datetime.utcnow().strftime('%d/%m/%Y')}")
    return "\n".join(lines)


# ═══════════════════════════════════════════════════════════════════════
#  INIT
# ═══════════════════════════════════════════════════════════════════════

def init(client_instance):
    commands = [
        ".cryptoraid - Show raid clicker status",
        ".cryptoraid_stats - Show stats",
        ".cryptoraid_log [n] - Show last N smashes",
        ".cryptoraid_reset - Reset records",
        "..wl - (in group) add group to reply whitelist",
        "..wl off - (in group) remove group from whitelist",
        "..wl list - (in log group) show whitelisted groups",
    ]
    description = "🎯 Crypto Raid v3.0 — Silent smash + X reply via Worker"
    add_handler("cryptoraid", commands, description)


# ═══════════════════════════════════════════════════════════════════════
#  COMMANDS
# ═══════════════════════════════════════════════════════════════════════

@CipherElite.on(events.NewMessage(pattern=r"\.cryptoraid$"))
@rishabh()
async def cmd_status(event):
    try:
        smashed = DB.get("smashed", {})
        total = DB.get("count", 0)
        wl = DB.get("whitelist", [])
        today = datetime.utcnow().strftime("%Y-%m-%d")
        today_count = sum(1 for v in smashed.values() if isinstance(v, dict) and v.get("date", "").startswith(today))

        await event.reply(
            f"🎯 **Crypto Raid v3.0**\n"
            f"━━━━━━━━━━━━━━━━━━━━\n"
            f"✅ Status: Active (Silent)\n"
            f"👊 Total smashes: `{total}`\n"
            f"📅 Today: `{today_count}`\n"
            f"📝 Whitelisted groups: `{len(wl)}`\n"
            f"🕒 Last smash: `{DB.get('last') or 'Never'}`\n"
            f"━━━━━━━━━━━━━━━━━━━━\n"
            f"🔗 Worker: `{WORKER_URL}`"
        )
    except Exception as e:
        await event.reply(f"❌ Error: `{e}`")


@CipherElite.on(events.NewMessage(pattern=r"\.cryptoraid_stats$"))
@rishabh()
async def cmd_stats(event):
    try:
        smashed = DB.get("smashed", {})
        total = DB.get("count", 0)
        wl = DB.get("whitelist", [])
        pending = DB.get("pending_replies", {})

        today = datetime.utcnow().strftime("%Y-%m-%d")
        today_count = sum(1 for v in smashed.values() if isinstance(v, dict) and v.get("date", "").startswith(today))

        await event.reply(
            f"📊 **Raid Stats**\n"
            f"━━━━━━━━━━━━━━━━━━━━\n"
            f"👊 Total smashes: `{total}`\n"
            f"📅 Today: `{today_count}`\n"
            f"🔗 Unique links: `{len(smashed)}`\n"
            f"📝 Whitelisted: `{len(wl)}`\n"
            f"⏳ Pending replies: `{len(pending)}`"
        )
    except Exception as e:
        await event.reply(f"❌ Error: `{e}`")


@CipherElite.on(events.NewMessage(pattern=r"\.cryptoraid_log(?:\s+(\d+))?"))
@rishabh()
async def cmd_log(event):
    try:
        n = int(event.pattern_match.group(1) or 10)
        smashed = DB.get("smashed", {})
        items = sorted(smashed.items(), key=lambda x: x[1].get("ts", 0) if isinstance(x[1], dict) else 0, reverse=True)[:n]
        if not items:
            return await event.reply("📭 No raids yet.")
        lines = [f"📜 **Last {len(items)} smashes:**\n"]
        for url, info in items:
            if isinstance(info, dict):
                lines.append(f"👊 `{url[:40]}`\n   {info.get('date','?')} {info.get('time12', info.get('time','?'))} — {info.get('chat','?')[:25]}")
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
        await event.reply("🔄 Record reset.")
    except Exception as e:
        await event.reply(f"❌ Error: `{e}`")


# ═══════════════════════════════════════════════════════════════════════
#  WHITELIST COMMANDS (..wl)
# ═══════════════════════════════════════════════════════════════════════

@CipherElite.on(events.NewMessage(pattern=r"\.\.wl$"))
async def cmd_wl_add(event):
    try:
        # Silent delete the command
        try:
            await event.delete()
        except Exception:
            pass

        chat = await event.get_chat()
        chat_id = event.chat_id
        chat_name = getattr(chat, "title", "Unknown")

        wl = DB.get("whitelist", [])
        if chat_id in wl:
            await tg_send_log(f"ℹ️ Already whitelisted: **{chat_name}** (`{chat_id}`)")
            return

        wl.append(chat_id)
        DB["whitelist"] = wl
        save_db(DB)

        await tg_send_log(
            f"✅ **WHITELIST UPDATED**\n"
            f"━━━━━━━━━━━━━━━━━━━━\n"
            f"Group: **{chat_name}**\n"
            f"ID: `{chat_id}`\n"
            f"Action: Added to reply whitelist\n"
            f"Total whitelisted: `{len(wl)}`\n"
            f"Time: {datetime.utcnow().strftime('%I:%M:%S %p')}"
        )
    except Exception as e:
        await tg_send_log(f"❌ Whitelist add error: `{e}`")


@CipherElite.on(events.NewMessage(pattern=r"\.\.wl\s+off$"))
async def cmd_wl_remove_here(event):
    try:
        try:
            await event.delete()
        except Exception:
            pass

        chat = await event.get_chat()
        chat_id = event.chat_id
        chat_name = getattr(chat, "title", "Unknown")

        wl = DB.get("whitelist", [])
        if chat_id not in wl:
            await tg_send_log(f"ℹ️ Not in whitelist: **{chat_name}**")
            return

        wl.remove(chat_id)
        DB["whitelist"] = wl
        save_db(DB)

        await tg_send_log(
            f"🗑️ **WHITELIST UPDATED**\n"
            f"━━━━━━━━━━━━━━━━━━━━\n"
            f"Group: **{chat_name}**\n"
            f"ID: `{chat_id}`\n"
            f"Action: Removed from whitelist\n"
            f"Total whitelisted: `{len(wl)}`"
        )
    except Exception as e:
        await tg_send_log(f"❌ Whitelist remove error: `{e}`")


@CipherElite.on(events.NewMessage(pattern=r"\.\.wl\s+list$"))
@rishabh()
async def cmd_wl_list(event):
    try:
        wl = DB.get("whitelist", [])
        if not wl:
            return await event.reply("📭 No groups whitelisted.")
        lines = ["📋 **Whitelisted Groups**\n"]
        for cid in wl:
            try:
                entity = await CipherElite.get_entity(cid)
                name = getattr(entity, "title", "Unknown")
            except Exception:
                name = "Unknown"
            lines.append(f"• **{name}** (`{cid}`)")
        await event.reply("\n".join(lines))
    except Exception as e:
        await event.reply(f"❌ Error: `{e}`")


# ═══════════════════════════════════════════════════════════════════════
#  THE ACTUAL RAID SMASHER
# ═══════════════════════════════════════════════════════════════════════

@CipherElite.on(events.NewMessage)
async def raid_detector(event):
    try:
        text = event.raw_text or ""
        if text.startswith(".") or text.startswith(".."):
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

        # Find the smash button
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

        # CLICK IT
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

        # Record smash
        chat = await event.get_chat()
        chat_name = getattr(chat, "title", "Unknown")
        chat_id = event.chat_id
        stamp = now_stamp()

        for url in new_urls:
            smashed[url] = {
                "date": stamp["date"],
                "time": stamp["time"],
                "time12": stamp["time12"],
                "ts": stamp["ts"],
                "chat": chat_name,
                "chat_id": chat_id,
                "button": clicked_text
            }

        DB["smashed"] = smashed
        DB["count"] = DB.get("count", 0) + len(new_urls)
        DB["last"] = f"{stamp['date']} {stamp['time']}"
        raid_num = DB["count"]
        save_db(DB)

        # Check whitelist
        wl = DB.get("whitelist", [])
        is_whitelisted = chat_id in wl

        # Build the initial growing log
        raid_id = f"{raid_num}_{int(stamp['ts'])}"
        steps = [
            f"1️⃣ 👊 SMASH DONE ✅\n   ▸ Detected raid keywords + X link\n   ▸ Found `{clicked_text}` button\n   ▸ Clicked successfully"
        ]

        if not is_whitelisted:
            steps.append(f"2️⃣ ⛔ WHITELIST SKIP\n   ▸ Group `{chat_name}` NOT in whitelist\n   ▸ Smash logged, reply skipped")
            log_text = format_log(raid_id, chat_name, chat_id, f"https://{new_urls[0]}", steps)
            try:
                await CipherElite.send_message(LOG_CHAT_ID, log_text, parse_mode="markdown")
            except Exception as e:
                print(f"[cryptoraid] log err: {e}")
            return

        steps.append(f"2️⃣ 🎯 WHITELIST CHECK ✅\n   ▸ Group in REPLY_WHITELIST\n   ▸ Proceeding to reply")

        # Send initial log message and capture its ID
        log_text = format_log(raid_id, chat_name, chat_id, f"https://{new_urls[0]}", steps)
        try:
            log_msg = await CipherElite.send_message(LOG_CHAT_ID, log_text, parse_mode="markdown")
            log_msg_id = log_msg.id
        except Exception as e:
            print(f"[cryptoraid] log err: {e}")
            log_msg_id = None

        # Track pending reply
        pending = DB.get("pending_replies", {})
        pending[raid_id] = {
            "link": new_urls[0],
            "chat_id": chat_id,
            "chat_name": chat_name,
            "msg_id": event.message.id,
            "ts": stamp["ts"],
            "stage": "smash_done",
            "log_msg_id": log_msg_id,
            "steps": steps,
            "worker_reply_url": None,
            "worker_status": None
        }
        DB["pending_replies"] = pending
        save_db(DB)

        # ─── STEP 3: Send to Worker ───
        steps.append(f"3️⃣ 📤 SENDING TO WORKER... ⏳\n   ▸ POST `{WORKER_URL}`")
        if log_msg_id:
            await tg_edit_log(log_msg_id, format_log(raid_id, chat_name, chat_id, f"https://{new_urls[0]}", steps))

        # Get AI reply text (simple placeholder — replace later with real AI)
        reply_text = "Nice one 🔥 this looks solid!"

        status, worker_resp = await call_worker(new_urls[0], reply_text, raid_id)

        # Update step 3
        steps[-1] = f"3️⃣ ✍️ WORKER RESPONSE ✅\n   ▸ HTTP: `{status}`\n   ▸ Raid ID: `{raid_id}`"
        if worker_resp.get("reply_url"):
            steps[-1] += f"\n   ▸ Reply URL: `{worker_resp['reply_url']}`"
        if worker_resp.get("error"):
            steps[-1] = f"3️⃣ ❌ WORKER ERROR\n   ▸ `{worker_resp.get('error', 'unknown')[:150]}`"

        pending[raid_id]["stage"] = "worker_done"
        pending[raid_id]["worker_reply_url"] = worker_resp.get("reply_url")
        pending[raid_id]["worker_status"] = status
        pending[raid_id]["steps"] = steps
        save_db(DB)

        if log_msg_id:
            await tg_edit_log(log_msg_id, format_log(raid_id, chat_name, chat_id, f"https://{new_urls[0]}", steps))

        # If worker failed, stop here
        if status != 200 or worker_resp.get("error"):
            return

        # ─── STEP 4-7 are handled by Raidar DM watcher + Verify clicker ───
        # Those will be added in Stage 2

    except Exception as e:
        print(f"[cryptoraid] detector error: {e}")


# ═══════════════════════════════════════════════════════════════════════
#  RAIDAR DM WATCHER + VERIFY CLICKER
#  (Stage 2 — placeholder, will be added after Stage 1 is verified)
# ═══════════════════════════════════════════════════════════════════════

# TODO: Stage 2 adds:
# - Watches DMs from @RaidarBot for "How to earn reply XP" (smash confirmation)
# - Watches DMs from @RaidarBot for "Reply verified! +3 XP"
# - Matches DM link with pending_replies link
# - Waits 45s
# - Clicks Verify button on original raid post
# - Updates log message with final steps
