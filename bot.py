"""
Telegram Voice Chat Music & Video Streaming Bot
================================================
Compatible with: py-tgcalls 2.x, pyrogram 2.x
Supports: YouTube, Spotify, Direct links, File uploads
"""

import asyncio
import os
import re
from typing import Optional

from pyrogram import Client, filters
from pyrogram.types import (
    Message, InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery
)
from pytgcalls import PyTgCalls, idle
from pytgcalls.types import (
    MediaStream,
    AudioQuality,
    VideoQuality,
)
from pytgcalls.exceptions import (
    NoActiveGroupCall,
    AlreadyJoinedError,
)

import yt_dlp
import spotipy
from spotipy.oauth2 import SpotifyClientCredentials

from config import Config
from database import db
from utils import (
    get_youtube_info, get_spotify_track, format_duration, is_url, get_file_info
)
from queue_manager import QueueManager


# ─── Initialize Clients ────────────────────────────────────────────────────────

app = Client(
    "MusicBot",
    api_id=Config.API_ID,
    api_hash=Config.API_HASH,
    bot_token=Config.BOT_TOKEN,
)

call_py = PyTgCalls(app)
queues = QueueManager()


# ─── Spotify Setup ─────────────────────────────────────────────────────────────

if Config.SPOTIFY_CLIENT_ID and Config.SPOTIFY_CLIENT_SECRET:
    sp = spotipy.Spotify(
        auth_manager=SpotifyClientCredentials(
            client_id=Config.SPOTIFY_CLIENT_ID,
            client_secret=Config.SPOTIFY_CLIENT_SECRET,
        )
    )
else:
    sp = None


# ─── Helpers ───────────────────────────────────────────────────────────────────

def make_stream(track: dict) -> MediaStream:
    if track["type"] == "video":
        return MediaStream(
            track["stream_url"],
            audio_quality=AudioQuality.HIGH,
            video_quality=VideoQuality.HD_720p,
        )
    else:
        return MediaStream(
            track["stream_url"],
            audio_quality=AudioQuality.HIGH,
            video_quality=VideoQuality.NO_VIDEO,
        )


def build_controls(chat_id: int) -> InlineKeyboardMarkup:
    queue_len = len(queues.get_queue(chat_id))
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("⏸ Pause",   callback_data="pause"),
            InlineKeyboardButton("▶️ Resume",  callback_data="resume"),
            InlineKeyboardButton("⏭ Skip",    callback_data="skip"),
        ],
        [
            InlineKeyboardButton("🔀 Shuffle", callback_data="shuffle"),
            InlineKeyboardButton("🔁 Loop",    callback_data="loop"),
            InlineKeyboardButton("⏹ Stop",    callback_data="stop"),
        ],
        [
            InlineKeyboardButton(f"📋 Queue ({queue_len})", callback_data="queue"),
            InlineKeyboardButton("🔊 Volume",  callback_data="volume"),
        ],
    ])


async def stream_next(chat_id: int):
    track = queues.pop(chat_id)
    if not track:
        try:
            await call_py.leave_group_call(chat_id)
        except Exception:
            pass
        return
    try:
        await call_py.change_stream(chat_id, make_stream(track))
        await db.set_current(chat_id, track)
    except Exception as e:
        print(f"[stream_next error] {e}")
        await stream_next(chat_id)


# ─── Commands ──────────────────────────────────────────────────────────────────

@app.on_message(filters.command(["start", "help"]) & filters.group)
async def start_cmd(_, msg: Message):
    await msg.reply_text(
        "🎵 **Music & Video Bot**\n\n"
        "**Commands:**\n"
        "• `/play <song/url>` — Play music (YouTube/Spotify/link)\n"
        "• `/vplay <song/url>` — Play video\n"
        "• `/pause` — Pause playback\n"
        "• `/resume` — Resume playback\n"
        "• `/skip` — Skip current track\n"
        "• `/stop` — Stop & clear queue\n"
        "• `/queue` — Show queue\n"
        "• `/volume <1-200>` — Set volume\n"
        "• `/loop` — Toggle loop mode\n"
        "• `/shuffle` — Shuffle queue\n"
        "• `/seek <seconds>` — Seek in track\n"
        "• `/now` — Now playing\n\n"
        "**Supports:** YouTube · Spotify · Direct URLs · File uploads",
    )


@app.on_message(filters.command(["play", "p"]) & filters.group)
async def play_cmd(_, msg: Message):
    await _play(msg, video=False)


@app.on_message(filters.command(["vplay", "vp"]) & filters.group)
async def vplay_cmd(_, msg: Message):
    await _play(msg, video=True)


