import pytest
from app.config import Settings

def test_settings_defaults():
    settings = Settings(
        nvidia_api_key="test_key",
        nvidia_model="custom-model-test",
        max_file_size_mb=25,
        chunk_size_chars=5000,
        chunk_overlap_chars=200,
        max_chunks=15
    )
    assert settings.nvidia_api_key == "test_key"
    assert settings.nvidia_model == "custom-model-test"
    assert settings.max_file_size_bytes == 25 * 1024 * 1024
    assert ".pdf" in settings.allowed_extensions_set
    assert ".docx" in settings.allowed_extensions_set
    assert settings.chunk_size_chars == 5000
    assert settings.max_chunks == 15

def test_settings_case_insensitive_extensions():
    settings = Settings(allowed_extensions=[".PDF", ".Docx"])
    assert ".pdf" in settings.allowed_extensions_set
    assert ".docx" in settings.allowed_extensions_set

def test_server_and_buffer_settings():
    settings = Settings(
        server_host="127.0.0.1",
        server_port=9000,
        upload_buffer_bytes=2097152
    )
    assert settings.server_host == "127.0.0.1"
    assert settings.server_port == 9000
    assert settings.upload_buffer_bytes == 2097152
