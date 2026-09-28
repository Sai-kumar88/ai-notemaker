import io
import os
from pathlib import Path
from typing import List, Dict, Any, Optional
import pypdf
import docx

from app.config import settings


class DocumentExtractionError(Exception):
    """Raised when text cannot be extracted from the document."""
    pass


class UnsupportedFileTypeError(Exception):
    """Raised when uploaded file type is not supported."""
    pass


class DocumentPage:
    def __init__(self, page_number: int, text: str):
        self.page_number = page_number
        self.text = text


class ExtractedDocument:
    def __init__(self, filename: str, file_type: str, full_text: str, pages: List[DocumentPage]):
        self.filename = filename
        self.file_type = file_type
        self.full_text = full_text
        self.pages = pages
        self.word_count = len(full_text.split())
        self.char_count = len(full_text)


class DocumentService:
    @staticmethod
    def validate_file(filename: str, file_size: int) -> str:
        """
        Validates file extension and size against environment settings.
        No upload limits or allowed extensions are hardcoded in business logic.
        """
        ext = Path(filename).suffix.lower()
        if ext not in settings.allowed_extensions_set:
            allowed_str = ", ".join(settings.allowed_extensions)
            raise UnsupportedFileTypeError(
                f"Unsupported file format '{ext}'. Allowed formats: {allowed_str}"
            )
        
        if file_size > settings.max_file_size_bytes:
            raise DocumentExtractionError(
                f"File size ({file_size / (1024*1024):.2f} MB) exceeds maximum allowed size "
                f"({settings.max_file_size_mb} MB)."
            )
        
        return ext

    @classmethod
    def extract_text_from_file(cls, file_path: Path, original_filename: str) -> ExtractedDocument:
        """
        Extracts structured text and pages from a PDF or DOCX file.
        """
        ext = cls.validate_file(original_filename, file_path.stat().st_size)

        if ext == ".pdf":
            return cls._extract_from_pdf(file_path, original_filename)
        elif ext == ".docx":
            return cls._extract_from_docx(file_path, original_filename)
        else:
            raise UnsupportedFileTypeError(f"Unsupported file type: {ext}")

    @staticmethod
    def _extract_from_pdf(file_path: Path, filename: str) -> ExtractedDocument:
        pages: List[DocumentPage] = []
        full_text_parts: List[str] = []

        # Engine 1: Try PyMuPDF (fitz) - industry gold standard for textbooks & complex PDFs
        try:
            import fitz
            doc = fitz.open(str(file_path))
            if len(doc) == 0:
                raise DocumentExtractionError("PDF file contains no pages.")

            for idx, page in enumerate(doc, start=1):
                try:
                    page_text = page.get_text("text") or ""
                    page_text = page_text.strip()
                    if page_text:
                        pages.append(DocumentPage(page_number=idx, text=page_text))
                        full_text_parts.append(page_text)
                except Exception as p_err:
                    import logging
                    logging.getLogger(__name__).warning("PyMuPDF failed on page %d: %s", idx, p_err)

            doc.close()
        except DocumentExtractionError:
            raise
        except Exception as fitz_err:
            import logging
            logging.getLogger(__name__).warning("PyMuPDF extraction issue, attempting fallback: %s", fitz_err)

        # Engine 2: Fallback to pypdf if PyMuPDF extracted no text
        if not full_text_parts:
            try:
                reader = pypdf.PdfReader(str(file_path), strict=False)
                if len(reader.pages) == 0:
                    raise DocumentExtractionError("PDF file contains no pages.")

                for idx, page in enumerate(reader.pages, start=1):
                    try:
                        page_text = page.extract_text() or ""
                        page_text = page_text.strip()
                        if page_text:
                            pages.append(DocumentPage(page_number=idx, text=page_text))
                            full_text_parts.append(page_text)
                    except Exception as page_err:
                        import logging
                        logging.getLogger(__name__).warning("pypdf error on page %d: %s", idx, page_err)
            except DocumentExtractionError:
                raise
            except Exception as pypdf_err:
                raise DocumentExtractionError(f"Failed to extract text from PDF: {str(pypdf_err)}") from pypdf_err

        full_text = "\n\n".join(full_text_parts).strip()
        if not full_text:
            raise DocumentExtractionError(
                "No readable text could be extracted from the PDF. The document might be image-only (scanned), empty, or password-protected."
            )

        return ExtractedDocument(
            filename=filename,
            file_type="pdf",
            full_text=full_text,
            pages=pages
        )

    @staticmethod
    def _extract_from_docx(file_path: Path, filename: str) -> ExtractedDocument:
        try:
            doc = docx.Document(str(file_path))
            paragraphs = []
            for p in doc.paragraphs:
                text = p.text.strip()
                if text:
                    paragraphs.append(text)
            
            # Also extract text inside tables if any
            for table in doc.tables:
                for row in table.rows:
                    row_text = " | ".join(cell.text.strip() for cell in row.cells if cell.text.strip())
                    if row_text:
                        paragraphs.append(row_text)

            full_text = "\n\n".join(paragraphs).strip()
            if not full_text:
                raise DocumentExtractionError("DOCX file does not contain readable text.")

            # DOCX does not have fixed physical pages, treat as single flow
            pages = [DocumentPage(page_number=1, text=full_text)]

            return ExtractedDocument(
                filename=filename,
                file_type="docx",
                full_text=full_text,
                pages=pages
            )
        except DocumentExtractionError:
            raise
        except Exception as e:
            raise DocumentExtractionError(f"Failed to extract text from DOCX: {str(e)}") from e
