"""AudioTo-txt — transcrição local de áudio para texto."""

from __future__ import annotations

import logging
import threading
import time
import uuid
from pathlib import Path

from flask import Flask, abort, jsonify, make_response, render_template, request, send_from_directory
from werkzeug.exceptions import HTTPException, RequestEntityTooLarge
from werkzeug.utils import secure_filename

import config
from media import inspect_file
from transcriber import transcribe_file, whisper_available

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
logger = logging.getLogger("audioto-txt")

config.ensure_directories()

app = Flask(__name__)
app.config["MAX_CONTENT_LENGTH"] = config.MAX_CONTENT_LENGTH
app.config["UPLOAD_FOLDER"] = str(config.UPLOAD_FOLDER)
app.config["TRANSCRIPTS_FOLDER"] = str(config.TRANSCRIPTS_FOLDER)

jobs_lock = threading.Lock()
jobs: dict[str, dict] = {}

USER_ERRORS = {
    "invalid_file": "Arquivo inválido. Selecione um áudio suportado.",
    "unsupported_format": "Formato não suportado. Envie áudio ou vídeo com faixa de som (MP3, WAV, MP4, M4A, WEBM e similares).",
    "no_audio": "Este arquivo não tem faixa de áudio. Envie um som ou um vídeo com áudio.",
    "file_too_large": "O arquivo é muito grande. O limite é 500 MB.",
    "ffmpeg_missing": "FFmpeg não encontrado. Verifique a instalação e o caminho configurado.",
    "whisper_missing": "O Whisper não está instalado neste ambiente. Ative a pasta audio e instale as dependências.",
    "conversion_failed": "Não foi possível transcrever este arquivo. Verifique se o áudio está válido e tente novamente.",
    "corrupted": "O arquivo parece corrompido ou incompleto. Tente outro áudio.",
    "not_found": "Transcrição não encontrada. Envie o áudio novamente.",
    "busy": "Já existe uma transcrição em andamento. Aguarde a conclusão.",
    "unexpected": "Ocorreu um erro inesperado. Tente novamente.",
}


def _user_error(code: str) -> str:
    return USER_ERRORS.get(code, USER_ERRORS["unexpected"])


def _extension(filename: str) -> str:
    return Path(filename).suffix.lower().lstrip(".")


BLOCKED_EXTENSIONS = {
    "exe",
    "bat",
    "cmd",
    "com",
    "ps1",
    "js",
    "msi",
    "dll",
    "scr",
    "vbs",
}


def _is_blocked(filename: str) -> bool:
    return _extension(filename) in BLOCKED_EXTENSIONS


def _safe_stem(filename: str) -> str:
    secured = secure_filename(filename)
    stem = Path(secured).stem.strip("._")
    return stem or "audio"


def _is_inside(path: Path, folder: Path) -> bool:
    try:
        path.resolve().relative_to(folder.resolve())
        return True
    except ValueError:
        return False


def _delete_quietly(path: Path | None) -> None:
    if not path:
        return
    try:
        if path.is_file():
            path.unlink()
    except OSError as exc:
        logger.warning("Não foi possível remover %s: %s", path, exc)


def cleanup_old_files(max_age: int = config.CLEANUP_MAX_AGE_SECONDS) -> None:
    now = time.time()
    for folder in (config.UPLOAD_FOLDER, config.TRANSCRIPTS_FOLDER):
        if not folder.is_dir():
            continue
        for item in folder.iterdir():
            if not item.is_file():
                continue
            try:
                age = now - item.stat().st_mtime
            except OSError:
                continue
            if age >= max_age:
                _delete_quietly(item)


def _cleanup_job_files(job: dict) -> None:
    _delete_quietly(job.get("input_path"))
    _delete_quietly(job.get("output_path"))


def _set_job(job_id: str, **updates) -> None:
    with jobs_lock:
        job = jobs.get(job_id)
        if job:
            job.update(updates)


def _run_transcription(job_id: str) -> None:
    with jobs_lock:
        job = jobs.get(job_id)
        if not job:
            return
        input_path: Path = job["input_path"]
        output_path: Path = job["output_path"]

    try:
        _set_job(job_id, stage="loading_model", progress=1.0)

        def on_progress(percent: float | None) -> None:
            _set_job(job_id, stage="transcribing", progress=percent)

        text = transcribe_file(input_path, on_progress)
        output_path.write_text(text + ("\n" if text else ""), encoding="utf-8")
        size = output_path.stat().st_size
        _set_job(
            job_id,
            status="done",
            stage="done",
            progress=100.0,
            text=text,
            output_size=size,
            error_code=None,
        )
        _delete_quietly(input_path)
        logger.info("Transcrição concluída: %s -> %s", input_path.name, output_path.name)
    except FileNotFoundError:
        logger.exception("FFmpeg ausente durante a transcrição.")
        _set_job(job_id, status="error", progress=None, error_code="ffmpeg_missing")
        _delete_quietly(input_path)
        _delete_quietly(output_path)
    except Exception:
        logger.exception("Falha na transcrição do job %s", job_id)
        _set_job(job_id, status="error", progress=None, error_code="conversion_failed")
        _delete_quietly(input_path)
        _delete_quietly(output_path)


