# Note Maker — Enterprise AI Document Summarizer & Study Guide Generator

[![Python 3.10+](https://img.shields.io/badge/python-3.10%20%7C%203.11-blue.svg)](https://www.python.org/)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.115+-009688.svg)](https://fastapi.tiangolo.com/)
[![NVIDIA NIM](https://img.shields.io/badge/NVIDIA%20NIM-meta%2Fllama--3.2--11b--vision--instruct-76B900.svg)](https://build.nvidia.com)
[![Docker](https://img.shields.io/badge/Docker-Ready-2496ED.svg)](https://www.docker.com/)
[![Tests Passing](https://img.shields.io/badge/tests-97%2F97%20passing-brightgreen.svg)]()
[![License](https://img.shields.io/badge/license-MIT-green.svg)]()

**Note Maker** is a production-grade, enterprise-ready document intelligence platform built with **FastAPI** and **NVIDIA NIM API** (`meta/llama-3.2-11b-vision-instruct`). It transforms complex **PDF** and **DOCX** textbooks, research papers, and technical manuals into structured, strictly faithful study notes with zero hallucinations, chapter-aware filtering, adaptive semantic chunking, and high-fidelity vector PDF export.

---

## 📌 Architecture & Processing Pipeline

```text
               User / Web Browser / API Client
                              │
                              ▼
               Reverse Proxy (Nginx / Cloudflare)
                              │
                    [X-Forwarded-Prefix]
                              ▼
  ┌────────────────────────────────────────────────────────┐
  │                 FastAPI Application                    │
  │  - ProxyHeadersMiddleware (Trust reverse proxy hops)   │
  │  - DynamicPrefixMiddleware (Prefix-aware routing)      │
  │  - TrailingSlashMiddleware (No 307 redirect loops)     │
  │  - CORSMiddleware (Configurable origins)               │
  └───────────────────────────┬────────────────────────────┘
                              │
                              ▼
  ┌────────────────────────────────────────────────────────┐
  │                app/routes/notes.py                     │
  │  - Filename Sanitization (app/utils/file_utils.py)     │
  │  - Stream-buffered upload (1MB chunks, size capped)    │
  │  - Chapter Input Normalization (app/utils/chapter.py)  │
  └───────────────────────────┬────────────────────────────┘
                              │
                              ▼
  ┌────────────────────────────────────────────────────────┐
  │            Document Ingestion & Parsing                │
  │  - DocumentService: PyMuPDF (PDF) + python-docx (DOCX) │
  │  - Page-by-page text & table cell de-duplication       │
  └───────────────────────────┬────────────────────────────┘
                              │
                              ▼
  ┌────────────────────────────────────────────────────────┐
  │          Chapter Detection & Zero Hallucination        │
  │  - ChapterService: Regex chapter boundary scanner      │
  │  - If requested chapters missing -> 404 Error Raised   │
  │  - If matched -> extracts ONLY requested chapter text  │
  └───────────────────────────┬────────────────────────────┘
                              │
                              ▼
  ┌────────────────────────────────────────────────────────┐
  │           Adaptive Linguistic Chunking                 │
  │  - ChunkingService: Natural boundary detection         │
  │  - Paragraph, sentence, & punctuation break ranking    │
  │  - Preserves 1,000 char overlap between chunks         │
  └───────────────────────────┬────────────────────────────┘
                              │
                              ▼
  ┌────────────────────────────────────────────────────────┐
  │         NVIDIA NIM Inference (Concurrent & Bounded)    │
  │  - Model: meta/llama-3.2-11b-vision-instruct           │
  │  - HTTP/2 keep-alive pool & exponential backoff retry  │
  │  - Bounded concurrency via asyncio.Semaphore           │
  │  - Strict source-only anti-hallucination prompts       │
  └───────────────────────────┬────────────────────────────┘
                              │
                              ▼
  ┌────────────────────────────────────────────────────────┐
  │             Structured Synthesis & Export              │
  │  - Synthesis of chunk summaries into unified notes     │
  │  - Guaranteed temporary disk cleanup in finally: block │
  │  - Vector PDF Export (PdfExportService / PyMuPDF)      │
  └────────────────────────────────────────────────────────┘
```

---

## 🛡️ Core Production Guarantees

1. **Strict Zero-Hallucination Policy**: If requested chapters or concepts are not present in the document, the system refuses to generate fictional content. When non-existent chapters are requested, it returns a structured `404 Not Found` response listing the missing chapters.
2. **Dual-Prefix & Reverse Proxy Ready**: Seamlessly runs at root (`/`) or mounted under any subpath (e.g. `/note-marker/`) via the `APPLICATION_ROOT` configuration. All HTML script/link tags and JS API calls adapt dynamically without code changes.
3. **Resilient Memory-Buffered Streaming**: Uploads are written to disk in 1 MB buffered chunks with continuous byte-counting, rejecting files over `MAX_FILE_SIZE_MB` before memory exhaustion occurs.
4. **Path Traversal & Security Hardened**: Every uploaded filename is sanitized with regex-safe slugification. Temporary files are isolated with UUID prefixes and guaranteed to be unlinked in `finally:` blocks.
5. **No Sentence Slicing PDF Export**: The server-side PDF generator uses PyMuPDF's block measurement algorithm to calculate space before writing elements. Long sections break cleanly across pages without cut sentences or clipped words.

---

## ⚙️ Prerequisites

- **Python**: `3.10` or higher (`3.11` recommended)
- **NVIDIA API Key**: Free inference API key from [NVIDIA Build](https://build.nvidia.com)
- **Operating System**: Windows, Linux, or macOS
- **Docker Desktop** *(Optional)*: Required only if running inside containers

---

## 🚀 Quick Setup Guide

### 1. Clone & Enter Project Directory

```bash
git clone https://github.com/Sai-kumar88/ai-notemaker.git
cd ai-notemaker
```

### 2. Create and Activate Virtual Environment

**Windows (PowerShell):**
```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
```
*(If PowerShell restricts script execution, run: `Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope CurrentUser`)*

**Windows (Command Prompt):**
```cmd
python -m venv .venv
.\.venv\Scripts\activate.bat
```

**macOS / Linux:**
```bash
python3 -m venv .venv
source .venv/bin/activate
```

### 3. Install Dependencies

```bash
pip install --upgrade pip
pip install -r requirements.txt
```

### 4. Configure Environment Variables (`.env`)

Copy `.env.example` to `.env` and fill in your NVIDIA API Key:

```bash
cp .env.example .env
```

Edit `.env`:
```ini
# NVIDIA NIM Inference Configuration
NVIDIA_API_KEY=nvapi-your_real_key_here
NVIDIA_MODEL=meta/llama-3.2-11b-vision-instruct
NVIDIA_BASE_URL=https://integrate.api.nvidia.com/v1
NVIDIA_TEMPERATURE=0.3
NVIDIA_MAX_TOKENS=4096
NVIDIA_TIMEOUT_SECONDS=60.0
NVIDIA_MAX_RETRIES=3
NVIDIA_RETRY_DELAY_SECONDS=1.5

# Server & Reverse Proxy Configuration
SERVER_HOST=127.0.0.1
SERVER_PORT=8052
ENVIRONMENT=production
LOG_LEVEL=INFO
APPLICATION_ROOT=/note-marker
CORS_ORIGINS=["*"]
TRUSTED_PROXIES=1

# Document Processing Constraints (Optimized for 128k context)
MAX_FILE_SIZE_MB=50
UPLOAD_BUFFER_BYTES=1048576
CHUNK_SIZE_CHARS=48000
CHUNK_OVERLAP_CHARS=1000
CHUNK_SUMMARY_MAX_TOKENS=1200
MAX_CHUNKS=30
MAX_CONCURRENT_CHUNK_REQUESTS=8
ALLOWED_EXTENSIONS=[".pdf", ".docx"]
UPLOAD_DIR=uploads
```

---

## 💻 Running the Application

### Method 1: Using `run.py` (Recommended for Local Development)

`run.py` automatically initializes `.env`, ensures directories exist, validates settings, and displays formatted service URLs:

```powershell
python run.py
```

### Method 2: Using `uvicorn` Directly

```powershell
uvicorn app.main:app --host 127.0.0.1 --port 8052 --reload
```

### Method 3: Using Docker Compose

```powershell
# 1. Build and run in background
docker compose up -d --build

# 2. View streaming logs
docker compose logs -f

# 3. Check container status
docker compose ps

# 4. Stop containers
docker compose down
```

### Method 4: Production Nginx Reverse Proxy Setup

To deploy Note Maker behind Nginx under `/note-marker/`:

```nginx
location /note-marker/ {
    proxy_pass http://127.0.0.1:8052/note-marker/;
    proxy_set_header Host $host;
    proxy_set_header X-Real-IP $remote_addr;
    proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
    proxy_set_header X-Forwarded-Proto $scheme;
    proxy_set_header X-Forwarded-Prefix /note-marker;
    proxy_buffering off;
    client_max_body_size 50M;
}
```

---

## 🌐 Endpoints & API Reference

When running locally, explore interactive API documentation at:
- **Swagger UI**: [http://127.0.0.1:8052/docs](http://127.0.0.1:8052/docs)
- **ReDoc**: [http://127.0.0.1:8052/redoc](http://127.0.0.1:8052/redoc)
- **Web Interface**: [http://127.0.0.1:8052/](http://127.0.0.1:8052/) or [http://127.0.0.1:8052/note-marker/](http://127.0.0.1:8052/note-marker/)

### 1. `POST /api/v1/notes/summarize`
Uploads a document and generates strictly grounded study notes.

**Parameters (multipart/form-data):**
- `file` (*required*, binary): PDF or DOCX file.
- `chapters` (*optional*, string): Comma-separated or JSON list of chapter numbers (e.g. `"1, 2"` or `"[1, 2]"`). Leave empty for entire document.

**Example Request (curl):**
```bash
curl -X POST "http://127.0.0.1:8052/api/v1/notes/summarize" \
  -F "file=@document.pdf" \
  -F "chapters=1, 2"
```

**Success Response (200 OK):**
```json
{
  "success": true,
  "filename": "document.pdf",
  "summary": "### Core Concepts\n- **Thermodynamics**: Energy can neither be created nor destroyed...",
  "metadata": {
    "total_pages": 45,
    "processed_scope": "Chapters 1, 2",
    "chunks_processed": 1,
    "source_word_count": 3200,
    "summary_word_count": 480,
    "model_used": "meta/llama-3.2-11b-vision-instruct",
    "extraction_method": "PyMuPDF",
    "total_chapters_detected": 10
  }
}
```

**Missing Chapter Error (404 Not Found):**
```json
{
  "success": false,
  "error": {
    "code": "HTTP_404",
    "message": "Requested chapter(s) 99 could not be found in the document.",
    "details": {
      "missing_chapters": ["99"]
    }
  }
}
```

---

### 2. `POST /api/v1/notes/detect-chapters`
Scans and returns all chapters present in a document without performing LLM summarization.

**Example Request:**
```bash
curl -X POST "http://127.0.0.1:8052/api/v1/notes/detect-chapters" \
  -F "file=@biology_textbook.pdf"
```

**Response (200 OK):**
```json
{
  "success": true,
  "filename": "biology_textbook.pdf",
  "total_chapters_detected": 3,
  "chapters": [
    { "chapter_number": "1", "title": "Cellular Biology", "start_page": 1, "end_page": 18, "word_count": 4500 },
    { "chapter_number": "2", "title": "Genetics & DNA", "start_page": 19, "end_page": 40, "word_count": 5200 },
    { "chapter_number": "3", "title": "Ecosystem Dynamics", "start_page": 41, "end_page": 65, "word_count": 4800 }
  ]
}
```

---

### 3. `POST /api/v1/notes/export-pdf`
Generates a vector A4 PDF using the PyMuPDF typography engine.

**Request Body (application/json):**
```json
{
  "html": "<h2>Overview</h2><p>Structured summary notes...</p>",
  "title": "Document Notes",
  "scope": "Chapters 1, 2",
  "word_count": "480 words"
}
```

**Response:** Binary stream with header `Content-Type: application/pdf`.

---

### 4. `GET /health`
Returns system health, active model, and URL prefix.

```json
{
  "status": "healthy",
  "project": "Note Maker - AI Document Summarizer",
  "environment": "production",
  "model": "meta/llama-3.2-11b-vision-instruct",
  "url_prefix": "/note-marker"
}
```

---

## 📁 Project Directory Structure

```
c:\Users\lokesh\NOTE MAKER\
├── app/
│   ├── prompts/
│   │   └── summary_prompt.py          # Grounded anti-hallucination prompt templates
│   ├── routes/
│   │   └── notes.py                   # REST endpoints (/summarize, /detect-chapters, /export-pdf)
│   ├── schemas/
│   │   └── note_schema.py             # Pydantic v2 schemas and validation models
│   ├── services/
│   │   ├── chapter_service.py         # Chapter boundary detection and validation
│   │   ├── chunking_service.py        # Natural linguistic chunking with character overlap
│   │   ├── document_service.py        # PDF (PyMuPDF) and DOCX (python-docx) extraction
│   │   ├── nvidia_service.py          # Asynchronous NVIDIA NIM API client with retry logic
│   │   ├── pdf_export_service.py      # Vector A4 PDF generation (PyMuPDF Story engine)
│   │   └── summary_service.py         # End-to-end summarization orchestrator
│   ├── static/
│   │   ├── app.js                     # Accessible frontend logic, drag-and-drop & API caller
│   │   ├── index.html                 # Accessible UI structure with semantic labels
│   │   └── style.css                  # Modern UI styles, dark mode & responsive layout
│   ├── utils/
│   │   ├── __init__.py                # Utilities package initialization
│   │   ├── chapter_parser.py          # Reusable chapter string/list normalization
│   │   └── file_utils.py              # Filename sanitization, extension checking & formatting
│   ├── config.py                      # Production settings loaded from environment/.env
│   └── main.py                        # FastAPI application, middlewares & static mounts
├── tests/
│   ├── test_api_workflows.py          # End-to-end API integration & validation tests
│   ├── test_chapter_service.py        # Chapter detection & missing chapter error tests
│   ├── test_chunking_service.py       # Linguistic chunking & boundary tests
│   ├── test_config.py                 # Configuration validation & normalization tests
│   ├── test_deployment_fixes.py       # Prefix-awareness & reverse-proxy contract tests
│   ├── test_document_service.py       # PDF/DOCX parsing & resource management tests
│   ├── test_nvidia_service.py         # NVIDIA client error handling & retry tests
│   ├── test_pdf_export_service.py     # Multi-page vector PDF generation tests
│   ├── test_prompts.py                # Prompt constraint & instruction tests
│   └── test_utils.py                  # Utility parsing & sanitization unit tests
├── uploads/                           # Temporary file staging directory (auto-cleaned)
├── .env.example                       # Environment variables template
├── docker-compose.yml                 # Multi-container orchestration definition
├── Dockerfile                         # Production-hardened container build
├── requirements.txt                   # Frozen production dependencies
├── run.py                             # Server bootstrapper with environment validation
└── README.md                          # Comprehensive documentation
```

---

## 🧪 Running the Test Suite

The test suite contains **97 comprehensive unit and integration tests** covering document extraction, chunking, NVIDIA NIM client retries, chapter validation, deployment prefixes, and security rules.

To run the complete test suite:

```powershell
# PowerShell:
$env:PYTHONPATH="."
.\.venv\Scripts\python.exe -m pytest -v
```

```bash
# Bash:
PYTHONPATH=. pytest -v
```

---

## 🔧 Troubleshooting & FAQ

### 1. `[Errno 10048] error while attempting to bind on address ('127.0.0.1', 8052)`
This occurs when a previous Python or Uvicorn instance is still holding port 8052.

**Solution on Windows (PowerShell):**
```powershell
# Find process holding port 8052
Get-NetTCPConnection -LocalPort 8052 -ErrorAction SilentlyContinue | Select-Object OwningProcess

# Terminate the process (replace <PID> with the ID found)
Stop-Process -Id <PID> -Force
```

### 2. PowerShell says `Running scripts is disabled on this system`
Execute the following in PowerShell as current user:
```powershell
Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope CurrentUser
```

### 3. File upload button does not open file dialog
Ensure your browser has permission to trigger file dialogues. The updated frontend uses an accessible `<label for="fileInput">` pattern with zero pop-up blocking issues across Chrome, Edge, Safari, and Firefox.

### 4. Running behind a reverse proxy shows 404 for CSS or API calls
Verify that `APPLICATION_ROOT` in `.env` matches your Nginx location block (e.g. `/note-marker`). In your Nginx configuration, ensure `X-Forwarded-Prefix /note-marker` is passed. Note Maker automatically maps static assets and routes to match.

---

## 📄 License

This project is licensed under the MIT License. See [LICENSE](LICENSE) for details.
