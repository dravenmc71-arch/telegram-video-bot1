import os
import asyncio
import subprocess
from pathlib import Path

import yt_dlp
from dotenv import load_dotenv

from aiogram import Bot, Dispatcher, types
from aiogram.filters import CommandStart
from aiogram.types import FSInputFile
from aiogram.client.session.aiohttp import AiohttpSession


# =========================================================
# SETTINGS
# =========================================================

load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN")

if not BOT_TOKEN:
    raise RuntimeError(
        "BOT_TOKEN topilmadi! .env fayl ichida BOT_TOKEN=... bo'lishi kerak."
    )

DOWNLOAD_DIR = Path("downloads")
DOWNLOAD_DIR.mkdir(exist_ok=True)

# Telegram Bot API upload limitidan pastroq xavfsiz limit
MAX_UPLOAD_SIZE = 49 * 1024 * 1024

# Telegramga upload uchun 5 daqiqalik timeout
session = AiohttpSession(timeout=300)

bot = Bot(
    token=BOT_TOKEN,
    session=session
)

dp = Dispatcher()


# =========================================================
# START
# =========================================================

@dp.message(CommandStart())
async def start_handler(message: types.Message):
    await message.answer(
        "🎬 Assalomu alaykum!\n\n"
        "YouTube yoki Instagram'dagi PUBLIC video/Reel linkini yuboring.\n\n"
        "Bot videoni yuklab, Telegramga video sifatida yuboradi."
    )


# =========================================================
# DOWNLOAD
# =========================================================

def download_video(url: str):
    output_template = str(
        DOWNLOAD_DIR / "%(id)s.%(ext)s"
    )

    # Instagram uchun oddiy format tezroq ishlaydi
    if "instagram.com" in url:
        video_format = "b[ext=mp4]/b/bv*+ba/b"
    else:
        # YouTube uchun 480p gacha — tezroq yuklanadi
        video_format = (
            "bv*[height<=480]+ba/"
            "b[height<=480]/"
            "bv*+ba/b"
        )

    options = {
        "format": video_format,
        "outtmpl": output_template,

        "merge_output_format": "mp4",
        "noplaylist": True,

        # YouTube JS challenge
        "js_runtimes": {
            "deno": {}
        },

        # Tezroq fragment yuklash
        "concurrent_fragment_downloads": 4,

        # Retry
        "retries": 3,
        "fragment_retries": 3,

        # Juda uzoq kutib qolmasin
        "socket_timeout": 30,

        # IPv4
        "source_address": "0.0.0.0",

        "http_headers": {
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 "
                "(KHTML, like Gecko) "
                "Chrome/154.0.0.0 Safari/537.36"
            )
        },

        "quiet": True,
        "no_warnings": False,
    }

    with yt_dlp.YoutubeDL(options) as ydl:
        info = ydl.extract_info(
            url,
            download=True
        )

        title = info.get("title", "Video")
        video_id = info.get("id")

    files = list(
        DOWNLOAD_DIR.glob(f"{video_id}.*")
    )

    files = [
        f for f in files
        if not f.name.endswith(".part")
        and not f.name.endswith(".ytdl")
        and not f.name.endswith(".json")
    ]

    if not files:
        raise FileNotFoundError(
            "Video yuklangandan keyin fayl topilmadi."
        )

    video_file = max(
        files,
        key=lambda f: f.stat().st_size
    )

    return video_file, title
# =========================================================
# COMPRESS
# =========================================================

def compress_video(input_file: Path) -> Path:
    """
    Video 49 MB dan katta bo'lsa, FFmpeg yordamida
    kichraytirishga urinadi.
    """

    output_file = input_file.with_name(
        input_file.stem + "_compressed.mp4"
    )

    # 720p dan oshirmaymiz.
    # CRF 30 - hajmni kamaytirishga yordam beradi.
    command = [
        "ffmpeg",
        "-y",
        "-i",
        str(input_file),

        "-vf",
        "scale='min(720,iw)':-2",

        "-c:v",
        "libx264",

        "-preset",
        "veryfast",

        "-crf",
        "30",

        "-c:a",
        "aac",

        "-b:a",
        "96k",

        "-movflags",
        "+faststart",

        str(output_file)
    ]

    result = subprocess.run(
        command,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True
    )

    if result.returncode != 0:
        raise RuntimeError(
            "FFmpeg video siqishda xato berdi:\n"
            + result.stderr[-1000:]
        )

    if not output_file.exists():
        raise FileNotFoundError(
            "Siqilgan video yaratilmadi."
        )

    return output_file


