# =============================================================================
#  CipherElite Plugin - db_seed.py v2.0
#  MAX SPEED puller — parallel, cached, batch-optimized
# =============================================================================

from telethon import events
from telethon.tl.types import Chat, Channel
from telethon.errors import FloodWaitError
from utils.utils import CipherElite
from utils.decorators import rishabh
from plugins.bot import add_handler
from pathlib import Path
import asyncio
import json
import time

VERSION = "2.0.0"
CATEGORY = "utilities"

PROJECT_ROOT = Path(__file__).parent.parent
DB_DIR = PROJECT_ROOT / "DB"
DB_DIR.mkdir(exist_ok=True)
SEED_FILE = DB_DIR / "aireply_seed.json"
AIRREPLY_DB = DB_DIR / "aireply.json"

# ── MAX SPEED settings ──
MSGS_PER_GROUP       = 1000
MAX_GROUPS           = 200
CONCURRENT_GROUPS    = 4
SLEEP_EVERY_N_MSGS   = 500
SLEEP_MS             = 0.5
MAX_FLOOD_WAIT       = 30
SKIP_EMPTY           = True


def load_json(path, default):
    try:
        if path.exists():
            return json.loads(path.read_text(encoding="utf-8"))
    except Exception as e:
        print(f"[db_seed] load err {path.name}: {e}")
    return default


def save_json(path, data):
    try:
        path.write_text(
            json.dumps(data, indent=2, ensure_ascii=False),
            encoding="utf-8"
        )
    except Exception as e:
        print(f"[db_seed] save err {path.name}: {e}")


def _name_from_entity(entity, fallback_id=None):
    if entity is None:
        return f"User{fallback_id}" if fallback_id else "Unknown"
    first = getattr(entity, "first_name", "") or ""
    uname = getattr(entity, "username", "") or ""
    if first and uname:
        return f"{first} (@{uname})"
    if uname:
        return f"@{uname}"
    if first:
        return first
    title = getattr(entity, "title", "")
    if title:
        return title
    return "Unknown"


async def _list_all_groups():
    groups = []
    try:
        async for dialog in CipherElite.iter_dialogs(limit=None):
            entity = dialog.entity
            if isinstance(entity, (Chat, Channel)):
                groups.append((dialog.id, getattr(entity, "title", "Unknown")))
    except Exception as e:
        print(f"[db_seed] list err: {e}")
    return groups


async def _pull_group_max(chat_id, title, limit, sender_cache):
    msgs = []
    try:
        entity = await CipherElite.get_entity(chat_id)
    except Exception as e:
        print(f"[db_seed] skip {chat_id}: {e}")
        return msgs, 0

    fetched = 0
    try:
        async for msg in CipherElite.iter_messages(
            entity,
            limit=limit,
            wait_time=0,
        ):
            text = msg.raw_text or ""
            if not text:
                continue

            sid = msg.sender_id
            if sid not in sender_cache:
                sender_cache[sid] = _name_from_entity(msg.sender, sid)
            name = sender_cache[sid]

            reply_to_name = None
            reply_to_text = None
            if msg.reply_to and hasattr(msg.reply_to, "reply_to_msg_id"):
                try:
                    replied = await msg.get_reply_message()
                    if replied:
                        rsid = replied.sender_id
                        if rsid not in sender_cache:
                            sender_cache[rsid] = _name_from_entity(
                                replied.sender, rsid
                            )
                        reply_to_name = sender_cache[rsid]
                        reply_to_text = (replied.raw_text or "")[:200]
                except Exception:
                    pass

            msgs.append({
                "name": name,
                "text": text[:300],
                "reply_to_name": reply_to_name,
                "reply_to_text": reply_to_text,
                "ts": msg.date.timestamp() if msg.date else time.time(),
            })
            fetched += 1

            if fetched % SLEEP_EVERY_N_MSGS == 0:
                await asyncio.sleep(SLEEP_MS)

    except FloodWaitError as e:
        print(f"[db_seed] FloodWait {e.seconds}s on {title[:30]}")
        if e.seconds > MAX_FLOOD_WAIT:
            return msgs, fetched
        await asyncio.sleep(e.seconds + 1)
    except Exception as e:
        print(f"[db_seed] err {title[:30]}: {e}")

    return msgs, fetched


async def _worker(chat_id, title, seed_lock, seed, send_to):
    t0 = time.time()
    sender_cache = {}
    msgs, count = await _pull_group_max(chat_id, title, MSGS_PER_GROUP, sender_cache)
    dt = time.time() - t0

    if msgs:
        async with seed_lock:
            seed["groups"][str(chat_id)] = msgs
            seed["titles"][str(chat_id)] = title
            seed["pulled_at"] = time.time()
            save_json(SEED_FILE, seed)
        print(f"[db_seed] OK {title[:30]} - {count} msgs in {dt:.1f}s")
        if send_to:
            try:
                await CipherElite.send_message(
                    send_to, f"✅ **{title[:30]}** — `{count}` msgs in {dt:.1f}s"
                )
            except Exception:
                pass
    else:
        print(f"[db_seed] SKIP {title[:30]} - 0 msgs ({dt:.1f}s)")


