"""
app/routes/notes.py

Production-ready API endpoints for document note making, summarization,
chapter detection, and vector PDF export.
"""
import logging
import uuid
from pathlib import Path
from typing import List, Optional, Union

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
from app.utils.chapter_parser import parse_chapters_input, IGNORED_CHAPTER_INPUTS
from app.utils.file_utils import sanitize_filename, is_allowed_extension

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/notes", tags=["Notes & Summarization"])


@router.post(
    "/summarize",
    response_model=SummaryResponse,
    responses={
        400: {"model": ErrorResponse, "description": "Invalid file, empty payload, or unsupported format"},
        404: {"model": ErrorResponse, "description": "Requested chapter not found in document"},
        413: {"model": ErrorResponse, "description": "File exceeds size limit"},
        422: {"model": ErrorResponse, "description": "Document parsing error"},
        429: {"model": ErrorResponse, "description": "NVIDIA API rate limit exceeded"},
        500: {"model": ErrorResponse, "description": "Internal server or NVIDIA API error"},
        502: {"model": ErrorResponse, "description": "Upstream NVIDIA service failure"},
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
    Guarantees zero hallucination and safe cleanup of uploaded temporary files.
    """
    clean_filename = sanitize_filename(file.filename)
    if not clean_filename:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="No valid filename provided.")

    # Validate file extension against environment configuration
    if not is_allowed_extension(clean_filename, settings.allowed_extensions_set):
        allowed_str = ", ".join(settings.allowed_extensions)
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Unsupported file format '{Path(clean_filename).suffix.lower()}'. Allowed formats: {allowed_str}"
        )

    temp_filename = f"upload_{uuid.uuid4().hex}_{clean_filename}"
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

        if bytes_written == 0:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Uploaded file is empty (0 bytes)."
            )

        # Parse requested chapter numbers (if any)
        requested_chapters = parse_chapters_input(chapters)

        # Execute end-to-end summarization
        response = await SummaryService.process_document(
            file_path=temp_path,
            original_filename=clean_filename,
            requested_chapters=requested_chapters
        )
        return response

    except HTTPException:
        raise
    except ChapterNotFoundError as e:
        logger.warning("Chapter not found in document %s: %s", clean_filename, str(e))
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
        logger.error("Document extraction error on %s: %s", clean_filename, str(e))
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
            detail=f"An unexpected error occurred while processing the document: {str(e)}"
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
    responses={
        400: {"model": ErrorResponse, "description": "Invalid file, empty payload, or unsupported format"},
        422: {"model": ErrorResponse, "description": "Document text extraction failure"},
        500: {"model": ErrorResponse, "description": "Server processing failure"}
    },
    summary="Detect all chapters available in a document without generating a summary"
)
async def detect_document_chapters(
    file: UploadFile = File(..., description="Document file (.pdf or .docx)")
):
    """
    Extracts text and identifies all detected chapters with page numbers and word counts.
    Allows frontend clients to present a structured chapter picker before summarization.
    """
    clean_filename = sanitize_filename(file.filename)
    if not clean_filename:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="No valid filename provided.")

    # Validate file extension
    if not is_allowed_extension(clean_filename, settings.allowed_extensions_set):
        allowed_str = ", ".join(settings.allowed_extensions)
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Unsupported file format '{Path(clean_filename).suffix.lower()}'. Allowed formats: {allowed_str}"
        )

    temp_filename = f"detect_{uuid.uuid4().hex}_{clean_filename}"
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

        if bytes_written == 0:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Uploaded file is empty (0 bytes)."
            )

        document = DocumentService.extract_text_from_file(
            file_path=temp_path,
            original_filename=clean_filename
        )
        detected_list = ChapterService.get_detected_chapters_schema(document)

        return DetectChaptersResponse(
            success=True,
            filename=clean_filename,
            total_chapters_detected=len(detected_list),
            chapters=detected_list
        )

    except HTTPException:
        raise
    except DocumentExtractionError as e:
        logger.error("Document extraction error during chapter detection: %s", str(e))
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(e))
    except Exception as e:
        logger.exception("Error detecting chapters in %s: %s", clean_filename, str(e))
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
    Returns non-sensitive configuration parameters to allow client interfaces
    to validate file size and format limits prior to upload.
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
    Renders formatted notes into a multi-page vector A4 PDF using the PyMuPDF typography engine.
    Guarantees no broken sentences or cut words across page boundaries.
    """
    if not PdfExportService.is_available():
        logger.warning("PyMuPDF engine not available on this system. Client-side PDF fallback should be used.")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Server-side PDF engine (PyMuPDF) is unavailable. Please use client-side PDF export."
        )

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
