"""
FastAPI application factory.

Supports deployment at any URL prefix (e.g. /note-marker/) via the
APPLICATION_ROOT environment variable, without any code changes.
Handles:
  - Reverse-proxy forwarded headers (X-Forwarded-Proto/Host/Port/Prefix)
  - Static assets and index.html served under the correct subpath
  - Trailing-slash tolerance on all API routes
  - CORS for same-origin and configurable remote origins
"""
import logging
from contextlib import asynccontextmanager
from pathlib import Path
from fastapi import FastAPI, Request, HTTPException, status
from fastapi.responses import JSONResponse, RedirectResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.base import BaseHTTPMiddleware

from app.config import settings
from app.routes.notes import router as notes_router
from app.schemas.note_schema import ErrorResponse, ErrorDetail

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------
logging.basicConfig(
    level=getattr(logging, settings.log_level.upper(), logging.INFO),
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)



# ---------------------------------------------------------------------------
# Lifespan
# ---------------------------------------------------------------------------
@asynccontextmanager
async def lifespan(app: FastAPI):
    settings.upload_path.mkdir(parents=True, exist_ok=True)
    logger.info("Application starting up. env=%s prefix=%s",
                settings.environment, settings.url_prefix or "/")
    logger.info("NVIDIA model: %s", settings.nvidia_model)
    logger.info("Max file size: %s MB", settings.max_file_size_mb)
    yield
    from app.services.nvidia_service import nvidia_service
    await nvidia_service.close()
    logger.info("Application shut down.")


# ---------------------------------------------------------------------------
# App factory
# NOTE: root_path tells FastAPI (and Starlette) the SCRIPT_NAME prefix so that
#       all generated URLs (OpenAPI, redirects) are prefix-correct.
# ---------------------------------------------------------------------------
prefix = settings.url_prefix  # e.g. "/note-marker"  or  ""

app = FastAPI(
    title=settings.project_name,
    version="1.0.0",
    description=(
        "Production-grade AI Document Note Maker & Summarizer API. "
        "Strictly grounded summarization of PDF/DOCX documents via NVIDIA NIM API."
    ),
    lifespan=lifespan,
    # -----------------------------------------------------------------------
    # root_path = the URL prefix when mounted behind a reverse proxy.
    # FastAPI uses this to build correct self-referencing URLs in OpenAPI docs
    # and in HTTP redirects (e.g. trailing-slash redirects will NOT strip the prefix).
    # -----------------------------------------------------------------------
    root_path=prefix,
)


# ---------------------------------------------------------------------------
# Middleware 1: Trust X-Forwarded-* headers from the reverse proxy
# ProxyHeadersMiddleware rewrites request.url.scheme/host based on those headers
# so that redirects use https:// and the correct public hostname.
# ---------------------------------------------------------------------------
from uvicorn.middleware.proxy_headers import ProxyHeadersMiddleware  # noqa: E402

app.add_middleware(
    ProxyHeadersMiddleware,
    # trusted_hosts must be "*" or list[str]; we use "*" when proxies are trusted
    trusted_hosts="*" if settings.trusted_proxies >= 1 else "127.0.0.1",
)


# ---------------------------------------------------------------------------
# Middleware 2: Dynamic prefix & SCRIPT_NAME handling
# Resolves the ASGI scope root_path so that:
#   1. Reverse-proxy headers (X-Forwarded-Prefix) are respected.
#   2. Direct access at root (/) without prefix does NOT inherit prefix root_path,
#      which would otherwise break Starlette's StaticFiles path matching (404s).
#   3. Direct access at prefix (/note-marker/...) retains prefix root_path.
# ---------------------------------------------------------------------------
class DynamicPrefixMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        fwd_prefix = request.headers.get("x-forwarded-prefix", "").strip().rstrip("/")
        if fwd_prefix:
            request.scope["root_path"] = fwd_prefix
        elif prefix and not request.url.path.startswith(prefix):
            request.scope["root_path"] = ""
        return await call_next(request)


app.add_middleware(DynamicPrefixMiddleware)


# ---------------------------------------------------------------------------
# Middleware 3: Trailing-slash normalization
# Rewrites scope['path'] for routes ending with / (e.g. /api/v1/health/)
# so both /path and /path/ resolve with 200 without issuing 307 redirect loops.
# Never redirects or modifies the app root (/, /{prefix}, /{prefix}/) or static files.
# ---------------------------------------------------------------------------
class TrailingSlashMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        path = request.url.path
        # Exclude root paths and prefix root paths
        if path in ("/", "") or (prefix and path in (prefix, f"{prefix}/")):
            return await call_next(request)

        # Exclude static assets
        if path.startswith("/static") or (prefix and path.startswith(f"{prefix}/static")):
            return await call_next(request)

        # For API or other sub-routes ending with slash, normalize path transparently
        if path.endswith("/"):
            request.scope["path"] = path.rstrip("/")

        return await call_next(request)


