# =============================================================================
#  CipherElite Userbot Plugin
#
#  Plugin Name:    ytsong
#  Version:        1.0.0
#  Author:         CipherElite Dev (@rishabhops)
#  Repository:     https://github.com/rishabhops/CipherElite
#
#  License:        MIT
#
#  IMPORTANT:
#    • If you copy, fork, or include this plugin in your own bot,
#      you MUST keep this header intact.
#    • You MUST give proper credit to the CipherElite Userbot author:
#      – GitHub:    https://github.com/rishabhops/CipherElite
#      – Telegram:  @thanosceo
#
#  Thank you for respecting open-source software!
# =============================================================================
#
#  CREDIT:
#    The original YouTube / MeowAPI downloader code (Pyrogram version) was
#    written by the bot owner's friend - this plugin is a Telethon port and
#    rebuild of HIS code for CipherElite. Full credit for the original
#
#
#  Target path:   plugins/ytsong.py
#
#  ---------------------------------------------------------------------------
#  YouTube music/video downloader - MeowAPI fast streams + yt-dlp fallback,
#  built for the CipherElite Telethon userbot.
#
#  Commands:
#    .play <query | youtube url>   - download & send the song (mp3)
#    .vplay <query | youtube url>  - download & send the video (mp4, <=480p)
#    .playlist <playlist url> [n]  - send the first n songs of a playlist
#    .ytapi [key]                  - set/show the MeowAPI key for faster
#                                    downloads (get one from @MeowApiRobot);
#                                    without a key the plugin falls back to
#                                    direct yt-dlp downloads
#
#  Download order: MeowAPI stream endpoint (fast, cached) -> yt-dlp fallback.
#  All yt-dlp work runs in a thread executor so the event loop never blocks.
# =============================================================================
import asyncio, json, os, re
from pathlib import Path
import aiohttp
import yt_dlp
from telethon import events
from telethon.tl.types import (
    DocumentAttributeAudio,
    MessageEntityUrl,
    MessageEntityTextUrl,
)
from utils.utils import CipherElite
from utils.decorators import rishabh
from plugins.bot import add_handler

VERSION = "1.0.0"
CATEGORY = "utilities"

PROJECT_ROOT = Path(__file__).parent.parent
DB_DIR = PROJECT_ROOT / "DB"
DB_DIR.mkdir(exist_ok=True)
DB_FILE = DB_DIR / "ytsong.json"
DOWNLOAD_DIR = PROJECT_ROOT / "downloads"
DOWNLOAD_DIR.mkdir(exist_ok=True)

MEOW_API_URL = os.environ.get("MEOW_API_URL", "https://music.yukiapi.site")


def _load_db():
    if DB_FILE.exists():
        try:
            return json.loads(DB_FILE.read_text())
        except Exception:
            pass
    return {}


def _save_db(d):
    try:
        DB_FILE.write_text(json.dumps(d, indent=2))
    except Exception:
        pass


def time_to_seconds(t):
    return sum(int(x) * 60 ** i for i, x in enumerate(reversed(str(t).split(":"))))


def video_id_from(link):
    """Accepts a full URL, youtu.be link or a raw id."""
    if not link:
        return None
    m = re.search(r"(?:v=|youtu\.be/|/shorts/)([A-Za-z0-9_-]{6,})", link)
    if m:
        return m.group(1)
    if re.fullmatch(r"[A-Za-z0-9_-]{6,}", link.strip()):
        return link.strip()
    return None


