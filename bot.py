import asyncio
from typing import Optional

from pyrogram import Client, filters
from pyrogram.types import (
    Message,
    InlineKeyboardMarkup,
    InlineKeyboardButton,
    CallbackQuery,
)

from pytgcalls import PyTgCalls, idle
from pytgcalls.types.input_stream import (
    AudioPiped,
    AudioVideoPiped,
)
from pytgcalls.types.input_stream.quality import (
    HighQualityAudio,
    HighQualityVideo,
)

from pytgcalls.exceptions import NoActiveGroupCall

import spotipy
from spotipy.oauth2 import SpotifyClientCredentials

from config import Config
from database import db
from utils import (
    get_youtube_info,
    get_spotify_track,
    format_duration,
    get_file_info,
)
from queue_manager import QueueManager


# ─────────────────────────────────────────────
# CLIENTS
# ─────────────────────────────────────────────

app = Client(
    "MusicBot",
    api_id=Config.API_ID,
    api_hash=Config.API_HASH,
    bot_token=Config.BOT_TOKEN,
)

call_py = PyTgCalls(app)
queues = QueueManager()


# ─────────────────────────────────────────────
# SPOTIFY
# ─────────────────────────────────────────────

if Config.SPOTIFY_CLIENT_ID and Config.SPOTIFY_CLIENT_SECRET:
    sp = spotipy.Spotify(
        auth_manager=SpotifyClientCredentials(
            client_id=Config.SPOTIFY_CLIENT_ID,
            client_secret=Config.SPOTIFY_CLIENT_SECRET,
        )
    )
else:
    sp = None


# ─────────────────────────────────────────────
# HELPERS
# ─────────────────────────────────────────────

def make_stream(track: dict):

    if track["type"] == "video":
        return AudioVideoPiped(
            track["stream_url"],
            audio_parameters=HighQualityAudio(),
            video_parameters=HighQualityVideo(),
        )

    return AudioPiped(
        track["stream_url"],
        audio_parameters=HighQualityAudio(),
    )


def build_controls(chat_id: int):

    q_len = len(queues.get_queue(chat_id))

    return InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton(
                    "⏸ Pause",
                    callback_data="pause",
                ),
                InlineKeyboardButton(
                    "▶️ Resume",
                    callback_data="resume",
                ),
                InlineKeyboardButton(
                    "⏭ Skip",
                    callback_data="skip",
                ),
            ],
            [
                InlineKeyboardButton(
                    "🔀 Shuffle",
                    callback_data="shuffle",
                ),
                InlineKeyboardButton(
                    "🔁 Loop",
                    callback_data="loop",
                ),
                InlineKeyboardButton(
                    "⏹ Stop",
                    callback_data="stop",
                ),
            ],
            [
                InlineKeyboardButton(
                    f"📋 Queue ({q_len})",
                    callback_data="queue",
                ),
                InlineKeyboardButton(
                    "🔊 Volume",
                    callback_data="volume",
                ),
            ],
        ]
    )


# ─────────────────────────────────────────────
# NEXT TRACK
# ─────────────────────────────────────────────

async def stream_next(chat_id: int):

    track = queues.pop(chat_id)

    if not track:
        try:
            await call_py.leave_group_call(chat_id)
        except:
            pass

        await db.del_current(chat_id)
        return

    try:
        await call_py.change_stream(
            chat_id,
            make_stream(track),
        )

        await db.set_current(chat_id, track)

    except Exception as e:
        print(f"STREAM NEXT ERROR: {e}")

        await db.del_current(chat_id)

        await stream_next(chat_id)


# ─────────────────────────────────────────────
# STREAM END
# ─────────────────────────────────────────────

@call_py.on_stream_end()
async def stream_ended(_, update):

    chat_id = update.chat_id

    loop_on = await db.get_loop(chat_id)

    if loop_on:
        current = await db.get_current(chat_id)

        if current:
            queues.add_front(chat_id, current)

    await db.del_current(chat_id)

    await stream_next(chat_id)


# ─────────────────────────────────────────────
# START / HELP
# ─────────────────────────────────────────────

@app.on_message(filters.command(["start", "help"]) & filters.group)
async def start_cmd(_, msg: Message):

    text = """
🎵 **Music & Video Streaming Bot**

Commands:

• /play song
• /vplay song
• /pause
• /resume
• /skip
• /stop
• /queue
• /volume 1-200
• /loop
• /shuffle
• /now
"""

    await msg.reply_text(text)


# ─────────────────────────────────────────────
# PLAY COMMANDS
# ─────────────────────────────────────────────

@app.on_message(filters.command(["play", "p"]) & filters.group)
async def play_cmd(_, msg: Message):
    await play_music(msg, video=False)


@app.on_message(filters.command(["vplay", "vp"]) & filters.group)
async def vplay_cmd(_, msg: Message):
    await play_music(msg, video=True)


