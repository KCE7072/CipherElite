# =============================================================================
#  CipherElite Userbot Plugin - cryptoraid v4.0 (Stage 2)
#  Sequential queue + Raidar DM watcher + Verify clicker
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

VERSION = "4.0.0"
CATEGORY = "utilities"

WORKER_URL = "https://raid-reply-bot.kce7072.workers.dev/reply"
WORKER_SECRET = "kce-raid-secret-2009-kce"
LOG_CHAT_ID = -1004453857887
RAIDAR_USER_ID = 5994885234

RAID_KEYWORDS = ['raid', 'smash', 'retweet', 'raid tweet', 'reply on x', 'lfg raid']
SMASH_BUTTON = '👊'
OTHER_TARGETS = ['🤛', '✊', '🤜', 'Verify', 'Verified', '✅', 'Confirmed']

DM1_WAIT_SECONDS = 5
REPLY_DELAY_SECONDS = 45
DM2_WAIT_SECONDS = 5

PROJECT_ROOT = Path(__file__).parent.parent
DB_DIR = PROJECT_ROOT / "DB"
DB_DIR.mkdir(exist_ok=True)
DB_FILE = DB_DIR / "cryptoraid_v4.json"


def load_db():
    try:
        if DB_FILE.exists():
            return json.loads(DB_FILE.read_text(encoding="utf-8"))
    except Exception as e:
        print(f"[cryptoraid] load error: {e}")
    return {
        "smashed": {}, "count": 0, "last": None,
        "started": datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S"),
        "whitelist": [], "queue": [], "current_raid": None,
        "completed": [], "failed": [], "raidar_dms": [],
    }


def save_db(data):
    try:
        DB_FILE.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
    except Exception as e:
        print(f"[cryptoraid] save error: {e}")


DB = load_db()
PROCESSING = {"active": False, "current_raid_id": None}

# ═══ END OF CHUNK 1 ═══
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


def now_dict():
    n = datetime.utcnow()
    return {
        "date": n.strftime("%Y-%m-%d"),
        "time": n.strftime("%H:%M:%S"),
        "time12": n.strftime("%I:%M:%S %p"),
        "ts": n.timestamp()
    }


async def tg_send_log(text):
    try:
        return await CipherElite.send_message(LOG_CHAT_ID, text, parse_mode="markdown")
    except Exception as e:
        print(f"[cryptoraid] log send error: {e}")
        return None


async def tg_edit_log(msg_id, text):
    try:
        await CipherElite.edit_message(LOG_CHAT_ID, msg_id, text, parse_mode="markdown")
    except Exception as e:
        print(f"[cryptoraid] log edit error: {e}")


async def call_worker(link, text, raid_id):
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
                    return resp.status, {"raw": body[:500], "error_type": "bad_response"}
    except Exception as e:
        return 0, {"error": str(e), "error_type": "network_error"}


def build_card(raid_id, chat_name, link, steps, status="processing"):
    emoji = "🎯"
    if status == "done":
        emoji = "✅"
    elif status == "failed":
        emoji = "❌"
    elif status == "queued":
        emoji = "⏸️"
    lines = [f"{emoji} RAID #{raid_id} — {chat_name}", "━━━━━━━━━━━━━━━━━━━━━━━━━━━", ""]
    for s in steps:
        lines.append(s)
        lines.append("")
    lines.append("━━━━━━━━━━━━━━━━━━━━━━━━━━━")
    lines.append(f"🔗 {link}")
    lines.append(f"💬 {chat_name}")
    lines.append(f"⏰ {datetime.utcnow().strftime('%I:%M:%S %p')} — {datetime.utcnow().strftime('%d/%m/%Y')}")
    return "\n".join(lines) to


def init(client_instance):
    commands = [
        ".cryptoraid - Show status",
        ".cryptoraid_stats - Show stats",
        ".cryptoraid_queue - Show queue",
        ".cryptoraid_reset - Reset records",
        "..wl - whitelist current group",
        "..wl off - un-whitelist",
        "..wl list - list whitelisted groups",
    ]
    description = "🎯 Crypto Raid v4.0 — Sequential queue + Verify automation"
    add_handler("cryptoraid", commands, description)

# ═══ END OF CHUNK 2 ═══

