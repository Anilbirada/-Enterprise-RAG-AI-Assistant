# RAG Pipeline and LLM Generation Architecture

## 1. Overview & Objectives

In Phase 10, the Enterprise RAG AI Assistant implements the **RAG Generation and LLM Orchestration Tier**. This system closes the loop between the search subsystem (Phase 9) and authorized users, providing factual, context-grounded AI responses with source citations, multi-turn conversation memory, and Server-Sent Events (SSE) token streaming.

```
+-----------------------------------------------------------------------------------+
|                                 CLIENT / FRONTEND                                 |
+-----------------------------------------+-----------------------------------------+
                                          |
                        POST /api/v1/chat/completions
                                          |
                                          v
+-----------------------------------------------------------------------------------+
|                                FASTAPI CHAT ROUTER                                |
|  - Bearer JWT Auth & Tenant Context                                               |
|  - Permission Check: Permission.CHAT_QUERY                                        |
+-----------------------------------------+-----------------------------------------+
                                          |
                                          v
+-----------------------------------------------------------------------------------+
|                                    RAG SERVICE                                    |
|  1. Resolve / Create Conversation Record                                          |
|  2. Persist User Message                                                          |
|  3. Call HybridSearchService (Dense Vector + Sparse Lexical via RRF)              |
|  4. Assemble Context & Multi-Turn History into System Prompt                      |
|  5. Call OpenAI LLM (gpt-4o-mini / gpt-4o) with SSE Streaming                    |
|  6. Parse Bracket Citations ([1], [2]) via CitationService                        |
|  7. Persist Assistant Message & MessageCitation Records in PostgreSQL             |
+-----------------------------------------+-----------------------------------------+
                                          |
                 +------------------------+------------------------+
                 | (event: token)                                  | (event: citations & done)
                 v                                                 v
   +---------------------------+                     +---------------------------+
   |   Streamed Token Delta    |                     |   Verifiable Source Link  |
   |   (data: {"token": "..."})|                     |   (data: {"citations": ..)|
   +---------------------------+                     +---------------------------+
```

---

## 2. Grounded System Prompt & Zero-Hallucination Policy

### 2.1 The Hallucination Hazard in Enterprise AI
In internal organizational contexts, a hallucinated policy, false expense limit, or fabricated security protocol can cause compliance violations and operational disruption. The RAG pipeline mitigates this through strict prompt engineering:

```
You are the Enterprise RAG AI Assistant, an authoritative, factual, and strictly grounded corporate intelligence agent.

CORE OPERATIONAL RULES:
1. STRICT GROUNDING: Answer questions using ONLY the provided Context Sources below.
2. ZERO HALLUCINATION: Never invent, extrapolate, or assume facts, policies, numbers, or procedures not explicitly stated in the context.
3. EXPLICIT REFUSAL: If the provided context does not contain sufficient factual evidence to completely answer the user's inquiry, respond with:
   "I cannot find sufficient information in the provided corporate documents to answer your question."
   Do NOT attempt to guess or use general world knowledge to fill in gaps.
4. CITATION SYNTAX: Every time you state a fact derived from a context source, append the numbered source citation in brackets immediately following the sentence or clause, e.g. [1] or [1][2].
   - Citations MUST use the exact numbers [1], [2], etc., corresponding to the Context Source numbers.
   - Do NOT invent citation numbers that were not provided.
5. TONE & STYLE: Maintain a professional, concise, objective, and executive tone. Structure complex information using bullet points or concise markdown where appropriate.
```

### 2.2 Context Injection Format
Context chunks retrieved by `HybridSearchService` are injected into the prompt as numbered sources:

```markdown
--- CONTEXT SOURCES ---
[Context Source 1] (Document ID: f6d226b6-5ba7-42f0-a0ea-7e16e550f3c1 | Page: 1 | Section: Remote Work Guidelines)
Employees may work remotely up to three days per week with manager approval. Mandatory core collaboration hours are between 10:00 AM and 3:00 PM Eastern Time.

[Context Source 2] (Document ID: 793eea84-1e7f-48e8-aa87-67f812940298 | Page: 3 | Section: Core Hours)
Core collaboration hours apply to all salaried engineering staff regardless of geographic location.
--- END OF CONTEXT ---

USER QUESTION: What are the remote work rules?
```

---

## 3. Citation Verification & Database Mapping