async def play_music(msg: Message, video=False):

    chat_id = msg.chat.id

    reply = msg.reply_to_message

    # FILE PLAY
    if reply and (
        reply.audio
        or reply.video
        or reply.voice
        or reply.document
    ):

        status = await msg.reply_text("📥 Downloading...")

        try:
            path = await reply.download()

            info = await get_file_info(path)

            track = {
                "title": info["title"],
                "duration": info["duration"],
                "stream_url": path,
                "thumbnail": "",
                "type": "video" if video else "audio",
                "requester": (
                    msg.from_user.mention
                    if msg.from_user
                    else "User"
                ),
            }

            await enqueue_track(
                msg,
                chat_id,
                track,
                status,
            )

        except Exception as e:
            await status.edit_text(f"❌ {e}")

        return

    # SEARCH QUERY
    query = " ".join(msg.command[1:])

    if not query:
        await msg.reply_text(
            "❌ Give song name or URL."
        )
        return

    status = await msg.reply_text("🔍 Searching...")

    try:

        track = await resolve_track(
            query,
            video,
            msg,
        )

        if not track:
            await status.edit_text(
                "❌ Song not found."
            )
            return

        await enqueue_track(
            msg,
            chat_id,
            track,
            status,
        )

    except Exception as e:
        await status.edit_text(f"❌ {e}")


# ─────────────────────────────────────────────
# RESOLVE TRACK
# ─────────────────────────────────────────────

async def resolve_track(
    query: str,
    video: bool,
    msg: Message,
) -> Optional[dict]:

    if "spotify.com/track" in query:

        if not sp:
            raise Exception(
                "Spotify credentials missing."
            )

        info = await get_spotify_track(sp, query)

        query = (
            f"{info['name']} "
            f"{info['artists']} official"
        )

    info = await get_youtube_info(
        query,
        video=video,
    )

    if not info:
        return None

    return {
        "title": info["title"],
        "duration": info.get("duration", 0),
        "stream_url": info["stream_url"],
        "thumbnail": info.get("thumbnail", ""),
        "webpage_url": info.get("webpage_url", ""),
        "type": "video" if video else "audio",
        "requester": (
            msg.from_user.mention
            if msg.from_user
            else "User"
        ),
    }


# ─────────────────────────────────────────────
# ENQUEUE
# ─────────────────────────────────────────────

async def enqueue_track(
    msg: Message,
    chat_id: int,
    track: dict,
    status: Message,
):

    current = await db.get_current(chat_id)

    # ALREADY PLAYING
    if current:

        queues.add(chat_id, track)

        pos = len(queues.get_queue(chat_id))

        await status.edit_text(
            f"📋 Added to Queue #{pos}\n\n"
            f"🎵 {track['title']}"
        )

        return

    # START PLAYBACK
    try:

        await call_py.join_group_call(
            chat_id,
            make_stream(track),
        )

        await db.set_current(chat_id, track)

        caption = (
            f"🎵 **Now Playing**\n\n"
            f"**{track['title']}**\n"
            f"⏱ {format_duration(track['duration'])}"
        )

        if track.get("thumbnail"):

            await msg.reply_photo(
                track["thumbnail"],
                caption=caption,
                reply_markup=build_controls(chat_id),
            )

            await status.delete()

        else:

            await status.edit_text(
                caption,
                reply_markup=build_controls(chat_id),
            )

    except NoActiveGroupCall:

        await status.edit_text(
            "❌ Start voice chat first."
        )

    except Exception as e:

        await status.edit_text(
            f"❌ Playback Error:\n`{e}`"
        )


# ─────────────────────────────────────────────
# CONTROLS
# ─────────────────────────────────────────────

@app.on_message(filters.command("pause") & filters.group)
async def pause_cmd(_, msg):

    try:
        await call_py.pause_stream(msg.chat.id)
        await msg.reply_text("⏸ Paused")
    except Exception as e:
        await msg.reply_text(str(e))


@app.on_message(filters.command("resume") & filters.group)
async def resume_cmd(_, msg):

    try:
        await call_py.resume_stream(msg.chat.id)
        await msg.reply_text("▶️ Resumed")
    except Exception as e:
        await msg.reply_text(str(e))


@app.on_message(filters.command("skip") & filters.group)
async def skip_cmd(_, msg):

    await db.del_current(msg.chat.id)

    await stream_next(msg.chat.id)

    await msg.reply_text("⏭ Skipped")


@app.on_message(filters.command("stop") & filters.group)
async def stop_cmd(_, msg):

    chat_id = msg.chat.id

    queues.clear(chat_id)

    await db.del_current(chat_id)

    try:
        await call_py.leave_group_call(chat_id)
    except:
        pass

    await msg.reply_text("⏹ Stopped")


# ─────────────────────────────────────────────
# MAIN
# ─────────────────────────────────────────────

async def main():

    await app.start()

    await call_py.start()

    print("✅ Music Bot Started")

    await idle()

    await app.stop()


if __name__ == "__main__":
    asyncio.run(main())
