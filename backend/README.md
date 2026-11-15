# Enterprise RAG AI Assistant - Backend Foundation (Phase 2)

Welcome to the backend foundation of the **Enterprise RAG AI Assistant**. This service provides the asynchronous REST API, tenant-aware database layer, structured observability, and health-check infrastructure designed for enterprise AI retrieval workloads.

---

## 1. Directory Structure

```text
backend/
├── alembic/                         # Database migration environment
│   ├── versions/                    # Version migration scripts (Phase 3+)
│   ├── env.py                       # Async Alembic execution runner
│   └── script.py.mako               # Migration template
├── app/
│   ├── api/                         # Transport layer & routing
│   │   ├── deps.py                  # FastAPI dependency injections (DB, Tenant, Settings)
│   │   └── v1/
│   │       ├── router.py            # Aggregated v1 router
│   │       └── endpoints/
│   │           └── health.py        # System health, readiness, and liveness probes
│   ├── core/                        # Configuration & infrastructure foundations
│   │   ├── config.py                # Pydantic Settings (environment validation)
│   │   ├── exceptions.py            # Domain exceptions & global exception handlers
│   │   └── logger.py                # Structured JSON logging with credential masking
│   ├── database/                    # Persistence layer
│   │   ├── base.py                  # SQLAlchemy 2 DeclarativeBase & Mixins
│   │   └── session.py               # AsyncEngine, sessionmaker & tenant scoping
│   ├── middleware/                  # HTTP processing pipeline
│   │   ├── logging_middleware.py    # Request latency tracking & X-Request-ID propagation
│   │   └── tenant_context_middleware.py # Tenant context extraction
│   ├── models/                      # SQLAlchemy ORM definitions (Phase 3)
│   ├── repositories/                # Data access abstractions (Phase 3+)
│   ├── schemas/                     # Pydantic DTOs & envelope schemas
│   │   ├── error.py                 # Standardized error envelope
│   │   └── health.py                # Health check schema
│   ├── services/                    # Pure business logic layer (Phase 4+)
│   ├── utils/                       # General helper utilities
│   └── main.py                      # FastAPI application factory & lifespan
├── tests/                           # Automated test suite
│   ├── conftest.py                  # Pytest fixtures & environment overrides
│   ├── unit/                        # Unit tests (config, exceptions, deps)
│   └── integration/                 # Integration tests (health, error envelopes)
├── .env.example                     # Environment template with dummy values
├── alembic.ini                      # Alembic migration configuration
├── pytest.ini                       # Pytest test discovery & flags
└── requirements.txt                 # Pinned application dependencies
```

---

## 2. Prerequisites & Setup

### Requirements
- **Python**: 3.11 or 3.12
- **Virtual Environment**: Recommended (`venv`)

### Installation

1. Create and activate a Python virtual environment:
   ```powershell
   # Windows
   python -m venv .venv
   .\.venv\Scripts\Activate.ps1

   # Linux/macOS
   python3 -m venv .venv
   source .venv/bin/activate
   ```

2. Install pinned dependencies:
   ```bash
   pip install -r backend/requirements.txt
   ```

3. Configure environment variables:
   ```bash
   cp backend/.env.example backend/.env
   ```

---

## 3. Running the Backend Locally

Start the development server with live reload:

```bash
# From workspace root
uvicorn app.main:app --app-dir backend --host 0.0.0.0 --port 8000 --reload
```

Once running:
- **Interactive Swagger Documentation**: [http://localhost:8000/docs](http://localhost:8000/docs)
- **ReDoc API Documentation**: [http://localhost:8000/redoc](http://localhost:8000/redoc)
- **Root Service Info**: [http://localhost:8000/](http://localhost:8000/)
- **Comprehensive Health Check**: [http://localhost:8000/api/v1/health](http://localhost:8000/api/v1/health)
- **Readiness Probe**: [http://localhost:8000/api/v1/ready](http://localhost:8000/api/v1/ready)
- **Liveness Probe**: [http://localhost:8000/api/v1/live](http://localhost:8000/api/v1/live)

---

## 4. Running the Automated Test Suite

Run all unit and integration tests with coverage reporting:

```bash
# Navigate to backend directory
cd backend
pytest --cov=app --cov-report=term-missing
```

---

## 5. Security & Architectural Standards Enforced

1. **Zero Secret Leakage:**
   - Secrets (`POSTGRES_PASSWORD`, `SECRET_KEY`, `OPENAI_API_KEY`) are managed exclusively via `pydantic-settings`.
   - The custom logger (`mask_sensitive_data`) automatically scrubs fields like `password`, `token`, and `api_key` from all JSON logs.
2. **Correlation ID Tracing (`X-Request-ID`):**
   - Every request is tagged with a unique UUID injected by `RequestLoggingMiddleware`. If a client sends an `X-Request-ID`, it is propagated across all log lines and returned in response headers.
3. **Transaction-Local Tenant Scoping:**
   - In `app/database/session.py`, `set_tenant_context` uses PostgreSQL `SET LOCAL app.current_org_id = :org_id` ensuring transaction-level isolation without connection pool pollution.
4. **Resilient Error Envelopes:**
   - Unhandled exceptions (500) are caught by global handlers and masked, returning clean structured envelopes (`{"success": false, "error": {"code": "...", "message": "..."}}`) without exposing raw Python tracebacks or database queries to users.
