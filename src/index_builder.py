"""Build or load TF-IDF and FAISS indexes with on-disk caching."""

from __future__ import annotations

import time
from pathlib import Path
from typing import Any

from src.config import (
    EMBEDDINGS_CACHE,
    FAISS_INDEX_BASE,
    MATCHER_INDEX_DIR,
    TFIDF_CACHE_FILE,
)
from src.matcher import ProductMatcher


def _faiss_cache_ready() -> bool:
    return FAISS_INDEX_BASE.with_suffix(".faiss").exists() and Path(
        f"{FAISS_INDEX_BASE}_meta.joblib"
    ).exists()


def build_or_load_tfidf(matcher: ProductMatcher, df_barcoded: Any, *, rebuild: bool) -> str:
    """Fit or restore the TF-IDF index. Returns a human-readable status message."""
    MATCHER_INDEX_DIR.mkdir(parents=True, exist_ok=True)

    if not rebuild and TFIDF_CACHE_FILE.exists():
        try:
            matcher.tfidf.load(str(TFIDF_CACHE_FILE))
            return "Loaded TF-IDF from cache"
        except Exception as exc:
            print(f"  ⚠ Cache load failed ({exc}) — rebuilding…")

    build_start = time.perf_counter()
    matcher.tfidf.fit(df_barcoded)
    matcher.tfidf.save(str(TFIDF_CACHE_FILE))
    elapsed = time.perf_counter() - build_start
    return f"Built TF-IDF index in {elapsed:.1f}s"


def build_or_load_faiss(matcher: ProductMatcher, df_barcoded: Any, *, rebuild: bool) -> str:
    """Fit or restore the FAISS embedding index. Returns a human-readable status message."""
    MATCHER_INDEX_DIR.mkdir(parents=True, exist_ok=True)

    if not rebuild and _faiss_cache_ready():
        try:
            matcher.embedder.load_index(str(FAISS_INDEX_BASE))
            matcher._built = True
            return "Loaded FAISS from cache"
        except Exception as exc:
            print(f"  ⚠ Cache load failed ({exc}) — rebuilding…")

    build_start = time.perf_counter()
    matcher.embedder.build_faiss_index(df_barcoded, embeddings_path=str(EMBEDDINGS_CACHE))
    matcher.embedder.save_index(str(FAISS_INDEX_BASE))
    matcher._built = True
    elapsed = time.perf_counter() - build_start
    return f"Built FAISS index in {elapsed:.1f}s"