async def _play(msg: Message, video: bool = False):
    chat_id = msg.chat.id

    reply = msg.reply_to_message
    if reply and (reply.audio or reply.video or reply.voice or reply.document):
        status = await msg.reply_text("📥 **Downloading file...**")
        try:
            path = await reply.download()
            info = await get_file_info(path)
            track = {
                "title": info["title"],
                "duration": info["duration"],
                "stream_url": path,
                "thumbnail": "",
                "type": "video" if video else "audio",
                "requester": msg.from_user.mention if msg.from_user else "Unknown",
            }
            await _enqueue_and_play(msg, chat_id, track, status)
        except Exception as e:
            await status.edit_text(f"❌ Error: `{e}`")
        return

    query = " ".join(msg.command[1:]).strip()
    if not query:
        await msg.reply_text("❗ Please provide a song name or URL.")
        return

    status = await msg.reply_text("🔍 **Searching...**")
    try:
        track = await resolve_track(query, video=video, msg=msg)
        if not track:
            await status.edit_text("❌ Could not find the requested track.")
            return
        await _enqueue_and_play(msg, chat_id, track, status)
    except Exception as e:
        await status.edit_text(f"❌ Error: `{e}`")


async def resolve_track(query: str, video: bool, msg: Message) -> Optional[dict]:
    if "spotify.com/track" in query:
        if not sp:
            raise RuntimeError("Spotify credentials not set in .env")
        info = await get_spotify_track(sp, query)
        query = f"{info['name']} {info['artists']} official audio"

    info = await get_youtube_info(query, video=video)
    if not info:
        return None

    return {
        "title": info["title"],
        "duration": info.get("duration", 0),
        "stream_url": info["stream_url"],
        "thumbnail": info.get("thumbnail", ""),
        "webpage_url": info.get("webpage_url", ""),
        "type": "video" if video else "audio",
        "requester": msg.from_user.mention if msg.from_user else "Unknown",
    }


async def _enqueue_and_play(msg: Message, chat_id: int, track: dict, status: Message):
    queues.add(chat_id, track)
    current = await db.get_current(chat_id)

    if current:
        pos = len(queues.get_queue(chat_id))
        await status.edit_text(
            f"📋 **Added to Queue** `#{pos}`\n\n"
            f"🎵 **{track['title']}**\n"
            f"⏱ Duration: `{format_duration(track['duration'])}`\n"
            f"👤 Requested by: {track['requester']}"
        )
        return

    await status.edit_text("⏳ **Connecting to voice chat...**")

    try:
        stream = make_stream(track)

        try:
            await call_py.join_group_call(chat_id, stream)
        except AlreadyJoinedError:
            await call_py.change_stream(chat_id, stream)

        queues.pop(chat_id)
        await db.set_current(chat_id, track)

        caption = (
            f"🎵 **Now Playing**\n\n"
            f"**{track['title']}**\n"
            f"⏱ Duration: `{format_duration(track['duration'])}`\n"
            f"👤 Requested by: {track['requester']}"
        )

        thumb = track.get("thumbnail", "")
        try:
            if thumb:
                await status.delete()
                await msg.reply_photo(thumb, caption=caption, reply_markup=build_controls(chat_id))
            else:
                await status.edit_text(caption, reply_markup=build_controls(chat_id))
        except Exception:
            await status.edit_text(caption, reply_markup=build_controls(chat_id))

    except NoActiveGroupCall:
        await status.edit_text(
            "❌ **No active voice chat found!**\n"
            "Start a Voice Chat in the group first, then use /play again."
        )
        queues.clear(chat_id)
    except Exception as e:
        await status.edit_text(f"❌ Playback error: `{e}`")
        await db.del_current(chat_id)


# ─── Playback Controls ─────────────────────────────────────────────────────────

@app.on_message(filters.command("pause") & filters.group)
async def pause_cmd(_, msg: Message):
    try:
        await call_py.pause_stream(msg.chat.id)
        await msg.reply_text("⏸ **Paused.**")
    except Exception as e:
        await msg.reply_text(f"❌ `{e}`")


@app.on_message(filters.command("resume") & filters.group)
async def resume_cmd(_, msg: Message):
    try:
        await call_py.resume_stream(msg.chat.id)
        await msg.reply_text("▶️ **Resumed.**")
    except Exception as e:
        await msg.reply_text(f"❌ `{e}`")


@app.on_message(filters.command("skip") & filters.group)
async def skip_cmd(_, msg: Message):
    await db.del_current(msg.chat.id)
    await stream_next(msg.chat.id)
    await msg.reply_text("⏭ **Skipped.**")


@app.on_message(filters.command("stop") & filters.group)
async def stop_cmd(_, msg: Message):
    chat_id = msg.chat.id
    queues.clear(chat_id)
    await db.del_current(chat_id)
    try:
        await call_py.leave_group_call(chat_id)
    except Exception:
        pass
    await msg.reply_text("⏹ **Stopped and queue cleared.**")


