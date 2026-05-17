import os
from dotenv import load_dotenv

load_dotenv()

class Config:
    # ── Required ──────────────────────────────────────────────────
    API_ID              = int(os.getenv("API_ID", "0"))
    API_HASH            = os.getenv("API_HASH", "")
    BOT_TOKEN           = os.getenv("BOT_TOKEN", "")

    # ── Optional: Spotify ─────────────────────────────────────────
    SPOTIFY_CLIENT_ID     = os.getenv("SPOTIFY_CLIENT_ID", "")
    SPOTIFY_CLIENT_SECRET = os.getenv("SPOTIFY_CLIENT_SECRET", "")

    # ── Optional: Cookie file for age-restricted YT videos ────────
    YT_COOKIES_PATH     = os.getenv("YT_COOKIES_PATH", "")   # e.g. "cookies.txt"

    # ── Quality ───────────────────────────────────────────────────
    AUDIO_QUALITY       = os.getenv("AUDIO_QUALITY", "high")   # low / medium / high
    VIDEO_QUALITY       = os.getenv("VIDEO_QUALITY", "720")    # 360 / 480 / 720 / 1080

    # ── Cache ─────────────────────────────────────────────────────
    DOWNLOAD_DIR        = os.getenv("DOWNLOAD_DIR", "./downloads")