async def run_pull(send_to=None, only_whitelisted=False):
    def _log(msg):
        print(f"[db_seed] {msg}")
        if send_to:
            try:
                asyncio.create_task(CipherElite.send_message(send_to, msg))
            except Exception:
                pass

    _log("⚡ MAX SPEED pull starting...")
    started = time.time()

    if only_whitelisted:
        db = load_json(AIRREPLY_DB, {})
        wl = db.get("whitelist", [])
        groups = []
        for cid in wl:
            try:
                e = await CipherElite.get_entity(cid)
                groups.append((cid, getattr(e, "title", str(cid))))
            except Exception:
                groups.append((cid, str(cid)))
        _log(f"📋 whitelist mode — {len(groups)}")
    else:
        groups = await _list_all_groups()
        _log(f"📋 ALL mode — {len(groups)} groups")

    if not groups:
        _log("❌ No groups.")
        return

    if len(groups) > MAX_GROUPS:
        _log(f"⚠️ Capping at {MAX_GROUPS}")
        groups = groups[:MAX_GROUPS]

    seed = load_json(SEED_FILE, {"groups": {}, "titles": {}, "pulled_at": 0})
    seed.setdefault("groups", {})
    seed.setdefault("titles", {})
    seed_lock = asyncio.Lock()

    sem = asyncio.Semaphore(CONCURRENT_GROUPS)

    async def bounded(cid, title):
        async with sem:
            await _worker(cid, title, seed_lock, seed, send_to)

    tasks = [bounded(cid, title) for cid, title in groups]
    await asyncio.gather(*tasks, return_exceptions=True)

    elapsed = time.time() - started
    total = sum(len(v) for v in seed["groups"].values())
    _log(f"✅ DONE — `{total}` msgs / `{len(seed['groups'])}` groups in {elapsed:.0f}s")


def init(client_instance):
    commands = [
        ".kceseed - MAX SPEED pull ALL groups",
        ".kceseed wl - MAX SPEED whitelist only",
        ".kceseed status - stats",
        ".kceseed apply - load into aireply",
        ".kceseed clear - wipe seed",
    ]
    add_handler("db_seed", commands, "⚡ MAX SPEED seeder v2.0")
    print("[db_seed] registered v2.0")


@CipherElite.on(events.NewMessage(pattern=r"\.kceseed$"))
@rishabh()
async def cmd_seed_all(event):
    await event.reply(f"⚡ Pulling ALL groups @ {CONCURRENT_GROUPS}x parallel...")
    await run_pull(send_to=event.chat_id, only_whitelisted=False)


@CipherElite.on(events.NewMessage(pattern=r"\.kceseed\s+wl$"))
@rishabh()
async def cmd_seed_wl(event):
    await event.reply(f"⚡ Pulling whitelist @ {CONCURRENT_GROUPS}x parallel...")
    await run_pull(send_to=event.chat_id, only_whitelisted=True)


@CipherElite.on(events.NewMessage(pattern=r"\.kceseed\s+status$"))
@rishabh()
async def cmd_seed_status(event):
    seed = load_json(SEED_FILE, {"groups": {}, "titles": {}, "pulled_at": 0})
    groups = seed.get("groups", {})
    titles = seed.get("titles", {})
    if not groups:
        return await event.reply("📭 No seed yet.")
    lines = ["🌱 **Seed stats**\n━━━━━━━━━━━━━━━━━━━━"]
    total = 0
    for cid, msgs in groups.items():
        title = titles.get(cid, cid)
        lines.append(f"• **{title[:25]}** — `{len(msgs)}`")
        total += len(msgs)
    lines.append(f"\n📊 `{total}` msgs / `{len(groups)}` groups")
    await event.reply("\n".join(lines))


@CipherElite.on(events.NewMessage(pattern=r"\.kceseed\s+apply$"))
@rishabh()
async def cmd_seed_apply(event):
    await event.reply("⏳ Applying...")
    seed = load_json(SEED_FILE, {"groups": {}})
    groups = seed.get("groups", {})
    if not groups:
        return await event.reply("❌ No seed.")
    db = load_json(AIRREPLY_DB, {})
    gm = db.get("group_messages", {})
    total = 0
    for cid, msgs in groups.items():
        existing = gm.get(cid, [])
        existing_ts = set(m.get("ts") for m in existing)
        fresh = [m for m in msgs if m.get("ts") not in existing_ts]
        gm[cid] = sorted(existing + fresh, key=lambda m: m.get("ts", 0))
        total += len(fresh)
    db["group_messages"] = gm
    save_json(AIRREPLY_DB, db)
    await event.reply(f"✅ Applied `{total}` msgs across `{len(groups)}` groups.")


@CipherElite.on(events.NewMessage(pattern=r"\.kceseed\s+clear$"))
@rishabh()
async def cmd_seed_clear(event):
    try:
        if SEED_FILE.exists():
            SEED_FILE.unlink()
        await event.reply("🗑️ Wiped.")
    except Exception as e:
        await event.reply(f"❌ {e}")
