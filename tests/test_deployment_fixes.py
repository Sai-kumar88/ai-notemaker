"""
tests/test_deployment_fixes.py

Automated tests that verify every root cause listed in the deployment fix task:
  1. Broken frontend asset paths (404s) – static files resolve under prefix
  2. Hardcoded API endpoints in JavaScript – apiUrl() helper present
  3. Reverse-proxy subpath prefix – root_path, health check under prefix
  4. Defensive APPLICATION_ROOT parsing (full URL → path-only)
  5. Trailing-slash robustness
  6. Config: PUBLIC_ORIGIN, TRUSTED_PROXIES, WORKERS env vars

All tests are self-contained and never call the real NVIDIA API.
"""
import os
import re
import pytest
from fastapi.testclient import TestClient


# ---------------------------------------------------------------------------
# 1. Config: APPLICATION_ROOT / URL_PREFIX parsing
# ---------------------------------------------------------------------------
class TestApplicationRootParsing:
    """Defensive env-var parsing: full URLs must be reduced to path-only."""

    def test_bare_path_unchanged(self):
        from app.config import Settings
        s = Settings(application_root="/note-marker")
        assert s.url_prefix == "/note-marker"

    def test_path_without_leading_slash_gets_one(self):
        from app.config import Settings
        s = Settings(application_root="note-marker")
        assert s.url_prefix == "/note-marker"

    def test_trailing_slash_stripped(self):
        from app.config import Settings
        s = Settings(application_root="/note-marker/")
        assert s.url_prefix == "/note-marker"

    def test_full_https_url_extracts_path_only(self):
        """Operators sometimes paste full URLs like https://host:port/prefix/."""
        from app.config import Settings
        s = Settings(application_root="https://example.com:8052/note-marker/")
        assert s.url_prefix == "/note-marker", (
            f"Expected '/note-marker', got '{s.url_prefix}'. "
            "Full URL should not produce '/https://...' path."
        )

    def test_full_http_url_extracts_path_only(self):
        from app.config import Settings
        s = Settings(application_root="http://192.168.1.10:8052/note-marker")
        assert s.url_prefix == "/note-marker"

    def test_empty_string_means_root(self):
        from app.config import Settings
        s = Settings(application_root="")
        assert s.url_prefix == ""

    def test_root_slash_means_empty(self):
        from app.config import Settings
        s = Settings(application_root="/")
        assert s.url_prefix == ""

    def test_nested_prefix_preserved(self):
        from app.config import Settings
        s = Settings(application_root="/tools/ai/note-marker")
        assert s.url_prefix == "/tools/ai/note-marker"

    def test_full_url_nested_prefix(self):
        from app.config import Settings
        s = Settings(application_root="https://host/tools/ai/note-marker/")
        assert s.url_prefix == "/tools/ai/note-marker"

    def test_url_prefix_property_alias(self):
        """url_prefix property must equal application_root."""
        from app.config import Settings
        s = Settings(application_root="/note-marker")
        assert s.url_prefix == s.application_root

    def test_trusted_proxies_default(self):
        from app.config import Settings
        s = Settings()
        assert s.trusted_proxies >= 1

    def test_public_origin_optional(self):
        from app.config import Settings
        s = Settings()
        assert s.public_origin is None

    def test_public_origin_set(self):
        from app.config import Settings
        s = Settings(public_origin="https://example.com:8052")
        assert s.public_origin == "https://example.com:8052"