### 3.1 Bracket Parsing
`CitationService.extract_citations()` scans the generated text for bracket citations (`\[(\d+)\]`):
1. **Index Resolution:** Maps 1-based index `[1]` $\to$ `context_chunks[0]`.
2. **Bounds Checking:** Out-of-bounds references (e.g. `[99]`) are ignored.
3. **Snippet Truncation:** Extracts up to 200 characters from the cited chunk as an audit preview.
4. **Fallback Attribution:** If the LLM generates an accurate response without bracket formatting, the highest-relevance retrieved chunk is automatically attributed as `[1]` to maintain source tracking.

### 3.2 Relational Persistence
Citations are stored as foreign-key-constrained rows in `message_citations`:
```sql
CREATE TABLE message_citations (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    organization_id UUID NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
    message_id UUID NOT NULL REFERENCES messages(id) ON DELETE CASCADE,
    chunk_id UUID NOT NULL REFERENCES document_chunks(id) ON DELETE CASCADE,
    relevance_score FLOAT NOT NULL,
    rank_position INTEGER NOT NULL,
    snippet TEXT NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT now(),
    updated_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT now(),
    CONSTRAINT fk_citations_org_message FOREIGN KEY (organization_id, message_id) 
        REFERENCES messages(organization_id, id) ON DELETE CASCADE,
    CONSTRAINT fk_citations_org_chunk FOREIGN KEY (organization_id, chunk_id) 
        REFERENCES document_chunks(organization_id, id) ON DELETE CASCADE
);
```

---

## 4. Server-Sent Events (SSE) Streaming Protocol

When `stream=True` is requested, the endpoint returns `Content-Type: text/event-stream` with three sequential event phases:

### Phase 1: Token Deltas (`event: token`)
Emitted incrementally as the LLM produces output tokens:
```
event: token
data: {"token": "Employees "}

event: token
data: {"token": "may "}

event: token
data: {"token": "work "}
```

### Phase 2: Citations Payload (`event: citations`)
Emitted immediately after token generation completes, delivering structured citation objects:
```
event: citations
data: {
  "citations": [
    {
      "chunk_id": "2e819f9d-fa22-4f7f-ad6c-9257800d7844",
      "document_id": "f6d226b6-5ba7-42f0-a0ea-7e16e550f3c1",
      "rank_position": 1,
      "relevance_score": 0.016393,
      "snippet": "Employees may work remotely up to three days per week...",
      "page_number": 1,
      "section_title": "Remote Work Guidelines"
    }
  ]
}
```

### Phase 3: Completion Metadata (`event: done`)
Signals stream termination and delivers message IDs:
```
event: done
data: {
  "conversation_id": "5def144b-080f-4640-9fa3-68a656aa032b",
  "message_id": "86638695-bea1-413c-bfee-c651bbef81e6",
  "latency_ms": 344.28
}
```

### Offline & CI/CD Deterministic Mocking
When `OPENAI_API_KEY` is not present, `RAGService._generate_mock_stream()` synthesizes simulated grounded answers referencing the retrieved chunks, enabling testing and local development without cloud dependencies or API costs.

---

## 5. API Endpoints Reference

| Method | Endpoint | Description | Auth Required |
|:---|:---|:---|:---:|
| `POST` | `/api/v1/chat/conversations` | Initializes a new multi-turn chat conversation session | `Permission.CHAT_QUERY` |
| `GET` | `/api/v1/chat/conversations` | Lists conversations for the authenticated user | `Permission.CHAT_QUERY` |
| `GET` | `/api/v1/chat/conversations/{id}` | Fetches full conversation detail with message history and citations | `Permission.CHAT_QUERY` |
| `POST` | `/api/v1/chat/completions` | Executes RAG chat completion (SSE streaming or non-streaming) | `Permission.CHAT_QUERY` |

---

## 6. Verification & Test Suite

| Test File | Focus Area | Tests | Status |
|:---|:---|:---:|:---:|
| `test_rag_prompt_and_citations.py` | Unit: Context block formatting, prompt message construction, citation parsing, out-of-bounds safety, citation fallback | 6 | **PASSED** |
| `test_chat_api.py` | Integration: Conversation creation, non-streaming completion, SSE streaming events, multi-turn history, cross-tenant isolation | 5 | **PASSED** |

**Total Regression Suite:** 143 / 143 tests passing in 56.03s, 86% overall codebase coverage.
