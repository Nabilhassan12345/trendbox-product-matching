"""End-to-end two-stage product matching orchestrator."""

from __future__ import annotations

import logging
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

import pandas as pd

from src.confidence import (
    compute_confidence,
    get_confidence_color,
    get_confidence_label,
    triage,
)
from src.embedding_reranker import DEFAULT_EMBEDDINGS_PATH, EmbeddingReranker
from src.preprocess import extract_brand, extract_weight, normalize
from src.tfidf_retriever import TFIDFRetriever

logger = logging.getLogger(__name__)

TOP_K_TFIDF = 50
TOP_K_RERANK = 3

MATCH_RESULT_KEYS = frozenset(
    {
        "rank",
        "barcode",
        "name",
        "tfidf_score",
        "embedding_score",
        "confidence_score",
        "confidence_label",
        "confidence_color",
        "explanation",
        "triage",
    }
)


class ProductMatcher:
    """Orchestrates Stage 1 (TF-IDF) and Stage 2 (embedding rerank) matching.

    Typical workflow::

        matcher = ProductMatcher()
        matcher.build(df_barcoded)
        results = matcher.match("Ulker Hanimeller 150g")
    """

    def __init__(self) -> None:
        """Initialise empty retriever and reranker instances."""
        logger.info("Initialising ProductMatcher")
        self.tfidf = TFIDFRetriever()
        self.embedder = EmbeddingReranker()
        self._built = False
        logger.info("ProductMatcher ready (call build() before matching)")

    def build(
        self,
        df_barcoded: pd.DataFrame,
        embeddings_path: str = DEFAULT_EMBEDDINGS_PATH,
    ) -> None:
        """Fit TF-IDF and build the FAISS embedding index on barcoded products.

        Args:
            df_barcoded: Reference catalogue with ``name_clean`` column.
            embeddings_path: Cache path for precomputed reference embeddings.
        """
        if "name_clean" not in df_barcoded.columns:
            raise ValueError("df_barcoded must contain a 'name_clean' column")

        logger.info("Building indexes on %s barcoded products", f"{len(df_barcoded):,}")
        build_start = time.perf_counter()

        self.tfidf.fit(df_barcoded)
        self.embedder.build_faiss_index(df_barcoded, embeddings_path=embeddings_path)

        self._built = True
        elapsed = time.perf_counter() - build_start
        logger.info("ProductMatcher build complete in %.2fs", elapsed)

    def _require_built(self) -> None:
        """Raise if indexes have not been built."""
        if not self._built:
            raise RuntimeError("ProductMatcher not built — call build() first")

    def match(self, product_name: str) -> List[Dict[str, Any]]:
        """Match a single product name against the barcoded reference catalogue.

        Pipeline:
        1. Normalise the query with :func:`preprocess.normalize`
        2. TF-IDF retrieval (top 50 candidates)
        3. Embedding rerank (top 5)
        4. Ensemble confidence scoring per candidate

        Args:
            product_name: Raw or partially cleaned product name.

        Returns:
            List of up to five result dicts, each containing ``rank``,
            ``barcode``, ``name``, scores, confidence metadata, ``explanation``,
            and ``triage`` action.
        """
        self._require_built()

        query = normalize(product_name)
        if not query:
            logger.warning("Empty query after normalisation — returning no matches")
            return []

        candidates = self.tfidf.search(query, top_k=TOP_K_TFIDF)
        if candidates.empty:
            return []

        reranked = self.embedder.rerank(query, candidates).head(TOP_K_RERANK)

        results: List[Dict[str, Any]] = []
        for rank, row in enumerate(reranked.itertuples(index=False), start=1):
            candidate_clean = row.name_clean if hasattr(row, "name_clean") else normalize(row.name)
            brand_match = bool(extract_brand(query)) and extract_brand(query) == extract_brand(candidate_clean)
            weight_match = bool(extract_weight(query)) and extract_weight(query) == extract_weight(candidate_clean)

            tfidf_score = float(row.tfidf_score)
            embedding_score = float(row.embedding_score)
            confidence_score = compute_confidence(
                tfidf_score=tfidf_score,
                embedding_score=embedding_score,
                brand_match=brand_match,
                weight_match=weight_match,
            )
            explanation = self.embedder.explain_match(query, candidate_clean)["explanation"]

            hit = {
                "rank": rank,
                "barcode": str(row.barcode) if row.barcode is not None else "",
                "name": str(row.name),
                "tfidf_score": round(tfidf_score, 4),
                "embedding_score": round(embedding_score, 4),
                "confidence_score": round(confidence_score, 4),
                "confidence_label": get_confidence_label(confidence_score),
                "confidence_color": get_confidence_color(confidence_score),
                "explanation": explanation,
                "triage": triage(confidence_score),
            }
            if set(hit.keys()) != MATCH_RESULT_KEYS:
                raise RuntimeError(f"Match result missing keys: {MATCH_RESULT_KEYS - set(hit.keys())}")
            results.append(hit)

        return results

    def batch_match(self, df_unmatched: pd.DataFrame) -> pd.DataFrame:
        """Run :meth:`match` on every row in an unmatched products DataFrame.

        Logs progress every 1,000 products.

        Args:
            df_unmatched: DataFrame with at least a ``name`` column.

        Returns:
            Long-format DataFrame with one row per (product, rank) match
            suggestion, including query metadata and all score fields.
        """
        self._require_built()

        if "name" not in df_unmatched.columns:
            raise ValueError("df_unmatched must contain a 'name' column")

        total = len(df_unmatched)
        logger.info("Batch matching %s unmatched products", f"{total:,}")

        rows: List[Dict[str, Any]] = []
        batch_start = time.perf_counter()

        for index, product in enumerate(df_unmatched.itertuples(index=False), start=1):
            raw_name = product.name
            query_clean = normalize(raw_name)
            matches = self.match(raw_name)

            for match in matches:
                rows.append(
                    {
                        "query_name": raw_name,
                        "query_name_clean": query_clean,
                        **match,
                    }
                )

            if index % 1_000 == 0:
                logger.info("Matched %s / %s products", f"{index:,}", f"{total:,}")

        elapsed = time.perf_counter() - batch_start
        logger.info(
            "Batch match complete: %s products, %s suggestions in %.2fs",
            f"{total:,}",
            f"{len(rows):,}",
            elapsed,
        )
        return pd.DataFrame(rows)

    def save(self, path: str) -> None:
        """Persist TF-IDF and embedding indexes to a directory.

        Writes:
        - ``<path>/tfidf.joblib``
        - ``<path>/embedding_index.faiss`` and ``<path>/embedding_index_meta.joblib``

        Args:
            path: Directory path for saved artefacts.
        """
        self._require_built()
        save_dir = Path(path)
        save_dir.mkdir(parents=True, exist_ok=True)

        tfidf_path = str(save_dir / "tfidf.joblib")
        index_base = str(save_dir / "embedding_index")

        self.tfidf.save(tfidf_path)
        self.embedder.save_index(index_base)
        logger.info("ProductMatcher saved to %s", save_dir)

    def load(self, path: str) -> None:
        """Load previously saved TF-IDF and embedding indexes.

        Args:
            path: Directory path written by :meth:`save`.
        """
        load_dir = Path(path)
        tfidf_path = load_dir / "tfidf.joblib"
        index_base = str(load_dir / "embedding_index")

        if not tfidf_path.exists():
            raise FileNotFoundError(f"TF-IDF artefact not found: {tfidf_path}")

        self.tfidf.load(str(tfidf_path))
        self.embedder.load_index(index_base)
        self._built = True
        logger.info("ProductMatcher loaded from %s", load_dir)


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )

    from src.preprocess import load_and_clean

    DATA_PATH = "data/mix_products.csv"
    SAVE_PATH = "data/matcher_index"

    df_barcoded, df_unmatched = load_and_clean(DATA_PATH)

    matcher = ProductMatcher()
    matcher.build(df_barcoded)

    test_name = df_unmatched.iloc[0]["name"]
    print(f"\nQuery: {test_name}\n")
    for hit in matcher.match(test_name):
        print(
            f"  {hit['rank']}. [{hit['confidence_score']:.3f} {hit['confidence_label']}] "
            f"{hit['barcode']} | {hit['name'][:50]}"
        )
        print(f"     triage={hit['triage']}  {hit['explanation'][:80]}...")

    print("\nBatch sample (3 products)...")
    batch_df = matcher.batch_match(df_unmatched.head(3))
    print(batch_df[["query_name", "rank", "barcode", "confidence_score", "triage"]])

    matcher.save(SAVE_PATH)
    matcher2 = ProductMatcher()
    matcher2.load(SAVE_PATH)
    print("\nLoad/save round-trip OK")