@app.on_message(filters.command(["queue", "q"]) & filters.group)
async def queue_cmd(_, msg: Message):
    chat_id = msg.chat.id
    current = await db.get_current(chat_id)
    q = queues.get_queue(chat_id)

    if not current and not q:
        await msg.reply_text("📋 Queue is empty.")
        return

    text = ""
    if current:
        text += f"🎵 **Now Playing:**\n➤ **{current['title']}** `[{format_duration(current['duration'])}]`\n\n"
    if q:
        text += "📋 **Up Next:**\n"
        for i, t in enumerate(q[:10], 1):
            text += f"`{i}.` {t['title']} `[{format_duration(t['duration'])}]`\n"
        if len(q) > 10:
            text += f"\n...and **{len(q) - 10}** more tracks."
    else:
        text += "📋 No more tracks in queue."

    await msg.reply_text(text)


@app.on_message(filters.command("volume") & filters.group)
async def volume_cmd(_, msg: Message):
    try:
        vol = int(msg.command[1])
        if not 1 <= vol <= 200:
            raise ValueError
        await call_py.change_volume_call(msg.chat.id, vol)
        await msg.reply_text(f"🔊 Volume set to **{vol}%**")
    except (IndexError, ValueError):
        await msg.reply_text("Usage: `/volume 1-200`")
    except Exception as e:
        await msg.reply_text(f"❌ `{e}`")


@app.on_message(filters.command("loop") & filters.group)
async def loop_cmd(_, msg: Message):
    state = await db.toggle_loop(msg.chat.id)
    await msg.reply_text(f"🔁 Loop mode **{'ON ✅' if state else 'OFF ❌'}**")


@app.on_message(filters.command("shuffle") & filters.group)
async def shuffle_cmd(_, msg: Message):
    queues.shuffle(msg.chat.id)
    await msg.reply_text("🔀 Queue **shuffled!**")


@app.on_message(filters.command("seek") & filters.group)
async def seek_cmd(_, msg: Message):
    try:
        secs = int(msg.command[1])
        await call_py.seek_stream(msg.chat.id, secs)
        await msg.reply_text(f"⏩ Seeked to **{format_duration(secs)}**")
    except (IndexError, ValueError):
        await msg.reply_text("Usage: `/seek <seconds>`")
    except Exception as e:
        await msg.reply_text(f"❌ `{e}`")


@app.on_message(filters.command("now") & filters.group)
async def now_cmd(_, msg: Message):
    current = await db.get_current(msg.chat.id)
    if not current:
        await msg.reply_text("🔇 Nothing is playing right now.")
        return
    await msg.reply_text(
        f"🎵 **Now Playing**\n\n"
        f"**{current['title']}**\n"
        f"⏱ Duration: `{format_duration(current['duration'])}`\n"
        f"👤 Requested by: {current['requester']}",
        reply_markup=build_controls(msg.chat.id),
    )


# ─── Callback Handlers ─────────────────────────────────────────────────────────

@app.on_callback_query()
async def cb_handler(_, cq: CallbackQuery):
    chat_id = cq.message.chat.id
    data = cq.data

    try:
        if data == "pause":
            await call_py.pause_stream(chat_id)
            await cq.answer("⏸ Paused")
        elif data == "resume":
            await call_py.resume_stream(chat_id)
            await cq.answer("▶️ Resumed")
        elif data == "skip":
            await db.del_current(chat_id)
            await stream_next(chat_id)
            await cq.answer("⏭ Skipped")
        elif data == "stop":
            queues.clear(chat_id)
            await db.del_current(chat_id)
            try:
                await call_py.leave_group_call(chat_id)
            except Exception:
                pass
            await cq.answer("⏹ Stopped")
            await cq.message.edit_text("⏹ **Playback stopped.**")
            return
        elif data == "shuffle":
            queues.shuffle(chat_id)
            await cq.answer("🔀 Shuffled!")
        elif data == "loop":
            state = await db.toggle_loop(chat_id)
            await cq.answer(f"🔁 Loop {'ON' if state else 'OFF'}")
        elif data == "queue":
            q = queues.get_queue(chat_id)
            current = await db.get_current(chat_id)
            lines = []
            if current:
                lines.append(f"➤ {current['title']}")
            for i, t in enumerate(q[:5], 1):
                lines.append(f"{i}. {t['title']}")
            await cq.answer("\n".join(lines) if lines else "Queue empty", show_alert=True)
            return
        elif data == "volume":
            await cq.answer("Use /volume 1-200 in chat", show_alert=True)
            return

        await cq.message.edit_reply_markup(build_controls(chat_id))

    except Exception as e:
        await cq.answer(f"Error: {e}", show_alert=True)


# ─── Stream End Handler ────────────────────────────────────────────────────────

@call_py.on_stream_end()
async def on_stream_end(_, update):
    chat_id = update.chat_id
    loop_on = await db.get_loop(chat_id)

    if loop_on:
        current = await db.get_current(chat_id)
        if current:
            queues.add_front(chat_id, current)

    await db.del_current(chat_id)
    await stream_next(chat_id)


# ─── Entry Point ───────────────────────────────────────────────────────────────

async def main():
    await app.start()
    await call_py.start()
    print("✅ MusicBot is running! Press Ctrl+C to stop.")
    await idle()
    await app.stop()


if __name__ == "__main__":
    asyncio.run(main())
