"""
utils.py — Async helpers for track resolution
"""

import asyncio
import os
import re
from typing import Optional

import yt_dlp

from config import Config


# ── YouTube ─────────────────────────────────────────────────────────────────────

YDL_BASE_OPTS = {
    "quiet": True,
    "no_warnings": True,
    "extract_flat": False,
    "nocheckcertificate": True,
    "geo_bypass": True,
    "source_address": "0.0.0.0",
}
if Config.YT_COOKIES_PATH:
    YDL_BASE_OPTS["cookiefile"] = Config.YT_COOKIES_PATH


def _ydl_audio_opts() -> dict:
    return {
        **YDL_BASE_OPTS,
        "format": "bestaudio[ext=m4a]/bestaudio[ext=webm]/bestaudio/best",
    }


def _ydl_video_opts(quality: str = "720") -> dict:
    fmt = (
        f"bestvideo[height<={quality}][ext=mp4]+bestaudio[ext=m4a]/"
        f"bestvideo[height<={quality}]+bestaudio/best[height<={quality}]/best"
    )
    return {
        **YDL_BASE_OPTS,
        "format": fmt,
    }


async def get_youtube_info(query: str, video: bool = False) -> Optional[dict]:
    """
    Resolve a YouTube URL or search query to stream info.
    Returns a dict with title, duration, stream_url, thumbnail, webpage_url.
    """
    opts = _ydl_video_opts(Config.VIDEO_QUALITY) if video else _ydl_audio_opts()

    # If not a URL, wrap in ytsearch
    if not is_url(query):
        query = f"ytsearch1:{query}"

    loop = asyncio.get_event_loop()

    def _extract():
        with yt_dlp.YoutubeDL(opts) as ydl:
            info = ydl.extract_info(query, download=False)
            if "entries" in info:
                info = info["entries"][0]
            if not info:
                return None

            # Get direct stream URL
            if video:
                # Prefer a direct combined URL if available, else pick best formats
                formats = info.get("formats", [])
                url = info.get("url") or _best_video_url(formats, Config.VIDEO_QUALITY)
            else:
                url = info.get("url") or _best_audio_url(info.get("formats", []))

            return {
                "title": info.get("title", "Unknown"),
                "duration": info.get("duration", 0),
                "stream_url": url,
                "thumbnail": info.get("thumbnail", ""),
                "webpage_url": info.get("webpage_url", query),
            }

    try:
        return await loop.run_in_executor(None, _extract)
    except Exception as e:
        print(f"[yt-dlp error] {e}")
        return None


def _best_audio_url(formats: list) -> str:
    audio_fmts = [
        f for f in formats
        if f.get("acodec") != "none" and f.get("vcodec") == "none"
    ]
    if audio_fmts:
        audio_fmts.sort(key=lambda f: f.get("abr") or 0, reverse=True)
        return audio_fmts[0]["url"]
    return formats[-1]["url"] if formats else ""


def _best_video_url(formats: list, max_height: str = "720") -> str:
    h = int(max_height)
    video_fmts = [
        f for f in formats
        if f.get("vcodec") != "none" and (f.get("height") or 0) <= h
    ]
    if video_fmts:
        video_fmts.sort(key=lambda f: (f.get("height") or 0, f.get("tbr") or 0), reverse=True)
        return video_fmts[0]["url"]
    return formats[-1]["url"] if formats else ""


# ── Spotify ─────────────────────────────────────────────────────────────────────

async def get_spotify_track(sp, url: str) -> dict:
    """Extract track info from a Spotify URL."""
    loop = asyncio.get_event_loop()

    def _fetch():
        match = re.search(r"track/([a-zA-Z0-9]+)", url)
        if not match:
            raise ValueError("Invalid Spotify track URL")
        track_id = match.group(1)
        track = sp.track(track_id)
        artists = ", ".join(a["name"] for a in track["artists"])
        return {
            "name": track["name"],
            "artists": artists,
            "duration": track["duration_ms"] // 1000,
            "thumbnail": track["album"]["images"][0]["url"] if track["album"]["images"] else "",
        }

    return await loop.run_in_executor(None, _fetch)


# ── File Info ────────────────────────────────────────────────────────────────────

async def get_file_info(path: str) -> dict:
    """Get metadata from a local audio/video file using yt-dlp."""
    loop = asyncio.get_event_loop()

    def _extract():
        with yt_dlp.YoutubeDL({"quiet": True}) as ydl:
            info = ydl.extract_info(path, download=False)
            return {
                "title": info.get("title") or os.path.basename(path),
                "duration": info.get("duration", 0),
                "thumbnail": info.get("thumbnail", ""),
            }

    try:
        return await loop.run_in_executor(None, _extract)
    except Exception:
        return {
            "title": os.path.basename(path),
            "duration": 0,
            "thumbnail": "",
        }


# ── Misc ─────────────────────────────────────────────────────────────────────────

def is_url(text: str) -> bool:
    return re.match(r"https?://", text.strip()) is not None


def format_duration(seconds: int) -> str:
    if not seconds:
        return "Live"
    m, s = divmod(int(seconds), 60)
    h, m = divmod(m, 60)
    return f"{h:02}:{m:02}:{s:02}" if h else f"{m:02}:{s:02}"


def thumbnail_gen(title: str) -> str:
    """Return a placeholder thumbnail URL when none is available."""
    return f"https://via.placeholder.com/480x270/0d0d0d/ffffff?text={title[:20].replace(' ', '+')}"
