import re
from typing import List, Dict, Optional, Tuple, Any
from app.services.document_service import ExtractedDocument
from app.schemas.note_schema import DetectedChapter


class ChapterNotFoundError(Exception):
    """Raised when one or more requested chapters cannot be found in the document."""
    def __init__(self, missing_chapters: List[str], available_chapters: List[str], message: Optional[str] = None):
        self.missing_chapters = missing_chapters
        self.available_chapters = available_chapters
        clean_nums = ", ".join(str(c) for c in missing_chapters)
        msg = message or f"Requested chapter(s) {clean_nums} could not be found in the document."
        super().__init__(msg)


class ChapterService:
    # Generic regex patterns to identify chapter/section headings across varied documents.
    # No document-specific titles or hardcoded chapter numbers.
    CHAPTER_PATTERNS = [
        # Explicit chapter / section / unit / module / part headers
        # Matches e.g. "Chapter 1: Introduction", "CHAPTER IV - Mechanics", "Section 2.1", "Unit 3"
        re.compile(
            r"(?im)^[ \t]*(?:chapter|ch\.|section|sec\.|unit|module|part)[ \t]+([0-9]+|[IVXLCDM]+|[A-Za-z]+)"
            r"(?:[ \t]*[:.\-–—][ \t]*(.*?)|[ \t]+([^\r\n]+))?$",
        ),
        # Numbered major headings at line start, e.g. "1. Overview of Neural Networks", "2. Methodology"
        re.compile(
            r"(?im)^[ \t]*([0-9]+)\.[ \t]+([A-Z0-9][^\r\n]{2,80})$"
        ),
        # Roman numeral headings, e.g. "I. Background", "IV. Results"
        re.compile(
            r"(?im)^[ \t]*([IVXLCDM]+)\.[ \t]+([A-Z0-9][^\r\n]{2,80})$"
        ),
    ]

    @staticmethod
    def normalize_identifier(identifier: Any) -> str:
        """
        Normalizes chapter identifiers to facilitate reliable matching.
        E.g., "Chapter 1" -> "1", " 02 " -> "2", "iv" -> "IV".
        """
        clean = str(identifier).strip()
        # Remove common prefixes like 'chapter', 'ch.', 'section', 'part'
        clean = re.sub(r"(?i)^(?:chapter|ch\.?|section|sec\.?|unit|module|part)\s*", "", clean).strip()
        # If numeric, strip leading zeros for consistent matching (01 == 1)
        if clean.isdigit():
            clean = str(int(clean))
        else:
            clean = clean.upper()
        return clean

    @classmethod
    def detect_chapters(cls, document: ExtractedDocument) -> List[Dict[str, Any]]:
        """
        Dynamically detects all chapters/sections in the document text.
        Returns a list of chapter descriptors sorted by their appearance in the text.
        """
        text = document.full_text
        detected: List[Dict[str, Any]] = []
        seen_identifiers = set()

        for pattern in cls.CHAPTER_PATTERNS:
            for match in pattern.finditer(text):
                raw_id = match.group(1).strip()
                norm_id = cls.normalize_identifier(raw_id)

                if norm_id in seen_identifiers:
                    continue

                # Determine title
                title_candidates = [g for g in match.groups()[1:] if g and g.strip()]
                title = title_candidates[0].strip() if title_candidates else f"Chapter {raw_id}"
                
                # Determine page number if document has page segmentation
                start_char = match.start()
                page_num = cls._estimate_page_number(document, start_char)

                detected.append({
                    "raw_identifier": raw_id,
                    "normalized_identifier": norm_id,
                    "title": title,
                    "header_line": match.group(0).strip(),
                    "start_char": start_char,
                    "page_number": page_num
                })
                seen_identifiers.add(norm_id)

        # Sort detected chapters by appearance order in document
        detected.sort(key=lambda c: c["start_char"])

        # Calculate end_char and chapter text slices
        for i in range(len(detected)):
            current = detected[i]
            if i + 1 < len(detected):
                next_chapter = detected[i + 1]
                current["end_char"] = next_chapter["start_char"]
            else:
                current["end_char"] = len(text)

            chapter_content = text[current["start_char"]:current["end_char"]].strip()
            current["text"] = chapter_content
            current["word_count"] = len(chapter_content.split())
            current["character_count"] = len(chapter_content)

        return detected

    @staticmethod
    def _estimate_page_number(document: ExtractedDocument, char_offset: int) -> Optional[int]:
        """Calculates which page contains the given character offset."""
        if not document.pages:
            return None
        
        running_length = 0
        for page in document.pages:
            page_len = len(page.text) + 2  # account for \n\n
            if running_length + page_len > char_offset:
                return page.page_number
            running_length += page_len
        return document.pages[-1].page_number if document.pages else None

    @classmethod
    def get_detected_chapters_schema(cls, document: ExtractedDocument) -> List[DetectedChapter]:
        """Returns detected chapters formatted as Pydantic models."""
        chapters = cls.detect_chapters(document)
        result = []
        for ch in chapters:
            result.append(
                DetectedChapter(
                    identifier=ch["normalized_identifier"],
                    title=ch["title"],
                    page_number=ch["page_number"],
                    word_count=ch["word_count"],
                    character_count=ch["character_count"],
                )
            )
        return result

    @classmethod
    def extract_requested_content(
        cls,
        document: ExtractedDocument,
        requested_chapters: Optional[List[Any]] = None
    ) -> Tuple[str, List[str], bool]:
        """
        Extracts content according to requested chapters.
        - If requested_chapters is None or empty: returns the full document text.
        - If requested_chapters are specified:
            - Validates that EVERY requested chapter exists.
            - If any chapter is missing: raises ChapterNotFoundError (ZERO hallucination).
            - Extracts and combines the exact text of requested chapters.
        
        Returns:
            Tuple of (extracted_text, found_chapter_identifiers, is_full_document)
        """
        # Filter out empty or whitespace inputs
        cleaned_requests = []
        if requested_chapters:
            for item in requested_chapters:
                if item is not None and str(item).strip():
                    cleaned_requests.append(str(item).strip())

        # Chapter numbers provided? -> NO / []
        if not cleaned_requests:
            return document.full_text, [], True

        # Chapter numbers provided? -> YES
        detected_chapters = cls.detect_chapters(document)
        chapter_map = {ch["normalized_identifier"]: ch for ch in detected_chapters}
        available_ids = list(chapter_map.keys())

        missing_chapters: List[str] = []
        matched_chapters: List[Dict[str, Any]] = []

        ROMAN_NUMERALS = ["I", "II", "III", "IV", "V", "VI", "VII", "VIII", "IX", "X",
                          "XI", "XII", "XIII", "XIV", "XV", "XVI", "XVII", "XVIII", "XIX", "XX"]

        for req in cleaned_requests:
            norm_req = cls.normalize_identifier(req)
            matched = None

            # 1. Direct normalized match
            if norm_req in chapter_map:
                matched = chapter_map[norm_req]

            # 2. Number to Roman match (e.g. user typed 1, document has Chapter I)
            elif norm_req.isdigit() and 1 <= int(norm_req) <= len(ROMAN_NUMERALS):
                roman_id = ROMAN_NUMERALS[int(norm_req) - 1]
                if roman_id in chapter_map:
                    matched = chapter_map[roman_id]

            # 3. Positional order match (e.g. user typed 1 -> 1st chapter in document)
            if not matched and norm_req.isdigit():
                pos = int(norm_req)
                if 1 <= pos <= len(detected_chapters):
                    matched = detected_chapters[pos - 1]

            # 4. Prefix/number match (e.g. user typed 1 -> Section 1.0 or Section 1)
            if not matched:
                for cid, ch in chapter_map.items():
                    if cid.startswith(f"{norm_req}.") or cid == norm_req:
                        matched = ch
                        break

            if matched:
                if matched not in matched_chapters:
                    matched_chapters.append(matched)
            else:
                missing_chapters.append(req)

        # Fallback if no chapters detected by header regex but document has pages
        if missing_chapters and not detected_chapters and document.pages:
            fallback_matched = []
            for req in list(missing_chapters):
                norm_req = cls.normalize_identifier(req)
                if norm_req.isdigit():
                    page_idx = int(norm_req)
                    if 1 <= page_idx <= len(document.pages):
                        page_obj = document.pages[page_idx - 1]
                        fallback_matched.append(page_obj.text)
                        missing_chapters.remove(req)
            if fallback_matched and not missing_chapters:
                return "\n\n".join(fallback_matched).strip(), [cls.normalize_identifier(r) for r in cleaned_requests], False

        # Critical rule: Missing chapters produce a clean error without exposing chapter names
        if missing_chapters:
            raise ChapterNotFoundError(
                missing_chapters=missing_chapters,
                available_chapters=available_ids
            )

        # Preserve the document order of matched chapters
        matched_chapters.sort(key=lambda c: c["start_char"])

        # Extract only those chapters
        extracted_sections: List[str] = []
        found_ids: List[str] = []

        for ch in matched_chapters:
            header = f"=== Chapter {ch['normalized_identifier']} ==="
            section_content = f"{header}\n\n{ch['text']}"
            extracted_sections.append(section_content)
            found_ids.append(ch["normalized_identifier"])

        combined_text = "\n\n".join(extracted_sections).strip()
        return combined_text, found_ids, False
