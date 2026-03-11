# 🧠 Personal AI Assistant

A production-ready **Personal AI Assistant** with multimodal storage, semantic search, and Retrieval-Augmented Generation (RAG) — powered by **Claude (Anthropic)**, **Qdrant**, **FastAPI**, and **AWS S3**.

Upload your documents, PDFs, and images. Ask questions. Get intelligent answers.

---

## ✨ Features

- 📄 **Multimodal Ingestion** — Upload PDFs, DOCX, TXT, Markdown, and images
- 🔍 **Semantic Search** — Vector similarity search scoped per user via Qdrant
- 🤖 **RAG Q&A** — Claude-powered reasoning over your personal knowledge base
- 🖼️ **Image Analysis** — EXIF GPS/timestamp extraction + YOLOv8 object detection
- ⚡ **Smart LLM Routing** — Simple queries skip Claude (saves cost); complex ones use full RAG
- 🗄️ **3-Layer Caching** — Redis caches query results, embeddings, and parsed intents
- 🔐 **Per-user Isolation** — API key auth, user-scoped vector search
- 🔄 **Async Ingestion** — Celery background workers for non-blocking file processing

---

## 🏗️ Architecture

```
Client → FastAPI (REST API)
              ├── POST /api/v1/upload   → S3 + Celery Worker
              ├── POST /api/v1/search   → Qdrant semantic search
              └── POST /api/v1/ask      → Claude RAG pipeline

Celery Worker:
    PDF/DOCX/TXT → Extract → Chunk (tiktoken) → Embed (MiniLM) → Qdrant
    Images       → EXIF + YOLO → Embed caption → Qdrant

Services:
    PostgreSQL  — File metadata & chunks
    Qdrant      — Vector store (384-dim cosine similarity)
    Redis       — Cache (query results, embeddings, intents)
    AWS S3      — Raw file storage
    Claude      — Query parsing & RAG reasoning
```

---

## 🚀 Quick Start (Local)

### Prerequisites
- Python 3.11+
- Docker & Docker Compose
- AWS credentials (for S3)
- Anthropic API key

### 1. Clone & configure
```bash
git clone https://github.com/mohityada/PersonalAIAssistant.git
cd PersonalAIAssistant
cp .env.example .env
# Edit .env and fill in your credentials
```

### 2. Start infrastructure
```bash
docker compose up -d
```

### 3. Install dependencies
```bash
pip install -e ".[dev]"
```

### 4. Run migrations
```bash
alembic upgrade head
```

### 5. Start the API server
```bash
uvicorn app.main:app --reload --port 8000
```

### 6. Start the Celery worker (separate terminal)
```bash
OBJC_DISABLE_INITIALIZE_FORK_SAFETY=YES celery -A app.workers.celery_app worker --loglevel=info
```

### 7. Open Swagger UI
```
http://localhost:8000/docs
```

---

## 🔑 Create Your First API Key

```bash
python -c "
import asyncio
from app.db.session import async_session_factory
from app.models.database import User
from app.utils.hashing import hash_api_key, generate_api_key

async def create_user():
    key = generate_api_key()
    hashed = hash_api_key(key)
    async with async_session_factory() as session:
        user = User(name='Admin', api_key_hash=hashed)
        session.add(user)
        await session.commit()
    print(f'API Key: {key}')

asyncio.run(create_user())
"
```

Pass this key as `X-API-Key` header in all requests.

---

## 📡 API Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| `POST` | `/api/v1/upload` | Upload a file (PDF, DOCX, image, etc.) |
| `POST` | `/api/v1/search` | Semantic search across your files |
| `POST` | `/api/v1/ask` | RAG-powered Q&A with Claude |
| `GET`  | `/health` | Health check |

### Upload a file
```bash
curl -X POST http://localhost:8000/api/v1/upload \
  -H "X-API-Key: your-key" \
  -F "file=@document.pdf" \
  -F "tags=work,project" \
  -F "location=Jaipur"
```

### Search
```json
POST /api/v1/search
{
  "query": "project related to dynamic memory allocation",
  "filters": { "file_type": "pdf" },
  "top_k": 5
}
```

### Ask a question
```json
POST /api/v1/ask
{
  "question": "Summarize the key findings from my uploaded reports"
}
```

---

## 🛠️ Tech Stack

| Layer | Technology |
|-------|-----------|
| API | FastAPI + Uvicorn |
| Database | PostgreSQL 16 + SQLAlchemy (async) |
| Vector Store | Qdrant |
| Cache | Redis |
| Worker | Celery |
| Storage | AWS S3 |
| Embeddings | `all-MiniLM-L6-v2` (sentence-transformers, local) |
| LLM | Claude via Anthropic API |
| Image AI | YOLOv8 (object detection) + Pillow (EXIF) |
| Text Parsing | PyPDF2, python-docx, tiktoken |
| Migrations | Alembic |

---

## 🧪 Running Tests

```bash
# Unit tests (no external services needed)
pytest tests/test_chunking.py tests/test_query_parser.py tests/test_api.py -v

# Embedding tests (downloads model ~90MB on first run)
pytest tests/test_embedding.py -v

# All tests
pytest -v
```

---

## 🌍 Deploying to AWS

See [AWS Deployment Guide](#) for full steps covering:
- ECS Fargate for FastAPI + Celery
- RDS PostgreSQL
- ElastiCache Redis
- EC2 for Qdrant
- ALB + ECR

**Estimated cost: ~$73/month** (t3/db.t3.micro instances)

---

## 📁 Project Structure

```
personal-ai-assistant/
├── app/
│   ├── api/           # FastAPI endpoints (upload, search, ask, auth)
│   ├── services/      # Core services (RAG, embedding, cache, S3, Qdrant)
│   ├── workers/       # Celery tasks for async ingestion
│   ├── models/        # SQLAlchemy models & Pydantic schemas
│   ├── db/            # Database session management
│   └── utils/         # Hashing helpers
├── alembic/           # Database migrations
├── tests/             # Test suite
├── docker-compose.yml # Local infrastructure
└── pyproject.toml     # Dependencies
```

---

## 📄 License

MIT License — feel free to use, modify, and distribute.
