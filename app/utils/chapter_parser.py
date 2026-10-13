"""
app/utils/chapter_parser.py

Robust parsing and normalization of chapter inputs sent from
HTML forms, JSON payloads, or interactive API documentation (Swagger UI).
"""
import json
from typing import List, Optional, Union, FrozenSet

# Common dummy or placeholder strings sent by clients or API explorers that should be ignored
IGNORED_CHAPTER_INPUTS: FrozenSet[str] = frozenset({
    "string", "none", "null", "all", "full", "[]", '""', "''", "-", "undefined"
})


def parse_chapters_input(chapters_raw: Optional[Union[str, List[str]]]) -> Optional[List[str]]:
    """
    Parses optional chapter input from multiple incoming formats.

    Supports:
      - None or empty string -> Returns None (triggers entire document summarization)
      - Comma-separated strings, e.g. "1, 2, 3" -> ['1', '2', '3']
      - JSON array string, e.g. '["1", "2"]' -> ['1', '2']
      - Native Python lists, e.g. ['1', '2'] -> ['1', '2']
      - Placeholder defaults from Swagger UI ("string") -> None

    Returns:
        List of cleaned chapter identifier strings, or None if no specific chapters requested.
    """
    if not chapters_raw:
        return None

    if isinstance(chapters_raw, list):
        parsed = [
            str(c).strip() for c in chapters_raw
            if str(c).strip() and str(c).strip().lower() not in IGNORED_CHAPTER_INPUTS
        ]
        return parsed if parsed else None

    raw_str = str(chapters_raw).strip()
    if not raw_str or raw_str.lower() in IGNORED_CHAPTER_INPUTS:
        return None

    # Attempt JSON list parsing
    if raw_str.startswith("[") and raw_str.endswith("]"):
        try:
            parsed_json = json.loads(raw_str)
            if isinstance(parsed_json, list):
                result = [
                    str(x).strip() for x in parsed_json
                    if str(x).strip() and str(x).strip().lower() not in IGNORED_CHAPTER_INPUTS
                ]
                return result if result else None
        except (json.JSONDecodeError, ValueError):
            pass

    # Comma-separated string parsing
    items = [
        c.strip() for c in raw_str.split(",")
        if c.strip() and c.strip().lower() not in IGNORED_CHAPTER_INPUTS
    ]
    return items if items else None
