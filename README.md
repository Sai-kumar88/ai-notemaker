# Note Maker - Production AI Document Summarizer Backend

A production-ready FastAPI backend designed to process **PDF** and **DOCX** documents and generate strictly faithful, structured study notes using **NVIDIA NIM API (`meta/llama-3.2-11b-vision-instruct`)**.

---

## 📌 Architecture & Pipeline

```text
User uploads PDF / DOCX
        ↓
Frontend sends file + optional chapter numbers
        ↓
FastAPI API (/api/v1/notes/summarize)
        ↓
Extract document text (pypdf / python-docx)
        ↓
Chapter numbers provided?
   ┌───────────────┴───────────────┐
   ↓                               ↓
YES                              NO / []
   ↓                               ↓
Find requested chapters          Use entire document
   ↓                               ↓
Extract only those chapters     Full document text
   └───────────────┬───────────────┘
                   ↓
          Check text size
                   ↓
       If large → split into chunks
                   ↓
          NVIDIA NIM API Execution:
     Model: meta/llama-3.2-11b-vision-instruct
                   ↓
      Source-only structured notes
                   ↓
        Return summary to frontend
```

### 🛡️ The Grounding Principle & Resilience
> **Zero Hallucination**: If the source document does not contain information, the models must NOT invent it.
>
> **Direct NVIDIA NIM Integration**: Document processing and summarization leverage NVIDIA's low-latency inference endpoint.
>
> **Missing Chapter Protection**: If a requested chapter does not exist in the document, the API returns a structured `404 Not Found` error listing the missing chapter(s) instead of generating hallucinated text.

---

## ⚙️ Prerequisites

- **Python**: Version `3.10` or higher (`3.11` recommended)
- **NVIDIA API Key**: High-speed LLM key from [NVIDIA Build](https://build.nvidia.com)

---

## 🚀 Quick Setup Guide

### Step 1: Open Terminal in the Project Directory

```powershell
cd "c:\Users\lokesh\NOTE MAKER"
```

### Step 2: Create & Activate Virtual Environment

**On Windows (PowerShell):**
```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
```

*(If PowerShell blocks execution of scripts, run: `Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope CurrentUser`)*

**On Windows (Command Prompt - cmd.exe):**
```cmd
python -m venv .venv
.\.venv\Scripts\activate.bat
```

**On macOS / Linux:**
```bash
python3 -m venv .venv
source .venv/bin/activate
```

---

### Step 3: Install Required Dependencies

```powershell
pip install -r requirements.txt
```

---

### Step 4: Configure Environment Variables (`.env`)

A `.env` file is already created in the workspace. You can configure or customize values as needed:

```ini
# NVIDIA API Configuration
NVIDIA_API_KEY=your_nvidia_api_key_here
NVIDIA_MODEL=deepseek-ai/deepseek-v3
NVIDIA_BASE_URL=https://integrate.api.nvidia.com/v1
NVIDIA_TEMPERATURE=0.1
NVIDIA_MAX_TOKENS=4096
NVIDIA_TIMEOUT_SECONDS=60.0

# Document & Processing Configuration
MAX_FILE_SIZE_MB=50
CHUNK_SIZE_CHARS=12000
CHUNK_OVERLAP_CHARS=1000
MAX_CHUNKS=30
ALLOWED_EXTENSIONS=[".pdf", ".docx"]
UPLOAD_DIR=uploads

# Application & Server Configuration
ENVIRONMENT=development
LOG_LEVEL=INFO
SERVER_HOST=127.0.0.1
SERVER_PORT=8052
UPLOAD_BUFFER_BYTES=1048576
```

#### Environment Variables Reference:

| Variable | Default Value | Description |
| :--- | :--- | :--- |
| `NVIDIA_API_KEY` | *(Required)* | NVIDIA API authentication key for inference. |
| `NVIDIA_MODEL` | `meta/llama-3.2-11b-vision-instruct` | High-performance model hosted on NVIDIA NIM. |
| `NVIDIA_BASE_URL` | `https://integrate.api.nvidia.com/v1` | Base URL for the NVIDIA API endpoint. |
| `NVIDIA_TEMPERATURE` | `0.1` | Low temperature ensures factual faithfulness and prevents hallucination. |
| `NVIDIA_MAX_TOKENS` | `4096` | Maximum token length for the summary response. |
| `SERVER_HOST` | `127.0.0.1` | Host interface to bind the server. |
| `SERVER_PORT` | `8052` | Port number to run the server on. |
| `MAX_FILE_SIZE_MB` | `50` | Maximum allowed upload size in megabytes. |
| `CHUNK_SIZE_CHARS` | `12000` | Character threshold before splitting text into multi-part chunks. |
| `CHUNK_OVERLAP_CHARS`| `1000` | Character overlap between consecutive chunks to preserve context. |
| `MAX_CHUNKS` | `30` | Safety limit on maximum chunks per document to avoid runaway API costs. |

---

## 💻 How to Run the Server

You can run the server using either of the following methods:

### Method 1: Using `run.py` (Recommended)

The project includes a root [run.py](file:///c:/Users/lokesh/NOTE%20MAKER/run.py) script that automatically reads `SERVER_HOST` and `SERVER_PORT` directly from your `.env` file:

```powershell
python run.py
```

### Method 2: Using `uvicorn` Directly

```powershell
uvicorn app.main:app --host 127.0.0.1 --port 8052 --reload
```

---

## 🌐 Endpoints & API Documentation

Once the server is running, visit:
- **Interactive Swagger Documentation**: [http://127.0.0.1:8052/docs](http://127.0.0.1:8052/docs)
- **ReDoc UI**: [http://127.0.0.1:8052/redoc](http://127.0.0.1:8052/redoc)
- **Frontend Web UI**: [http://127.0.0.1:8052/](http://127.0.0.1:8052/)

---

## 🧪 Running Automated Tests

Run the complete test suite:

```powershell
$env:PYTHONPATH="."
.\.venv\Scripts\python.exe -m pytest
```

---

## 📁 Project Structure

```
c:\Users\lokesh\NOTE MAKER\
├── app/
│   ├── prompts/
│   │   └── summary_prompt.py      # Strict, anti-hallucination prompts
│   ├── routes/
│   │   └── notes.py               # FastAPI endpoints & file cleanup
│   ├── schemas/
│   │   └── note_schema.py         # Pydantic request & response models
│   ├── services/
│   │   ├── chapter_service.py     # Dynamic chapter detection & validation
│   │   ├── chunking_service.py    # Semantic chunking for large documents
│   │   ├── document_service.py    # PDF and DOCX text extractors
│   │   ├── nvidia_service.py      # NVIDIA NIM API client
│   │   └── summary_service.py     # Orchestrator pipeline
│   ├── config.py                  # Pydantic BaseSettings (.env loader)
│   ├── static/                    # Frontend UI static files
│   └── main.py                    # FastAPI application & CORS
├── tests/
│   ├── test_api_workflows.py      # End-to-end API integration tests
│   ├── test_chapter_service.py    # Chapter detection & missing chapter error tests
│   ├── test_chunking_service.py   # Large document text chunking tests
│   ├── test_config.py             # Environment configuration tests
│   ├── test_document_service.py   # PDF & DOCX extraction tests
│   ├── test_nvidia_service.py     # NVIDIA service unit & error tests
│   └── test_prompts.py            # Prompt constraint tests
├── uploads/                       # Temporary upload directory (auto-cleaned)
├── .env                           # Local environment variables
├── .env.example                   # Environment template
├── requirements.txt               # Production dependencies
├── run.py                         # Python entrypoint runner
└── README.md                      # Documentation
```
