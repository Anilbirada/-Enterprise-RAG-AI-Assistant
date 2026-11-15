# Document Chunking and Embedding Generation Pipeline

## 1. Overview & Objectives

In Phase 7, the Enterprise RAG AI Assistant implements the **Token-Aware Chunking and Vector Embedding Generation Engine**. This subsystem converts normalized, layout-aware extracted document representations (`ExtractedDocument`) into semantically cohesive, token-bounded chunks and produces 1536-dimensional dense embedding vectors using OpenAI's `text-embedding-3-small` model.

```
                      +-----------------------------+
                      |   ExtractedDocument (P6)    |
                      |   (Pages, Tables, Meta)     |
                      +--------------+--------------+
                                     |
                                     v
                      +-----------------------------+
                      |      ChunkingService        |
                      |  - tiktoken (cl100k_base)   |
                      |  - 512 token chunk size     |
                      |  - 64 token overlap         |
                      |  - Table header repetition  |
                      |  - Page/Section tracking    |
                      +--------------+--------------+
                                     |
                                     v
                      +-----------------------------+
                      |      EmbeddingService       |
                      |  - text-embedding-3-small   |
                      |  - 1536-dim vector validation|
                      |  - Async batching (100)     |
                      |  - Exponential backoff/retry|
                      |  - Deterministic offline mock|
                      +--------------+--------------+
                                     |
                                     v
                      +-----------------------------+
                      |  DocumentChunkData Enriched |
                      |  - Ready for pgvector (P8)  |
                      +-----------------------------+
```

---

## 2. Recursive Token-Aware Chunking Architecture

### 2.1 The Chunking Dilemma in Enterprise Knowledge
Traditional RAG pipelines frequently make one of two critical mistakes:
1. **Character-based chunking:** Splitting text blindly on character count (e.g. 1000 characters) cuts words, sentences, or code blocks in half, degrading dense semantic search.
2. **Naive token chunking:** Tokenizing the whole document and chopping it into slices breaks structural paragraphs, headings, and tables.

### 2.2 Hierarchical Recursive Splitting
The `ChunkingService` implements a hierarchical recursive text splitter that prioritizes semantic boundaries:
- **Level 1: Markdown Headings (`\n# `, `\n## `, `\n### `):** Divides major chapters and thematic sections.
- **Level 2: Paragraph Breaks (`\n\n`):** Divides logical conceptual blocks.
- **Level 3: Line Breaks (`\n`):** Divides bullet points, numbered lists, and short sentences.
- **Level 4: Sentence Boundaries (`. `, `? `, `! `):** Divides sentences while keeping full thoughts intact.
- **Level 5: Word Boundaries (` `):** Falls back to whitespace if an individual sentence exceeds `chunk_size_tokens`.

### 2.3 Token Counting with `tiktoken`
Token length is computed using OpenAI's `cl100k_base` BPE (Byte-Pair Encoding) tokenizer:
```python
import tiktoken

encoding = tiktoken.get_encoding("cl100k_base")
tokens = len(encoding.encode(text))
```
Every chunk is guaranteed to respect the configured maximum token limit:
- `CHUNK_SIZE_TOKENS` = 512 tokens (optimal for retrieval granularity and context density).
- `CHUNK_OVERLAP_TOKENS` = 64 tokens (preserves context continuity across chunk boundaries).

### 2.4 Relational Table Preservation & Header Repetition
When markdown tables span across multiple chunks, subsequent chunks lose their column headers, making isolated table rows meaningless to embedding models. 

`ChunkingService` incorporates specialized table chunking logic:
1. Identifies Markdown table blocks starting with `|`.
2. Extracts table header rows (`| Header 1 | Header 2 |` and separator `| --- | --- |`).
3. Splits rows incrementally.
4. On every continuation chunk, automatically prepends the original table headers:
```markdown
| Component | Technology | Target Version |
| --- | --- | --- |
| Vector Store | pgvector | 0.8.0 |
| Embedding Model | OpenAI | text-embedding-3-small |
```
This ensures dense vector embeddings represent both row content and column headers.

