"""Local text embeddings via Ollama (``POST /api/embed``) — free, nothing leaves the machine.

``embed(texts)`` returns one vector per text, or ``None`` on *any* failure (embeddings
disabled, server down, model not pulled, timeout, malformed reply). Callers treat
``None`` as "no embeddings" and keep their deterministic behaviour.

Vectors are cached in process memory (LRU, :data:`CACHE_MAX_VECTORS` entries) under the
sha256 of ``model + text``, so re-analysing the same resume against the same jobs costs
no request at all. Only texts missing from the cache are sent, in batches of
:data:`BATCH_SIZE`.
"""
from __future__ import annotations

import hashlib
import logging
import math
import threading
from collections import OrderedDict
from typing import Sequence

import httpx

from app.core.config import settings

logger = logging.getLogger(__name__)

TIMEOUT_SECONDS = 30.0
BATCH_SIZE = 32
CACHE_MAX_VECTORS = 5_000
#: Longer inputs are clipped; embeddinggemma's context is 2k tokens and job posts can be long.
MAX_CHARS = 4_000

_cache: "OrderedDict[str, list[float]]" = OrderedDict()
_lock = threading.Lock()


def _key(model: str, text: str) -> str:
    return hashlib.sha256(f"{model}\x00{text}".encode("utf-8")).hexdigest()


def _cache_get(key: str) -> list[float] | None:
    with _lock:
        vector = _cache.get(key)
        if vector is not None:
            _cache.move_to_end(key)
        return vector


def _cache_put(key: str, vector: list[float]) -> None:
    with _lock:
        _cache[key] = vector
        _cache.move_to_end(key)
        while len(_cache) > CACHE_MAX_VECTORS:
            _cache.popitem(last=False)


def clear_cache() -> None:
    with _lock:
        _cache.clear()


def cache_size() -> int:
    with _lock:
        return len(_cache)


def _post(model: str, inputs: list[str], transport: httpx.BaseTransport | None) -> list[list[float]]:
    base = settings.OLLAMA_BASE_URL.rstrip("/")
    body: dict = {"model": model, "input": inputs}
    keep_alive = str(settings.OLLAMA_KEEP_ALIVE or "").strip()
    if keep_alive:
        body["keep_alive"] = int(keep_alive) if keep_alive.lstrip("-").isdigit() else keep_alive
    with httpx.Client(base_url=base, timeout=TIMEOUT_SECONDS, transport=transport) as client:
        response = client.post("/api/embed", json=body)
        response.raise_for_status()
        vectors = response.json().get("embeddings")
    if not isinstance(vectors, list) or len(vectors) != len(inputs):
        raise ValueError(f"expected {len(inputs)} embeddings, got {len(vectors) if isinstance(vectors, list) else 'none'}")
    out: list[list[float]] = []
    for vector in vectors:
        if not isinstance(vector, list) or not vector:
            raise ValueError("empty embedding in the reply")
        out.append([float(x) for x in vector])
    return out


def embed(texts: Sequence[str], *, transport: httpx.BaseTransport | None = None) -> list[list[float]] | None:
    """One vector per text (same order), or ``None`` when embeddings are unavailable."""
    if not settings.EMBEDDINGS_ENABLED:
        return None
    items = [str(t or "")[:MAX_CHARS] for t in texts]
    if not items:
        return []
    model = settings.EMBEDDING_MODEL
    keys = [_key(model, text) for text in items]
    found: dict[str, list[float]] = {}
    missing: list[tuple[str, str]] = []
    queued: set[str] = set()
    for key, text in zip(keys, items):
        if key in found or key in queued:
            continue
        vector = _cache_get(key)
        if vector is not None:
            found[key] = vector
        else:
            missing.append((key, text))
            queued.add(key)
    try:
        for start in range(0, len(missing), BATCH_SIZE):
            batch = missing[start : start + BATCH_SIZE]
            vectors = _post(model, [text for _, text in batch], transport)
            for (key, _), vector in zip(batch, vectors):
                found[key] = vector
                _cache_put(key, vector)
    except Exception as exc:  # noqa: BLE001 - any failure means "no embeddings", never an error
        logger.info("Embeddings unavailable (%s: %s); using the deterministic fallback", type(exc).__name__, exc)
        return None
    return [found[key] for key in keys]


def cosine(a: Sequence[float], b: Sequence[float]) -> float:
    """Cosine similarity; 0.0 for empty or zero vectors or mismatched lengths."""
    if not a or not b or len(a) != len(b):
        return 0.0
    dot = sum(x * y for x, y in zip(a, b))
    norm = math.sqrt(sum(x * x for x in a)) * math.sqrt(sum(y * y for y in b))
    return dot / norm if norm else 0.0


__all__ = ["cache_size", "clear_cache", "cosine", "embed"]
