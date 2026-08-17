"""Transcrição de áudio para texto com Whisper."""

from __future__ import annotations

import importlib
import importlib.util
import logging
import os
import threading
from collections.abc import Callable
from pathlib import Path

import config

logger = logging.getLogger("audioto-txt")

ProgressCallback = Callable[[float | None], None]

_model = None
_model_lock = threading.Lock()
_transcribe_lock = threading.Lock()
_ffmpeg_patched = False


def whisper_available() -> bool:
    """Verifica se o pacote Whisper existe, sem importar PyTorch na subida."""
    try:
        return importlib.util.find_spec("whisper") is not None
    except (ImportError, ValueError, ModuleNotFoundError):
        return False


def _whisper_transcribe_module():
    """O pacote expõe `whisper.transcribe` como função; precisamos do módulo."""
    return importlib.import_module("whisper.transcribe")


def _patch_whisper_ffmpeg() -> None:
    """Faz o Whisper usar o FFmpeg configurado, sem janela de console no Windows."""
    global _ffmpeg_patched
    if _ffmpeg_patched:
        return

    import subprocess

    import numpy as np
    import whisper.audio as whisper_audio

    ffmpeg = str(config.FFMPEG_PATH) if config.FFMPEG_PATH else "ffmpeg"
    flags = subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0

    def load_audio(file: str, sr: int = whisper_audio.SAMPLE_RATE):
        cmd = [
            ffmpeg,
            "-nostdin",
            "-threads",
            "0",
            "-i",
            file,
            "-f",
            "s16le",
            "-ac",
            "1",
            "-acodec",
            "pcm_s16le",
            "-ar",
            str(sr),
            "-",
        ]
        try:
            out = subprocess.run(
                cmd,
                capture_output=True,
                check=True,
                creationflags=flags,
            ).stdout
        except subprocess.CalledProcessError as exc:
            err = (exc.stderr or b"").decode("utf-8", errors="replace")
            raise RuntimeError(f"Failed to load audio: {err}") from exc
        return np.frombuffer(out, np.int16).flatten().astype(np.float32) / 32768.0

    whisper_audio.load_audio = load_audio
    _ffmpeg_patched = True


def get_model():
    global _model
    with _model_lock:
        if _model is None:
            import whisper

            _patch_whisper_ffmpeg()
            logger.info("Carregando modelo Whisper '%s'...", config.WHISPER_MODEL)
            _model = whisper.load_model(config.WHISPER_MODEL)
            logger.info("Modelo Whisper carregado.")
        return _model


def _patch_whisper_tqdm(progress_callback: ProgressCallback | None):
    import tqdm as tqdm_mod

    whisper_transcribe = _whisper_transcribe_module()
    original = whisper_transcribe.tqdm

    class ProgressTqdm(tqdm_mod.tqdm):
        def update(self, n=1):
            result = super().update(n)
            if progress_callback and self.total:
                percent = min(99.0, max(1.0, (float(self.n) / float(self.total)) * 100.0))
                progress_callback(percent)
            return result

        def close(self):
            if progress_callback and self.total:
                progress_callback(99.0)
            return super().close()

    class TqdmModule:
        tqdm = ProgressTqdm

    whisper_transcribe.tqdm = TqdmModule
    return original


def transcribe_file(input_path: Path, progress_callback: ProgressCallback | None = None) -> str:
    if not config.FFMPEG_PATH or not Path(config.FFMPEG_PATH).is_file():
        raise FileNotFoundError("FFmpeg não encontrado.")

    model = get_model()
    if progress_callback:
        progress_callback(1.0)

    whisper_transcribe = _whisper_transcribe_module()

    with _transcribe_lock:
        original_tqdm = _patch_whisper_tqdm(progress_callback)
        try:
            result = model.transcribe(
                str(input_path),
                language=config.WHISPER_LANGUAGE,
                verbose=False,
            )
        finally:
            whisper_transcribe.tqdm = original_tqdm

    if progress_callback:
        progress_callback(100.0)
    return str(result.get("text") or "").strip()
