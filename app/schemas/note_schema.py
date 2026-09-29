from typing import List, Optional, Any, Dict
from pydantic import BaseModel, Field

class DetectedChapter(BaseModel):
    """Schema representing an identified chapter or section within a document."""
    identifier: str = Field(..., description="Normalized chapter identifier, e.g. '1', '2', 'IV'")
    title: str = Field(..., description="Detected chapter heading or title")
    page_number: Optional[int] = Field(None, description="Starting page number if detectable")
    word_count: int = Field(0, description="Estimated words in chapter")
    character_count: int = Field(0, description="Total characters in chapter")

class DetectChaptersResponse(BaseModel):
    """Schema for document chapter detection."""
    success: bool = True
    filename: str
    total_chapters_detected: int
    chapters: List[DetectedChapter] = []

class SummaryMetadata(BaseModel):
    """Execution and processing metadata for the generated summary."""
    filename: str
    file_type: str
    total_document_words: int
    total_document_characters: int
    processed_words: int
    processed_characters: int
    chapters_requested: Optional[List[str]] = None
    chapters_found: List[str] = []
    chunks_processed: int = 1
    model_used: str
    provider_used: str
    is_full_document: bool

class SummaryResponse(BaseModel):
    """Schema for document summarization response."""
    success: bool = True
    summary: str
    metadata: SummaryMetadata

class ErrorDetail(BaseModel):
    """Detailed error object conforming to API standard."""
    code: str
    message: str
    details: Optional[Any] = None

class ErrorResponse(BaseModel):
    """Standardized API error response format."""
    success: bool = False
    error: ErrorDetail

class PdfExportRequest(BaseModel):
    """Schema for server-side vector PDF generation."""
    html: str = Field(..., description="Rendered HTML content of the study notes")
    title: str = Field(default="Document", description="Document name for header")
    scope: Optional[str] = Field(default="Full Document", description="Document scope or selected chapters")
    word_count: Optional[str] = Field(default=None, description="Document word count")