import re
import logging
from typing import List, Optional, Tuple
from app.config import settings

logger = logging.getLogger(__name__)

class ChunkingError(Exception):
    """Raised when text cannot be safely chunked."""
    pass

class ChunkingService:
    """
    Production-grade semantic chunking service.
    Splits long documents along natural linguistic boundaries (paragraphs, sentences, words)
    without arbitrary magic numbers or hardcoded thresholds.
    """

    # Structured priority hierarchy for breakpoint detection:
    # Each entry defines: (regex_pattern, name, post_match_offset)
    BOUNDARY_RULES: Tuple[Tuple[re.Pattern, str], ...] = (
        (re.compile(r"\n\s*\n"), "paragraph_break"),
        (re.compile(r"\n"), "line_break"),
        (re.compile(r"(?<=[.!?])\s+"), "sentence_break"),
        (re.compile(r"\s+"), "word_boundary")
    )

    @staticmethod
    def is_large_text(text: str, threshold: Optional[int] = None) -> bool:
        """
        Determines whether the document text length exceeds the single-pass limit.
        """
        limit = threshold if threshold is not None else settings.chunk_size_chars
        return len(text) > limit

    @classmethod
    def find_natural_breakpoint(
        cls,
        window: str,
        min_pos: int
    ) -> Optional[int]:
        """
        Scans a candidate text window to locate the best natural break point
        that occurs at or after `min_pos`.
        Returns the absolute character index in `window` to break at, or None.
        """
        for pattern, _ in cls.BOUNDARY_RULES:
            matches = list(pattern.finditer(window))
            if not matches:
                continue

            # Pick the last match that meets or exceeds the minimum position
            for match in reversed(matches):
                if match.end() >= min_pos:
                    return match.end()

        return None

    @classmethod
    def split_into_chunks(
        cls,
        text: str,
        chunk_size: Optional[int] = None,
        overlap: Optional[int] = None,
        max_chunks: Optional[int] = None,
        min_boundary_ratio: Optional[float] = None
    ) -> List[str]:
        """
        Splits text into contextually coherent chunks.
        All sizing, overlap, boundaries, and safety caps are environment-driven.
        """
        size = chunk_size if chunk_size is not None else settings.chunk_size_chars
        ovlp = overlap if overlap is not None else settings.chunk_overlap_chars
        max_c = max_chunks if max_chunks is not None else settings.max_chunks
        ratio = min_boundary_ratio if min_boundary_ratio is not None else settings.chunk_min_boundary_ratio

        # Prevent invalid configurations where overlap is equal or exceeds chunk size
        if ovlp >= size:
            original_ovlp = ovlp
            ovlp = max(0, size // 4)
            logger.warning("Configured overlap (%d) >= chunk size (%d). Adjusted overlap to %d.", original_ovlp, size, ovlp)

        clean_text = text.strip()
        if not clean_text:
            return []

        text_len = len(clean_text)
        if text_len <= size:
            return [clean_text]

        chunks: List[str] = []
        start_idx = 0
        min_relative_pos = int(size * ratio)

        while start_idx < text_len:
            if len(chunks) >= max_c:
                raise ChunkingError(
                    f"Document exceeds maximum allowable chunks ({max_c}). "
                    f"Please filter by specific chapters or increase the MAX_CHUNKS setting."
                )

            end_idx = min(start_idx + size, text_len)

            if end_idx < text_len:
                window = clean_text[start_idx:end_idx]
                breakpoint_offset = cls.find_natural_breakpoint(window, min_pos=min_relative_pos)
                if breakpoint_offset is not None:
                    end_idx = start_idx + breakpoint_offset

            chunk_content = clean_text[start_idx:end_idx].strip()
            if chunk_content:
                chunks.append(chunk_content)

            if end_idx >= text_len:
                break

            # Advance window ensuring strictly forward progress
            step = max(1, (end_idx - start_idx) - ovlp)
            start_idx += step

        logger.info("Successfully split %d characters into %d coherent chunks.", text_len, len(chunks))
        return chunks
