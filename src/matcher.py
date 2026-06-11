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

def _match_state(query_value: str, candidate_value: str) -> Optional[bool]:
    """Tri-state agreement: True (equal), False (differ), or None (unknown).

    Returns ``None`` when either side is missing so the confidence score stays
    neutral rather than penalising for absent metadata.
    """
    if not query_value or not candidate_value:
        return None
    return query_value == candidate_value


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
        3. Embedding rerank to add a semantic score to every candidate
        4. Score every candidate with the penalised ensemble confidence and
           return the top 3 by confidence

        Ranking by the ensemble (rather than by raw embedding similarity) lets
        brand/weight mismatch penalties demote near-duplicates — e.g. a
        same-product-different-brand or different-size item — that the embedding
        model otherwise scores very highly.

        Args:
            product_name: Raw or partially cleaned product name.

        Returns:
            List of up to three result dicts, each containing ``rank``,
            ``barcode``, ``name``, scores, confidence metadata, ``explanation``,
            and ``triage`` action, ordered by confidence descending.
        """
        self._require_built()

        query = normalize(product_name)
        if not query:
            logger.warning("Empty query after normalisation — returning no matches")
            return []

        candidates = self.tfidf.search(query, top_k=TOP_K_TFIDF)
        if candidates.empty:
            return []

        query_vec = self.embedder.encode([query], show_progress_bar=False)[0]
        embedding_scores = self.embedder.candidate_scores(query_vec, candidates)
        return self._assemble_hits(query, candidates, embedding_scores)

    def _assemble_hits(
        self,
        query: str,
        candidates: pd.DataFrame,
        embedding_scores: Any,
    ) -> List[Dict[str, Any]]:
        """Score candidates with the penalised ensemble and return the top 3.

        Shared by :meth:`match` (single query) and :meth:`match_many` (batched)
        so both paths produce byte-for-byte identical results.

        Args:
            query: Normalised query name.
            candidates: Stage-1 candidate DataFrame for this query.
            embedding_scores: Embedding cosine scores aligned to ``candidates``
                row order (from :meth:`EmbeddingReranker.candidate_scores`).

        Returns:
            Up to three result dicts ordered by confidence descending.
        """
        query_brand = extract_brand(query)
        query_weight = extract_weight(query)

        ranked: List[Dict[str, Any]] = []
        for position, row in enumerate(candidates.itertuples(index=False)):
            candidate_clean = row.name_clean if hasattr(row, "name_clean") else normalize(row.name)
            brand_match = _match_state(query_brand, extract_brand(candidate_clean))
            weight_match = _match_state(query_weight, extract_weight(candidate_clean))

            tfidf_score = float(row.tfidf_score)
            embedding_score = float(embedding_scores[position])
            confidence_score = compute_confidence(
                tfidf_score=tfidf_score,
                embedding_score=embedding_score,
                brand_match=brand_match,
                weight_match=weight_match,
            )
            ranked.append(
                {
                    "barcode": str(row.barcode) if row.barcode is not None else "",
                    "name": str(row.name),
                    "name_clean": candidate_clean,
                    "tfidf_score": tfidf_score,
                    "embedding_score": embedding_score,
                    "confidence_score": confidence_score,
                }
            )

        # Deterministic ordering: confidence first, then embedding, then barcode
        # as a stable tiebreaker so results never depend on upstream candidate
        # order (single search() vs batched batch_search() return top-k unsorted).
        ranked.sort(
            key=lambda item: (-item["confidence_score"], -item["embedding_score"], item["barcode"])
        )

        results: List[Dict[str, Any]] = []
        for rank, item in enumerate(ranked[:TOP_K_RERANK], start=1):
            confidence_score = item["confidence_score"]
            explanation = self.embedder.build_explanation(
                query, item["name_clean"], item["embedding_score"]
            )["explanation"]

            hit = {
                "rank": rank,
                "barcode": item["barcode"],
                "name": item["name"],
                "tfidf_score": round(item["tfidf_score"], 4),
                "embedding_score": round(item["embedding_score"], 4),
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

    def match_many(
        self,
        product_names: List[str],
        chunk_size: int = 512,
    ) -> List[List[Dict[str, Any]]]:
        """Match many product names with batched embedding encoding.

        This is the fast path for whole-catalogue runs. Instead of encoding one
        query at a time (a transformer forward pass per product), queries are
        processed in chunks: each chunk's queries are encoded in a single batched
        call and retrieved with one batched TF-IDF multiply. Reranking then reuses
        the cached reference embeddings. Results are identical to calling
        :meth:`match` per product, but far faster on CPU.

        Args:
            product_names: Raw product names to match.
            chunk_size: Number of queries encoded/retrieved together. Larger
                chunks improve throughput but use more transient memory.

        Returns:
            List aligned to ``product_names`` where each element is that
            product's ranked hit list (empty if the query was blank or had no
            candidates).
        """
        self._require_built()

        total = len(product_names)
        queries = [normalize(name) for name in product_names]
        results: List[List[Dict[str, Any]]] = [[] for _ in range(total)]

        start = time.perf_counter()
        for chunk_start in range(0, total, chunk_size):
            chunk_end = min(chunk_start + chunk_size, total)
            chunk = [
                (idx, queries[idx])
                for idx in range(chunk_start, chunk_end)
                if queries[idx]
            ]
            if not chunk:
                continue

            chunk_queries = [query for _, query in chunk]
            query_vecs = self.embedder.encode(chunk_queries, show_progress_bar=False)
            tfidf_results = self.tfidf.batch_search(chunk_queries, top_k=TOP_K_TFIDF)

            for (global_idx, query), query_vec in zip(chunk, query_vecs):
                candidates = tfidf_results[query]
                if candidates.empty:
                    continue
                embedding_scores = self.embedder.candidate_scores(query_vec, candidates)
                results[global_idx] = self._assemble_hits(query, candidates, embedding_scores)

            logger.info("Matched %s/%s products", f"{chunk_end:,}", f"{total:,}")

        elapsed = time.perf_counter() - start
        logger.info("match_many complete: %s products in %.2fs", f"{total:,}", elapsed)
        return results

    def batch_match(self, df_unmatched: pd.DataFrame) -> pd.DataFrame:
        """Match every row in an unmatched products DataFrame (batched).

        Delegates to :meth:`match_many`, which encodes queries in chunks for
        speed, then flattens the per-product hits into a long-format frame.

        Args:
            df_unmatched: DataFrame with at least a ``name`` column.

        Returns:
            Long-format DataFrame with one row per (product, rank) match
            suggestion, including query metadata and all score fields.
        """
        self._require_built()

        if "name" not in df_unmatched.columns:
            raise ValueError("df_unmatched must contain a 'name' column")

        names = df_unmatched["name"].tolist()
        logger.info("Batch matching %s unmatched products", f"{len(names):,}")

        per_product_hits = self.match_many(names)

        rows: List[Dict[str, Any]] = []
        for raw_name, matches in zip(names, per_product_hits):
            query_clean = normalize(raw_name)
            for match in matches:
                rows.append(
                    {
                        "query_name": raw_name,
                        "query_name_clean": query_clean,
                        **match,
                    }
                )

        logger.info(
            "Batch match complete: %s products, %s suggestions",
            f"{len(names):,}",
            f"{len(rows):,}",
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