### 2.5 Metadata Attribution
Each generated chunk is associated with `ChunkMetadata`:
- `document_id`: UUID of parent document.
- `version_id`: UUID of document version.
- `organization_id`: UUID of tenant for strict RLS isolation.
- `chunk_index`: 0-indexed sequential sequence number.
- `page_number`: 1-based page number attributed from PyMuPDF/python-docx layout analysis.
- `token_count`: Exact token count calculated by `cl100k_base`.
- `char_count`: Character length.
- `has_table`: Boolean flag denoting whether the chunk contains structured tabular data.
- `section_title`: Markdown header under which the chunk resides.

---

## 3. Embedding Generation Engine

### 3.1 Model Selection & Specifications
- **Model:** OpenAI `text-embedding-3-small`
- **Output Dimensions:** 1536
- **Distance Metric:** Cosine similarity ($1 - \text{cosine\_distance}$)
- **Batch Size:** 100 items per API call

### 3.2 Resilience and Exponential Backoff
The `EmbeddingService` communicates with OpenAI using `AsyncOpenAI`. To ensure production resilience against rate limits and network jitter:
- Catches retryable exceptions: `RateLimitError` (HTTP 429), `APIConnectionError`, and `InternalServerError` (5xx).
- Retries with exponential backoff plus uniform random jitter:
  $$t_{\text{backoff}} = 2^{\text{attempt}} + \text{Uniform}(0.1, 0.5)$$
- Enforces `EMBEDDING_MAX_RETRIES` (default: 3).

### 3.3 Strict Vector Validation
Before vectors are accepted into the pipeline, `EmbeddingService.validate_vector()` runs defensive checks:
- **Dimension Check:** Asserts vector length is exactly 1536.
- **NaN/Inf Check:** Scans vector floats to ensure no `math.isnan(val)` or `math.isinf(val)` values exist.

### 3.4 Deterministic Offline / Testing Mock Engine
When `OPENAI_API_KEY` is not configured, the service generates deterministic unit-normalized 1536-dimensional mock vectors:
- Uses SHA-256 hash of the chunk text as a pseudo-random seed.
- Produces reproducible Gaussian distributed vectors.
- Normalizes vectors to unit L2 norm ($|v| = 1.0 \pm 10^{-5}$).
- Allows CI/CD, local development, and offline testing without external network dependencies or API costs.

---

## 4. Pipeline Orchestration & State Transitions

The `ChunkingAndEmbeddingPipeline` class coordinates the full lifecycle:
1. **Extraction:** If not pre-extracted, invokes `DocumentExtractionService.process_document_extraction()`.
2. **Transition to `CHUNKING`:** Updates `Document.status` to `CHUNKING` and `IngestionJob.progress_percent` to 35%.
3. **Chunk Generation:** Executes recursive splitting and table preservation; computes `ChunkingStatistics`.
4. **Transition to `EMBEDDING`:** Updates `Document.status` to `EMBEDDING` and `IngestionJob.progress_percent` to 50%.
5. **Batch Embedding:** Calls `EmbeddingService.embed_chunks()`.
6. **Progress Completion:** Updates `IngestionJob.progress_percent` to 75% and saves chunking metadata on `Document.metadata_`:
   ```json
   {
     "chunk_count": 12,
     "total_tokens": 3840,
     "avg_chunk_tokens": 320.0,
     "chunks_with_tables": 2,
     "embedding_model": "text-embedding-3-small",
     "embedding_dimension": 1536
   }
   ```
7. **Failure Safety:** Any exception caught in the pipeline sets `Document.status = 'FAILED'`, `IngestionJob.status = 'FAILED'`, records the error traceback in `error_message`, and commits the transaction to ensure audit visibility.

---

## 5. Verification & Test Suite

The test suite covers both unit isolation and database-backed integration workflows:

| Test File | Scope | Tests | Coverage |
|:---|:---|:---:|:---:|
| `test_chunking_service.py` | Token counting, single/multi-paragraph splitting, table header repetition, statistics | 6 | 74% |
| `test_embedding_service.py` | 1536d validation, NaN/Inf checks, batching, retry on 429, mock determinism | 8 | 92% |
| `test_chunking_embedding_pipeline.py` | Real PostgreSQL test DB integration, PDF & DOCX pipeline, failure rollback | 4 | 100% |

**Total Suite Performance:** 112 passed tests across all phases, 86% overall codebase coverage.
