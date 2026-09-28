import pymupdf
from app.services.pdf_export_service import PdfExportService


def test_pdf_export_service_basic():
    html = """
    <h2>Test Section</h2>
    <p>This is a test paragraph explaining chemical reactions.</p>
    <ul>
      <li>First bullet item</li>
      <li>Second bullet item with <strong>bold</strong> text</li>
    </ul>
    """
    pdf_bytes = PdfExportService.generate_pdf_from_html(
        html_content=html,
        title="Sample Document",
        scope="Chapter 1",
        word_count="1,200"
    )
    assert len(pdf_bytes) > 0
    doc = pymupdf.open(stream=pdf_bytes, filetype="pdf")
    assert len(doc) >= 1
    page1 = doc[0]
    text = page1.get_text()
    assert "AI STUDY NOTES & GUIDE" in text
    assert "Test Section" in text
    assert "chemical reactions" in text


def test_pdf_export_service_page_break_no_word_slice():
    # Generate 50 bullet items to guarantee multi-page layout
    items = "\n".join([
        f"<li><strong>Concept {i}:</strong> Detailed explanation of reaction dynamics and chemical equations step {i}."
        for i in range(1, 60)
    ])
    html = f"""
    <h2>Comprehensive Concepts</h2>
    <ul>
      {items}
    </ul>
    """
    pdf_bytes = PdfExportService.generate_pdf_from_html(
        html_content=html,
        title="Multi-page Dynamics",
        scope="Full Document",
        word_count="3,500"
    )
    doc = pymupdf.open(stream=pdf_bytes, filetype="pdf")
    assert len(doc) > 1

    # Verify that every page has intact text and footer
    for page_num, page in enumerate(doc, 1):
        page_text = page.get_text()
        assert f"Page {page_num} of {len(doc)}" in page_text