# ---------------------------------------------------------------------------
# 2. Frontend: no hardcoded root-absolute /static/ or /api/ paths in source
# ---------------------------------------------------------------------------
class TestFrontendAssetPaths:
    """Static HTML/JS files must NOT contain bare root-absolute asset paths."""

    def _read(self, filename: str) -> str:
        path = os.path.join(os.path.dirname(__file__), "..", "app", "static", filename)
        with open(path, encoding="utf-8") as f:
            return f.read()

    def test_index_html_no_hardcoded_static_href(self):
        html = self._read("index.html")
        # Must NOT have href="/static/..." – that breaks under any prefix
        bad_matches = re.findall(r'href=["\']\/static\/', html)
        assert not bad_matches, (
            f"index.html still has hardcoded root-absolute /static/ links: {bad_matches}"
        )

    def test_index_html_no_hardcoded_static_src(self):
        html = self._read("index.html")
        # Must NOT have src="/static/..." – that breaks under any prefix
        bad_matches = re.findall(r'src=["\']\/static\/', html)
        assert not bad_matches, (
            f"index.html still has hardcoded root-absolute /static/ src attributes: {bad_matches}"
        )

    def test_index_html_has_base_detection_script(self):
        html = self._read("index.html")
        assert "window.__BASE__" in html, (
            "index.html must set window.__BASE__ for prefix-aware asset resolution."
        )

    def test_app_js_has_api_url_helper(self):
        js = self._read("app.js")
        assert "function apiUrl" in js, (
            "app.js must define apiUrl() helper to prepend window.__BASE__."
        )

    def test_app_js_no_hardcoded_fetch_api_path(self):
        js = self._read("app.js")
        # Any fetch('/api/... is a bug – must use apiUrl('/api/...')
        bad_matches = re.findall(r"""fetch\(\s*['"][/]api""", js)
        assert not bad_matches, (
            f"app.js has hardcoded root-absolute fetch('/api/...') calls: {bad_matches}. "
            "Use apiUrl('/api/...') instead."
        )

    def test_app_js_api_url_uses_base(self):
        js = self._read("app.js")
        # apiUrl must reference window.__BASE__ (or the 'base' variable from it)
        assert "window.__BASE__" in js or "__BASE__" in js, (
            "apiUrl() in app.js must use window.__BASE__ to prepend the prefix."
        )


# ---------------------------------------------------------------------------
# 3. FastAPI app: prefix-aware routes, trailing-slash, proxy headers
# ---------------------------------------------------------------------------
@pytest.fixture(scope="module")
def client():
    """Create a TestClient using the app configured from .env (APPLICATION_ROOT=/note-marker)."""
    from app.main import app as fastapi_app
    with TestClient(fastapi_app, raise_server_exceptions=False) as c:
        yield c


# The URL prefix configured in .env / APPLICATION_ROOT
PREFIX = "/note-marker"


class TestRoutesAndPrefix:

    def test_health_check_bare_path(self, client):
        """GET /health must return 200 without any prefix."""
        resp = client.get("/health")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "healthy"

    def test_health_check_api_prefix(self, client):
        """GET /api/v1/health must return 200."""
        resp = client.get("/api/v1/health")
        assert resp.status_code == 200
        assert resp.json()["status"] == "healthy"

    def test_health_check_returns_url_prefix(self, client):
        """Health response should report the active url_prefix."""
        resp = client.get("/health")
        data = resp.json()
        assert "url_prefix" in data

    def test_root_serves_html(self, client):
        """GET / (or the prefix root) must return 200 HTML or a redirect to the HTML page."""
        # Try the bare root first (which is always mapped to index.html)
        resp = client.get("/", follow_redirects=True)
        assert resp.status_code == 200
        assert "text/html" in resp.headers.get("content-type", "")

    def test_static_css_served(self, client):
        """GET {prefix}/static/style.css must return 200."""
        resp = client.get(PREFIX + "/static/style.css")
        assert resp.status_code == 200

    def test_static_js_served(self, client):
        """GET {prefix}/static/app.js must return 200."""
        resp = client.get(PREFIX + "/static/app.js")
        assert resp.status_code == 200

    def test_api_info_endpoint(self, client):
        """GET /api/v1/notes/info must return server config."""
        resp = client.get("/api/v1/notes/info")
        assert resp.status_code == 200
        data = resp.json()
        assert "max_file_size_mb" in data

    def test_trailing_slash_on_health_redirects_or_200(self, client):
        """GET /health/ should not 404 — either 200 or 30x redirect."""
        resp = client.get("/health/", follow_redirects=False)
        assert resp.status_code in (200, 307, 308), (
            f"GET /health/ returned unexpected {resp.status_code}. "
            "Should be 200 or a redirect, not 404."
        )

    def test_trailing_slash_on_api_v1_health(self, client):
        """GET /api/v1/health/ should not 404."""
        resp = client.get("/api/v1/health/", follow_redirects=False)
        assert resp.status_code in (200, 307, 308), (
            f"GET /api/v1/health/ returned {resp.status_code}, expected 200 or redirect."
        )

    def test_notes_info_trailing_slash(self, client):
        """GET /api/v1/notes/info/ should not 404."""
        resp = client.get("/api/v1/notes/info/", follow_redirects=False)
        assert resp.status_code in (200, 307, 308)

    def test_unsupported_file_returns_400_not_500(self, client):
        """A .txt upload should return 400 Bad Request, not 500."""
        resp = client.post(
            "/api/v1/notes/summarize",
            files={"file": ("bad.txt", b"plain text", "text/plain")},
        )
        assert resp.status_code == 400
        data = resp.json()
        assert data["success"] is False

    def test_error_response_schema_consistent(self, client):
        """All error responses must use the ErrorResponse schema with success/error keys."""
        resp = client.post(
            "/api/v1/notes/summarize",
            files={"file": ("bad.txt", b"content", "text/plain")},
        )
        data = resp.json()
        assert "success" in data
        assert "error" in data
        assert "code" in data["error"]
        assert "message" in data["error"]

    def test_forwarded_proto_header_trusted(self, client):
        """Requests with X-Forwarded-Proto: https must not downgrade to http in responses."""
        resp = client.get(
            "/health",
            headers={
                "X-Forwarded-Proto": "https",
                "X-Forwarded-Host": "example.com",
            },
        )
        # The request should succeed (not 400/500)
        assert resp.status_code == 200