class YouTubeAPI:
    """YouTube search, metadata and download helpers."""

    BASE = "https://www.youtube.com/watch?v="

    # -- metadata via yt-dlp (runs in executor, never blocks the loop) --
    def _extract(self, url, opts=None):
        o = {"quiet": True, "no_warnings": True, "skip_download": True}
        if opts:
            o.update(opts)
        with yt_dlp.YoutubeDL(o) as ydl:
            return ydl.extract_info(url, download=False)

    async def search(self, query, limit=1):
        loop = asyncio.get_running_loop()
        info = await loop.run_in_executor(
            None, self._extract, f"ytsearch{limit}:{query}"
        )
        out = []
        for e in (info or {}).get("entries") or []:
            out.append({
                "id": e.get("id"),
                "title": e.get("title"),
                "duration": e.get("duration") or 0,
                "thumb": (e.get("thumbnails") or [{}])[0].get("url", ""),
                "link": e.get("webpage_url") or self.BASE + str(e.get("id")),
            })
        return out

    async def details(self, link):
        vid = video_id_from(link)
        url = self.BASE + vid if vid else link
        loop = asyncio.get_running_loop()
        info = await loop.run_in_executor(None, self._extract, url)
        return {
            "id": info.get("id"),
            "title": info.get("title"),
            "duration": info.get("duration") or 0,
            "thumb": (info.get("thumbnails") or [{}])[0].get("url", ""),
            "link": url,
        }

    async def playlist(self, link, limit=5):
        loop = asyncio.get_running_loop()
        try:
            info = await loop.run_in_executor(None, self._extract, link)
        except Exception:
            return []
        ids = []
        for e in (info or {}).get("entries") or []:
            if e and e.get("id"):
                ids.append(e["id"])
            if len(ids) >= limit:
                break
        return ids

    # -- downloads: MeowAPI first, yt-dlp fallback ----------------------
    async def _meow(self, vid, kind):
        key = _load_db().get("api_key", "")
        if not key:
            return None
        path = DOWNLOAD_DIR / f"{vid}.{'mp3' if kind == 'audio' else 'mp4'}"
        if path.exists() and path.stat().st_size > 10000:
            return str(path)
        timeout = aiohttp.ClientTimeout(total=300 if kind == "audio" else 600)
        try:
            async with aiohttp.ClientSession(timeout=timeout) as sess:
                url = (
                    f"{MEOW_API_URL}/stream/{vid}?key={key}"
                    f"&type={kind}&quality={'128' if kind == 'audio' else '480'}"
                )
                async with sess.get(url) as resp:
                    if resp.status != 200:
                        return None
                    tmp = path.with_suffix(".part")
                    with open(tmp, "wb") as f:
                        async for chunk in resp.content.iter_chunked(131072):
                            f.write(chunk)
                    os.replace(tmp, path)
            if path.exists() and path.stat().st_size > 10000:
                return str(path)
            return None
        except Exception:
            if path.exists():
                try:
                    os.remove(path)
                except Exception:
                    pass
            return None

    def _ytdl_download(self, vid, kind):
        path = DOWNLOAD_DIR / f"{vid}.{'mp3' if kind == 'audio' else 'mp4'}"
        if path.exists() and path.stat().st_size > 10000:
            return str(path)
        if kind == "audio":
            opts = {
                "quiet": True,
                "format": "bestaudio/best",
                "outtmpl": str(path.with_suffix(".%(ext)s")),
                "postprocessors": [{
                    "key": "FFmpegExtractAudio",
                    "preferredcodec": "mp3",
                    "preferredquality": "128",
                }],
            }
        else:
            opts = {
                "quiet": True,
                "format": "best[height<=480][ext=mp4]/best[height<=480]/best",
                "outtmpl": str(path.with_suffix(".%(ext)s")),
            }
        with yt_dlp.YoutubeDL(opts) as ydl:
            ydl.download([self.BASE + vid])
        # yt-dlp may name the file with the real extension
        if not path.exists():
            for cand in DOWNLOAD_DIR.glob(vid + ".*"):
                if cand.suffix in (".mp3", ".mp4") and cand.stat().st_size > 10000:
                    os.replace(cand, path)
                    break
        return str(path) if path.exists() else None

    async def download(self, vid, kind="audio"):
        got = await self._meow(vid, kind)
        if got:
            return got, "meow"
        loop = asyncio.get_running_loop()
        got = await loop.run_in_executor(None, self._ytdl_download, vid, kind)
        return got, "yt-dlp"

    async def thumb(self, url):
        if not url:
            return None
        try:
            async with aiohttp.ClientSession() as sess:
                async with sess.get(url, timeout=aiohttp.ClientTimeout(total=20)) as r:
                    if r.status != 200:
                        return None
                    p = DOWNLOAD_DIR / "_thumb.jpg"
                    p.write_bytes(await r.read())
                    return str(p)
        except Exception:
            return None


YouTube = YouTubeAPI()


def _extract_url(event, args):
    """URL from the command text, or from message entities."""
    m = re.search(r"https?://\S+", args or "")
    if m:
        return m.group(0)
    msg = event.message
    text = msg.text or msg.caption or ""
    for ent in (msg.entities or []):
        if isinstance(ent, MessageEntityTextUrl):
            return ent.url
        if isinstance(ent, MessageEntityUrl):
            return text[ent.offset:ent.offset + ent.length]
    return None


def _fmt_dur(sec):
    sec = int(sec or 0)
    return f"{sec // 60}:{sec % 60:02d}"


def init(client_instance):
    add_handler(
        "ytsong",
        [
            ".play <query | url> - Download & send a YouTube song (mp3)",
            ".vplay <query | url> - Download & send a YouTube video (480p)",
            ".playlist <url> [n] - Send first n songs of a playlist",
            ".ytapi [key] - Set/show MeowAPI key (@MeowApiRobot) for fast downloads",
        ],
        "🎵 YouTube song/video downloader - MeowAPI fast streams with a "
        "yt-dlp fallback, playlist support, cached downloads.",
    )


