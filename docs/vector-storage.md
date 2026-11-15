# PostgreSQL & pgvector Vector Storage Architecture

## 1. Overview & Objectives

In Phase 8, the Enterprise RAG AI Assistant implements the **Vector Storage Engine and Data Access Repository Layer** using PostgreSQL 16 and the `pgvector 0.8.0` extension. This layer persists 1536-dimensional dense vector embeddings generated in Phase 7 into the `document_chunks` table, enables high-speed approximate nearest neighbor (ANN) retrieval using Hierarchical Navigable Small World (HNSW) indexing, and automatically maintains English full-text search vectors (`tsvector`) for Phase 9 hybrid search.

```
                      +-----------------------------+
                      |   DocumentChunkData (P7)    |
                      |  (Tokens, 1536d Embeddings) |
                      +--------------+--------------+
                                     |
                                     v
                      +-----------------------------+
                      |      VectorRepository       |
                      |  - batch_insert_chunks      |
                      |  - search_vector_similarity |
                      |  - search_full_text         |
                      |  - deactivate_by_version    |
                      +--------------+--------------+
                                     |
                     +---------------+---------------+
                     |                               |
                     v                               v
       +----------------------------+  +----------------------------+
       |   pgvector HNSW Index      |  |     GIN Full-Text Index    |
       | - vector_cosine_ops (<=>)  |  | - to_tsvector('english')   |
       | - m=16, ef_construction=64 |  | - plainto_tsquery / rank_cd|
       | - Cosine Similarity        |  | - Keyword exact matching   |
       +----------------------------+  +----------------------------+
                     |                               |
                     +---------------+---------------+
                                     |
                                     v
                      +-----------------------------+
                      |      ChunkSearchResult      |
                      | - Tenant Scoped             |
                      | - Active Version Filtered   |
                      +-----------------------------+
```

---

## 2. Table Design & Indexing Mechanics

### 2.1 The `document_chunks` Schema
The `document_chunks` table stores chunk content, positional metadata, dense vectors, and generated sparse vectors:

```sql
CREATE TABLE public.document_chunks (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    organization_id UUID NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
    document_id UUID NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
    version_id UUID NOT NULL REFERENCES document_versions(id) ON DELETE CASCADE,
    chunk_index INTEGER NOT NULL,
    content TEXT NOT NULL,
    token_count INTEGER NOT NULL,
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    embedding VECTOR(1536) NOT NULL,
    search_vector TSVECTOR GENERATED ALWAYS AS (to_tsvector('english'::regconfig, content)) STORED,
    metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT now(),
    updated_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT now(),

    -- Constraints
    CONSTRAINT uq_chunks_version_index UNIQUE (version_id, chunk_index),
    CONSTRAINT uq_chunks_org_id UNIQUE (organization_id, id),
    CONSTRAINT fk_chunks_org_document FOREIGN KEY (organization_id, document_id) 
        REFERENCES documents(organization_id, id) ON DELETE CASCADE,
    CONSTRAINT fk_chunks_org_version FOREIGN KEY (organization_id, version_id) 
        REFERENCES document_versions(organization_id, id) ON DELETE CASCADE
);
```

### 2.2 HNSW Index Configuration
Dense vector retrieval uses an HNSW index configured for cosine distance:
```sql
CREATE INDEX idx_chunks_embedding_hnsw ON document_chunks 
USING hnsw (embedding vector_cosine_ops) 
WITH (m = 16, ef_construction = 64);
```
- **Distance Operator:** `<=>` (Cosine distance, where $\text{similarity} = 1.0 - \text{distance}$).
- **`m = 16`**: Maximum number of bidirectional links per graph node. Provides optimal recall and graph navigation efficiency.
- **`ef_construction = 64`**: Size of dynamic candidate list evaluated during index construction, balancing index build speed with neighbor connectivity.

### 2.3 Automated Full-Text `tsvector` Generation
Rather than maintaining external application logic to tokenize English content for keyword search, PostgreSQL's `GENERATED ALWAYS AS (to_tsvector('english', content)) STORED` column automates English stemming, stopword stripping, and lexeme normalization at write time. A GIN index (`idx_chunks_search_vector`) accelerates keyword filtering:
```sql
CREATE INDEX idx_chunks_search_vector ON document_chunks USING gin (search_vector);
```

---

## 3. Multi-Tenant Security & Version Control