def _job_payload(job_id: str, job: dict) -> dict:
    payload = {
        "ok": True,
        "job_id": job_id,
        "status": job["status"],
        "stage": job.get("stage"),
        "progress": job.get("progress"),
        "original_name": job.get("original_name"),
        "download_name": job.get("download_name"),
        "detected_format": job.get("detected_format"),
        "detected_codec": job.get("detected_codec"),
    }
    if job["status"] == "done":
        payload.update(
            {
                "filename": job["output_name"],
                "size": job.get("output_size"),
                "text": job.get("text") or "",
                "download_url": f"/download/{job['output_name']}",
            }
        )
    if job["status"] == "error":
        payload.update(
            {
                "ok": False,
                "error": _user_error(job.get("error_code") or "conversion_failed"),
                "code": job.get("error_code") or "conversion_failed",
            }
        )
    return payload


@app.errorhandler(RequestEntityTooLarge)
@app.errorhandler(413)
def handle_too_large(_error):
    return jsonify(ok=False, error=_user_error("file_too_large"), code="file_too_large"), 413


@app.errorhandler(404)
def handle_not_found(_error):
    if request.path.startswith(("/download/", "/status/", "/reset/", "/transcribe", "/convert")):
        return jsonify(ok=False, error=_user_error("not_found"), code="not_found"), 404
    return jsonify(ok=False, error=_user_error("not_found"), code="not_found"), 404


@app.errorhandler(Exception)
def handle_unexpected(error):
    if isinstance(error, HTTPException):
        return error
    logger.exception("Erro não tratado: %s", error)
    return jsonify(ok=False, error=_user_error("unexpected"), code="unexpected"), 500


@app.get("/")
def index():
    cleanup_old_files()
    html = render_template(
        "index.html",
        max_file_size=config.MAX_FILE_SIZE,
        allowed_extensions=sorted(config.ALLOWED_EXTENSIONS),
        whisper_model=config.WHISPER_MODEL,
        whisper_language=config.WHISPER_LANGUAGE,
    )
    response = make_response(html)
    response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
    response.headers["Pragma"] = "no-cache"
    return response


def _start_job():
    cleanup_old_files()

    if not config.FFMPEG_PATH or not Path(config.FFMPEG_PATH).is_file():
        logger.error("FFmpeg não encontrado.")
        return jsonify(ok=False, error=_user_error("ffmpeg_missing"), code="ffmpeg_missing"), 503

    if not whisper_available():
        logger.error("Whisper não está instalado neste ambiente.")
        return jsonify(ok=False, error=_user_error("whisper_missing"), code="whisper_missing"), 503

    with jobs_lock:
        if any(job.get("status") == "converting" for job in jobs.values()):
            return jsonify(ok=False, error=_user_error("busy"), code="busy"), 409

    uploaded = request.files.get("file")
    if uploaded is None or not uploaded.filename:
        return jsonify(ok=False, error=_user_error("invalid_file"), code="invalid_file"), 400

    original_name = uploaded.filename
    if _is_blocked(original_name):
        return jsonify(ok=False, error=_user_error("unsupported_format"), code="unsupported_format"), 400

    content_length = request.content_length
    if content_length is not None and content_length > config.MAX_FILE_SIZE + (1024 * 1024):
        return jsonify(ok=False, error=_user_error("file_too_large"), code="file_too_large"), 413

    job_id = uuid.uuid4().hex
    ext = _extension(original_name) or "bin"
    if ext in BLOCKED_EXTENSIONS:
        return jsonify(ok=False, error=_user_error("unsupported_format"), code="unsupported_format"), 400
    input_name = f"{job_id}.{ext}"
    output_name = f"{job_id}.txt"
    input_path = (config.UPLOAD_FOLDER / input_name).resolve()
    output_path = (config.TRANSCRIPTS_FOLDER / output_name).resolve()

    if not _is_inside(input_path, config.UPLOAD_FOLDER) or not _is_inside(output_path, config.TRANSCRIPTS_FOLDER):
        return jsonify(ok=False, error=_user_error("invalid_file"), code="invalid_file"), 400

    try:
        uploaded.save(str(input_path))
    except OSError:
        logger.exception("Falha ao salvar o upload.")
        return jsonify(ok=False, error=_user_error("unexpected"), code="unexpected"), 500

    if not input_path.is_file() or input_path.stat().st_size == 0:
        _delete_quietly(input_path)
        return jsonify(ok=False, error=_user_error("corrupted"), code="corrupted"), 400

    if input_path.stat().st_size > config.MAX_FILE_SIZE:
        _delete_quietly(input_path)
        return jsonify(ok=False, error=_user_error("file_too_large"), code="file_too_large"), 413

    inspection = inspect_file(input_path, original_name)
    logger.info(
        "Mídia detectada: arquivo=%s formato=%s codec=%s audio=%s video=%s",
        original_name,
        inspection.get("detected_format"),
        inspection.get("detected_codec"),
        inspection.get("has_audio"),
        inspection.get("has_video"),
    )
    if not inspection.get("has_audio"):
        _delete_quietly(input_path)
        return jsonify(ok=False, error=_user_error("no_audio"), code="no_audio"), 400
    if not inspection.get("is_supported"):
        _delete_quietly(input_path)
        return jsonify(ok=False, error=_user_error("unsupported_format"), code="unsupported_format"), 400

    download_name = f"{_safe_stem(original_name)}.txt"
    job = {
        "status": "converting",
        "stage": "queued",
        "progress": None,
        "original_name": Path(original_name).name,
        "download_name": download_name,
        "detected_format": inspection.get("detected_format"),
        "detected_codec": inspection.get("detected_codec"),
        "input_path": input_path,
        "output_path": output_path,
        "output_name": output_name,
        "output_size": None,
        "text": None,
        "error_code": None,
        "created_at": time.time(),
    }

    with jobs_lock:
        jobs[job_id] = job

    worker = threading.Thread(target=_run_transcription, args=(job_id,), daemon=True)
    worker.start()

    return jsonify(
        ok=True,
        job_id=job_id,
        status="converting",
        stage="queued",
        progress=None,
        detected_format=inspection.get("detected_format"),
        detected_codec=inspection.get("detected_codec"),
    )


