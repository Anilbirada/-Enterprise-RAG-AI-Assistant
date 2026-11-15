# Enterprise RAG AI Assistant - System Architecture

## 1. High-Level Architecture Overview

The **Enterprise RAG AI Assistant** is an enterprise-grade retrieval-augmented generation platform providing grounded, citation-backed answers over internal corporate documents.

```mermaid
flowchart TB
    subgraph Client ["Client Tier (Frontend)"]
        SPA["React 18 + TypeScript SPA\n(Vite, Tailwind CSS, SSE Token Rendering)"]
    end

    subgraph API ["Application Server (FastAPI Core)"]
        CORS["CORS & Request ID Middleware"]
        TenantContext["Tenant Context Middleware"]
        Router["/api/v1 Endpoints"]

        subgraph Services ["Domain Services"]
            AuthSvc["Auth & RBAC Service"]
            DocSvc["Document Lifecycle Service"]
            RAGSvc["RAG Generation Service"]
            HybridRetriever["Hybrid Retrieval Engine\n(pgvector + tsvector)"]
        end

        subgraph Repositories ["Data Access Layer"]
            Repo["Tenant-Scoped Repositories"]
        end
    end

    subgraph AsyncWorker ["Asynchronous Ingestion Worker"]
        WorkerPool["Background Worker"]
        Parser["PyMuPDF / python-docx"]
        Chunker["Token-Aware Recursive Chunker"]
        Embedder["Batch Embedding Client"]
    end

    subgraph Database ["Persistence Layer (PostgreSQL 16 + pgvector 0.8.0)"]
        Relational["Relational Tables\n(RLS Enforced via SET LOCAL)"]
        HNSW["HNSW Vector Index (1536d)"]
        FTS["Full-Text GIN Index"]
    end

    subgraph ExternalAI ["External AI Provider"]
        OpenAI["OpenAI API\n(text-embedding-3-small & gpt-4o-mini)"]
    end

    SPA -->|"HTTPS / SSE"| CORS
    CORS --> TenantContext
    TenantContext --> Router
    Router --> Services
    Services --> Repositories
    Repositories --> Relational
    HybridRetriever --> HNSW
    HybridRetriever --> FTS

    Router -->|"Queue Ingestion"| WorkerPool
    WorkerPool --> Parser --> Chunker --> Embedder --> Repositories
    Embedder -->|"Vectors"| OpenAI
    RAGSvc -->|"Inference Prompts"| OpenAI
```

---

## 2. Multi-Tenant Security & Defense-in-Depth

1. **Authentication Token Binding:** The verified JWT payload injects immutable tenant identity (`org_id`).
2. **Transaction-Local Database Context:** Every async connection executes:
   ```sql
   SELECT set_config('app.current_org_id', :org_id, true);
   ```
3. **PostgreSQL Row Level Security (RLS):** Non-superuser application roles (`rag_app_user`) cannot read or write rows with mismatched `organization_id`.
4. **Composite Foreign Keys:** Child entities cannot reference parent entities from foreign organizations.
5. **Pre-Filtered Retrieval:** Vector similarity search executes with an explicit `organization_id = :org_id` predicate, preventing unauthorized cross-department data exposure.

---

## 3. Technology Stack Reference

- **Backend:** Python 3.12, FastAPI, Pydantic Settings, Uvicorn
- **ORM & Migrations:** SQLAlchemy 2.0 (Async), Asyncpg, Alembic
- **Database:** PostgreSQL 16 with pgvector 0.8.0
- **Document Processing (Phases 5-7):** PyMuPDF (`fitz`), `python-docx`, TikToken
- **Embeddings:** OpenAI `text-embedding-3-small` (1536 dimensions)
- **Frontend (Phase 11):** React 18, TypeScript, Vite, Tailwind CSS
- **Testing:** Pytest, pytest-asyncio, pytest-cov, HTTPX