### 3.1 Strict Tenant Isolation
Every query executed through `VectorRepository` explicitly scopes operations by `organization_id`. Even if an attacker attempts to guess another tenant's `document_id` or `version_id`:
- **Repository Scope:** SQL queries explicitly include `WHERE organization_id = :org_id`.
- **Composite Foreign Keys:** Prevent any chunk from being associated with a document or version from a different tenant.
- **PostgreSQL Row Level Security (RLS):** Database-level security policy enforces:
  ```sql
  CREATE POLICY rls_document_chunks_tenant_isolation ON document_chunks
  USING (organization_id = NULLIF(current_setting('app.current_org_id', true), '')::uuid)
  WITH CHECK (organization_id = NULLIF(current_setting('app.current_org_id', true), '')::uuid);
  ```

### 3.2 Active Version Filtering & Supersession
Enterprise documents evolve through revisions. When version $N+1$ is uploaded:
1. `VectorRepository.deactivate_chunks_by_version(session, org_id, version_n_id)` updates $N$'s chunks to `is_active = FALSE`.
2. New chunks for version $N+1$ are inserted with `is_active = TRUE`.
3. Standard retrieval calls enforce `active_only = True`, guaranteeing that outdated facts, deprecated policies, and superseded figures are never retrieved by the RAG assistant.

---

## 4. VectorRepository API Reference

The `VectorRepository` class (`backend/app/repositories/vector_repository.py`) provides data access methods:

### 4.1 `batch_insert_chunks`
```python
async def batch_insert_chunks(
    session: AsyncSession,
    chunks: List[DocumentChunkData],
    is_active: bool = True,
) -> List[DocumentChunk]:
```
- Validates vector presence and 1536-dimensional size.
- Maps `DocumentChunkData` and `ChunkMetadata` to `DocumentChunk` ORM instances.
- Flushes the session and returns persisted records.

### 4.2 `search_vector_similarity`
```python
async def search_vector_similarity(
    session: AsyncSession,
    organization_id: uuid.UUID,
    query_embedding: List[float],
    limit: int = 10,
    similarity_threshold: float = 0.0,
    filter_document_ids: Optional[List[uuid.UUID]] = None,
    active_only: bool = True,
) -> List[ChunkSearchResult]:
```
- Computes `1.0 - embedding.cosine_distance(query_embedding)`.
- Scopes by `organization_id` and `is_active`.
- Applies optional document ID allowlist and similarity threshold cutoff.
- Returns normalized `ChunkSearchResult` objects ordered by highest similarity.

### 4.3 `search_full_text`
```python
async def search_full_text(
    session: AsyncSession,
    organization_id: uuid.UUID,
    query_text: str,
    limit: int = 10,
    filter_document_ids: Optional[List[uuid.UUID]] = None,
    active_only: bool = True,
) -> List[ChunkSearchResult]:
```
- Queries `search_vector @@ plainto_tsquery('english', query_text)`.
- Ranks results using Cover Density ranking `ts_rank_cd`.
- Scopes by tenant and active status.

---

## 5. End-to-End Ingestion Integration

The `ChunkingAndEmbeddingPipeline` in Phase 8 connects extraction, chunking, embedding, and vector persistence:

```
[UPLOADED] -> [PARSING] -> [CHUNKING] (35%) -> [EMBEDDING] (50%-75%) -> [COMPLETED] (100%)
```

When `persist_chunks=True` is passed:
1. `VectorRepository.batch_insert_chunks()` stores all chunks and embeddings.
2. `Document.status` transitions to `"COMPLETED"`.
3. `IngestionJob.status` transitions to `"COMPLETED"` and `progress_percent` reaches `100`.
4. `IngestionJob.completed_at` is stamped with the UTC completion timestamp.

---

## 6. Test Suite & Verification

The vector storage implementation was verified against the local PostgreSQL 16 + pgvector instance:

| Test File | Focus Area | Tests | Status |
|:---|:---|:---:|:---:|
| `test_vector_repository.py` | Unit: Missing vectors, invalid dimensions, empty inputs, blank queries | 5 | **PASSED** |
| `test_vector_storage.py` | Integration: Batch insert, tsvector generation, nearest-neighbor ranking, threshold cutoff, multi-tenant isolation, version supersession, full-text search, end-to-end pipeline | 6 | **PASSED** |

**Total Regression Suite:** 123 / 123 tests passing in 50.79s, 87% overall codebase coverage.
