import io
import os
import pytest
from unittest.mock import AsyncMock, patch
from fastapi.testclient import TestClient
import docx
from pypdf import PdfWriter
from app.main import app
from app.config import settings
from app.services.nvidia_service import nvidia_service

client = TestClient(app)

def generate_test_docx() -> io.BytesIO:
    """Generates an in-memory DOCX with chapters for testing."""
    doc = docx.Document()
    doc.add_heading("Academic Research Handbook", level=0)
    
    doc.add_heading("Chapter 1: Foundations of Methodology", level=1)
    doc.add_paragraph("Quantitative research relies on measurable empirical observations and statistical analysis.")
    doc.add_paragraph("Hypothesis testing establishes validity through significance testing.")

    doc.add_heading("Chapter 2: Data Collection Techniques", level=1)
    doc.add_paragraph("Surveys and randomized trials serve as standard experimental instruments.")
    doc.add_paragraph("Sampling bias must be minimized using stratified random sampling.")

    doc.add_heading("Chapter 3: Qualitative Discourse", level=1)
    doc.add_paragraph("Ethnography and phenomenological interviews capture lived human experience.")

    buffer = io.BytesIO()
    doc.save(buffer)
    buffer.seek(0)
    return buffer

def test_health_check():
    response = client.get("/api/v1/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "healthy"
    assert "model" in data

def test_root_serves_frontend_ui():
    response = client.get("/")
    assert response.status_code == 200
    assert "text/html" in response.headers.get("content-type", "")
    assert "NoteMaker" in response.text

def test_detect_chapters_endpoint():
    docx_file = generate_test_docx()
    files = {"file": ("research.docx", docx_file.getvalue(), "application/vnd.openxmlformats-officedocument.wordprocessingml.document")}
    
    response = client.post("/api/v1/notes/detect-chapters", files=files)
    assert response.status_code == 200
    data = response.json()
    assert data["success"] is True
    assert data["total_chapters_detected"] == 3
    identifiers = [ch["identifier"] for ch in data["chapters"]]
    assert identifiers == ["1", "2", "3"]


@pytest.mark.asyncio
async def test_summarize_full_document_when_no_chapters_provided():
    docx_file = generate_test_docx()
    files = {"file": ("research.docx", docx_file.getvalue(), "application/vnd.openxmlformats-officedocument.wordprocessingml.document")}
    
    mock_summary = "# Faithful Summary\n- Quantitative and qualitative research methodologies."

    with patch.object(nvidia_service, "generate_chat_completion", new_callable=AsyncMock) as mock_nvidia:
        mock_nvidia.return_value = mock_summary

        # No chapters provided
        response = client.post("/api/v1/notes/summarize", files=files)
        assert response.status_code == 200
        data = response.json()

        assert data["success"] is True
        assert data["summary"] == mock_summary
        assert data["metadata"]["is_full_document"] is True
        assert data["metadata"]["chapters_requested"] is None
        assert data["metadata"]["chunks_processed"] == 1
        
        # Verify prompt passed to NVIDIA contained the entire text
        mock_nvidia.assert_called_once()
        user_prompt_arg = mock_nvidia.call_args[1]["user_prompt"]
        assert "Chapter 1" in user_prompt_arg
        assert "Chapter 2" in user_prompt_arg
        assert "Chapter 3" in user_prompt_arg


@pytest.mark.asyncio
async def test_summarize_full_document_when_swagger_string_placeholder_sent():
    docx_file = generate_test_docx()
    files = {"file": ("research.docx", docx_file.getvalue(), "application/vnd.openxmlformats-officedocument.wordprocessingml.document")}
    
    # Swagger UI sends "string" by default if user does not delete the text box
    mock_summary = "# Faithful Full Summary"

    with patch.object(nvidia_service, "generate_chat_completion", new_callable=AsyncMock) as mock_nvidia:
        mock_nvidia.return_value = mock_summary

        response = client.post("/api/v1/notes/summarize", files=files, data={"chapters": "string"})
        assert response.status_code == 200
        data = response.json()

        assert data["success"] is True
        assert data["metadata"]["is_full_document"] is True
        assert data["metadata"]["chapters_requested"] is None


@pytest.mark.asyncio
async def test_summarize_selected_multiple_chapters():
    docx_file = generate_test_docx()
    files = {"file": ("research.docx", docx_file.getvalue(), "application/vnd.openxmlformats-officedocument.wordprocessingml.document")}
    data_form = {"chapters": "1, 2"}

    mock_summary = "# Summary of Chapters 1 and 2"

    with patch.object(nvidia_service, "generate_chat_completion", new_callable=AsyncMock) as mock_nvidia:
        mock_nvidia.return_value = mock_summary

        response = client.post("/api/v1/notes/summarize", files=files, data=data_form)
        assert response.status_code == 200
        data = response.json()

        assert data["success"] is True
        assert data["metadata"]["is_full_document"] is False
        assert set(data["metadata"]["chapters_found"]) == {"1", "2"}

        # Verify Chapter 3 was excluded from the text sent to NVIDIA
        user_prompt_arg = mock_nvidia.call_args[1]["user_prompt"]
        assert "Chapter 1" in user_prompt_arg
        assert "Chapter 2" in user_prompt_arg
        assert "Qualitative Discourse" not in user_prompt_arg


def test_missing_chapter_returns_404_error_no_hallucination():
    docx_file = generate_test_docx()
    files = {"file": ("research.docx", docx_file.getvalue(), "application/vnd.openxmlformats-officedocument.wordprocessingml.document")}
    data_form = {"chapters": "5"}

    response = client.post("/api/v1/notes/summarize", files=files, data=data_form)
    assert response.status_code == 404
    data = response.json()

    assert data["success"] is False
    assert data["error"]["code"] == "HTTP_404"
    assert "could not be found" in data["error"]["message"]
    assert "5" in data["error"]["details"]["missing_chapters"]


def test_unsupported_file_extension():
    files = {"file": ("notes.txt", b"plain text", "text/plain")}
    response = client.post("/api/v1/notes/summarize", files=files)
    assert response.status_code == 400
    data = response.json()
    assert data["success"] is False
    assert "Unsupported file format" in data["error"]["message"]


def test_temporary_files_are_safely_cleaned_up():
    upload_dir = settings.upload_path
    initial_files = set(upload_dir.glob("upload_*"))

    docx_file = generate_test_docx()
    files = {"file": ("clean_test.docx", docx_file.getvalue(), "application/vnd.openxmlformats-officedocument.wordprocessingml.document")}
    
    # Intentionally trigger an error with a missing chapter
    client.post("/api/v1/notes/summarize", files=files, data={"chapters": "99"})
    
    # Check that any created temp file has been removed
    after_files = set(upload_dir.glob("upload_*"))
    assert after_files == initial_files


@pytest.mark.asyncio
async def test_summarize_pdf_document():
    pdf_bytes = (
        b"%PDF-1.4\n"
        b"1 0 obj <</Type /Catalog /Pages 2 0 R>> endobj\n"
        b"2 0 obj <</Type /Pages /Kids [3 0 R] /Count 1>> endobj\n"
        b"3 0 obj <</Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Resources <</Font <</F1 4 0 R>>>> /Contents 5 0 R>> endobj\n"
        b"4 0 obj <</Type /Font /Subtype /Type1 /BaseFont /Helvetica>> endobj\n"
        b"5 0 obj <</Length 94>> stream\n"
        b"BT\n"
        b"/F1 12 Tf\n"
        b"72 700 Td\n"
        b"(Chapter 1: Foundations of Artificial Intelligence) Tj\n"
        b"ET\n"
        b"endstream\n"
        b"endobj\n"
        b"xref\n"
        b"0 6\n"
        b"0000000000 65535 f \n"
        b"0000000009 00000 n \n"
        b"0000000058 00000 n \n"
        b"0000000115 00000 n \n"
        b"0000000227 00000 n \n"
        b"0000000298 00000 n \n"
        b"trailer <</Size 6 /Root 1 0 R>>\n"
        b"startxref\n"
        b"442\n"
        b"%%EOF"
    )

    files = {"file": ("ai_primer.pdf", pdf_bytes, "application/pdf")}
    mock_summary = "# Notes on Artificial Intelligence\n- Foundations and core principles."

    with patch.object(nvidia_service, "generate_chat_completion", new_callable=AsyncMock) as mock_nvidia:
        mock_nvidia.return_value = mock_summary

        response = client.post("/api/v1/notes/summarize", files=files)
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert data["metadata"]["file_type"] == "pdf"
        assert "Artificial Intelligence" in data["summary"]


def test_export_pdf_endpoint():
    payload = {
        "html": "<h1>Chemical Reactions</h1><p>Test paragraph.</p><ul><li>First point.</li></ul>",
        "title": "Chemical Reactions",
        "scope": "Full Document",
        "word_count": "50"
    }
    response = client.post("/api/v1/notes/export-pdf", json=payload)
    assert response.status_code == 200
    assert response.headers["content-type"] == "application/pdf"
    assert response.content.startswith(b"%PDF")
    assert "AI STUDY NOTES & GUIDE.pdf" in response.headers["content-disposition"]


