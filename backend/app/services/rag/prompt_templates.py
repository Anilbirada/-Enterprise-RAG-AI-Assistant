from typing import Any, Dict, List, Optional
from app.schemas.chunk import ChunkSearchResult

SYSTEM_PROMPT = """You are the Enterprise RAG AI Assistant, an authoritative, factual, and strictly grounded corporate intelligence agent.

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
"""


def format_rag_context(chunks: List[ChunkSearchResult]) -> str:
    """Formats retrieved chunks into numbered context blocks for prompt injection."""
    if not chunks:
        return "No relevant corporate documents found."

    context_blocks = []
    for idx, chunk in enumerate(chunks, start=1):
        page_info = f" | Page: {chunk.page_number}" if chunk.page_number else ""
        section_info = f" | Section: {chunk.section_title}" if chunk.section_title else ""
        block = (
            f"[Context Source {idx}] (Document ID: {chunk.document_id}{page_info}{section_info})\n"
            f"{chunk.content.strip()}"
        )
        context_blocks.append(block)

    return "\n\n".join(context_blocks)


def build_rag_messages(
    query: str,
    context_chunks: List[ChunkSearchResult],
    conversation_history: Optional[List[Dict[str, str]]] = None,
) -> List[Dict[str, str]]:
    """Builds chat completion message list including system prompt, history, and context-augmented user prompt."""
    messages: List[Dict[str, str]] = [
        {"role": "system", "content": SYSTEM_PROMPT}
    ]

    # Append recent conversation turns (up to last 6 messages to stay well within token bounds)
    if conversation_history:
        recent_history = conversation_history[-6:]
        for turn in recent_history:
            messages.append({"role": turn["role"].lower(), "content": turn["content"]})

    # Format the user message with explicit context injection
    formatted_context = format_rag_context(context_chunks)
    augmented_user_content = (
        f"--- CONTEXT SOURCES ---\n"
        f"{formatted_context}\n"
        f"--- END OF CONTEXT ---\n\n"
        f"USER QUESTION: {query}"
    )

    messages.append({"role": "user", "content": augmented_user_content})
    return messages