@CipherElite.on(events.NewMessage(pattern=r"\.cryptoraid$"))
@rishabh()
async def cmd_status(event):
    try:
        wl = DB.get("whitelist", [])
        q = DB.get("queue", [])
        cur = DB.get("current_raid")
        completed = DB.get("completed", [])
        failed = DB.get("failed", [])
        today = datetime.utcnow().strftime("%Y-%m-%d")
        today_done = sum(1 for r in completed if r.get("date", "").startswith(today))
        msg = (
            f"🎯 **Crypto Raid v4.0**\n"
            f"━━━━━━━━━━━━━━━━━━━━\n"
            f"✅ Status: Active\n"
            f"👊 Total smashes: `{DB.get('count', 0)}`\n"
            f"✅ Completed: `{len(completed)}` (today: `{today_done}`)\n"
            f"❌ Failed: `{len(failed)}`\n"
            f"📝 Whitelisted: `{len(wl)}`\n"
            f"📦 In queue: `{len(q)}`\n"
            f"⚙️ Currently processing: `{cur['raid_id'] if cur else 'None'}`\n"
        )
        await event.reply(msg)
    except Exception as e:
        await event.reply(f"❌ Error: `{e}`")


@CipherElite.on(events.NewMessage(pattern=r"\.cryptoraid_stats$"))
@rishabh()
async def cmd_stats(event):
    try:
        completed = DB.get("completed", [])
        failed = DB.get("failed", [])
        today = datetime.utcnow().strftime("%Y-%m-%d")
        today_done = sum(1 for r in completed if r.get("date", "").startswith(today))
        today_failed = sum(1 for r in failed if r.get("date", "").startswith(today))
        lines = [
            f"📊 **Raid Stats**",
            f"━━━━━━━━━━━━━━━━━━━━",
            f"✅ Completed total: `{len(completed)}`",
            f"📅 Today completed: `{today_done}`",
            f"❌ Failed total: `{len(failed)}`",
            f"📅 Today failed: `{today_failed}`",
        ]
        if completed:
            lines.append("")
            lines.append("**Last 3 completed:**")
            for r in completed[-3:]:
                lines.append(f"• #{r.get('raid_id')} — {r.get('time12', '?')}")
        await event.reply("\n".join(lines))
    except Exception as e:
        await event.reply(f"❌ Error: `{e}`")


@CipherElite.on(events.NewMessage(pattern=r"\.cryptoraid_queue$"))
@rishabh()
async def cmd_queue(event):
    try:
        q = DB.get("queue", [])
        cur = DB.get("current_raid")
        lines = [f"📦 **Queue Status**\n━━━━━━━━━━━━━━━━━━━━"]
        if cur:
            lines.append(f"⚙️ **Processing:** #{cur.get('raid_id')} — {cur.get('chat_name', '?')}")
        if q:
            lines.append(f"\n**Waiting ({len(q)}):**")
            for r in q[:10]:
                lines.append(f"⏸️ #{r.get('raid_id')} — {r.get('chat_name', '?')}")
        else:
            lines.append("✅ Queue empty")
        await event.reply("\n".join(lines))
    except Exception as e:
        await event.reply(f"❌ Error: `{e}`")


@CipherElite.on(events.NewMessage(pattern=r"\.cryptoraid_reset$"))
@rishabh()
async def cmd_reset(event):
    try:
        DB["queue"] = []
        DB["current_raid"] = None
        DB["completed"] = []
        DB["failed"] = []
        save_db(DB)
        await event.reply("🔄 Queue + records reset.")
    except Exception as e:
        await event.reply(f"❌ Error: `{e}`")

# ═══ END OF CHUNK 3 ═══

@CipherElite.on(events.NewMessage(pattern=r"\.\.wl$"))
async def cmd_wl_add(event):
    try:
        try: await event.delete()
        except: pass
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
            f"Group: **{chat_name}**\n"
            f"ID: `{chat_id}`\n"
            f"Action: Added\n"
            f"Total: `{len(wl)}`"
        )
    except Exception as e:
        await tg_send_log(f"❌ WL add error: `{e}`")


@CipherElite.on(events.NewMessage(pattern=r"\.\.wl\s+off$"))
async def cmd_wl_remove(event):
    try:
        try: await event.delete()
        except: pass
        chat = await event.get_chat()
        chat_id = event.chat_id
        chat_name = getattr(chat, "title", "Unknown")
        wl = DB.get("whitelist", [])
        if chat_id not in wl:
            await tg_send_log(f"ℹ️ Not whitelisted: **{chat_name}**")
            return
        wl.remove(chat_id)
        DB["whitelist"] = wl
        save_db(DB)
        await tg_send_log(f"🗑️ Removed from whitelist: **{chat_name}** (`{chat_id}`)")
    except Exception as e:
        await tg_send_log(f"❌ WL remove error: `{e}`")


