# Changelog

All notable changes to the **Enterprise RAG AI Assistant** project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

---

## [1.0.0] - 2026-11-15

### Added
- **Core Architecture & Models**:
  - PostgreSQL 16 + pgvector 0.8.0 vector persistence with HNSW cosine indexes (`m=16`, `ef_construction=64`).
  - Strict tenant isolation using PostgreSQL Row Level Security (RLS) and composite foreign keys.
  - 11 SQLAlchemy 2.0 async ORM models covering Organizations, Departments, Users, Documents, Versions, Chunks, IngestionJobs, Conversations, Messages, Citations, and Feedback.
- **Authentication & RBAC**:
  - Multi-tenant authentication disambiguated by organization slug (`POST /api/v1/auth/login`).
  - Argon2id password hashing with isolated salts.
  - Rotating refresh token lifecycle with cryptographic reuse-breach detection.
  - 4-tier Role-Based Access Control (`SUPER_ADMIN`, `ORG_ADMIN`, `KNOWLEDGE_MANAGER`, `EMPLOYEE`).
- **Document Ingestion Pipeline**:
  - Multipart upload API accepting PDF, DOCX, and TXT documents up to 50MB.
  - Streaming SHA-256 fingerprint deduplication and magic-byte signature validation.
  - Layout-aware PDF extraction via PyMuPDF and DOCX hierarchy parsing.
  - Hierarchical recursive token-aware chunking (`tiktoken` `cl100k_base`) with Markdown table header repetition.
  - Batch embedding generation via OpenAI `text-embedding-3-small` (1536d) with exponential retry backoff and deterministic offline mocks.
- **Hybrid Retrieval & RAG Pipeline**:
  - Reciprocal Rank Fusion (RRF) merging dense cosine vector search with sparse PostgreSQL `tsvector` full-text search.
  - Server-Sent Events (SSE) streaming chat completions (`POST /api/v1/chat/completions`).
  - Verifiable bracket citation parser (`[1]`, `[2]`) mapping assistant claims to source chunks.
- **Frontend SPA**:
  - Modern React 18 + TypeScript + Vite 6 + Tailwind CSS single-page application.
  - Drag-and-drop document upload interface with progress bar and live status polling.
  - Streaming conversational chat interface with retrieval mode toggle (Hybrid vs Dense).
  - Slide-out Citation Inspector drawer displaying source document title, page number, similarity score, and exact text snippet.
  - Demo account one-click quick-fill buttons.
- **Automated Evaluation Suite**:
  - RAG triad evaluation engine computing Faithfulness / Groundedness, Answer Relevance, Context Precision (MAP), Context Recall, and Citation Accuracy.
  - Multi-domain golden benchmark dataset and CLI runner (`python -m app.evaluation.cli`).
  - 151 passing automated tests with 86% codebase test coverage.
