# Enterprise RAG AI Assistant - API Documentation

Base URL: `http://localhost:8000/api/v1`  
Interactive OpenAPI Swagger Docs: `http://localhost:8000/docs`

All endpoints requiring authentication mandate the header:
```http
Authorization: Bearer <access_token>
```

---

## 1. Authentication Endpoints (`/auth`)

### `POST /auth/login`
Authenticates a user scoped to their organization slug.

- **Request Body**:
  ```json
  {
    "organization_slug": "acme-corp",
    "email": "admin@acme.com",
    "password": "Password123!"
  }
  ```
- **Response** (`200 OK`):
  ```json
  {
    "access_token": "eyJhbGciOi...",
    "refresh_token": "a4f89d3...",
    "token_type": "bearer",
    "expires_in": 900
  }
  ```

### `POST /auth/refresh`
Rotates the current refresh token and issues a new access token.

- **Request Body**:
  ```json
  {
    "refresh_token": "a4f89d3..."
  }
  ```
- **Response** (`200 OK`):
  ```json
  {
    "access_token": "eyJhbGciOi...",
    "refresh_token": "b9c12e8...",
    "token_type": "bearer",
    "expires_in": 900
  }
  ```

### `POST /auth/logout`
Revokes the presented refresh token and terminates the session.

- **Request Body**:
  ```json
  {
    "refresh_token": "b9c12e8..."
  }
  ```
- **Response** (`200 OK`):
  ```json
  {
    "success": true,
    "message": "Session successfully terminated."
  }
  ```

### `GET /auth/me`
Returns the authoritative profile of the authenticated user.

- **Response** (`200 OK`):
  ```json
  {
    "id": "c4677ff0-4e54-4cf8-a547-5b879cdad795",
    "organization_id": "59d6537a-2011-4f6d-a4d9-6279f2fb6bd2",
    "department_id": "c0d5ba2f-54ed-4d13-9220-a05b5e04d278",
    "email": "admin@acme.com",
    "full_name": "Alice Admin",
    "role": "ORG_ADMIN",
    "is_active": true,
    "created_at": "2026-11-15T13:58:38.626814Z"
  }
  ```

---

## 2. Document Management Endpoints (`/documents`)

### `POST /documents/upload`
Uploads and queues a document for asynchronous parsing, chunking, and embedding.
- **Content-Type**: `multipart/form-data`
- **Permissions**: `UPLOAD_DOCUMENTS` (`ORG_ADMIN`, `KNOWLEDGE_MANAGER`, `SUPER_ADMIN`)
- **Form Fields**:
  - `file`: Binary file data (PDF, DOCX, TXT)
  - `title` *(optional)*: Custom document title
  - `department_id` *(optional)*: Department UUID ownership
- **Response** (`201 Created`):
  ```json
  {
    "document_id": "1c6c7786-e687-4b67-b8c6-76e3747ac52e",
    "version_id": "fea44dbe-0ec7-450a-b3ae-c2e27fd7bf49",
    "job_id": "07a928d1-93f8-4aee-8caa-ceea18de542e",
    "organization_id": "59d6537a-2011-4f6d-a4d9-6279f2fb6bd2",
    "title": "Acme Corporate Operations & Security Policy 2026",
    "file_name": "acme_corporate_policy_2026.pdf",
    "file_type": "PDF",
    "file_size_bytes": 3798,
    "file_hash": "2a02d9ec...",
    "status": "UPLOADED",
    "created_at": "2026-11-15T14:43:56.869777Z"
  }
  ```

### `GET /documents`
Lists documents for the user's organization with status and pagination.
- **Query Parameters**:
  - `department_id` *(optional)*: Filter by department UUID
  - `status` *(optional)*: Filter by status (`UPLOADED`, `PARSING`, `CHUNKING`, `EMBEDDING`, `COMPLETED`, `FAILED`)
  - `skip` *(default: 0)*: Pagination offset
  - `limit` *(default: 50)*: Page size

### `DELETE /documents/{id}`
Soft-deletes a document and triggers async storage key purge.
- **Permissions**: `DELETE_DOCUMENTS`

---

## 3. Search & Hybrid Retrieval Endpoints (`/search`)

### `POST /search/semantic`
Executes dense vector similarity search using OpenAI 1536-dimensional embeddings.

- **Request Body**:
  ```json
  {
    "query": "VPN remote work guidelines",
    "limit": 5,
    "similarity_threshold": 0.5
  }
  ```

### `POST /search/hybrid`
Executes hybrid retrieval combining dense cosine similarity with sparse PostgreSQL `tsvector` full-text search via Reciprocal Rank Fusion (RRF).

- **Request Body**:
  ```json
  {
    "query": "remote work VPN policy",
    "limit": 5,
    "dense_weight": 0.7,
    "sparse_weight": 0.3,
    "rrf_k": 60
  }
  ```

---

## 4. Chat & LLM Completions Endpoints (`/chat`)

### `POST /chat/conversations`
Creates a new conversation session.

- **Request Body**:
  ```json
  {
    "title": "Security Policy Inquiry"
  }
  ```

### `GET /chat/conversations`
Lists all recent conversations for the authenticated user.

### `GET /chat/conversations/{id}`
Returns conversation details with complete ordered message history and citations.

### `POST /chat/completions`
Generates a grounded RAG assistant completion with optional Server-Sent Events (SSE) token streaming.

- **Request Body**:
  ```json
  {
    "conversation_id": "d8e3b7a1-...",
    "message": "What is our policy on remote work and VPN usage?",
    "search_mode": "hybrid",
    "stream": true
  }
  ```
- **SSE Stream Events**:
  - `event: token` $\rightarrow$ `data: {"token": "All "}`
  - `event: token` $\rightarrow$ `data: {"token": "remote "}`
  - `event: citations` $\rightarrow$ `data: {"citations": [{"citation_number": 1, "document_title": "...", "page_number": 1, "snippet": "..."}]}`
  - `event: done` $\rightarrow$ `data: {"conversation_id": "...", "message_id": "...", "latency_ms": 142.5}`
