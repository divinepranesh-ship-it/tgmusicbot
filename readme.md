# 🎵 Telegram Voice Chat Music & Video Bot

A smooth, lag-free Telegram bot for streaming music and video in group voice chats.
Supports **YouTube**, **Spotify**, **direct URLs**, and **file uploads**.

---

## ✨ Features

| Feature | Details |
|---|---|
| 🎵 Audio Streaming | YouTube, Spotify (via YT), direct links, uploaded files |
| 🎬 Video Streaming | YouTube video in voice chat |
| 📋 Queue System | Add, skip, shuffle, loop |
| 🔊 Volume Control | 1–200% |
| ⏩ Seek | Jump to any position |
| 🔁 Loop Mode | Repeat current track |
| 🔀 Shuffle | Randomise queue |
| 🎛 Inline Controls | Pause/Resume/Skip/Stop buttons |
| 📥 File Upload | Audio/Video/Voice message support |

---

## ⚙️ Setup

### 1. Clone & Install

```bash
git clone <your-repo>
cd MusicBot
pip install -r requirements.txt
```

> **System dependencies** (Ubuntu/Debian):
> ```bash
> sudo apt install ffmpeg python3-dev -y
> ```

### 2. Configure

```bash
cp .env.example .env
nano .env
```

Fill in:
| Variable | Where to get |
|---|---|
| `API_ID` & `API_HASH` | https://my.telegram.org |
| `BOT_TOKEN` | @BotFather on Telegram |
| `SPOTIFY_CLIENT_ID/SECRET` | https://developer.spotify.com/dashboard |

### 3. Run

```bash
python bot.py
```

---

## 📖 Commands

| Command | Description |
|---|---|
| `/play <song or URL>` | Play audio (YouTube/Spotify/link) |
| `/vplay <song or URL>` | Play video in voice chat |
| `/pause` | Pause playback |
| `/resume` | Resume playback |
| `/skip` | Skip current track |
| `/stop` | Stop and clear queue |
| `/queue` | Show current queue |
| `/volume <1-200>` | Set volume |
| `/loop` | Toggle loop mode |
| `/shuffle` | Shuffle the queue |
| `/seek <seconds>` | Seek to position |
| `/now` | Show now playing |

---

## 🏗 Architecture

```
bot.py            — Main entry point, command handlers, callback handlers
config.py         — Environment-based configuration
utils.py          — YouTube/Spotify resolution, file info, formatting
queue_manager.py  — Per-chat FIFO queue with shuffle & front-insert
database.py       — In-memory store for current track & loop state
```

---

## 🔧 Tips for Zero Lag

- Run on a **VPS with at least 2 vCPU and 2 GB RAM** (e.g. DigitalOcean, Hetzner, AWS EC2).
- Use **`TgCrypto`** (already in requirements) — speeds up Pyrogram encryption 10–100×.
- For video streaming, prefer **720p** (`VIDEO_QUALITY=720`) to balance quality and bandwidth.
- YouTube cookies (`YT_COOKIES_PATH`) help bypass throttling for some regions.
- For Spotify playlists, the bot resolves each track to YouTube automatically.

---

## 📝 Notes

- The bot must be **added to the group** with admin rights.
- A **voice chat must already be started** in the group before using `/play`.
- Spotify direct audio streaming is not possible (Spotify ToS); the bot searches YouTube for the same track.
