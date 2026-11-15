import asyncio
import hashlib
import logging
import math
import random
from typing import List, Optional, Tuple
from openai import AsyncOpenAI, RateLimitError, APIConnectionError, InternalServerError

from app.core.config import get_settings
from app.core.exceptions import ExternalServiceException, ValidationException
from app.schemas.chunk import DocumentChunkData, EmbeddingBatchResult

logger = logging.getLogger("enterprise_rag.embedding_service")


class EmbeddingService:
    """Asynchronous batch embedding service for OpenAI text-embedding-3-small with retry and validation."""

    def __init__(
        self,
        api_key: Optional[str] = None,
        model: Optional[str] = None,
        dimensions: Optional[int] = None,
        batch_size: Optional[int] = None,
        max_retries: Optional[int] = None,
    ) -> None:
        settings = get_settings()
        self.api_key = api_key or settings.OPENAI_API_KEY
        self.model = model or settings.EMBEDDING_MODEL
        self.dimensions = dimensions or settings.EMBEDDING_DIMENSION
        self.batch_size = batch_size or settings.EMBEDDING_BATCH_SIZE
        self.max_retries = max_retries or settings.EMBEDDING_MAX_RETRIES

        self.client = AsyncOpenAI(api_key=self.api_key) if self.api_key else None

    def _generate_mock_vector(self, text: str) -> List[float]:
        """Generates a deterministic, normalized 1536-dimensional float vector for tests/offline dev."""
        # Use SHA-256 hash seeds to produce reproducible unit-normalized vectors
        hash_digest = hashlib.sha256(text.encode("utf-8")).digest()
        seed = int.from_bytes(hash_digest[:4], "big")
        rng = random.Random(seed)

        raw_values = [rng.gauss(0, 1) for _ in range(self.dimensions)]
        norm = math.sqrt(sum(v * v for v in raw_values))
        return [v / norm for v in raw_values]

    def validate_vector(self, vector: List[float], chunk_index: int) -> None:
        """Validates dimension count and absence of NaN / Inf values."""
        if not vector or len(vector) != self.dimensions:
            raise ValidationException(
                f"Embedding vector dimension mismatch for chunk {chunk_index}: "
                f"expected {self.dimensions}, got {len(vector) if vector else 0}."
            )

        for val in vector:
            if math.isnan(val) or math.isinf(val):
                raise ValidationException(
                    f"Invalid floating point value (NaN or Inf) detected in embedding vector for chunk {chunk_index}."
                )

    async def _embed_batch_with_retry(self, texts: List[str]) -> Tuple[List[List[float]], int]:
        """Executes a single batch call to OpenAI with exponential backoff and jitter."""
        if not texts:
            return [], 0

        # If no API key configured, use deterministic mock vectors (enables offline development & testing)
        if not self.client:
            logger.debug(f"OpenAI API key not set; generating {len(texts)} deterministic mock vectors.")
            return [self._generate_mock_vector(t) for t in texts], sum(len(t.split()) for t in texts)

        attempt = 0
        while attempt < self.max_retries:
            try:
                response = await self.client.embeddings.create(
                    input=texts,
                    model=self.model,
                    dimensions=self.dimensions,
                )
                embeddings = [item.embedding for item in response.data]
                tokens_used = response.usage.total_tokens if response.usage else 0
                return embeddings, tokens_used

            except (RateLimitError, APIConnectionError, InternalServerError) as retryable_err:
                attempt += 1
                if attempt >= self.max_retries:
                    logger.error(f"OpenAI embedding batch failed after {attempt} retries: {retryable_err}")
                    raise ExternalServiceException("OpenAI Embeddings API", str(retryable_err))

                backoff_time = (2 ** attempt) + random.uniform(0.1, 0.5)
                logger.warning(
                    f"Transient error from OpenAI API ({retryable_err.__class__.__name__}): "
                    f"retrying attempt {attempt}/{self.max_retries} in {backoff_time:.2f}s..."
                )
                await asyncio.sleep(backoff_time)

            except Exception as non_retryable_err:
                logger.error(f"Non-retryable error from OpenAI embedding API: {non_retryable_err}")
                raise ExternalServiceException("OpenAI Embeddings API", str(non_retryable_err))

        raise ExternalServiceException("OpenAI Embeddings API", "Maximum retry limit exceeded.")

    async def generate_embeddings_for_texts(self, texts: List[str]) -> EmbeddingBatchResult:
        """Processes an arbitrary list of texts into embedding vectors in batches."""
        if not texts:
            return EmbeddingBatchResult(
                embeddings=[],
                total_tokens_consumed=0,
                model=self.model,
                dimension=self.dimensions,
            )

        all_embeddings: List[List[float]] = []
        total_tokens = 0

        # Batch texts to respect OpenAI limits
        for i in range(0, len(texts), self.batch_size):
            batch = texts[i : i + self.batch_size]
            batch_vectors, tokens = await self._embed_batch_with_retry(batch)
            all_embeddings.extend(batch_vectors)
            total_tokens += tokens

        # Validate all returned vectors
        for idx, vec in enumerate(all_embeddings):
            self.validate_vector(vec, idx)

        return EmbeddingBatchResult(
            embeddings=all_embeddings,
            total_tokens_consumed=total_tokens,
            model=self.model,
            dimension=self.dimensions,
        )

    async def embed_chunks(self, chunks: List[DocumentChunkData]) -> List[DocumentChunkData]:
        """Generates and attaches embedding vectors to each chunk in-place."""
        if not chunks:
            return []

        texts = [c.content for c in chunks]
        result = await self.generate_embeddings_for_texts(texts)

        for chunk, embedding in zip(chunks, result.embeddings):
            chunk.embedding = embedding

        logger.info(
            f"Successfully embedded {len(chunks)} chunks with model '{self.model}' "
            f"({result.total_tokens_consumed} tokens consumed)"
        )
        return chunks