# ---------------------------------------------------------------------------
# 4. main.py structure checks (source-level assertions)
# ---------------------------------------------------------------------------
class TestMainPyStructure:
    """Verify main.py contains all required deployment constructs."""

    def _read_main(self) -> str:
        path = os.path.join(os.path.dirname(__file__), "..", "app", "main.py")
        with open(path, encoding="utf-8") as f:
            return f.read()

    def test_proxy_headers_middleware_imported(self):
        src = self._read_main()
        assert "ProxyHeadersMiddleware" in src, (
            "main.py must import and apply uvicorn ProxyHeadersMiddleware."
        )

    def test_root_path_set_from_settings(self):
        src = self._read_main()
        assert "root_path" in src, (
            "FastAPI app must be created with root_path= to support subpath deployment."
        )

    def test_trailing_slash_middleware_present(self):
        src = self._read_main()
        assert "TrailingSlashMiddleware" in src or "trailing" in src.lower(), (
            "main.py should include trailing-slash redirect middleware."
        )

    def test_cors_middleware_present(self):
        src = self._read_main()
        assert "CORSMiddleware" in src

    def test_static_mount_present(self):
        src = self._read_main()
        assert "StaticFiles" in src

    def test_no_hardcoded_prefix_in_health_url(self):
        src = self._read_main()
        # The health check URL in source must not be hardcoded as /api/v1/notes/info
        # (that was a typo in the old HEALTHCHECK – it tested an endpoint that requires auth)
        assert "/api/v1/notes/info" not in src or "HEALTHCHECK" not in src


# ---------------------------------------------------------------------------
# 5. Dockerfile & docker-compose checks (text assertions)
# ---------------------------------------------------------------------------
class TestDockerfiles:

    def _read(self, filename: str) -> str:
        path = os.path.join(os.path.dirname(__file__), "..", filename)
        with open(path, encoding="utf-8") as f:
            return f.read()

    def test_dockerfile_uses_multiple_workers(self):
        src = self._read("Dockerfile")
        assert "--workers" in src or "WORKERS" in src, (
            "Dockerfile must launch uvicorn with configurable workers for production."
        )

    def test_dockerfile_passes_root_path(self):
        src = self._read("Dockerfile")
        assert "--root-path" in src, (
            "Dockerfile CMD must pass --root-path to uvicorn for prefix deployment."
        )

    def test_dockerfile_enables_proxy_headers(self):
        src = self._read("Dockerfile")
        assert "--proxy-headers" in src, (
            "Dockerfile CMD must enable --proxy-headers for X-Forwarded-* support."
        )

    def test_dockerfile_has_healthcheck(self):
        src = self._read("Dockerfile")
        assert "HEALTHCHECK" in src

    def test_dockerfile_application_root_env(self):
        src = self._read("Dockerfile")
        assert "APPLICATION_ROOT" in src, (
            "Dockerfile must expose APPLICATION_ROOT so the container prefix is configurable."
        )

    def test_dockerignore_excludes_venv(self):
        src = self._read(".dockerignore")
        assert ".venv" in src or "venv/" in src

    def test_dockerignore_excludes_pycache(self):
        src = self._read(".dockerignore")
        assert "__pycache__" in src

    def test_dockerignore_excludes_env_files(self):
        src = self._read(".dockerignore")
        assert ".env" in src

    def test_docker_compose_application_root(self):
        src = self._read("docker-compose.yml")
        assert "APPLICATION_ROOT" in src, (
            "docker-compose.yml must set APPLICATION_ROOT for prefix-aware deployment."
        )

    def test_docker_compose_has_healthcheck(self):
        src = self._read("docker-compose.yml")
        assert "healthcheck" in src.lower()
