"""Stage 2 reranker: multilingual sentence embeddings with FAISS vector search."""

from __future__ import annotations

import logging
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

import faiss
import joblib
import numpy as np
import pandas as pd
from sentence_transformers import SentenceTransformer

from src.confidence import HIGH_THRESHOLD, MEDIUM_THRESHOLD
from src.preprocess import extract_brand, extract_weight

logger = logging.getLogger(__name__)

DEFAULT_MODEL = "paraphrase-multilingual-MiniLM-L12-v2"
DEFAULT_EMBEDDINGS_PATH = "data/reference_embeddings.npy"


class EmbeddingReranker:
    """Multilingual embedding reranker for the barcoded reference catalogue.

    Stage 2 of the pipeline: takes TF-IDF candidates (or direct FAISS search)
    and reranks by semantic similarity using ``paraphrase-multilingual-MiniLM-L12-v2``.
    """

    def __init__(self, model_name: str = DEFAULT_MODEL) -> None:
        """Load the SentenceTransformer model.

        Args:
            model_name: HuggingFace model identifier for sentence embeddings.
        """
        logger.info("Loading SentenceTransformer model: %s", model_name)
        load_start = time.perf_counter()
        self.model = SentenceTransformer(model_name)
        load_elapsed = time.perf_counter() - load_start
        logger.info("Model loaded in %.2fs", load_elapsed)

        self.model_name = model_name
        self.embeddings: Optional[np.ndarray] = None
        self.index: Optional[faiss.IndexFlatIP] = None
        self.reference_df: Optional[pd.DataFrame] = None

    def encode(self, texts: List[str], show_progress_bar: bool = True) -> np.ndarray:
        """Encode texts into unit-normalised embedding vectors.

        Args:
            texts: Product names to encode (typically ``name_clean`` values).
            show_progress_bar: Whether to display a tqdm progress bar.

        Returns:
            Float32 array of shape ``(len(texts), embedding_dim)`` with L2
            unit-normalised rows suitable for inner-product cosine search.
        """
        if not texts:
            return np.empty((0, self.model.get_sentence_embedding_dimension()), dtype=np.float32)

        logger.info("Encoding %s texts", f"{len(texts):,}")
        vectors = self.model.encode(
            texts,
            batch_size=256,
            show_progress_bar=show_progress_bar,
            normalize_embeddings=True,
            convert_to_numpy=True,
        )
        return np.asarray(vectors, dtype=np.float32)

    @staticmethod
    def _ensure_unit_norm(embeddings: np.ndarray) -> np.ndarray:
        """L2-normalise embedding rows so inner product equals cosine similarity."""
        norms = np.linalg.norm(embeddings, axis=1, keepdims=True)
        norms = np.where(norms == 0, 1.0, norms)
        return (embeddings / norms).astype(np.float32)

    def save_embeddings(self, path: str) -> None:
        """Persist the reference embedding matrix to disk.

        Args:
            path: Destination ``.npy`` file path.

        Raises:
            RuntimeError: If embeddings have not been computed yet.
        """
        if self.embeddings is None:
            raise RuntimeError("No embeddings to save — call build_faiss_index first")
        np.save(path, self.embeddings)
        logger.info("Embeddings saved to %s (shape %s)", path, self.embeddings.shape)

    def load_embeddings(self, path: str) -> bool:
        """Load a previously saved embedding matrix.

        Args:
            path: Source ``.npy`` file path.

        Returns:
            ``True`` if the file existed and was loaded, ``False`` otherwise.
        """
        file_path = Path(path)
        if not file_path.exists():
            logger.info("No cached embeddings found at %s", path)
            return False

        self.embeddings = self._ensure_unit_norm(np.load(path).astype(np.float32))
        logger.info("Loaded embeddings from %s (shape %s)", path, self.embeddings.shape)
        return True

    def build_faiss_index(
        self,
        df_barcoded: pd.DataFrame,
        embeddings_path: str = DEFAULT_EMBEDDINGS_PATH,
    ) -> None:
        """Build a FAISS inner-product index over barcoded product embeddings.

        Loads cached embeddings from ``embeddings_path`` when available;
        otherwise encodes ``name_clean`` and saves the result.

        Args:
            df_barcoded: Reference DataFrame with ``name_clean`` column.
            embeddings_path: Path for cached ``.npy`` embeddings.

        Raises:
            ValueError: If required columns are missing or the frame is empty.
        """
        if "name_clean" not in df_barcoded.columns:
            raise ValueError("df_barcoded must contain a 'name_clean' column")
        if df_barcoded.empty:
            raise ValueError("df_barcoded is empty — nothing to index")

        self.reference_df = df_barcoded.reset_index(drop=True).copy()
        build_start = time.perf_counter()

        if self.load_embeddings(embeddings_path):
            if len(self.embeddings) != len(self.reference_df):
                logger.warning(
                    "Cached embeddings count (%s) != products (%s) — recomputing",
                    f"{len(self.embeddings):,}",
                    f"{len(self.reference_df):,}",
                )
                self.embeddings = None

        if self.embeddings is None:
            texts = self.reference_df["name_clean"].tolist()
            self.embeddings = self._ensure_unit_norm(self.encode(texts))
            self.save_embeddings(embeddings_path)
        else:
            self.embeddings = self._ensure_unit_norm(self.embeddings)

        dimension = self.embeddings.shape[1]
        self.index = faiss.IndexFlatIP(dimension)
        self.index.add(self.embeddings)

        elapsed = time.perf_counter() - build_start
        size_mb = self.embeddings.nbytes / (1024 * 1024)
        logger.info(
            "FAISS index built: %s vectors, dim=%s, size=%.1f MB, time=%.2fs",
            f"{self.index.ntotal:,}",
            dimension,
            size_mb,
            elapsed,
        )

    def _require_index(self) -> None:
        """Raise if the FAISS index has not been built."""
        if self.index is None or self.reference_df is None:
            raise RuntimeError("FAISS index not built — call build_faiss_index first")

    @staticmethod
    def _candidate_names(candidates: pd.DataFrame) -> List[str]:
        """Return the text column to encode for a candidate DataFrame."""
        if "name_clean" in candidates.columns:
            return candidates["name_clean"].tolist()
        if "name" in candidates.columns:
            return candidates["name"].tolist()
        raise ValueError("candidates must contain 'name_clean' or 'name'")

    def rerank(self, query: str, candidates: pd.DataFrame) -> pd.DataFrame:
        """Rerank TF-IDF candidates by embedding cosine similarity.

        Args:
            query: Normalised query product name.
            candidates: Stage-1 candidate DataFrame (must include name text).

        Returns:
            Copy of ``candidates`` with ``embedding_score`` added, sorted
            descending by that score.
        """
        if candidates.empty:
            return candidates.copy()

        candidate_texts = self._candidate_names(candidates)
        # Encode query + candidates in one batch for consistency and speed.
        all_vecs = self.encode([query] + candidate_texts, show_progress_bar=False)
        query_vec = all_vecs[0:1]
        candidate_vecs = all_vecs[1:]

        # Unit-normalised vectors → inner product equals cosine similarity ∈ [-1, 1].
        scores = np.clip((candidate_vecs @ query_vec.T).ravel(), -1.0, 1.0)

        reranked = candidates.copy()
        reranked["embedding_score"] = scores
        return reranked.sort_values("embedding_score", ascending=False).reset_index(drop=True)

    def search_faiss(self, query: str, top_k: int = 5) -> pd.DataFrame:
        """Search the full reference index directly via FAISS.

        Args:
            query: Normalised query product name.
            top_k: Number of neighbours to return.

        Returns:
            DataFrame with ``barcode``, ``name``, ``name_clean``, and
            ``embedding_score``, sorted descending.
        """
        self._require_index()

        query_vec = self._ensure_unit_norm(self.encode([query], show_progress_bar=False))
        k = min(top_k, self.index.ntotal)
        scores, indices = self.index.search(query_vec, k)

        hits = self.reference_df.iloc[indices[0]].copy()
        hits["embedding_score"] = np.clip(scores[0], -1.0, 1.0)
        return hits.reset_index(drop=True)

    @staticmethod
    def _common_words(query: str, candidate: str) -> List[str]:
        """Return sorted tokens shared by query and candidate."""
        query_tokens = set(query.lower().split())
        candidate_tokens = set(candidate.lower().split())
        return sorted(query_tokens & candidate_tokens)

    def explain_match(self, query: str, candidate: str) -> Dict[str, Any]:
        """Produce a human-readable explanation for a query–candidate pair.

        Args:
            query: Normalised query product name.
            candidate: Normalised (or raw) candidate product name.

        Returns:
            Dict with ``embedding_similarity``, ``common_words``,
            ``brand_match``, ``weight_match``, and ``explanation``.
        """
        vecs = self.encode([query, candidate], show_progress_bar=False)
        similarity = float(np.clip((vecs[1:2] @ vecs[0:1].T)[0, 0], -1.0, 1.0))

        common = self._common_words(query, candidate)
        query_brand = extract_brand(query)
        query_weight = extract_weight(query)
        brand_match = bool(query_brand) and query_brand == extract_brand(candidate)
        weight_match = bool(query_weight) and query_weight == extract_weight(candidate)

        parts = [f"Embedding similarity: {similarity:.3f}"]
        if common:
            parts.append(f"Shared tokens: {', '.join(common[:8])}")
        if brand_match:
            parts.append(f"Brand matches exactly ({query_brand})")
        if weight_match:
            parts.append(f"Weight matches exactly ({query_weight})")
        if similarity >= HIGH_THRESHOLD:
            parts.append("High semantic similarity — likely the same product")
        elif similarity >= MEDIUM_THRESHOLD:
            parts.append("Moderate semantic similarity — human review recommended")
        else:
            parts.append("Low semantic similarity — likely not a match")

        return {
            "embedding_similarity": similarity,
            "common_words": common,
            "brand_match": brand_match,
            "weight_match": weight_match,
            "explanation": " | ".join(parts),
        }

    def save_index(self, path: str) -> None:
        """Persist the FAISS index and reference DataFrame.

        Args:
            path: Base path; writes ``<path>.faiss`` and ``<path>_meta.joblib``.
        """
        self._require_index()
        faiss.write_index(self.index, f"{path}.faiss")
        joblib.dump(
            {"reference_df": self.reference_df, "embeddings": self.embeddings},
            f"{path}_meta.joblib",
        )
        logger.info("FAISS index saved to %s.faiss", path)

    def load_index(self, path: str) -> None:
        """Load a previously saved FAISS index and reference data.

        Args:
            path: Base path used by :meth:`save_index`.
        """
        meta_path = f"{path}_meta.joblib"
        index_path = f"{path}.faiss"
        if not Path(index_path).exists() or not Path(meta_path).exists():
            raise FileNotFoundError(f"Index files not found for base path: {path}")

        self.index = faiss.read_index(index_path)
        meta = joblib.load(meta_path)
        self.reference_df = meta["reference_df"]
        self.embeddings = meta.get("embeddings")
        logger.info(
            "FAISS index loaded from %s (%s vectors)",
            path,
            f"{self.index.ntotal:,}",
        )


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )

    from src.preprocess import load_and_clean
    from src.tfidf_retriever import TFIDFRetriever

    DATA_PATH = "data/mix_products.csv"
    EMBEDDINGS_PATH = "data/reference_embeddings.npy"

    print("Loading and cleaning data...")
    df_barcoded, df_unmatched = load_and_clean(DATA_PATH)

    print("\nBuilding TF-IDF index (Stage 1)...")
    tfidf_start = time.perf_counter()
    retriever = TFIDFRetriever()
    retriever.fit(df_barcoded)
    tfidf_build_time = time.perf_counter() - tfidf_start
    print(f"TF-IDF index built in {tfidf_build_time:.2f}s")

    print("\nBuilding embedding FAISS index (Stage 2)...")
    embed_start = time.perf_counter()
    reranker = EmbeddingReranker()
    reranker.build_faiss_index(df_barcoded, embeddings_path=EMBEDDINGS_PATH)
    embed_build_time = time.perf_counter() - embed_start
    print(f"Embedding index built in {embed_build_time:.2f}s")

    test_queries = df_unmatched["name_clean"].head(3).tolist()

    print("\n" + "=" * 72)
    print("TF-IDF only  vs  TF-IDF (top 50) + Embedding rerank (top 3)")
    print("=" * 72)

    for query in test_queries:
        print(f"\nQuery: {query}")
        print("-" * 72)

        # TF-IDF only (top 3)
        t0 = time.perf_counter()
        tfidf_hits = retriever.search(query, top_k=3)
        tfidf_time = time.perf_counter() - t0

        # TF-IDF top 50 → rerank to top 3
        t0 = time.perf_counter()
        candidates = retriever.search(query, top_k=50)
        reranked = reranker.rerank(query, candidates).head(3)
        pipeline_time = time.perf_counter() - t0

        print(f"\n  TF-IDF only ({tfidf_time*1000:.1f} ms):")
        for rank, row in tfidf_hits.iterrows():
            print(
                f"    {rank+1}. [{row['tfidf_score_adjusted']:.4f}] "
                f"{row['barcode']} | {row['name'][:55]}"
            )

        print(f"\n  TF-IDF + Rerank ({pipeline_time*1000:.1f} ms):")
        for rank, row in reranked.iterrows():
            print(
                f"    {rank+1}. [emb={row['embedding_score']:.4f}  "
                f"tfidf={row['tfidf_score_adjusted']:.4f}] "
                f"{row['barcode']} | {row['name'][:45]}"
            )

        top_tfidf = tfidf_hits.iloc[0]
        top_reranked = reranked.iloc[0]
        explanation = reranker.explain_match(query, top_reranked["name_clean"])
        print(f"\n  Top reranked explanation: {explanation['explanation']}")

        if top_tfidf["barcode"] != top_reranked["barcode"]:
            print(
                f"  >> Reranker changed top result: "
                f"{top_tfidf['barcode']} -> {top_reranked['barcode']}"
            )

    print("\n" + "=" * 72)
    print("Done.")
