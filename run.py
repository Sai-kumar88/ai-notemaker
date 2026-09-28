"""
Entry point script to run the FastAPI application using Python directly.
Reads host, port, and environment settings dynamically from the .env configuration.
Usage:
    python run.py
"""
import uvicorn
from app.config import settings

if __name__ == "__main__":
    is_dev = settings.environment.lower() != "production"
    
    # On Windows, browsers cannot open 0.0.0.0 directly (ERR_ADDRESS_INVALID).
    # Use 127.0.0.1 or localhost for clickable links in terminal.
    display_host = "127.0.0.1" if settings.server_host in ("0.0.0.0", "::") else settings.server_host
    base_url = f"http://{display_host}:{settings.server_port}"

    print("=" * 60)
    print(f"[*] Starting {settings.project_name}")
    print("=" * 60)
    print(f"-> Web UI:      {base_url}")
    print(f"-> API Docs:    {base_url}/docs")
    print(f"-> NVIDIA Model: {settings.nvidia_model}")
    print(f"-> Host & Port: {settings.server_host}:{settings.server_port}")
    print("=" * 60)
    print(f"[*] Open {base_url} in your browser to view the UI.")
    print("=" * 60)

    uvicorn.run(
        "app.main:app",
        host=settings.server_host,
        port=settings.server_port,
        reload=is_dev
    )
