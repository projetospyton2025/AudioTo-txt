"""Configurações centralizadas do AudioTo-txt."""

from __future__ import annotations

import os
import shutil
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent

UPLOAD_FOLDER = BASE_DIR / "uploads"
TRANSCRIPTS_FOLDER = BASE_DIR / "transcripts"

MAX_FILE_SIZE = 500 * 1024 * 1024  # 500 MB
MAX_CONTENT_LENGTH = MAX_FILE_SIZE

ALLOWED_EXTENSIONS = {
    "mp3",
    "wav",
    "wave",
    "m4a",
    "aac",
    "flac",
    "ogg",
    "opus",
    "wma",
    "webm",
    "mp4",
    "mov",
    "mkv",
    "avi",
    "mpeg",
    "mpg",
    "3gp",
    "3gpp",
    "3g2",
    "m4v",
    "m4b",
    "amr",
    "aiff",
    "aif",
    "caf",
    "weba",
    "ts",
    "mts",
    "m2ts",
    "flv",
    "wmv",
    "mpga",
}

WHISPER_MODEL = "base"
WHISPER_LANGUAGE = "pt"

CLEANUP_MAX_AGE_SECONDS = 60 * 60  # 1 hora

HOST = "127.0.0.1"
PORT = 5000

FFMPEG_FALLBACK_CANDIDATES = (
    Path(r"D:\ffmpeg_\bin\ffmpeg.exe"),
    Path(r"D:\ffmpeg\bin\ffmpeg.exe"),
)

FFPROBE_FALLBACK_CANDIDATES = (
    Path(r"D:\ffmpeg_\bin\ffprobe.exe"),
    Path(r"D:\ffmpeg\bin\ffprobe.exe"),
)


def _first_existing(candidates: tuple[Path, ...]) -> Path | None:
    for candidate in candidates:
        if candidate.is_file():
            return candidate
    return None


def resolve_ffmpeg() -> Path | None:
    """Localiza o FFmpeg no PATH; se não achar, usa o fallback local."""
    found = shutil.which("ffmpeg")
    if found:
        return Path(found)
    return _first_existing(FFMPEG_FALLBACK_CANDIDATES)


def ensure_ffmpeg_on_path() -> Path | None:
    """Garante que o Whisper encontre o FFmpeg no PATH."""
    ffmpeg = resolve_ffmpeg()
    if not ffmpeg:
        return None
    bin_dir = str(ffmpeg.parent)
    current = os.environ.get("PATH", "")
    parts = current.split(os.pathsep)
    if bin_dir not in parts:
        os.environ["PATH"] = bin_dir + os.pathsep + current
    return ffmpeg


def resolve_ffprobe() -> Path | None:
    found = shutil.which("ffprobe")
    if found:
        return Path(found)

    ffmpeg = resolve_ffmpeg()
    if ffmpeg:
        sibling = ffmpeg.with_name("ffprobe.exe" if os.name == "nt" else "ffprobe")
        if sibling.is_file():
            return sibling
    return _first_existing(FFPROBE_FALLBACK_CANDIDATES)


FFMPEG_PATH = ensure_ffmpeg_on_path()
FFPROBE_PATH = resolve_ffprobe()


def ensure_directories() -> None:
    UPLOAD_FOLDER.mkdir(parents=True, exist_ok=True)
    TRANSCRIPTS_FOLDER.mkdir(parents=True, exist_ok=True)
