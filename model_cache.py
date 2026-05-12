from __future__ import annotations

import logging
from typing import Optional

from chromadb.utils.embedding_functions import SentenceTransformerEmbeddingFunction

LOGGER = logging.getLogger("viernes.model_cache")

_embedding_fn: Optional[SentenceTransformerEmbeddingFunction] = None
_embedding_model_name: Optional[str] = None


def get_embedding_function(model_name: str = "all-MiniLM-L6-v2") -> SentenceTransformerEmbeddingFunction:
    global _embedding_fn, _embedding_model_name

    if _embedding_fn is None or _embedding_model_name != model_name:
        LOGGER.info(f"Cargando modelo de embeddings: {model_name}")
        _embedding_fn = SentenceTransformerEmbeddingFunction(model_name=model_name)
        _embedding_model_name = model_name
        LOGGER.info("Modelo de embeddings cargado y cacheado")
    else:
        LOGGER.info("Usando modelo de embeddings desde cache")

    return _embedding_fn


def clear_cache():
    global _embedding_fn, _embedding_model_name
    _embedding_fn = None
    _embedding_model_name = None
    LOGGER.info("Cache de modelos limpiado")