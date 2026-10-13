"""
tests/test_utils.py

Unit tests for chapter parsing and file utility functions.
"""
import pytest
from app.utils.chapter_parser import parse_chapters_input, IGNORED_CHAPTER_INPUTS
from app.utils.file_utils import sanitize_filename, is_allowed_extension, format_bytes


def test_parse_chapters_none_or_empty():
    assert parse_chapters_input(None) is None
    assert parse_chapters_input("") is None
    assert parse_chapters_input("   ") is None
    assert parse_chapters_input([]) is None


def test_parse_chapters_ignored_placeholders():
    for item in IGNORED_CHAPTER_INPUTS:
        assert parse_chapters_input(item) is None
        assert parse_chapters_input([item]) is None


def test_parse_chapters_comma_separated():
    assert parse_chapters_input("1, 2, 3") == ["1", "2", "3"]
    assert parse_chapters_input("1, , 2") == ["1", "2"]
    assert parse_chapters_input("Chapter 1, Chapter 2") == ["Chapter 1", "Chapter 2"]


def test_parse_chapters_json_array():
    assert parse_chapters_input('["1", "2", "3"]') == ["1", "2", "3"]
    assert parse_chapters_input('["Chapter 1", "Chapter 2"]') == ["Chapter 1", "Chapter 2"]


def test_parse_chapters_list_input():
    assert parse_chapters_input(["1", "2", "string"]) == ["1", "2"]
    assert parse_chapters_input(["1", ""]) == ["1"]


def test_sanitize_filename():
    assert sanitize_filename("document.pdf") == "document.pdf"
    assert sanitize_filename("../../etc/passwd.pdf") == "passwd.pdf"
    assert sanitize_filename("..\\..\\windows\\system.docx") == "system.docx"
    assert sanitize_filename(' "report.pdf" ') == "report.pdf"
    assert sanitize_filename(None) == ""


def test_is_allowed_extension():
    allowed = {".pdf", ".docx"}
    assert is_allowed_extension("notes.pdf", allowed) is True
    assert is_allowed_extension("notes.PDF", allowed) is True
    assert is_allowed_extension("book.docx", allowed) is True
    assert is_allowed_extension("script.py", allowed) is False
    assert is_allowed_extension("malicious.exe", allowed) is False


def test_format_bytes():
    assert format_bytes(500) == "500 B"
    assert format_bytes(2048) == "2.0 KB"
    assert format_bytes(5 * 1024 * 1024) == "5.0 MB"
    assert format_bytes(2 * 1024 * 1024 * 1024) == "2.0 GB"
