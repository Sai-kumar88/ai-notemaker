import io
import pytest
from pathlib import Path
from pypdf import PdfWriter
import docx

from app.services.document_service import (
    DocumentService,
    DocumentExtractionError,
    UnsupportedFileTypeError
)
from app.config import settings

def create_in_memory_pdf(text: str) -> io.BytesIO:
    """Creates a minimal valid PDF containing text using pypdf."""
    from pypdf.generic import DictionaryObject, NameObject, ArrayObject, DecodedStreamObject, TextStringObject

    # Simple text stream in PDF
    stream = f"BT /F1 12 Tf 72 712 Td ({text}) Tj ET"
    writer = PdfWriter()
    page = writer.add_blank_page(width=612, height=792)
    buffer = io.BytesIO()
    writer.write(buffer)
    buffer.seek(0)
    return buffer

def test_validate_file_extensions():
    assert DocumentService.validate_file("document.pdf", 1024) == ".pdf"
    assert DocumentService.validate_file("document.docx", 1024) == ".docx"
    assert DocumentService.validate_file("DOCUMENT.PDF", 1024) == ".pdf"

    with pytest.raises(UnsupportedFileTypeError):
        DocumentService.validate_file("document.txt", 1024)

    with pytest.raises(UnsupportedFileTypeError):
        DocumentService.validate_file("document.exe", 1024)

def test_validate_file_size_limit():
    max_bytes = settings.max_file_size_bytes
    # Within limit
    DocumentService.validate_file("doc.pdf", max_bytes)

    # Exceeds limit
    with pytest.raises(DocumentExtractionError):
        DocumentService.validate_file("doc.pdf", max_bytes + 1)

def test_extract_from_docx(tmp_path: Path):
    doc = docx.Document()
    doc.add_heading("Chapter 1: The Solar System", level=1)
    doc.add_paragraph("The sun is a G-type main-sequence star comprising 99.86% of the solar system mass.")
    
    file_path = tmp_path / "solar.docx"
    doc.save(str(file_path))

    extracted = DocumentService.extract_text_from_file(file_path, "solar.docx")
    assert extracted.file_type == "docx"
    assert "Chapter 1: The Solar System" in extracted.full_text
    assert "99.86%" in extracted.full_text
    assert extracted.word_count > 10
