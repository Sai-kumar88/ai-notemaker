"""
app/utils/file_utils.py

File and path sanitization helpers for secure upload handling.
"""
from pathlib import Path
from typing import Optional, Set


def sanitize_filename(filename: Optional[str]) -> str:
    """
    Strips directory traversal sequences, surrounding whitespace, and quotes
    to yield a safe basename for filesystem operations.

    Example:
        '../../sensitive.pdf' -> 'sensitive.pdf'
        ' "book.docx" '       -> 'book.docx'
    """
    if not filename:
        return ""
    clean = filename.strip(' "\'')
    return Path(clean).name


def is_allowed_extension(filename: str, allowed_extensions: Set[str]) -> bool:
    """
    Checks if the filename has an extension permitted in allowed_extensions.
    """
    ext = Path(filename).suffix.lower()
    return ext in {e.lower() for e in allowed_extensions}


def format_bytes(size_bytes: int) -> str:
    """
    Formats a byte count into a human-readable string (KB, MB, GB).
    """
    if size_bytes < 1024:
        return f"{size_bytes} B"
    elif size_bytes < 1024 * 1024:
        return f"{size_bytes / 1024:.1f} KB"
    elif size_bytes < 1024 * 1024 * 1024:
        return f"{size_bytes / (1024 * 1024):.1f} MB"
    else:
        return f"{size_bytes / (1024 * 1024 * 1024):.1f} GB"
