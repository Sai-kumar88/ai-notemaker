import pytest
from app.services.chunking_service import ChunkingService, ChunkingError

def test_small_text_not_chunked():
    small_text = "This is a brief text about machine learning."
    assert ChunkingService.is_large_text(small_text, threshold=1000) is False
    chunks = ChunkingService.split_into_chunks(small_text, chunk_size=1000)
    assert len(chunks) == 1
    assert chunks[0] == small_text

def test_large_text_splits_cleanly():
    paragraphs = [
        f"Paragraph {i}: " + ("This is detailed explanatory text about distributed computing. " * 10)
        for i in range(10)
    ]
    large_text = "\n\n".join(paragraphs)

    chunk_size = 500
    overlap = 50
    chunks = ChunkingService.split_into_chunks(large_text, chunk_size=chunk_size, overlap=overlap, max_chunks=30)
    
    assert len(chunks) > 1
    for chunk in chunks:
        assert len(chunk) <= chunk_size + 100  # Allows slight boundary buffer
        assert len(chunk.strip()) > 0

def test_max_chunks_safety_limit():
    huge_text = "word " * 50000
    with pytest.raises(ChunkingError) as exc_info:
        ChunkingService.split_into_chunks(huge_text, chunk_size=100, overlap=10, max_chunks=5)
    
    assert "exceeds maximum allowable chunks" in str(exc_info.value)
