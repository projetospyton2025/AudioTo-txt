"""Conversão de áudio para MP3 via FFmpeg (subprocess seguro)."""

from __future__ import annotations

import logging
import os
import subprocess
import threading
from collections.abc import Callable
from pathlib import Path

import config

logger = logging.getLogger("audioto-mp3")

ProgressCallback = Callable[[float | None], None]


def _creation_flags() -> int:
    if os.name == "nt":
        return getattr(subprocess, "CREATE_NO_WINDOW", 0)
    return 0


def _parse_timecode(value: str) -> float | None:
    value = value.strip()
    if not value or value.startswith("N/A"):
        return None
    parts = value.split(":")
    if len(parts) != 3:
        return None
    try:
        hours = int(parts[0])
        minutes = int(parts[1])
        seconds = float(parts[2])
    except ValueError:
        return None
    return hours * 3600 + minutes * 60 + seconds


def get_duration_seconds(input_path: Path) -> float | None:
    if not config.FFPROBE_PATH:
        return None

    cmd = [
        str(config.FFPROBE_PATH),
        "-v",
        "error",
        "-show_entries",
        "format=duration",
        "-of",
        "default=noprint_wrappers=1:nokey=1",
        str(input_path),
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
        logger.warning("Não foi possível obter a duração do áudio: %s", exc)
        return None

    raw = (result.stdout or "").strip()
    if not raw:
        return None
    try:
        duration = float(raw)
    except ValueError:
        return None
    if duration <= 0:
        return None
    return duration


def convert_to_mp3(
    input_path: Path,
    output_path: Path,
    progress_callback: ProgressCallback | None = None,
) -> None:
    if not config.FFMPEG_PATH or not Path(config.FFMPEG_PATH).is_file():
        raise FileNotFoundError("FFmpeg não encontrado.")

    duration = get_duration_seconds(input_path)
    if progress_callback:
        progress_callback(0.0 if duration else None)

    cmd = [
        str(config.FFMPEG_PATH),
        "-y",
        "-i",
        str(input_path),
        "-vn",
        "-codec:a",
        config.MP3_CODEC,
        "-b:a",
        config.MP3_BITRATE,
        "-ar",
        config.MP3_SAMPLE_RATE,
        "-progress",
        "pipe:1",
        "-nostats",
        "-loglevel",
        "error",
        str(output_path),
    ]

    try:
        process = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding="utf-8",
            errors="replace",
            bufsize=1,
            creationflags=_creation_flags(),
        )
    except OSError as exc:
        logger.exception("Falha ao iniciar o FFmpeg: %s", exc)
        raise RuntimeError("Falha ao iniciar o FFmpeg.") from exc

    stderr_chunks: list[str] = []

    def _consume_stderr() -> None:
        if not process.stderr:
            return
        for line in process.stderr:
            stderr_chunks.append(line)

    stderr_thread = threading.Thread(target=_consume_stderr, daemon=True)
    stderr_thread.start()

    try:
        if process.stdout:
            for raw_line in process.stdout:
                line = raw_line.strip()
                if not line or "=" not in line:
                    continue
                key, value = line.split("=", 1)
                if key != "out_time":
                    continue
                current = _parse_timecode(value)
                if current is None or duration is None or duration <= 0:
                    if progress_callback:
                        progress_callback(None)
                    continue
                percent = min(99.0, max(0.0, (current / duration) * 100.0))
                if progress_callback:
                    progress_callback(percent)

        return_code = process.wait(timeout=config.CONVERSION_TIMEOUT_SECONDS)
    except subprocess.TimeoutExpired as exc:
        process.kill()
        process.wait(timeout=10)
        logger.error("Conversão excedeu o tempo limite.")
        raise RuntimeError("A conversão demorou demais e foi interrompida.") from exc
    finally:
        stderr_thread.join(timeout=2)

    stderr_text = "".join(stderr_chunks).strip()
    if return_code != 0:
        logger.error("FFmpeg falhou (código %s): %s", return_code, stderr_text)
        raise RuntimeError("Falha na conversão do FFmpeg.")

    if not output_path.is_file() or output_path.stat().st_size == 0:
        logger.error("Arquivo MP3 de saída ausente ou vazio.")
        raise RuntimeError("A conversão não gerou um arquivo MP3 válido.")

    if progress_callback:
        progress_callback(100.0)