async def register_commands():

    async def _send_audio(event, vid, title, dur, status):
        await status.edit(f"⬇️ **Downloading:** {title} …")
        path, via = await YouTube.download(vid, "audio")
        if not path:
            return await status.edit("❌ **Download failed** - try another link.")
        info = None
        try:
            info = await YouTube.details(vid)
        except Exception:
            pass
        thumb = await YouTube.thumb((info or {}).get("thumb", ""))
        await status.edit(f"📤 **Uploading:** {title} …")
        await event.reply(
            file=path,
            attributes=[DocumentAttributeAudio(
                duration=int(dur or 0), title=title, performer="CipherElite",
            )],
            thumb=thumb or None,
            caption=f"🎵 **{title}**\n⏱ {_fmt_dur(dur)} · via {via}",
        )
        await status.delete()

    @CipherElite.on(events.NewMessage(pattern=r"\.play(?:\s+(.+))?$", outgoing=True))
    @rishabh()
    async def play(event):
        args = (event.pattern_match.group(1) or "").strip()
        url = _extract_url(event, args)
        status = await event.reply("🔎 **Searching YouTube…**")
        try:
            if url and ("youtu" in url or video_id_from(url)):
                info = await YouTube.details(url)
            else:
                if not args:
                    return await status.edit("❌ Give a song name or YouTube link.")
                res = await YouTube.search(args, 1)
                if not res:
                    return await status.edit("❌ No results found.")
                info = res[0]
            await _send_audio(event, info["id"], info["title"], info["duration"], status)
        except Exception as e:
            await status.edit(f"❌ **Error:** {str(e)[:140]}")

    @CipherElite.on(events.NewMessage(pattern=r"\.vplay(?:\s+(.+))?$", outgoing=True))
    @rishabh()
    async def vplay(event):
        args = (event.pattern_match.group(1) or "").strip()
        url = _extract_url(event, args)
        status = await event.reply("🔎 **Searching YouTube…**")
        try:
            if url and ("youtu" in url or video_id_from(url)):
                info = await YouTube.details(url)
            else:
                if not args:
                    return await status.edit("❌ Give a video name or YouTube link.")
                res = await YouTube.search(args, 1)
                if not res:
                    return await status.edit("❌ No results found.")
                info = res[0]
            await status.edit(f"⬇️ **Downloading video:** {info['title']} …")
            path, via = await YouTube.download(info["id"], "video")
            if not path:
                return await status.edit("❌ **Video download failed.**")
            await status.edit(f"📤 **Uploading:** {info['title']} …")
            await event.reply(
                file=path,
                caption=f"🎬 **{info['title']}**\n⏱ {_fmt_dur(info['duration'])} · via {via}",
            )
            await status.delete()
        except Exception as e:
            await status.edit(f"❌ **Error:** {str(e)[:140]}")

    @CipherElite.on(events.NewMessage(pattern=r"\.playlist(?:\s+(.+))?$", outgoing=True))
    @rishabh()
    async def playlist(event):
        args = (event.pattern_match.group(1) or "").strip()
        parts = args.split()
        limit = 5
        if parts and parts[-1].isdigit():
            limit = min(10, int(parts[-1]))
            args = " ".join(parts[:-1])
        url = _extract_url(event, args) or args
        if "list=" not in url and "playlist" not in url:
            return await event.reply("❌ Give a YouTube playlist link.")
        status = await event.reply(f"📃 **Reading playlist (first {limit})…**")
        ids = await YouTube.playlist(url, limit)
        if not ids:
            return await status.edit("❌ Could not read that playlist.")
        done = 0
        for vid in ids:
            try:
                info = await YouTube.details(vid)
                await _send_audio(
                    event, info["id"], info["title"], info["duration"], status
                )
                done += 1
            except Exception:
                continue
        if done:
            m = await event.reply(f"✅ **Playlist done** — {done}/{len(ids)} songs sent.")
            await asyncio.sleep(8)
            await m.delete()
        else:
            await status.edit("❌ Playlist download failed.")

    @CipherElite.on(events.NewMessage(pattern=r"\.ytapi(?:\s+(.+))?$", outgoing=True))
    @rishabh()
    async def ytapi(event):
        key = (event.pattern_match.group(1) or "").strip()
        db = _load_db()
        if key:
            db["api_key"] = key
            _save_db(db)
            return await event.reply(
                "🔑 **MeowAPI key saved** - downloads will use the fast stream "
                "endpoint (unlimited requests)."
            )
        cur = db.get("api_key", "")
        await event.reply(
            f"🔑 **MeowAPI status:** {'key set ✅' if cur else 'not set (yt-dlp fallback active)'}\n"
            "💡 Get a free key from @MeowApiRobot, then `.ytapi YOUR_KEY`."
        )