app.add_middleware(TrailingSlashMiddleware)


# ---------------------------------------------------------------------------
# Middleware 4: CORS
# ---------------------------------------------------------------------------
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ---------------------------------------------------------------------------
# Exception handlers
# ---------------------------------------------------------------------------
@app.exception_handler(HTTPException)
async def custom_http_exception_handler(request: Request, exc: HTTPException):
    """Ensures all HTTP exceptions conform to the consistent ErrorResponse schema."""
    detail = exc.detail
    if isinstance(detail, dict):
        message = detail.get("message", "An error occurred")
        extra_details = {k: v for k, v in detail.items() if k != "message"}
    else:
        message = str(detail)
        extra_details = None

    error_response = ErrorResponse(
        success=False,
        error=ErrorDetail(
            code=f"HTTP_{exc.status_code}",
            message=message,
            details=extra_details,
        ),
    )
    return JSONResponse(status_code=exc.status_code, content=error_response.model_dump())


@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception):
    """Catches unhandled exceptions and outputs a clean, safe ErrorResponse."""
    logger.exception("Unhandled server error: %s", str(exc))
    error_response = ErrorResponse(
        success=False,
        error=ErrorDetail(
            code="INTERNAL_SERVER_ERROR",
            message="An internal server error occurred.",
            details={"type": type(exc).__name__}
            if settings.environment != "production"
            else None,
        ),
    )
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content=error_response.model_dump(),
    )


# ---------------------------------------------------------------------------
# Static assets — mounted at BOTH /static and {prefix}/static
# Guarantees that static assets (CSS, JS, fonts) are ALWAYS found regardless of
# whether the user visits the root directly or via the configured prefix or proxy.
# ---------------------------------------------------------------------------
_HERE = Path(__file__).parent  # app/
static_dir = _HERE / "static"
if static_dir.exists():
    app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")
    if prefix:
        app.mount(f"{prefix}/static", StaticFiles(directory=str(static_dir)), name="static_prefixed")


# ---------------------------------------------------------------------------
# Frontend root: serve index.html
# Handles both direct root access (/) and prefixed access (/{prefix} and /{prefix}/).
# ---------------------------------------------------------------------------
@app.get("/", include_in_schema=False)
async def root():
    """Serves the interactive frontend web application at domain root."""
    index_file = _HERE / "static" / "index.html"
    if index_file.exists():
        return FileResponse(str(index_file))
    return RedirectResponse(url=f"{prefix}/docs" if prefix else "/docs")


if prefix:
    @app.get(prefix, include_in_schema=False)
    @app.get(prefix + "/", include_in_schema=False)
    async def prefixed_root():
        """Serves the frontend when accessed directly under the prefix path."""
        index_file = _HERE / "static" / "index.html"
        if index_file.exists():
            return FileResponse(str(index_file))
        return RedirectResponse(url=f"{prefix}/docs")

    @app.get(f"{prefix}/docs", include_in_schema=False)
    async def prefixed_docs():
        """Serves Swagger UI documentation under the prefix path."""
        from fastapi.openapi.docs import get_swagger_ui_html
        return get_swagger_ui_html(
            openapi_url=f"{prefix}/openapi.json",
            title=f"{app.title} - Swagger UI",
        )

    @app.get(f"{prefix}/openapi.json", include_in_schema=False)
    async def prefixed_openapi():
        """Serves the OpenAPI schema JSON under the prefix path."""
        return JSONResponse(app.openapi())


# ---------------------------------------------------------------------------
# Health check — available at bare /health, API prefix, and subpath prefix
# ---------------------------------------------------------------------------
@app.get("/health", tags=["Health"])
@app.get(f"{settings.api_v1_prefix}/health", tags=["Health"])
async def health_check():
    return {
        "status": "healthy",
        "project": settings.project_name,
        "environment": settings.environment,
        "model": settings.nvidia_model,
        "url_prefix": prefix or "/",
    }


if prefix:
    @app.get(f"{prefix}/health", tags=["Health"], include_in_schema=False)
    @app.get(f"{prefix}{settings.api_v1_prefix}/health", tags=["Health"], include_in_schema=False)
    async def prefixed_health_check():
        return await health_check()


# ---------------------------------------------------------------------------
# API routes — registered at both /api/v1 and {prefix}/api/v1
# ---------------------------------------------------------------------------
app.include_router(notes_router, prefix=settings.api_v1_prefix)
if prefix:
    app.include_router(notes_router, prefix=f"{prefix}{settings.api_v1_prefix}")