# =========================================================
# HANDLE VIDEO
# =========================================================

@dp.message()
async def video_handler(message: types.Message):

    if not message.text:
        return

    url = message.text.strip()

    # URL tekshirish
    if not url.startswith(("http://", "https://")):
        await message.answer(
            "❌ Iltimos, YouTube yoki Instagram video linkini yuboring."
        )
        return

    # Faqat kerakli platformalar
    supported = (
        "youtube.com" in url
        or "youtu.be" in url
        or "instagram.com" in url
    )

    if not supported:
        await message.answer(
            "❌ Hozircha faqat YouTube va Instagram "
            "linklarini qabul qilaman."
        )
        return

    status = await message.answer(
        "⏳ Videoni yuklayapman..."
    )

    video_file = None
    compressed_file = None

    try:
        # -------------------------------------------------
        # DOWNLOAD
        # -------------------------------------------------

        video_file, title = await asyncio.to_thread(
            download_video,
            url
        )

        size_mb = video_file.stat().st_size / 1024 / 1024

        print(
            f"[DOWNLOAD] {video_file} | "
            f"{size_mb:.2f} MB"
        )

        # -------------------------------------------------
        # COMPRESS IF NEEDED
        # -------------------------------------------------

        if video_file.stat().st_size > MAX_UPLOAD_SIZE:

            await status.edit_text(
                "📦 Video katta ekan.\n"
                "Telegramga yuborish uchun siqilyapti..."
            )

            compressed_file = await asyncio.to_thread(
                compress_video,
                video_file
            )

            compressed_size = (
                compressed_file.stat().st_size
                / 1024
                / 1024
            )

            print(
                f"[COMPRESSED] "
                f"{compressed_file} | "
                f"{compressed_size:.2f} MB"
            )

            if compressed_file.stat().st_size > MAX_UPLOAD_SIZE:

                await status.edit_text(
                    "❌ Video juda katta.\n\n"
                    "Avtomatik siqilgandan keyin ham "
                    "Telegram limitidan oshib ketdi."
                )

                return

            upload_file = compressed_file

        else:
            upload_file = video_file

        # -------------------------------------------------
        # TELEGRAM UPLOAD
        # -------------------------------------------------

        await status.edit_text(
            "📤 Video Telegramga yuborilmoqda..."
        )

        telegram_video = FSInputFile(
            upload_file
        )

        await message.answer_video(
            video=telegram_video,
            caption=(
                f"🎬 {title}\n\n"
                "✅ Video tayyor."
            ),
            supports_streaming=True
        )

        await status.delete()

        print("[SUCCESS] Video Telegramga yuborildi.")

    except Exception as e:

        print("\n" + "=" * 60)
        print("BOT ERROR")
        print("=" * 60)
        print(repr(e))
        print("=" * 60 + "\n")

        error_text = str(e)

        if len(error_text) > 800:
            error_text = error_text[:800] + "..."

        try:
            await status.edit_text(
                "❌ Videoni yuklab bo‘lmadi.\n\n"
                "Sabab:\n"
                f"{error_text}"
            )
        except Exception:
            await message.answer(
                "❌ Xatolik yuz berdi.\n\n"
                f"{error_text}"
            )

    finally:

        # -------------------------------------------------
        # CLEANUP
        # -------------------------------------------------

        for file in [video_file, compressed_file]:

            if file and file.exists():

                try:
                    file.unlink()
                except Exception as cleanup_error:
                    print(
                        "Cleanup error:",
                        cleanup_error
                    )


# =========================================================
# MAIN
# =========================================================

async def main():

    print("=" * 60)
    print("TELEGRAM VIDEO BOT")
    print("=" * 60)
    print("Bot ishga tushmoqda...")
    print("YouTube + Instagram")
    print("Telegram upload timeout: 300 seconds")
    print("=" * 60)

    try:
        await dp.start_polling(bot)

    finally:
        await bot.session.close()


if __name__ == "__main__":
    asyncio.run(main())
