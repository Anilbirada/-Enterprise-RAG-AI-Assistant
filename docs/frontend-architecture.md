# Frontend Architecture & Implementation Guide

## 1. Overview & Technology Stack

The Enterprise RAG AI Assistant frontend is a single-page application (SPA) built with modern web technologies:

- **Framework**: React 18 with TypeScript 5.6
- **Build Tool**: Vite 6.0
- **Styling**: Tailwind CSS 3.4 with custom slate/indigo enterprise theme
- **Icons**: Lucide React
- **Routing**: React Router DOM 6.28
- **Markdown & Streaming**: `react-markdown` with `remark-gfm` for rich text and tables
- **Streaming Protocol**: Server-Sent Events (SSE) via native `fetch` and `ReadableStream` (`TextDecoder`)

---

## 2. Component Hierarchy & Directory Structure

```
frontend/
├── index.html
├── package.json
├── tsconfig.json
├── vite.config.ts
├── tailwind.config.js
└── src/
    ├── main.tsx                      # Application entry point
    ├── App.tsx                       # Main router & layout configuration
    ├── index.css                     # Tailwind imports & custom scrollbar styles
    ├── types/
    │   └── index.ts                  # Shared TypeScript interfaces (User, Auth, Doc, Citation, Message)
    ├── lib/
    │   └── api.ts                    # Strongly typed API client with JWT refresh and SSE streaming
    ├── context/
    │   └── AuthContext.tsx           # Multi-tenant authentication & RBAC provider
    ├── components/
    │   ├── Navbar.tsx                # Header with org badge, role indicator, and logout
    │   ├── Sidebar.tsx               # Navigation & chat history sidebar
    │   ├── ProtectedRoute.tsx        # Route guard checking session and RBAC permissions
    │   ├── StatusBadge.tsx           # Document ingestion status pill (UPLOADED..COMPLETED..FAILED)
    │   └── CitationInspector.tsx     # Slide-over drawer for source chunk snippet verification
    └── pages/
        ├── LoginPage.tsx             # Multi-tenant login (Org slug, Email, Password)
        ├── ChatPage.tsx              # Flagship RAG assistant chat with streaming & citation pills
        └── DocumentsPage.tsx         # Document library, drag-and-drop upload, status tracker
```

---

## 3. Key Architectural Features

### 3.1 Multi-Tenant Authentication & Session Management
- **Organization Slug Context**: Authentication requires the explicit organization slug (`acme-corp`), ensuring tenant isolation before credentials reach backend RLS policies.
- **JWT Refresh Token Rotation**:
  - `ApiClient` intercepts any `401 Unauthorized` responses.
  - Automatically invokes `POST /api/v1/auth/refresh` with the persisted refresh token.
  - Transparently replays the failed request with the new access token.
- **Role-Based Access Control (RBAC)**:
  - `ProtectedRoute` enforces role boundaries (`SUPER_ADMIN`, `ORG_ADMIN`, `KNOWLEDGE_MANAGER`, `EMPLOYEE`).
  - Employees have read access to authorized documents and personal conversations, while Knowledge Managers and Admins have document upload and deletion privileges.

### 3.2 Real-Time SSE Token Streaming
- Chat completions (`POST /api/v1/chat/completions`) stream output over HTTP/1.1 or HTTP/2 using Server-Sent Events.
- `streamChatCompletion()` utilizes the native `ReadableStream` interface to process incoming chunks line-by-line:
  - `event: token`: Decodes JSON string and appends partial response token to assistant message bubble with 0ms UI lag.
  - `event: citations`: Emits source chunk metadata including document title, page number, snippet, and similarity score.
  - `event: done`: Emits final conversation and message identifiers for DB synchronization.

### 3.3 Verifiable Citation Badges & Inspector Drawer
- Assistant responses format citations with bracket notation (e.g. `[1]`, `[2]`).
- Custom Markdown paragraph renderer parses bracket patterns via regular expression:
  - Transforms `[1]` into an interactive button badge: `<button>[1]</button>`.
  - Clicking any citation badge opens the `CitationInspector` slide-over drawer.
  - The drawer highlights:
    1. **Document Title** and **File Format**.
    2. **Page Number** (e.g. `Page 4`).
    3. **Cosine / RRF Relevance Score** (e.g. `94.2%`).
    4. **Exact Extracted Passage** rendered in a clean monospace block.

### 3.4 Document Library & Ingestion Pipeline Monitoring
- **Drag-and-Drop File Upload**:
  - Validates MIME type and extensions (`.pdf`, `.docx`, `.txt`) up to 50MB.
  - Displays real-time upload progress percentage via `XMLHttpRequest.upload.onprogress`.
  - Immediate duplicate detection alerts if the file has already been ingested.
- **Status Lifecycle Tracker**:
  - Visual status badges (`UPLOADED`, `PARSING`, `CHUNKING`, `EMBEDDING`, `COMPLETED`, `FAILED`).
  - Automatic background polling every 5 seconds while documents are processing.

---

## 4. Verification & Build Artifacts

The frontend builds cleanly with zero TypeScript errors:
```bash
cd frontend
npm run build
```
Build Output:
```
✓ 1842 modules transformed.
dist/index.html                   0.80 kB │ gzip:   0.46 kB
dist/assets/index-BttiJi2V.css   24.34 kB │ gzip:   5.02 kB
dist/assets/index-dSBPLYbu.js   383.51 kB │ gzip: 118.27 kB
✓ built in 5.71s
```
