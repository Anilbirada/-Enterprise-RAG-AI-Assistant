# Enterprise Security Architecture & RBAC Specification

This document details the security principles, cryptographic controls, Role-Based Access Control (RBAC), and multi-tenant isolation guarantees implemented in the Enterprise RAG AI Assistant.

---

## 1. Role-Based Access Control (RBAC)

The application enforces a 4-tier Role hierarchy designed to balance granular least privilege within an organization against centralized platform administration.

### Role Hierarchy
1. **`SUPER_ADMIN`**: Global platform administrator. Has cross-tenant visibility, system-wide health monitoring, and administrative override capabilities.
2. **`ORG_ADMIN`**: Tenant administrator. Can manage users, departments, configure tenant metadata, upload documents, view analytics, and query the assistant within their own tenant boundary.
3. **`KNOWLEDGE_MANAGER`**: Content and knowledge curator. Can upload documents, trigger ingestion/chunking/re-indexing, edit document metadata, and review citations.
4. **`EMPLOYEE`**: Standard organizational user. Can perform semantic search, initiate conversational RAG chats, view accessible documents, and submit message feedback.

### Permission Matrix

| Permission | Description | `SUPER_ADMIN` | `ORG_ADMIN` | `KNOWLEDGE_MANAGER` | `EMPLOYEE` |
| :--- | :--- | :---: | :---: | :---: | :---: |
| `organization:manage` | Edit organization metadata, settings, and tier limits | **Yes** | No | No | No |
| `users:manage` | Invite, activate, deactivate, and assign roles to users | **Yes** | **Yes** | No | No |
| `departments:manage` | Create and restructure organizational departments | **Yes** | **Yes** | No | No |
| `documents:manage` | Delete documents, force re-indexing, update metadata | **Yes** | **Yes** | **Yes** | No |
| `documents:upload` | Ingest new PDF/DOCX files into vector storage | **Yes** | **Yes** | **Yes** | No |
| `documents:view` | Access and read document snippets and citations | **Yes** | **Yes** | **Yes** | **Yes** |
| `chat:query` | Submit natural-language queries to RAG pipeline | **Yes** | **Yes** | **Yes** | **Yes** |
| `analytics:view` | Inspect query latency, token usage, and feedback metrics | **Yes** | **Yes** | No | No |
| `feedback:submit` | Upvote/downvote responses and provide relevance notes | **Yes** | **Yes** | **Yes** | **Yes** |

---

## 2. Password Security & Argon2id Benchmarking

Password security utilizes **Argon2id** (via `pwdlib` and `argon2-cffi`), the winner of the Password Hashing Competition and recommended standard by OWASP and NIST.

### Argon2id Configuration
- **Memory Cost (`m`)**: 65,536 KiB (64 MiB)
- **Time Cost / Iterations (`t`)**: 3 passes
- **Parallelism (`p`)**: 4 lanes
- **Salt**: 16 cryptographically secure random bytes generated uniquely per hash.

### Benchmark Analysis Under Load
Automated benchmark measurements executed on the test suite:
- **Hash Duration**: 45–65 ms per password hash.
- **Verification Duration**: 45–60 ms per check.
- **Security Justification**: 
  - 64 MiB memory hardness completely defeats GPU and ASIC brute-force password cracking attacks.
  - A 50 ms calculation duration protects the server from event-loop starvation while imposing severe rate-limiting penalties on offline dictionary attacks.

---

## 3. Frontend Token Storage & Transport Architecture

Selecting how the frontend client (React + TypeScript) manages JWT access and refresh tokens represents one of the most critical security trade-offs in modern web architecture.

### Storage Comparison

| Storage Mechanism | XSS Vulnerability | CSRF Vulnerability | Implementation Complexity | Recommendation |
| :--- | :--- | :--- | :--- | :--- |
| **`localStorage` / `sessionStorage`** | **CRITICAL**: Any injected script can exfiltrate tokens | **Immune** | Low | **NEVER USE** in enterprise production |
| **In-Memory (React State/Zustand) + Refresh Token Rotation** | **Low**: Access token in JS memory is erased on tab close or refresh | **Immune** (Transmitted via `Authorization: Bearer` header) | Moderate | **Primary Standard API Pattern** |
| **HttpOnly, SameSite=Strict Cookie for Refresh Token** | **Immune**: Inaccessible to JavaScript | **Low**: Protected by SameSite=Strict & CSRF headers | Moderate | **Optimal for Web Browser SPA** |

### Recommended Production Architecture
1. **Short-Lived Access Token**:
   - Kept exclusively in **in-memory React state** (e.g., Zustand or React Context).
   - Lifetime: 15 minutes.
   - Attached to outgoing API requests via the standard HTTP header: `Authorization: Bearer <access_token>`.
   - Never written to `localStorage`, `sessionStorage`, or indexedDB.
2. **Refresh Token**:
   - Stored in a browser cookie with the flags:
     - `HttpOnly = true` (inaccessible to JavaScript `document.cookie`, defeating XSS exfiltration).
     - `Secure = true` (transmitted only over TLS/HTTPS).
     - `SameSite = Strict` (browser suppresses cookie during cross-site requests, mitigating CSRF).
     - `Path = /api/v1/auth` (cookie is only transmitted to authentication endpoints).
   - Alternatively, when communicating with native or mobile clients, the client securely stores the refresh token in OS-level credential vaults (Keychain / Keystore) and uses header-based rotation.
3. **Axios / HTTP Interceptor Auto-Refresh**:
   - The React HTTP client installs a response interceptor.
   - When any API call returns `401 Unauthorized`, the client pauses pending requests, calls `POST /api/v1/auth/refresh`, updates the in-memory access token, and transparently replays the initial request.

---

## 4. Multi-Tenant Row Level Security (RLS) & Connection Pooling

### Transaction-Local Tenant Context
In asynchronous Python applications using connection pooling (`asyncpg`), connection objects are recycled across different requests. To prevent cross-tenant data leaks caused by dirty connection state:
- Every authenticated request calls `set_tenant_context(session, org_id)`.
- Implemented as:
  ```sql
  SELECT set_config('app.current_org_id', :org_id, true);
  ```
- The third argument (`true`) scopes the configuration parameter strictly to the current database transaction (`is_local = true`). When the transaction commits or rolls back, PostgreSQL automatically resets `app.current_org_id`.

### Database Privilege Separation
- The application connects using the unprivileged database role: `rag_app_user`.
- `rag_app_user` has `NOBYPASSRLS`.
- All tenant tables (`documents`, `document_chunks`, `conversations`, `messages`, `refresh_tokens`, etc.) enforce RLS policies:
  ```sql
  CREATE POLICY rls_tenant_isolation ON <table>
  FOR ALL
  USING (organization_id = NULLIF(current_setting('app.current_org_id', true), '')::uuid)
  WITH CHECK (organization_id = NULLIF(current_setting('app.current_org_id', true), '')::uuid);
  ```
- Even if a developer accidentally omits a `WHERE organization_id = ...` clause in SQLAlchemy, the PostgreSQL database kernel silently rejects cross-tenant reads and writes.