@CipherElite.on(events.NewMessage(pattern=r"\.\.wl\s+list$"))
@rishabh()
async def cmd_wl_list(event):
    try:
        wl = DB.get("whitelist", [])
        if not wl:
            return await event.reply("📭 No whitelisted groups.")
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

# ═══ END OF CHUNK 4 ═══

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

        try:
            await event.click(clicked_row, clicked_col)
        except FloodWaitError as e:
            await asyncio.sleep(e.seconds)
            try: await event.click(clicked_row, clicked_col)
            except: return
        except Exception as e:
            print(f"[cryptoraid] click error: {e}")
            return

        chat = await event.get_chat()
        chat_name = getattr(chat, "title", "Unknown")
        chat_id = event.chat_id
        stamp = now_dict()

        for url in new_urls:
            smashed[url] = {
                "date": stamp["date"], "time": stamp["time"], "time12": stamp["time12"],
                "ts": stamp["ts"], "chat": chat_name, "chat_id": chat_id, "button": clicked_text
            }
        DB["smashed"] = smashed
        DB["count"] = DB.get("count", 0) + len(new_urls)
        raid_num = DB["count"]
        raid_id = f"{raid_num}_{int(stamp['ts'])}"
        DB["last"] = f"{stamp['date']} {stamp['time']}"
        save_db(DB)

        wl = DB.get("whitelist", [])
        is_whitelisted = chat_id in wl

        if not is_whitelisted:
            steps = [f"1️⃣ 👊 SMASH DONE ✅\n   ▸ Detected raid + clicked `{clicked_text}`"]
            steps.append(f"2️⃣ ⛔ WHITELIST SKIP\n   ▸ `{chat_name}` not whitelisted")
            card = build_card(raid_id, chat_name, f"https://{new_urls[0]}", steps, status="failed")
            await tg_send_log(card)
            return

        raid_obj = {
            "raid_id": raid_id, "chat_id": chat_id, "chat_name": chat_name,
            "msg_id": event.message.id, "link": new_urls[0], "ts": stamp["ts"],
            "date": stamp["date"], "time12": stamp["time12"],
            "clicked_button": clicked_text, "status": "queued",
            "steps": [f"1️⃣ 👊 SMASH DONE ✅\n   ▸ Detected raid + clicked `{clicked_text}`"],
            "log_msg_id": None, "worker_reply_url": None, "worker_status": None,
            "worker_error": None, "dm1_received": False, "dm2_received": False,
            "dm1_time": None, "dm2_time": None
        }
        queue = DB.get("queue", [])
        queue.append(raid_obj)
        DB["queue"] = queue
        save_db(DB)

        card = build_card(raid_id, chat_name, f"https://{new_urls[0]}", raid_obj["steps"], status="queued")
        log_msg = await tg_send_log(card)
        if log_msg:
            raid_obj["log_msg_id"] = log_msg.id
            for i, r in enumerate(queue):
                if r["raid_id"] == raid_id:
                    queue[i]["log_msg_id"] = log_msg.id
                    break
            DB["queue"] = queue
            save_db(DB)

        if not PROCESSING["active"]:
            asyncio.create_task(process_queue())
    except Exception as e:
        print(f"[cryptoraid] detector error: {e}")


