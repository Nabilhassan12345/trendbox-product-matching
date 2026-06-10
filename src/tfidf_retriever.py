"""Stage 1 retriever: TF-IDF character n-gram similarity over barcoded products."""

from __future__ import annotations

import logging
import time
from typing import Dict, List, Optional

import joblib
import numpy as np
import pandas as pd
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity

from src.preprocess import extract_brand, extract_weight

logger = logging.getLogger(__name__)

BRAND_MATCH_BONUS = 0.2
WEIGHT_MATCH_BONUS = 0.15


class TFIDFRetriever:
    """Fast TF-IDF candidate retrieval over the barcoded reference catalogue.

    Uses character n-grams (``char_wb``, 2–4) so minor Turkish spelling and
    unit-format differences still produce overlapping features.  Brand and weight
    exact-match bonuses are applied on top of cosine similarity before ranking.
    """

    def __init__(self) -> None:
        """Initialise an empty retriever (call :meth:`fit` before searching)."""
        self.vectorizer: Optional[TfidfVectorizer] = TfidfVectorizer(
            analyzer="char_wb",
            ngram_range=(2, 4),
            min_df=1,
            sublinear_tf=True,
        )
        self.matrix = None
        self.reference_df: Optional[pd.DataFrame] = None

    def fit(self, df_barcoded: pd.DataFrame) -> None:
        """Fit the vectorizer and build the TF-IDF index from barcoded products.

        Args:
            df_barcoded: Reference DataFrame with a ``name_clean`` column.

        Raises:
            ValueError: If ``name_clean`` is missing or the frame is empty.
        """
        if "name_clean" not in df_barcoded.columns:
            raise ValueError("df_barcoded must contain a 'name_clean' column")
        if df_barcoded.empty:
            raise ValueError("df_barcoded is empty — nothing to index")

        self.reference_df = df_barcoded.reset_index(drop=True).copy()
        if (self.reference_df["barcode"] == "").any():
            raise ValueError("df_barcoded must not contain rows with empty barcodes")

        logger.info("Fitting TF-IDF index on %s products", f"{len(self.reference_df):,}")

        corpus = self.reference_df["name_clean"].tolist()

        self.matrix = self.vectorizer.fit_transform(corpus)
        logger.info(
            "TF-IDF index built with %s products",
            f"{len(self.reference_df):,}",
        )

    def _require_fitted(self) -> None:
        """Raise if the retriever has not been fitted yet."""
        if self.matrix is None or self.reference_df is None or self.vectorizer is None:
            raise RuntimeError("TFIDFRetriever is not fitted — call fit() first")

    def _apply_bonus_vector(
        self,
        base_scores: np.ndarray,
        query_brand: str,
        query_weight: str,
    ) -> np.ndarray:
        """Apply brand (+0.2) and weight (+0.15) bonuses across all candidate scores.

        Bonuses are applied before top-k selection so a strong brand/weight match
        is never excluded because its raw TF-IDF score ranked outside the initial pool.
        """
        adjusted = base_scores.copy()
        if query_brand:
            brand_match = self.reference_df["brand"].values == query_brand
            adjusted += brand_match * BRAND_MATCH_BONUS
        if query_weight:
            weight_match = self.reference_df["weight"].values == query_weight
            adjusted += weight_match * WEIGHT_MATCH_BONUS
        return adjusted

    def _build_results_frame(
        self,
        candidate_indices: np.ndarray,
        base_scores: np.ndarray,
        adjusted_scores: np.ndarray,
    ) -> pd.DataFrame:
        """Assemble a ranked results DataFrame for one query."""
        order = np.argsort(adjusted_scores)[::-1]
        ranked_indices = candidate_indices[order]

        results = self.reference_df.iloc[ranked_indices][
            ["barcode", "name", "name_clean"]
        ].copy()
        # Position of each candidate in the reference catalogue. Lets Stage 2
        # reuse its cached embedding matrix instead of re-encoding candidates.
        results["ref_index"] = np.asarray(ranked_indices)
        results["tfidf_score"] = base_scores[order]
        results["tfidf_score_adjusted"] = adjusted_scores[order]
        return results.reset_index(drop=True)

    def search(self, query: str, top_k: int = 50) -> pd.DataFrame:
        """Return the top-k barcoded candidates for a single cleaned query.

        Args:
            query: Normalised product name (``name_clean`` format).
            top_k: Number of candidates to return.

        Returns:
            DataFrame with columns ``barcode``, ``name``, ``name_clean``,
            ``ref_index`` (position in the reference catalogue),
            ``tfidf_score`` (cosine similarity in [0, 1]),
            ``tfidf_score_adjusted`` (with bonuses; may exceed 1.0),
            sorted by adjusted score descending.
        """
        self._require_fitted()

        query_vec = self.vectorizer.transform([query])
        base_scores_all = cosine_similarity(query_vec, self.matrix).ravel()

        query_brand = extract_brand(query)
        query_weight = extract_weight(query)
        adjusted_all = self._apply_bonus_vector(base_scores_all, query_brand, query_weight)

        k = min(top_k, len(adjusted_all))
        candidate_indices = np.argpartition(adjusted_all, -k)[-k:]
        base_scores = base_scores_all[candidate_indices]
        adjusted_scores = adjusted_all[candidate_indices]

        return self._build_results_frame(candidate_indices, base_scores, adjusted_scores)

    def batch_search(self, queries: List[str], top_k: int = 50) -> Dict[str, pd.DataFrame]:
        """Search multiple queries using a single sparse matrix multiply.

        Transforms all queries at once, computes the full cosine-similarity
        matrix in one call, then extracts per-query top-k results.

        Args:
            queries: List of normalised product names.
            top_k: Number of candidates per query.

        Returns:
            Dict mapping each query string to its results DataFrame.
        """
        self._require_fitted()

        if not queries:
            logger.warning("batch_search called with empty query list")
            return {}

        start = time.perf_counter()

        query_matrix = self.vectorizer.transform(queries)
        similarity_matrix = cosine_similarity(query_matrix, self.matrix)

        k = min(top_k, similarity_matrix.shape[1])
        results: Dict[str, pd.DataFrame] = {}

        for row_idx, query in enumerate(queries):
            base_scores_all = similarity_matrix[row_idx]
            query_brand = extract_brand(query)
            query_weight = extract_weight(query)
            adjusted_all = self._apply_bonus_vector(
                base_scores_all, query_brand, query_weight
            )

            candidate_indices = np.argpartition(adjusted_all, -k)[-k:]
            base_scores = base_scores_all[candidate_indices]
            adjusted_scores = adjusted_all[candidate_indices]

            results[query] = self._build_results_frame(
                candidate_indices, base_scores, adjusted_scores
            )

        elapsed = time.perf_counter() - start
        qps = len(queries) / elapsed if elapsed > 0 else float("inf")
        logger.info(
            "batch_search: %s queries in %.3fs (%.1f queries/sec)",
            f"{len(queries):,}",
            elapsed,
            qps,
        )
        return results

    def save(self, path: str) -> None:
        """Persist the fitted vectorizer, matrix, and reference DataFrame.

        Args:
            path: Destination file path (joblib format).
        """
        self._require_fitted()
        payload = {
            "vectorizer": self.vectorizer,
            "matrix": self.matrix,
            "reference_df": self.reference_df,
        }
        joblib.dump(payload, path)
        logger.info("TF-IDF retriever saved to %s", path)

    def load(self, path: str) -> None:
        """Load a previously saved retriever from disk.

        Args:
            path: Source file path (joblib format).
        """
        payload = joblib.load(path)
        required = ("vectorizer", "matrix", "reference_df")
        missing = [key for key in required if key not in payload]
        if missing:
            raise ValueError(f"Invalid retriever file — missing keys: {missing}")

        self.vectorizer = payload["vectorizer"]
        self.matrix = payload["matrix"]
        self.reference_df = payload["reference_df"]
        logger.info(
            "TF-IDF retriever loaded from %s (%s products)",
            path,
            f"{len(self.reference_df):,}",
        )

    def get_stats(self) -> Dict[str, float]:
        """Return index statistics for monitoring and debugging.

        Returns:
            Dict with ``vocabulary_size``, ``num_products_indexed``,
            and ``index_size_mb``.
        """
        self._require_fitted()

        vocab_size = len(self.vectorizer.vocabulary_)
        num_products = len(self.reference_df)
        index_bytes = self.matrix.data.nbytes + self.matrix.indices.nbytes + self.matrix.indptr.nbytes

        return {
            "vocabulary_size": vocab_size,
            "num_products_indexed": num_products,
            "index_size_mb": round(index_bytes / (1024 * 1024), 2),
        }


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )

    from src.preprocess import load_and_clean

    DATA_PATH = "data/mix_products.csv"

    print("Loading and cleaning data...")
    df_barcoded, df_unmatched = load_and_clean(DATA_PATH)

    retriever = TFIDFRetriever()

    print("\nBuilding TF-IDF index...")
    build_start = time.perf_counter()
    retriever.fit(df_barcoded)
    build_elapsed = time.perf_counter() - build_start
    print(f"Index build time: {build_elapsed:.3f}s")

    stats = retriever.get_stats()
    print(
        f"Stats: vocabulary={stats['vocabulary_size']:,}  "
        f"products={stats['num_products_indexed']:,}  "
        f"index_size={stats['index_size_mb']} MB"
    )

    test_queries = df_unmatched["name_clean"].head(3).tolist()
    print("\n=== Single-query search (top 5 each) ===\n")

    search_times: List[float] = []
    for query in test_queries:
        t0 = time.perf_counter()
        hits = retriever.search(query, top_k=5)
        elapsed = time.perf_counter() - t0
        search_times.append(elapsed)

        print(f"Query : {query}")
        print(f"Time  : {elapsed * 1000:.2f} ms")
        for rank, row in hits.iterrows():
            print(
                f"  {rank + 1}. [{row['tfidf_score_adjusted']:.4f}] "
                f"{row['barcode']} | {row['name']}"
            )
        print()

    print(f"Avg single-search time: {np.mean(search_times) * 1000:.2f} ms")

    print("\n=== Benchmark: 100 random searches ===\n")
    sample_queries = df_unmatched["name_clean"].sample(100, random_state=42).tolist()

    bench_times: List[float] = []
    bench_start = time.perf_counter()
    for query in sample_queries:
        t0 = time.perf_counter()
        retriever.search(query, top_k=50)
        bench_times.append(time.perf_counter() - t0)
    bench_elapsed = time.perf_counter() - bench_start

    bench_ms = np.array(bench_times) * 1000
    print(f"Total      : {bench_elapsed:.3f}s")
    print(f"Avg        : {bench_ms.mean():.2f} ms/query")
    print(f"Min        : {bench_ms.min():.2f} ms/query")
    print(f"Max        : {bench_ms.max():.2f} ms/query")
    print(f"Throughput : {len(sample_queries) / bench_elapsed:.1f} queries/sec")

    print("\n=== Batch search sanity check (same 100 queries) ===\n")
    batch_start = time.perf_counter()
    retriever.batch_search(sample_queries, top_k=50)
    batch_elapsed = time.perf_counter() - batch_start
    print(f"Batch total: {batch_elapsed:.3f}s  ({len(sample_queries) / batch_elapsed:.1f} queries/sec)")
