import io
import re
from typing import Optional, List, Dict, Any
from bs4 import BeautifulSoup, Tag

try:
    import pymupdf
except Exception as _mupdf_err:
    pymupdf = None
    _pymupdf_error_msg = str(_mupdf_err)
else:
    _pymupdf_error_msg = ""

class PdfExportService:
    """
    High-fidelity, vector-based PDF generator using PyMuPDF (fitz.Story).
    Unlike continuous-canvas or unmeasured inline flows that slice text at rect borders,
    this engine measures each block (heading, paragraph, list item, table) individually.
    If a block cannot fit in the remaining page space, it automatically advances to a
    clean new page, ensuring zero horizontally sliced sentences or cut words across page ends.
    """

    DEFAULT_CSS = """
    body {
        font-family: sans-serif;
        font-size: 10pt;
        line-height: 1.5;
        color: #1f2937;
        margin: 0;
        padding: 0;
    }
    .pdf-meta-box {
        border-bottom: 2px solid #6366f1;
        padding-bottom: 4pt;
        margin-bottom: 6pt;
    }
    .doc-title {
        color: #312e81;
        font-size: 16pt;
        font-weight: bold;
        margin: 0;
    }
    .meta-line {
        color: #4b5563;
        font-size: 9.5pt;
        margin: 0;
    }
    h1 {
        color: #1e1b4b;
        font-size: 15pt;
        font-weight: bold;
        border-bottom: 1.5px solid #e0e7ff;
        padding-bottom: 3pt;
        margin: 0 0 6pt 0;
    }
    h2 {
        color: #3730a3;
        font-size: 13pt;
        font-weight: bold;
        margin: 0 0 5pt 0;
    }
    h3 {
        color: #4338ca;
        font-size: 11pt;
        font-weight: bold;
        margin: 0 0 4pt 0;
    }
    p {
        margin: 0 0 5pt 0;
    }
    ul, ol {
        margin: 0;
        padding-left: 18pt;
    }
    li {
        margin-bottom: 3pt;
    }
    strong, b {
        color: #0f172a;
        font-weight: bold;
    }
    blockquote {
        border-left: 3px solid #6366f1;
        background-color: #f5f3ff;
        padding: 5pt 8pt;
        margin: 4pt 0;
        color: #3730a3;
    }
    table {
        width: 100%;
        border-collapse: collapse;
        margin: 6pt 0;
        font-size: 9pt;
    }
    th, td {
        border: 1px solid #e5e7eb;
        padding: 4pt 6pt;
        text-align: left;
    }
    th {
        background-color: #f3f4f6;
        color: #111827;
        font-weight: bold;
    }
    code {
        font-family: monospace;
        background-color: #f1f5f9;
        color: #0f172a;
        padding: 1pt 3pt;
        font-size: 8.5pt;
    }
    hr {
        border: none;
        border-top: 1px solid #e5e7eb;
        margin: 8pt 0;
    }
    """

    @classmethod
    def _extract_blocks(cls, element: Tag) -> List[Dict[str, Any]]:
        """
        Recursively unpacks HTML into discrete printable blocks (headings, paragraphs,
        individual list items with preserved nesting, tables, etc.).
        """
        blocks = []
        for child in element.children:
            if not isinstance(child, Tag):
                text = str(child).strip()
                if text:
                    blocks.append({"html": f"<p>{text}</p>", "is_heading": False})
                continue

            tag = child.name.lower()
            if tag in ["div", "section", "article", "main"]:
                blocks.extend(cls._extract_blocks(child))
            elif tag in ["h1", "h2", "h3", "h4", "h5", "h6"]:
                blocks.append({"html": str(child), "is_heading": True})
            elif tag in ["ul", "ol"]:
                # Decompose list items so each item is an atomic block with its bullet/number
                for idx, li in enumerate(child.find_all("li", recursive=False), 1):
                    li_html = f'<{tag} start="{idx}"><li>{li.decode_contents()}</li></{tag}>'
                    blocks.append({"html": li_html, "is_heading": False})
            else:
                blocks.append({"html": str(child), "is_heading": False})

        return blocks

    @classmethod
    def is_available(cls) -> bool:
        """Returns True if PyMuPDF library is successfully loaded with required native DLLs."""
        return pymupdf is not None

    @classmethod
    def _make_story(cls, content: str) -> Any:
        if pymupdf is None:
            raise RuntimeError(
                f"PyMuPDF is unavailable ({_pymupdf_error_msg}). "
                "Please install Microsoft Visual C++ 2015-2022 Redistributable (x64)."
            )
        full_html = (
            f'<!DOCTYPE html><html><head><meta charset="utf-8">'
            f'<style>{cls.DEFAULT_CSS}</style></head>'
            f'<body>{content}</body></html>'
        )
        return pymupdf.Story(html=full_html)

    @classmethod
    def generate_pdf_from_html(
        cls,
        html_content: str,
        title: str = "Document",
        scope: Optional[str] = "Full Document",
        word_count: Optional[str] = None
    ) -> bytes:
        """
        Renders styled HTML into a crisp, multi-page vector A4 PDF with running headers and page numbers.
        Uses discrete block-level height measurement to prevent horizontal text slicing across page breaks.
        """
        if pymupdf is None:
            raise RuntimeError(
                f"PyMuPDF native extension failed to load ({_pymupdf_error_msg}). "
                "Please install the Microsoft Visual C++ 2015-2022 Redistributable (x64) from "
                "https://aka.ms/vs/17/release/vc_redist.x64.exe and run: pip install --force-reinstall pymupdf"
            )

        clean_title = re.sub(r"[^\w\s\-\.\(\)]", "", title).strip() or "Document"
        meta_info = f"Scope: {scope or 'Full Document'}"
        if word_count:
            meta_info += f"  |  Words: {word_count}"

        # Parse HTML into atomic blocks
        soup = BeautifulSoup(html_content, "html.parser")
        blocks = cls._extract_blocks(soup)

        # Setup A4 portrait document (210 x 297 mm, 595.3 x 841.9 pt)
        bio = io.BytesIO()
        writer = pymupdf.DocumentWriter(bio)
        rect = pymupdf.paper_rect("a4")

        margin_x = 36  # Left & right margins (0.5 inch)
        top_margin = 30  # Start close to top of page
        bottom_margin = 36  # Leave room for running footer
        page_width = rect.width
        page_height = rect.height
        content_width = page_width - (2 * margin_x)
        max_y = page_height - bottom_margin
        page_content_height = max_y - top_margin

        current_y = top_margin
        device = writer.begin_page(rect)

        # Render Header Banner on Page 1 (Title only, no scope or word count line)
        banner_html = """
        <div class="pdf-meta-box">
            <div class="doc-title">AI STUDY NOTES & GUIDE</div>
        </div>
        """
        banner_story = cls._make_story(banner_html)
        banner_target = pymupdf.Rect(margin_x, current_y, margin_x + content_width, max_y)
        _, banner_filled = banner_story.place(banner_target)
        banner_story.draw(device)
        current_y = banner_filled[3] + 6

        # Place each content block with intelligent pagination
        for block in blocks:
            block_html = block["html"]
            is_heading = block["is_heading"]

            # Pre-measure block height in virtual space
            story_measure = cls._make_story(block_html)
            measure_rect = pymupdf.Rect(margin_x, 0, margin_x + content_width, 10000)
            _, filled_measure = story_measure.place(measure_rect)
            block_h = filled_measure[3] - filled_measure[1]

            remaining_space = max_y - current_y

            # Check if block needs to advance to a fresh page:
            # 1. Block fits within a normal page, but exceeds remaining space on the current page
            # 2. Heading orphan prevention: a heading should have at least 50pt of content space beneath it
            needs_new_page = False
            if block_h <= page_content_height:
                if block_h > remaining_space:
                    needs_new_page = True
                elif is_heading and (remaining_space < (block_h + 50)):
                    needs_new_page = True

            if needs_new_page:
                writer.end_page()
                device = writer.begin_page(rect)
                current_y = top_margin

            # Place and draw block onto the active page
            story_draw = cls._make_story(block_html)
            more = 1
            while more:
                draw_target = pymupdf.Rect(margin_x, current_y, margin_x + content_width, max_y)
                more, filled_draw = story_draw.place(draw_target)
                story_draw.draw(device)
                current_y = filled_draw[3] + 3

                # Fallback only for single blocks taller than an entire page
                if more:
                    writer.end_page()
                    device = writer.begin_page(rect)
                    current_y = top_margin

        writer.end_page()
        writer.close()

        # Add running headers and footers with total page count
        raw_pdf_bytes = bio.getvalue()
        doc = pymupdf.open(stream=raw_pdf_bytes, filetype="pdf")
        total_pages = len(doc)

        header_text = "AI STUDY NOTES & GUIDE"

        for page_num, page in enumerate(doc, 1):
            # Running header from page 2 onwards (page 1 already has top header banner)
            if page_num > 1:
                page.insert_text(
                    (margin_x, 26),
                    header_text,
                    fontsize=8,
                    color=(0.4, 0.4, 0.5)
                )

            # Footer on every page
            footer_text = f"Page {page_num} of {total_pages}"
            page.insert_text(
                (rect.width - margin_x - 55, rect.height - 18),
                footer_text,
                fontsize=8,
                color=(0.4, 0.4, 0.5)
            )

        output_bio = io.BytesIO()
        doc.save(output_bio)
        doc.close()

        return output_bio.getvalue()
