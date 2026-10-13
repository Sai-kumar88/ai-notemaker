import os
from pathlib import Path
from typing import List, Optional, Set, Union
from urllib.parse import urlparse
from pydantic import Field, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    """
    Application configuration loaded dynamically from environment variables or .env file.
    All parameters are strictly environment-driven with production-grade defaults.
    No secrets or magic operational numbers are hardcoded into business logic.
    """

    # Environment & Logging
    environment: str = Field(default="production", description="Environment mode: development, staging, production")
    log_level: str = Field(default="INFO", description="Log level: DEBUG, INFO, WARNING, ERROR, CRITICAL")
    api_v1_prefix: str = Field(default="/api/v1", description="API route prefix for v1 endpoints")
    project_name: str = Field(default="Note Maker - AI Document Summarizer", description="Project name")

    # Server configuration
    server_host: str = Field(default="127.0.0.1", description="Host address for binding the server")
    server_port: int = Field(default=8052, description="Port number for the server")
    cors_origins: Union[List[str], str] = Field(default=["*"], description="Allowed CORS origins")

    # Reverse-proxy / subpath deployment
    # Accepts bare path ("/note-marker") OR full URL ("https://host:port/note-marker/").
    # The validator always extracts ONLY the path component so nothing downstream
    # ever sees a full URL or double-slash prefix.
    application_root: str = Field(
        default="/note-marker",
        alias="APPLICATION_ROOT",
        description="URL prefix/subpath for the app (e.g. /note-marker). "
                    "Also settable via URL_PREFIX env var."
    )
    # Canonical public-facing base URL (protocol + host + port) used for redirects
    public_origin: Optional[str] = Field(
        default=None,
        description="Optional canonical origin, e.g. https://example.com:8052. "
                    "Used to build self-referencing absolute URLs."
    )
    # Number of reverse-proxy hops to trust for X-Forwarded-* headers
    trusted_proxies: int = Field(
        default=1,
        description="Number of trusted reverse-proxy hops (for X-Forwarded-* headers)."
    )

    # NVIDIA API configuration
    nvidia_api_key: str = Field(default="", description="NVIDIA NIM API key")
    nvidia_model: str = Field(default="meta/llama-3.2-11b-vision-instruct", description="Active model identifier")
    nvidia_base_url: str = Field(default="https://integrate.api.nvidia.com/v1", description="NVIDIA NIM API base URL")
    nvidia_temperature: float = Field(default=0.3, ge=0.0, le=2.0, description="Sampling temperature for summarization")
    nvidia_max_tokens: int = Field(default=4096, ge=1, le=16384, description="Max token limit per completion")
    nvidia_timeout_seconds: float = Field(default=120.0, gt=0.0, description="HTTP timeout for NVIDIA API calls")
    nvidia_max_retries: int = Field(default=3, ge=0, le=10, description="Max retries for transient HTTP failures")
    nvidia_retry_delay_seconds: float = Field(default=1.5, ge=0.1, description="Initial backoff delay between retries")
    nvidia_max_connections: int = Field(default=100, ge=5, description="HTTP connection pool maximum connections")
    nvidia_max_keepalive_connections: int = Field(default=20, ge=1, description="HTTP connection pool keep-alive")

    # Document & Processing configuration
    max_file_size_mb: int = Field(default=50, gt=0, description="Maximum allowed upload size in megabytes")
    upload_buffer_bytes: int = Field(default=1048576, gt=0, description="Stream buffer size in bytes (default 1 MB)")
    chunk_size_chars: int = Field(default=48000, gt=500, description="Character threshold for chunk splitting (optimized for 128k context)")
    chunk_overlap_chars: int = Field(default=1000, ge=0, description="Character overlap between consecutive chunks")
    chunk_min_boundary_ratio: float = Field(default=0.4, gt=0.0, lt=1.0, description="Ratio threshold for natural text boundary")
    chunk_summary_max_tokens: int = Field(default=1200, ge=100, le=4096, description="Max token limit per intermediate chunk extraction for high speed")
    max_chunks: int = Field(default=30, gt=0, description="Safety limit on max chunks processed per document")
    max_concurrent_chunk_requests: int = Field(default=2, gt=0, le=20, description="Concurrent chunk summarization workers (safe for NIM rate limits)")
    allowed_extensions: Union[List[str], str] = Field(default=[".pdf", ".docx"], description="Supported file extensions")
    upload_dir: str = Field(default="uploads", description="Directory path for temporary uploads")

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
        # Allow both APPLICATION_ROOT and URL_PREFIX as env-var names
        populate_by_name=True,
    )

    @field_validator("allowed_extensions", mode="before")
    @classmethod
    def parse_allowed_extensions(cls, v: Union[List[str], str]) -> List[str]:
        if isinstance(v, str):
            clean = v.strip("[]").replace("'", "").replace('"', "")
            return [f".{ext.strip().lstrip('.').lower()}" for ext in clean.split(",") if ext.strip()]
        return [f".{str(ext).strip().lstrip('.').lower()}" for ext in v if str(ext).strip()]

    @field_validator("cors_origins", mode="before")
    @classmethod
    def parse_cors_origins(cls, v: Union[List[str], str]) -> List[str]:
        if isinstance(v, str):
            clean = v.strip("[]").replace("'", "").replace('"', "")
            return [origin.strip() for origin in clean.split(",") if origin.strip()]
        return [str(origin).strip() for origin in v if str(origin).strip()]

    @field_validator("application_root", mode="before")
    @classmethod
    def parse_application_root(cls, v: str) -> str:
        """
        Defensive URL parsing: if the operator accidentally sets APPLICATION_ROOT
        (or URL_PREFIX) to a full URL like 'https://example.com:8052/note-marker/',
        extract ONLY the path component ('/note-marker').  A bare path like
        '/note-marker' or 'note-marker' is also normalised correctly.
        """
        raw = str(v).strip()
        if not raw:
            return ""
        parsed = urlparse(raw)
        # urlparse: if no scheme, the whole string lands in 'path'
        path = parsed.path if parsed.scheme else raw
        # Normalise: strip trailing slash, ensure leading slash
        path = path.rstrip("/")
        if path and not path.startswith("/"):
            path = "/" + path
        return path  # e.g. "/note-marker" or "" for root

    @model_validator(mode="after")
    def _apply_url_prefix_alias(self):
        """Allow URL_PREFIX as an alternative env-var name for application_root."""
        url_prefix_env = os.environ.get("URL_PREFIX", "").strip()
        if url_prefix_env and self.application_root in ("", "/note-marker"):
            # Re-run the same normalisation logic
            from urllib.parse import urlparse as _up
            raw = url_prefix_env
            parsed = _up(raw)
            path = parsed.path if parsed.scheme else raw
            path = path.rstrip("/")
            if path and not path.startswith("/"):
                path = "/" + path
            self.application_root = path
        return self

    @property
    def max_file_size_bytes(self) -> int:
        return self.max_file_size_mb * 1024 * 1024

    @property
    def allowed_extensions_set(self) -> Set[str]:
        return {ext.lower().strip() for ext in self.allowed_extensions}

    @property
    def upload_path(self) -> Path:
        p = Path(self.upload_dir)
        p.mkdir(parents=True, exist_ok=True)
        return p

    @property
    def url_prefix(self) -> str:
        """Canonical URL prefix path, always without trailing slash.
        Returns '' for root deployment, '/note-marker' for subpath."""
        return self.application_root


settings = Settings()
