"""Safe asynchronous document-upload endpoints."""

import os
import tempfile
import threading
import uuid
from pathlib import Path
from typing import Any

import logfire
from fastapi import APIRouter, BackgroundTasks, Depends, File, HTTPException, UploadFile, status

from app.config import settings
from app.ingestion.processor import process_file
from app.utils.security import verify_api_key

router = APIRouter(prefix="/ingest", tags=["ingestion"])

ALLOWED_EXTENSIONS = {"pdf", "html", "htm", "txt", "docx", "pptx"}
_MIME_TYPES = {
    "pdf": {"application/pdf"},
    "html": {"text/html", "application/xhtml+xml"},
    "htm": {"text/html", "application/xhtml+xml"},
    "txt": {"text/plain"},
    "docx": {"application/vnd.openxmlformats-officedocument.wordprocessingml.document"},
    "pptx": {"application/vnd.openxmlformats-officedocument.presentationml.presentation"},
}
_GENERIC_MIME_TYPES = {"", "application/octet-stream"}
_jobs: dict[str, dict[str, Any]] = {}
_jobs_lock = threading.Lock()


def _safe_filename(filename: str | None) -> tuple[str, str]:
    name = Path(filename or "").name
    if not name or name in {".", ".."} or len(name) > 255:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Provide a valid file name.")
    ext = name.lower().rsplit(".", 1)[-1] if "." in name else ""
    if ext not in ALLOWED_EXTENSIONS:
        allowed = ", ".join(sorted(ALLOWED_EXTENSIONS))
        raise HTTPException(status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE, detail=f"Unsupported file type. Allowed: {allowed}.")
    return name, ext


def _validate_content_type(extension: str, content_type: str | None) -> None:
    mime = (content_type or "").lower().split(";", 1)[0].strip()
    if mime not in _GENERIC_MIME_TYPES and mime not in _MIME_TYPES[extension]:
        raise HTTPException(status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE, detail="File content type does not match its extension.")


def _validate_file_signature(extension: str, first_bytes: bytes) -> None:
    if extension == "pdf" and not first_bytes.startswith(b"%PDF-"):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="The uploaded file is not a valid PDF.")
    if extension in {"docx", "pptx"} and not first_bytes.startswith(b"PK\x03\x04"):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="The uploaded file is not a valid Office document.")
    if extension in {"html", "htm", "txt"} and b"\x00" in first_bytes:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="The uploaded file does not appear to be text content.")


def _set_job(job_id: str, **values: Any) -> None:
    with _jobs_lock:
        _jobs[job_id].update(values)


def _process_upload(job_id: str, path: str, filename: str) -> None:
    _set_job(job_id, status="processing", progress=10)
    try:
        process_file(path, filename, "upload")
        _set_job(job_id, status="completed", progress=100, message="Document ingested successfully.")
    except Exception:
        logfire.exception("Ingestion failed.", job_id=job_id, filename=filename)
        _set_job(job_id, status="failed", progress=100, message="Document ingestion failed. Please verify the file and try again.")
    finally:
        try:
            os.unlink(path)
        except FileNotFoundError:
            pass


@router.post("/document", status_code=status.HTTP_202_ACCEPTED)
async def ingest_document(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    _api_key: str | None = Depends(verify_api_key),
):
    """Validate and queue a document; poll the returned job URL for completion."""
    filename, extension = _safe_filename(file.filename)
    _validate_content_type(extension, file.content_type)

    content_length = file.size
    if content_length is not None and content_length > settings.MAX_UPLOAD_BYTES:
        raise HTTPException(status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, detail="File exceeds the upload size limit.")

    tmp = tempfile.NamedTemporaryFile(delete=False, suffix=f".{extension}")
    try:
        total_size = 0
        first_bytes = b""
        while chunk := await file.read(64 * 1024):
            total_size += len(chunk)
            if total_size > settings.MAX_UPLOAD_BYTES:
                raise HTTPException(status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, detail="File exceeds the upload size limit.")
            if len(first_bytes) < 8 * 1024:
                first_bytes += chunk[: 8 * 1024 - len(first_bytes)]
            tmp.write(chunk)
        tmp.close()

        if not total_size:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="The uploaded file is empty.")
        _validate_file_signature(extension, first_bytes)

        job_id = str(uuid.uuid4())
        with _jobs_lock:
            _jobs[job_id] = {
                "job_id": job_id,
                "filename": filename,
                "status": "queued",
                "progress": 0,
                "message": "Document queued for ingestion.",
            }
        background_tasks.add_task(_process_upload, job_id, tmp.name, filename)
        return _jobs[job_id]
    except HTTPException:
        tmp.close()
        if os.path.exists(tmp.name):
            os.unlink(tmp.name)
        raise
    except Exception:
        tmp.close()
        if os.path.exists(tmp.name):
            os.unlink(tmp.name)
        logfire.exception("Could not accept document upload.", filename=filename)
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Could not accept the uploaded file.")
    finally:
        await file.close()


@router.get("/document/{job_id}")
def ingestion_status(job_id: str, _api_key: str | None = Depends(verify_api_key)):
    """Return the state of a previously accepted upload job."""
    with _jobs_lock:
        job = _jobs.get(job_id)
        if job is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Ingestion job not found.")
        return job.copy()
