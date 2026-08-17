"""Transcrição de áudio para texto com Whisper."""

from __future__ import annotations

import logging
import threading
from collections.abc import Callable
from pathlib import Path

import config

logger = logging.getLogger("audioto-txt")

ProgressCallback = Callable[[float | None], None]

_model = None
_model_lock = threading.Lock()
_transcribe_lock = threading.Lock()


def whisper_available() -> bool:
    try:
        import whisper  # noqa: F401
    except ImportError:
        return False
    return True


def get_model():
    global _model
    with _model_lock:
        if _model is None:
            import whisper

            logger.info("Carregando modelo Whisper '%s'...", config.WHISPER_MODEL)
            _model = whisper.load_model(config.WHISPER_MODEL)
            logger.info("Modelo Whisper carregado.")
        return _model


def _patch_whisper_tqdm(progress_callback: ProgressCallback | None):
    import tqdm as tqdm_mod
    import whisper.transcribe as whisper_transcribe

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

    import whisper.transcribe as whisper_transcribe

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
