"""
Entry point script to run the FastAPI application using Python directly.
Reads host, port, environment settings, and URL prefix dynamically from .env.
Usage:
    python run.py
"""
import uvicorn
from app.config import settings

if __name__ == "__main__":
    is_dev = settings.environment.lower() != "production"
    prefix = settings.url_prefix  # e.g. "/note-marker" or ""

    # On Windows, browsers cannot open 0.0.0.0 directly (ERR_ADDRESS_INVALID).
    display_host = "127.0.0.1" if settings.server_host in ("0.0.0.0", "::") else settings.server_host
    base_url = f"http://{display_host}:{settings.server_port}"

    print("=" * 65)
    print(f"[*] Starting {settings.project_name}")
    print("=" * 65)

    # ── Local / direct access URLs (no proxy needed) ──────────────────────
    # The app registers routes at BOTH "/" and "/{prefix}/" so both URLs work
    # regardless of whether you're running behind Nginx or not.
    print(f"  Web UI (direct):   {base_url}/")
    if prefix:
        print(f"  Web UI (prefixed): {base_url}{prefix}/")
    print(f"  API Docs:          {base_url}/docs")
    print(f"  Health check:      {base_url}/health")

    # ── Configuration ─────────────────────────────────────────────────────
    print(f"  URL Prefix:        {prefix or '/ (root)'}")
    print(f"  NVIDIA Model:      {settings.nvidia_model}")
    print(f"  Host & Port:       {settings.server_host}:{settings.server_port}")
    print(f"  Environment:       {settings.environment}")
    print(f"  Reload (dev):      {is_dev}")

    if prefix:
        print()
        print(f"  [Nginx proxy URL]  https://<your-domain>{prefix}/")
        print(f"  Set APPLICATION_ROOT=  (empty) to run at domain root instead.")

    print("=" * 65)
    print(f"  Open {base_url}/ in your browser to view the UI.")
    print("=" * 65)

    uvicorn.run(
        "app.main:app",
        host=settings.server_host,
        port=settings.server_port,
        reload=is_dev,
        # root_path tells uvicorn/starlette what SCRIPT_NAME prefix the app
        # is mounted under behind the reverse proxy.
        root_path=prefix,
        # Trust X-Forwarded-* headers from upstream proxies
        proxy_headers=True,
        forwarded_allow_ips="*",
    )
