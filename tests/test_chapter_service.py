import pytest
from app.services.document_service import ExtractedDocument, DocumentPage
from app.services.chapter_service import ChapterService, ChapterNotFoundError


SAMPLE_DOCUMENT_TEXT = """
Introduction to Modern Computing

Chapter 1: The Foundations
This chapter explains basic computer architecture.
CPUs execute instructions fetched from memory.
Binary code forms the lowest level of software.

Chapter 2: Operating Systems
Operating systems manage hardware resources like memory and disk.
Processes and threads execute concurrently under OS scheduling.
Virtual memory allows programs to address more space than physical RAM.

Chapter 3: Computer Networks
Networks connect independent computing nodes across links.
The TCP/IP stack provides layered communication protocols.
Routers direct packets across wide area networks.
"""


def create_sample_document(text: str = SAMPLE_DOCUMENT_TEXT) -> ExtractedDocument:
    pages = [
        DocumentPage(page_number=1, text=text[: len(text) // 2]),
        DocumentPage(page_number=2, text=text[len(text) // 2 :]),
    ]
    return ExtractedDocument(
        filename="test_course.pdf",
        file_type="pdf",
        full_text=text,
        pages=pages
    )


def test_missing_chapter_numbers_triggers_full_document():
    doc = create_sample_document()
    
    # None triggers full document
    extracted, chapters, is_full = ChapterService.extract_requested_content(doc, requested_chapters=None)
    assert is_full is True
    assert extracted == doc.full_text
    assert chapters == []

    # Empty list triggers full document
    extracted, chapters, is_full = ChapterService.extract_requested_content(doc, requested_chapters=[])
    assert is_full is True
    assert extracted == doc.full_text
    assert chapters == []

    # List of whitespace strings triggers full document
    extracted, chapters, is_full = ChapterService.extract_requested_content(doc, requested_chapters=["", "   "])
    assert is_full is True
    assert extracted == doc.full_text


def test_detect_all_chapters():
    doc = create_sample_document()
    detected = ChapterService.detect_chapters(doc)
    identifiers = [c["normalized_identifier"] for c in detected]
    assert identifiers == ["1", "2", "3"]
    assert "The Foundations" in detected[0]["title"]
    assert "Operating Systems" in detected[1]["title"]
    assert "Computer Networks" in detected[2]["title"]


def test_single_chapter_extraction():
    doc = create_sample_document()
    extracted, chapters, is_full = ChapterService.extract_requested_content(doc, requested_chapters=["2"])
    assert is_full is False
    assert chapters == ["2"]
    assert "Operating systems manage hardware resources" in extracted
    assert "The Foundations" not in extracted
    assert "Computer Networks" not in extracted


def test_multiple_chapter_numbers_work():
    doc = create_sample_document()
    extracted, chapters, is_full = ChapterService.extract_requested_content(doc, requested_chapters=["1", "3"])
    assert is_full is False
    assert set(chapters) == {"1", "3"}
    assert "Chapter 1: The Foundations" in extracted
    assert "CPUs execute instructions fetched from memory" in extracted
    assert "Chapter 3: Computer Networks" in extracted
    assert "The TCP/IP stack provides layered communication protocols" in extracted
    # Chapter 2 content must NOT be in the extracted text
    assert "Operating systems manage hardware resources" not in extracted


def test_missing_chapter_produces_error_rather_than_hallucination():
    doc = create_sample_document()
    
    # Asking for a chapter that does not exist in the document (e.g. Chapter 5)
    with pytest.raises(ChapterNotFoundError) as exc_info:
        ChapterService.extract_requested_content(doc, requested_chapters=["5"])
    
    assert "5" in exc_info.value.missing_chapters
    assert "1" in exc_info.value.available_chapters

    # Asking for both valid and missing chapter
    with pytest.raises(ChapterNotFoundError) as exc_info_mixed:
        ChapterService.extract_requested_content(doc, requested_chapters=["1", "99"])
    
    assert "99" in exc_info_mixed.value.missing_chapters


def test_roman_numeral_and_flexible_formatting():
    roman_text = """
    PREFACE
    A quick intro.

    I. First Principles
    Matter and energy are conserved in isolated systems.

    II. Thermodynamics
    Entropy increases over time in an irreversible process.
    """
    doc = ExtractedDocument(
        filename="physics.docx",
        file_type="docx",
        full_text=roman_text,
        pages=[DocumentPage(page_number=1, text=roman_text)]
    )

    detected = ChapterService.detect_chapters(doc)
    identifiers = [c["normalized_identifier"] for c in detected]
    assert "I" in identifiers
    assert "II" in identifiers

    extracted, chapters, is_full = ChapterService.extract_requested_content(doc, requested_chapters=["II"])
    assert "Entropy increases over time" in extracted
    assert "Matter and energy are conserved" not in extracted
