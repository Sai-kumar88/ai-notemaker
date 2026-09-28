import logging
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request, HTTPException, status
from fastapi.staticfiles import StaticFiles
from fastapi.responses import JSONResponse, RedirectResponse, FileResponse
from fastapi.middleware.cors import CORSMiddleware

from app.config import settings
from app.routes.notes import router as notes_router
from app.schemas.note_schema import ErrorResponse, ErrorDetail

# Configure application logging
logging.basicConfig(
    level=getattr(logging, settings.log_level.upper(), logging.INFO),
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup: Ensure upload directory exists
    settings.upload_path.mkdir(parents=True, exist_ok=True)
    logger.info("Application starting up with environment: %s", settings.environment)
    logger.info("Configured NVIDIA model: %s", settings.nvidia_model)
    logger.info("Max file size: %s MB", settings.max_file_size_mb)
    yield
    # Shutdown: Cleanly close connection pools
    from app.services.nvidia_service import nvidia_service
    await nvidia_service.close()
    logger.info("Application shutting down.")


app = FastAPI(
    title=settings.project_name,
    version="1.0.0",
    description=(
        "Production-grade AI Document Note Maker & Summarizer API. "
        "Strictly grounded summarization of PDF/DOCX documents via NVIDIA NIM API."
    ),
    lifespan=lifespan
)

# CORS middleware for frontend integration
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.exception_handler(HTTPException)
async def custom_http_exception_handler(request: Request, exc: HTTPException):
    """
    Ensures all HTTP exceptions conform to the consistent ErrorResponse schema.
    """
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
            details=extra_details
        )
    )
    return JSONResponse(
        status_code=exc.status_code,
        content=error_response.model_dump()
    )


@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception):
    """
    Catches unhandled exceptions and outputs a clean, safe ErrorResponse.
    """
    logger.exception("Unhandled server error: %s", str(exc))
    error_response = ErrorResponse(
        success=False,
        error=ErrorDetail(
            code="INTERNAL_SERVER_ERROR",
            message="An internal server error occurred.",
            details={"type": type(exc).__name__} if settings.environment != "production" else None
        )
    )
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content=error_response.model_dump()
    )


from pathlib import Path

# Mount static assets for frontend web UI
static_dir = Path("app/static")
if static_dir.exists():
    app.mount("/static", StaticFiles(directory="app/static"), name="static")


@app.get("/", include_in_schema=False)
async def root():
    """Serves the interactive frontend web application."""
    index_file = Path("app/static/index.html")
    if index_file.exists():
        return FileResponse(str(index_file))
    return RedirectResponse(url="/docs")


# Health check endpoint
@app.get("/health", tags=["Health"])
@app.get(f"{settings.api_v1_prefix}/health", tags=["Health"])
async def health_check():
    return {
        "status": "healthy",
        "project": settings.project_name,
        "environment": settings.environment,
        "model": settings.nvidia_model,
    }


# Register routes
app.include_router(notes_router, prefix=settings.api_v1_prefix)

