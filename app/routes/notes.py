import json
import logging
import uuid
import shutil
from pathlib import Path
from typing import List, Optional, Union

import re
from fastapi import APIRouter, File, Form, UploadFile, HTTPException, status
from fastapi.responses import Response
from app.config import settings
from app.schemas.note_schema import (
    SummaryResponse,
    DetectChaptersResponse,
    ErrorResponse,
    PdfExportRequest
)
from app.services.pdf_export_service import PdfExportService
from app.services.document_service import (
    DocumentService,
    DocumentExtractionError,
    UnsupportedFileTypeError
)
from app.services.chapter_service import ChapterService, ChapterNotFoundError
from app.services.summary_service import SummaryService
from app.services.nvidia_service import NvidiaAuthError, NvidiaRateLimitError, NvidiaServiceError

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/notes", tags=["Notes & Summarization"])

IGNORED_CHAPTER_INPUTS = frozenset({
    "string", "none", "null", "all", "full", "[]", '""', "''", "-", "undefined"
})

def parse_chapters_input(chapters_raw: Optional[Union[str, List[str]]]) -> Optional[List[str]]:
    """
    Parses optional chapter input from various frontend formats.
    If omitted, empty, or dummy default (e.g. Swagger's 'string'), returns None,
    which triggers full document summarization without asking for chapter numbers.
    """
    if not chapters_raw:
        return None

    if isinstance(chapters_raw, list):
        parsed = [
            str(c).strip() for c in chapters_raw
            if str(c).strip() and str(c).strip().lower() not in IGNORED_CHAPTER_INPUTS
        ]
        return parsed if parsed else None

    raw_str = chapters_raw.strip()
    if not raw_str or raw_str.lower() in IGNORED_CHAPTER_INPUTS:
        return None

    # Try JSON parsing first
    if raw_str.startswith("[") and raw_str.endswith("]"):
        try:
            parsed_json = json.loads(raw_str)
            if isinstance(parsed_json, list):
                result = [
                    str(x).strip() for x in parsed_json
                    if str(x).strip() and str(x).strip().lower() not in IGNORED_CHAPTER_INPUTS
                ]
                return result if result else None
        except Exception:
            pass

    # Comma-separated fallback
    items = [
        c.strip() for c in raw_str.split(",")
        if c.strip() and c.strip().lower() not in IGNORED_CHAPTER_INPUTS
    ]
    return items if items else None