@app.post("/transcribe")
@app.post("/convert")
def transcribe():
    return _start_job()


@app.get("/status/<job_id>")
def status(job_id: str):
    safe_id = secure_filename(job_id)
    if not safe_id or safe_id != job_id:
        abort(404)

    with jobs_lock:
        job = jobs.get(job_id)
        if not job:
            return jsonify(ok=False, error=_user_error("not_found"), code="not_found"), 404
        payload = _job_payload(job_id, job)
    return jsonify(payload)


@app.get("/download/<filename>")
def download(filename: str):
    safe_name = secure_filename(filename)
    if not safe_name or Path(safe_name).suffix.lower() != ".txt":
        abort(404)

    file_path = (config.TRANSCRIPTS_FOLDER / safe_name).resolve()
    if not _is_inside(file_path, config.TRANSCRIPTS_FOLDER) or not file_path.is_file():
        abort(404)

    download_name = safe_name
    with jobs_lock:
        for job in jobs.values():
            if job.get("output_name") == safe_name and job.get("download_name"):
                download_name = job["download_name"]
                break

    return send_from_directory(
        directory=str(config.TRANSCRIPTS_FOLDER),
        path=safe_name,
        as_attachment=True,
        download_name=download_name,
        mimetype="text/plain; charset=utf-8",
    )


@app.post("/reset/<job_id>")
def reset_job(job_id: str):
    safe_id = secure_filename(job_id)
    if not safe_id or safe_id != job_id:
        abort(404)

    with jobs_lock:
        job = jobs.pop(job_id, None)

    if job:
        if job.get("status") == "converting":
            with jobs_lock:
                jobs[job_id] = job
            return jsonify(ok=False, error=_user_error("busy"), code="busy"), 409
        _cleanup_job_files(job)

    return jsonify(ok=True)


def main() -> None:
    import sys

    cleanup_old_files()
    ffmpeg_info = str(config.FFMPEG_PATH) if config.FFMPEG_PATH else "não encontrado"
    print("AudioTo-txt iniciado!")
    print(f"Acesse: http://{config.HOST}:{config.PORT}")
    print(f"Python: {sys.executable}")
    print(f"FFprobe: {config.FFPROBE_PATH or 'não encontrado'}")
    print(f"Whisper: modelo {config.WHISPER_MODEL} · idioma {config.WHISPER_LANGUAGE}")
    if not config.FFMPEG_PATH:
        print("Aviso: FFmpeg não foi localizado. A transcrição não funcionará até o caminho ser configurado.")
    if not whisper_available():
        audio_python = config.BASE_DIR / "audio" / "Scripts" / "python.exe"
        print("ERRO: Whisper não está neste Python.")
        print("Não use: py app.py")
        print("Use este comando:")
        print(f'  "{audio_python}" app.py')
        raise SystemExit(1)
    app.run(host=config.HOST, port=config.PORT, debug=False, threaded=True)


if __name__ == "__main__":
    main()