@CipherElite.on(events.NewMessage(from_users=RAIDAR_USER_ID))
async def raidar_dm_watcher(event):
    try:
        text = event.raw_text or ""
        stamp = now_dict()
        dm_record = {
            "text": text[:500], "date": stamp["date"], "time": stamp["time"],
            "time12": stamp["time12"], "ts": stamp["ts"]
        }
        dms = DB.get("raidar_dms", [])
        dms.append(dm_record)
        DB["raidar_dms"] = dms[-20:]

        if "How to earn reply XP" in text:
            cur = DB.get("current_raid")
            if cur:
                cur["dm1_received"] = True
                cur["dm1_time"] = stamp["time12"]
                cur["steps"].append(
                    f"3️⃣ 📩 RAIDAR DM #1 ✅\n"
                    f"   ▸ \"How to earn reply XP\"\n"
                    f"   ▸ Smash CONFIRMED by Raidar\n"
                    f"   ▸ Time: {stamp['time12']}"
                )
                if cur.get("log_msg_id"):
                    await tg_edit_log(cur["log_msg_id"], build_card(
                        cur["raid_id"], cur["chat_name"], f"https://{cur['link']}",
                        cur["steps"], status="processing"
                    ))
                DB["current_raid"] = cur
                save_db(DB)
            else:
                await tg_send_log(f"📩 Raidar DM #1 received (no active raid)")
            return

        if "Reply verified" in text or "Received 3 XP" in text:
            cur = DB.get("current_raid")
            if cur:
                cur["dm2_received"] = True
                cur["dm2_time"] = stamp["time12"]
                cur["steps"].append(
                    f"8️⃣ 🎉 RAIDAR DM #2 — XP CONFIRMED ✅\n"
                    f"   ▸ \"{text[:100]}\"\n"
                    f"   ▸ Time: {stamp['time12']}"
                )
                if cur.get("log_msg_id"):
                    await tg_edit_log(cur["log_msg_id"], build_card(
                        cur["raid_id"], cur["chat_name"], f"https://{cur['link']}",
                        cur["steps"], status="done"
                    ))
                cur["status"] = "done"
                completed = DB.get("completed", [])
                completed.append({
                    "raid_id": cur["raid_id"], "chat": cur["chat_name"],
                    "link": cur["link"], "date": stamp["date"],
                    "time12": stamp["time12"], "status": "done"
                })
                DB["completed"] = completed[-100:]
                DB["current_raid"] = None
                save_db(DB)
            else:
                await tg_send_log(f"🎉 Raidar DM #2 received:\n{text[:200]}")
            return

        await tg_send_log(f"📩 Raidar DM (unknown pattern):\n{text[:200]}")
        save_db(DB)
    except Exception as e:
        print(f"[cryptoraid] raidar watcher error: {e}")

# ═══ END OF CHUNK 5 ═══