@router.post(
    "/summarize",
    response_model=SummaryResponse,
    responses={
        400: {"model": ErrorResponse, "description": "Invalid file or parameters"},
        404: {"model": ErrorResponse, "description": "Requested chapter not found in document"},
        413: {"model": ErrorResponse, "description": "File exceeds size limit"},
        422: {"model": ErrorResponse, "description": "Document parsing error"},
        500: {"model": ErrorResponse, "description": "Server or NVIDIA API error"},
    },
    summary="Upload document and generate strictly faithful notes"
)
async def summarize_document(
    file: UploadFile = File(..., description="Document file (.pdf or .docx)"),
    chapters: Optional[str] = Form(
        None,
        description="Optional chapter numbers (e.g. '1, 2' or leave blank). If empty, entire document is summarized."
    )
):
    """
    Uploads a PDF or DOCX file, extracts text, optionally filters by requested chapters,
    splits into chunks if large, and produces a strictly faithful summary via NVIDIA NIM API.
    Temporary files are guaranteed to be cleaned up after processing.
    """
    if not file.filename:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="No filename provided.")

    # Validate file extension
    ext = Path(file.filename).suffix.lower()
    if ext not in settings.allowed_extensions_set:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Unsupported file format '{ext}'. Allowed formats: {', '.join(settings.allowed_extensions)}"
        )

    # Save to a temporary file safely
    temp_filename = f"upload_{uuid.uuid4().hex}_{Path(file.filename).name}"
    temp_path = settings.upload_path / temp_filename
    bytes_written = 0

    try:
        with open(temp_path, "wb") as buffer:
            while chunk := await file.read(settings.upload_buffer_bytes):
                bytes_written += len(chunk)
                if bytes_written > settings.max_file_size_bytes:
                    raise HTTPException(
                        status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                        detail=f"File exceeds maximum allowed size of {settings.max_file_size_mb} MB."
                    )
                buffer.write(chunk)

        # Parse chapter numbers
        requested_chapters = parse_chapters_input(chapters)

        # Execute end-to-end summarization
        response = await SummaryService.process_document(
            file_path=temp_path,
            original_filename=file.filename,
            requested_chapters=requested_chapters
        )
        return response

    except HTTPException:
        raise
    except ChapterNotFoundError as e:
        logger.warning("Chapter not found: %s", str(e))
        clean_missing = ", ".join(str(c) for c in e.missing_chapters)
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={
                "message": f"Requested chapter(s) {clean_missing} could not be found in the document.",
                "missing_chapters": e.missing_chapters
            }
        )
    except UnsupportedFileTypeError as e:
        logger.warning("Unsupported file type: %s", str(e))
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except DocumentExtractionError as e:
        logger.error("Document extraction error: %s", str(e))
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(e))
    except NvidiaAuthError as e:
        logger.error("NVIDIA authentication error: %s", str(e))
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))
    except NvidiaRateLimitError as e:
        logger.warning("NVIDIA rate limit: %s", str(e))
        raise HTTPException(status_code=status.HTTP_429_TOO_MANY_REQUESTS, detail=str(e))
    except NvidiaServiceError as e:
        logger.error("NVIDIA service failure: %s", str(e))
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(e))
    except Exception as e:
        logger.exception("Unexpected error in summarize_document: %s", str(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"An unexpected error occurred: {str(e)}"
        )
    finally:
        # Guarantee safe cleanup of uploaded file
        if temp_path.exists():
            try:
                temp_path.unlink()
                logger.info("Cleaned up temporary file: %s", temp_path)
            except Exception as clean_err:
                logger.warning("Failed to clean up temporary file %s: %s", temp_path, clean_err)

@router.post(
    "/detect-chapters",
    response_model=DetectChaptersResponse,
    summary="Detect all chapters available in a document without generating a summary"
)
async def detect_document_chapters(
    file: UploadFile = File(..., description="Document file (.pdf or .docx)")
):
    """
    Extracts text and lists all detected chapters with page numbers and word counts.
    Allows the frontend to show a chapter selector to the user.
    """
    if not file.filename:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="No filename provided.")

    temp_filename = f"detect_{uuid.uuid4().hex}_{Path(file.filename).name}"
    temp_path = settings.upload_path / temp_filename
    bytes_written = 0

    try:
        with open(temp_path, "wb") as buffer:
            while chunk := await file.read(settings.upload_buffer_bytes):
                bytes_written += len(chunk)
                if bytes_written > settings.max_file_size_bytes:
                    raise HTTPException(
                        status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                        detail=f"File exceeds maximum allowed size of {settings.max_file_size_mb} MB."
                    )
                buffer.write(chunk)

        document = DocumentService.extract_text_from_file(
            file_path=temp_path,
            original_filename=file.filename
        )
        detected_list = ChapterService.get_detected_chapters_schema(document)

        return DetectChaptersResponse(
            success=True,
            filename=file.filename,
            total_chapters_detected=len(detected_list),
            chapters=detected_list
        )

    except HTTPException:
        raise
    except DocumentExtractionError as e:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(e))
    except Exception as e:
        logger.exception("Error detecting chapters: %s", str(e))
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))
    finally:
        if temp_path.exists():
            try:
                temp_path.unlink()
            except Exception as clean_err:
                logger.warning("Failed to clean up temporary file %s: %s", temp_path, clean_err)

@router.get(
    "/info",
    summary="Get current server configuration and limits"
)
async def get_service_info():
    """
    Returns non-sensitive configuration to allow the frontend to validate client-side limits.
    """
    return {
        "allowed_extensions": settings.allowed_extensions,
        "max_file_size_mb": settings.max_file_size_mb,
        "nvidia_model": settings.nvidia_model,
        "chunk_size_chars": settings.chunk_size_chars,
        "is_api_key_configured": bool(
            settings.nvidia_api_key and settings.nvidia_api_key != "your_nvidia_api_key_here"
        )
    }


@router.post(
    "/export-pdf",
    summary="Generate high-fidelity vector PDF study notes without sentence breaks"
)
async def export_pdf(payload: PdfExportRequest):
    """
    Renders formatted notes into a multi-page vector A4 PDF using PyMuPDF typography engine.
    Guarantees no broken sentences or cut words across page boundaries.
    """
    try:
        pdf_bytes = PdfExportService.generate_pdf_from_html(
            html_content=payload.html,
            title=payload.title,
            scope=payload.scope,
            word_count=payload.word_count
        )
        return Response(
            content=pdf_bytes,
            media_type="application/pdf",
            headers={
                "Content-Disposition": 'attachment; filename="AI STUDY NOTES & GUIDE.pdf"'
            }
        )
    except Exception as e:
        logger.exception("Failed to export PDF: %s", str(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to generate PDF: {str(e)}"
        )
