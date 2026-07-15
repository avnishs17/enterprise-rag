import asyncio
import os
import tempfile

import logfire
from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.config import settings as app_settings
from app.ingestion.processor import process_file

router = APIRouter(prefix="/ingest", tags=["ingestion"])

_security = HTTPBearer(auto_error=False)

ALLOWED_EXTENSIONS = {"pdf", "html", "htm", "txt", "docx", "pptx"}


def _verify_api_key(credentials: HTTPAuthorizationCredentials = Depends(_security)):
    if not app_settings.API_KEY:
        return None
    if not credentials or credentials.credentials != app_settings.API_KEY:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or missing API key",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return credentials.credentials


@router.post("/document")
async def ingest_document(
    file: UploadFile = File(...),
    source_type: str = "upload",
    _api_key: str = Depends(_verify_api_key),
):
    ext = (file.filename or "").lower().rsplit(".", 1)[-1]
    if ext not in ALLOWED_EXTENSIONS:
        return {
            "status": "error",
            "message": f"Unsupported file type '.{ext}'. Allowed: {', '.join(sorted(ALLOWED_EXTENSIONS))}.",
        }

    tmp = tempfile.NamedTemporaryFile(delete=False, suffix=f".{ext}")
    try:
        while chunk := await file.read(65536):
            tmp.write(chunk)
        tmp.close()

        await asyncio.to_thread(process_file, tmp.name, file.filename or "uploaded_file", source_type)

        return {
            "status": "success",
            "message": f"'{file.filename}' ingested successfully.",
        }
    except Exception as e:
        logfire.error(f"Ingestion failed for {file.filename}: {e}")
        return {
            "status": "error",
            "message": f"Ingestion failed: {e}",
        }
    finally:
        if os.path.exists(tmp.name):
            os.unlink(tmp.name)