async def process_queue():
    if PROCESSING["active"]:
        return
    PROCESSING["active"] = True

    try:
        while True:
            queue = DB.get("queue", [])
            if not queue:
                break

            raid = queue.pop(0)
            DB["queue"] = queue
            DB["current_raid"] = raid
            save_db(DB)

            raid_id = raid["raid_id"]
            chat_name = raid["chat_name"]
            link = raid["link"]
            log_msg_id = raid.get("log_msg_id")
            steps = raid["steps"]

            try:
                steps.append(f"⏳ Waiting for Raidar DM #1 ({DM1_WAIT_SECONDS}s)...")
                if log_msg_id:
                    await tg_edit_log(log_msg_id, build_card(raid_id, chat_name, f"https://{link}", steps, "processing"))

                for _ in range(DM1_WAIT_SECONDS * 2):
                    await asyncio.sleep(0.5)
                    current = DB.get("current_raid")
                    if current and current.get("dm1_received"):
                        break

                raid = DB.get("current_raid", raid)
                if not raid.get("dm1_received"):
                    steps.append(
                        f"3️⃣ ⚠️ RAIDAR DM #1 NOT RECEIVED\n"
                        f"   ▸ No confirmation within {DM1_WAIT_SECONDS}s\n"
                        f"   ▸ Continuing anyway..."
                    )
                raid = DB.get("current_raid", raid)
                steps = raid["steps"]

                steps.append(f"4️⃣ 📤 SENDING TO WORKER ⏳\n   ▸ `{WORKER_URL}`")
                if log_msg_id:
                    await tg_edit_log(log_msg_id, build_card(raid_id, chat_name, f"https://{link}", steps, "processing"))

                reply_text = "Nice one 🔥 this looks solid!"
                status, worker_resp = await call_worker(link, reply_text, raid_id)
                error_type = worker_resp.get("error_type", "unknown")
                reply_url = worker_resp.get("reply_url")
                worker_error = worker_resp.get("error")

                raid["worker_status"] = status
                raid["worker_reply_url"] = reply_url
                raid["worker_error"] = worker_error

                if reply_url and status == 200:
                    steps[-1] = (
                        f"4️⃣ ✍️ WORKER RESPONSE ✅\n"
                        f"   ▸ HTTP: `{status}`\n"
                        f"   ▸ Reply URL: `{reply_url}`"
                    )
                else:
                    steps[-1] = (
                        f"4️⃣ ❌ WORKER FAILED\n"
                        f"   ▸ HTTP: `{status}`\n"
                        f"   ▸ Type: `{error_type}`\n"
                        f"   ▸ Error: `{(worker_error or 'unknown')[:150]}`\n"
                        f"   ▸ Will still try Verify"
                    )
                if log_msg_id:
                    await tg_edit_log(log_msg_id, build_card(raid_id, chat_name, f"https://{link}", steps, "processing"))

                steps.append(f"5️⃣ ⏳ DELAY {REPLY_DELAY_SECONDS}s\n   ▸ Simulating human behavior")
                if log_msg_id:
                    await tg_edit_log(log_msg_id, build_card(raid_id, chat_name, f"https://{link}", steps, "processing"))

                await asyncio.sleep(REPLY_DELAY_SECONDS)
                steps[-1] = f"5️⃣ ⏱️ DELAY COMPLETE ✅\n   ▸ Waited {REPLY_DELAY_SECONDS}s"

                steps.append(f"6️⃣ 🔍 LOCATING VERIFY BUTTON...")
                if log_msg_id:
                    await tg_edit_log(log_msg_id, build_card(raid_id, chat_name, f"https://{link}", steps, "processing"))

                verify_clicked = False
                try:
                    msg = await CipherElite.get_messages(raid["chat_id"], ids=raid["msg_id"])
                    if msg and msg.buttons:
                        for r_idx, row in enumerate(msg.buttons):
                            for c_idx, btn in enumerate(row):
                                btn_text = (getattr(btn, "text", "") or "").strip()
                                if "Verify" in btn_text or "✅" in btn_text:
                                    await msg.click(r_idx, c_idx)
                                    verify_clicked = True
                                    break
                            if verify_clicked:
                                break
                except Exception as e:
                    print(f"[cryptoraid] verify click error: {e}")

                if verify_clicked:
                    steps[-1] = f"6️⃣ ✅ VERIFY CLICKED ✅\n   ▸ Button clicked successfully"
                else:
                    steps[-1] = f"6️⃣ ⚠️ VERIFY BUTTON NOT FOUND\n   ▸ Could not locate Verify"
                if log_msg_id:
                    await tg_edit_log(log_msg_id, build_card(raid_id, chat_name, f"https://{link}", steps, "processing"))

                steps.append(f"7️⃣ ⏳ Waiting for Raidar DM #2 ({DM2_WAIT_SECONDS}s)...")
                if log_msg_id:
                    await tg_edit_log(log_msg_id, build_card(raid_id, chat_name, f"https://{link}", steps, "processing"))

                for _ in range(DM2_WAIT_SECONDS * 2):
                    await asyncio.sleep(0.5)
                    current = DB.get("current_raid")
                    if current and current.get("dm2_received"):
                        break

                raid = DB.get("current_raid", raid)
                if raid.get("dm2_received"):
                    continue
                else:
                    steps[-1] = (
                        f"7️⃣ ⚠️ NO DM #2 IN {DM2_WAIT_SECONDS}s\n"
                        f"   ▸ Likely \"No reply found yet\" overlay\n"
                        f"   ▸ Reply not detected by Raidar\n"
                        f"   ▸ Marking raid FAILED"
                    )
                    if log_msg_id:
                        await tg_edit_log(log_msg_id, build_card(raid_id, chat_name, f"https://{link}", steps, "failed"))

                    failed = DB.get("failed", [])
                    failed.append({
                        "raid_id": raid_id, "chat": chat_name, "link": link,
                        "date": raid.get("date"), "time12": raid.get("time12"),
                        "reason": "no_dm2_after_verify",
                        "worker_error": worker_error, "worker_reply_url": reply_url
                    })
                    DB["failed"] = failed[-50:]
                    DB["current_raid"] = None
                    save_db(DB)

            except Exception as e:
                print(f"[cryptoraid] processor error on raid {raid_id}: {e}")
                failed = DB.get("failed", [])
                failed.append({
                    "raid_id": raid_id, "chat": chat_name, "link": link,
                    "reason": "processor_exception", "error": str(e)[:300]
                })
                DB["failed"] = failed[-50:]
                DB["current_raid"] = None
                save_db(DB)

    finally:
        PROCESSING["active"] = False
        DB["current_raid"] = None
        save_db(DB)

# ╔══════════════════════════════════════════════════════════════╗
# ║  === END OF CRYPTORAID V4.0 ===                              ║
# ║  All 6 chunks pasted successfully if you see this marker.    ║
# ╚══════════════════════════════════════════════════════════════╝

