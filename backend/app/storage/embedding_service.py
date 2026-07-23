"""
EmbeddingService — local embedding via Ollama API

Replaces Zep Cloud's built-in embedding with local nomic-embed-text model.
Uses Ollama's /api/embed endpoint for vector generation (768 dimensions).
"""

import time
import logging
from typing import List, Optional
from functools import lru_cache

import requests

from ..config import Config

logger = logging.getLogger('writegod.embedding')


class EmbeddingService:
    """Generate embeddings using local Ollama server."""

    def __init__(
        self,
        model: Optional[str] = None,
        base_url: Optional[str] = None,
        max_retries: int = 3,
        timeout: int = 15,
    ):
        self.model = model or Config.EMBEDDING_MODEL_NAME
        self.base_url = (base_url or Config.EMBEDDING_BASE_URL).rstrip('/')
        self.max_retries = max_retries
        self.timeout = timeout
        if "11434" in (self.base_url or "") or "ollama" in (self.base_url or "").lower():
            self._embed_url = self.base_url + "/api/embed"
        else:
            self._embed_url = self.base_url + "/embeddings"

        # Simple in-memory cache (text -> embedding vector)
        # Using dict instead of lru_cache because lists aren't hashable
        self._cache: dict[str, List[float]] = {}
        self._cache_max_size = 2000

    def embed(self, text: str) -> List[float]:
        """
        Generate embedding for a single text.

        Args:
            text: Input text to embed

        Returns:
            768-dimensional float vector

        Raises:
            EmbeddingError: If Ollama request fails after retries
        """
        if not text or not text.strip():
            raise EmbeddingError("Cannot embed empty text")

        text = text.strip()

        # Check cache
        if text in self._cache:
            return self._cache[text]

        vectors = self._request_embeddings([text])
        vector = vectors[0]

        # Cache result
        self._cache_put(text, vector)

        return vector

    def embed_batch(self, texts: List[str], batch_size: int = 128) -> List[List[float]]:
        """Generate embeddings for multiple texts. Uses concurrent requests."""
        if not texts:
            return []

        results: List[Optional[List[float]]] = [None] * len(texts)
        uncached_indices: List[int] = []
        uncached_texts: List[str] = []

        # Check cache first
        for i, text in enumerate(texts):
            text = text.strip() if text else ""
            if text in self._cache:
                results[i] = self._cache[text]
            elif text:
                uncached_indices.append(i)
                uncached_texts.append(text)
            else:
                # Empty text — zero vector
                results[i] = [0.0] * 768

        # Batch-embed uncached texts with concurrent requests
        if uncached_texts:
            from concurrent.futures import ThreadPoolExecutor, as_completed
            all_results: dict[int, List[List[float]]] = {}
            
            def process_batch(start_idx, batch):
                return start_idx, self._request_embeddings(batch)
            
            batches = [(i, uncached_texts[i:i+batch_size]) for i in range(0, len(uncached_texts), batch_size)]
            
            with ThreadPoolExecutor(max_workers=4) as executor:
                futures = [executor.submit(process_batch, i, batch) for i, batch in batches]
                for future in as_completed(futures):
                    start_idx, vectors = future.result()
                    all_results[start_idx] = vectors
            
            # Reassemble in order
            all_vectors: List[List[float]] = []
            for i, _ in batches:
                all_vectors.extend(all_results.get(i, []))

            # Place results and cache
            for idx, vec, text in zip(uncached_indices, all_vectors, uncached_texts):
                results[idx] = vec
                self._cache_put(text, vec)

        return results  # type: ignore

    def _request_embeddings(self, texts: List[str]) -> List[List[float]]:
        """
        Make HTTP request to Ollama /api/embed endpoint with retry.

        Args:
            texts: List of texts to embed (Ollama supports batch in single request)

        Returns:
            List of embedding vectors
        """
        payload = {
            "model": self.model,
            "input": texts,
        }

        last_error = None
        for attempt in range(self.max_retries):
            try:
                headers = {}
                if "11434" not in (self.base_url or "") and "ollama" not in (self.base_url or "").lower():
                    ak = Config.EMBEDDING_API_KEY or Config.LLM_API_KEY or ""
                    headers["Authorization"] = f"Bearer {ak}"
                response = requests.post(
                    self._embed_url,
                    json=payload,
                    headers=headers,
                    timeout=self.timeout,
                )
                response.raise_for_status()
                data = response.json()

                if "/api/embed" in self._embed_url:
                    embeddings = data.get("embeddings", [])
                else:
                    embeddings = [x["embedding"] for x in data.get("data", [])]
                if len(embeddings) != len(texts):
                    raise EmbeddingError(
                        f"Expected {len(texts)} embeddings, got {len(embeddings)}"
                    )

                return embeddings

            except requests.exceptions.ConnectionError as e:
                last_error = e
                logger.warning(
                    f"Embedding connection failed (attempt {attempt + 1}/{self.max_retries}): {e}"
                )
            except requests.exceptions.Timeout as e:
                last_error = e
                logger.warning(
                    f"Embedding request timed out (attempt {attempt + 1}/{self.max_retries})"
                )
            except requests.exceptions.HTTPError as e:
                last_error = e
                logger.error(f"Embedding HTTP error: {e.response.status_code} - {e.response.text}")
                if e.response.status_code >= 500:
                    # Server error — retry
                    pass
                else:
                    # Client error (4xx) — don't retry
                    raise EmbeddingError(f"Embedding failed: {e}") from e
            except (KeyError, ValueError) as e:
                raise EmbeddingError(f"Invalid Ollama response: {e}") from e

            # Exponential backoff
            if attempt < self.max_retries - 1:
                wait = 2 ** attempt
                logger.info(f"Retrying in {wait}s...")
                time.sleep(wait)

        raise EmbeddingError(
            f"Embedding failed after {self.max_retries} retries: {last_error}"
        )

    def _cache_put(self, text: str, vector: List[float]) -> None:
        """Add to cache, evicting oldest entries if full."""
        if len(self._cache) >= self._cache_max_size:
            # Remove ~10% of oldest entries
            keys_to_remove = list(self._cache.keys())[:self._cache_max_size // 10]
            for key in keys_to_remove:
                del self._cache[key]
        self._cache[text] = vector

    def health_check(self) -> bool:
        """Check if Ollama embedding endpoint is reachable."""
        try:
            vec = self.embed("health check")
            return len(vec) > 0
        except Exception:
            return False


class EmbeddingError(Exception):
    """Raised when embedding generation fails."""
    pass
