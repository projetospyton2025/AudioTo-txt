"""Detecção do tipo real de mídia (assinatura + FFprobe)."""

from __future__ import annotations

import json
import logging
import os
import subprocess
from pathlib import Path

import config

logger = logging.getLogger("audioto-txt")

FRIENDLY_FORMATS = {
    "mp3": "MP3",
    "wav": "WAV",
    "wave": "WAV",
    "flac": "FLAC",
    "ogg": "OGG",
    "opus": "OPUS",
    "aac": "AAC",
    "m4a": "M4A",
    "mp4": "MP4",
    "mov": "MOV",
    "qt": "MOV",
    "matroska": "MKV",
    "webm": "WEBM",
    "wma": "WMA",
    "asf": "WMA",
    "avi": "AVI",
    "mpeg": "MPEG",
    "mpegts": "MPEG",
    "3gp": "3GP",
    "amr": "AMR",
    "aiff": "AIFF",
}

CONTAINER_TO_EXT = {
    "MP3": "mp3",
    "WAV": "wav",
    "FLAC": "flac",
    "OGG": "ogg",
    "OPUS": "opus",
    "AAC": "aac",
    "M4A": "m4a",
    "MP4": "mp4",
    "MOV": "mov",
    "MKV": "mkv",
    "WEBM": "webm",
    "WMA": "wma",
    "AVI": "avi",
    "MPEG": "mpeg",
    "3GP": "3gp",
    "AMR": "amr",
    "AIFF": "aiff",
}


def _creation_flags() -> int:
    if os.name == "nt":
        return getattr(subprocess, "CREATE_NO_WINDOW", 0)
    return 0


def _friendly_from_ffprobe(format_name: str) -> str | None:
    names = [part.strip().lower() for part in format_name.split(",") if part.strip()]
    for name in names:
        if name in FRIENDLY_FORMATS:
            return FRIENDLY_FORMATS[name]
    for name in names:
        if name in {"mp4", "isom", "iso2", "mp41", "mp42"}:
            return "MP4"
        if name in {"3g2", "3gp2"}:
            return "3GP"
    return names[0].upper() if names else None


def sniff_magic(path: Path) -> str | None:
    """Identifica o container pelos bytes iniciais, sem confiar no nome."""
    try:
        header = path.read_bytes()[:64]
    except OSError:
        return None
    if len(header) < 12:
        return None

    if header.startswith(b"ID3") or header[:2] in {b"\xff\xfb", b"\xff\xf3", b"\xff\xf2", b"\xff\xe3"}:
        return "MP3"
    if header.startswith(b"RIFF") and header[8:12] == b"WAVE":
        return "WAV"
    if header.startswith(b"RIFF") and header[8:12] == b"AVI ":
        return "AVI"
    if header.startswith(b"fLaC"):
        return "FLAC"
    if header.startswith(b"OggS"):
        return "OGG"
    if header.startswith(b"FORM") and header[8:12] in {b"AIFF", b"AIFC"}:
        return "AIFF"
    if header[4:8] == b"ftyp":
        brand = header[8:12].decode("latin-1", errors="ignore").strip().lower()
        if brand.startswith("m4a") or brand in {"m4b", "m4p"}:
            return "M4A"
        if brand in {"qt", "qt  "}:
            return "MOV"
        if brand.startswith("3gp") or brand.startswith("3g2"):
            return "3GP"
        return "MP4"
    if header.startswith(b"\x1aE\xdf\xa3"):
        return "WEBM"
    if header.startswith(b"\x30\x26\xb2\x75\x8e\x66\xcf\x11"):
        return "WMA"
    if header.startswith(b"#!AMR"):
        return "AMR"
    if header[:4] == b"\x00\x00\x01\xba" or header[:4] == b"\x00\x00\x01\xb3":
        return "MPEG"
    return None


def probe_media(path: Path) -> dict:
    """Usa FFprobe para confirmar formato e se existe faixa de áudio."""
    empty = {"format": None, "codec": None, "has_audio": False, "has_video": False}
    if not config.FFPROBE_PATH or not Path(config.FFPROBE_PATH).is_file():
        return empty

    cmd = [
        str(config.FFPROBE_PATH),
        "-v",
        "error",
        "-show_entries",
        "format=format_name",
        "-show_entries",
        "stream=codec_type,codec_name",
        "-of",
        "json",
        str(path),
    ]
    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=45,
            creationflags=_creation_flags(),
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        logger.warning("FFprobe falhou ao inspecionar o arquivo: %s", exc)
        return empty

    if result.returncode != 0 or not (result.stdout or "").strip():
        logger.info("FFprobe não reconheceu o arquivo: %s", (result.stderr or "").strip())
        return empty

    try:
        data = json.loads(result.stdout)
    except json.JSONDecodeError:
        return empty

    fmt = _friendly_from_ffprobe(str((data.get("format") or {}).get("format_name") or ""))
    has_audio = False
    has_video = False
    codec = None
    for stream in data.get("streams") or []:
        kind = str(stream.get("codec_type") or "").lower()
        name = str(stream.get("codec_name") or "").upper() or None
        if kind == "audio":
            has_audio = True
            codec = codec or name
        elif kind == "video":
            has_video = True

    return {"format": fmt, "codec": codec, "has_audio": has_audio, "has_video": has_video}


def inspect_file(path: Path, original_name: str = "") -> dict:
    """Combina assinatura, FFprobe e extensão para descrever o arquivo."""
    magic = sniff_magic(path)
    probed = probe_media(path)
    ext = Path(original_name or path.name).suffix.lower().lstrip(".")
    ext_label = FRIENDLY_FORMATS.get(ext)

    detected = probed["format"] or magic or ext_label
    has_audio = probed["has_audio"]
    if probed["format"] is None and magic:
        has_audio = True

    return {
        "detected_format": detected,
        "detected_codec": probed["codec"],
        "has_audio": has_audio,
        "has_video": probed["has_video"],
        "extension": ext or None,
        "magic": magic,
        "is_supported": bool(detected) and has_audio,
    }


def extension_for_label(label: str | None, fallback: str = "bin") -> str:
    if not label:
        return fallback
    return CONTAINER_TO_EXT.get(label.upper(), fallback)
