#!/usr/bin/env python3
"""Quantitative evaluation of the two-stage matcher on held-out ground truth.

Ground truth is mined from the catalogue itself: products that share a barcode
but are written with different names are, by definition, the same product. For
each such group we hold one spelling out of the reference index and check
whether the pipeline retrieves the correct barcode.

Metrics:
  - Recall@1 / Recall@3 for TF-IDF only, embedding (FAISS) only, and two-stage
  - A precision-vs-coverage sweep over the rank-1 confidence score, used to
    justify the auto-approve / auto-reject thresholds with evidence

The reference index reuses cached embeddings when available, so a full run takes
about a minute on CPU (plus one-time model load) rather than re-encoding 58k
products.

Usage:
    python scripts/evaluate.py --max-queries 1000 --target-precision 0.95
"""

from __future__ import annotations

import argparse
import logging
import sys
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.matcher import ProductMatcher
from src.preprocess import load_and_clean

logger = logging.getLogger(__name__)

DATA_CSV = ROOT / "data" / "mix_products.csv"
EMBED_CACHE_CANDIDATES = (
    ROOT / "data" / "faiss_cache" / "reference_embeddings.npy",
    ROOT / "data" / "reference_embeddings.npy",
)


def build_ground_truth(
    df_barcoded: pd.DataFrame, max_queries: int, seed: int
) -> List[int]:
    """Pick one held-out query row position per multi-spelling barcode group.

    Args:
        df_barcoded: Reference catalogue (positionally indexed 0..N-1).
        max_queries: Cap on the number of held-out queries (for runtime).
        seed: RNG seed for reproducible sampling.

    Returns:
        Sorted list of row positions to hold out as queries.
    """
    eligible: List[int] = []
    for _barcode, group in df_barcoded.groupby("barcode"):
        distinct = group.drop_duplicates("name_clean")
        if len(distinct) >= 2:
            # Hold out the variant whose cleaned name is rarest in the group,
            # i.e. a genuinely different spelling rather than an exact copy.
            eligible.append(int(distinct.index[-1]))

    rng = np.random.default_rng(seed)
    if len(eligible) > max_queries:
        eligible = rng.choice(eligible, size=max_queries, replace=False).tolist()
    return sorted(int(pos) for pos in eligible)


def _load_cached_embeddings(expected_rows: int) -> Optional[np.ndarray]:
    """Return cached embeddings aligned to df_barcoded, or None to re-encode."""
    for path in EMBED_CACHE_CANDIDATES:
        if path.exists():
            arr = np.load(path)
            if len(arr) == expected_rows:
                logger.info("Reusing cached embeddings from %s", path)
                return arr.astype(np.float32)
            logger.warning(
                "Cached embeddings at %s have %s rows (expected %s) — ignoring",
                path,
                len(arr),
                expected_rows,
            )
    return None


def build_holdout_matcher(
    df_barcoded: pd.DataFrame, query_positions: List[int]
) -> ProductMatcher:
    """Build a matcher whose reference index excludes the held-out queries."""
    query_set = set(query_positions)
    reference_positions = [pos for pos in range(len(df_barcoded)) if pos not in query_set]
    reference_df = df_barcoded.iloc[reference_positions].reset_index(drop=True)

    matcher = ProductMatcher()  # loads the embedding model once
    matcher.tfidf.fit(reference_df)

    cached = _load_cached_embeddings(len(df_barcoded))
    if cached is not None:
        matcher.embedder.set_reference(reference_df, cached[reference_positions])
    else:
        logger.warning("No aligned embedding cache found — encoding reference (slow)…")
        import tempfile

        tmp = str(Path(tempfile.mkdtemp()) / "eval_embeddings.npy")
        matcher.embedder.build_faiss_index(reference_df, embeddings_path=tmp)

    matcher._built = True
    return matcher


def _recall_at_k(predicted_barcodes: List[str], true_barcode: str, k: int) -> bool:
    """Whether the true barcode appears in the first k predictions."""
    return true_barcode in predicted_barcodes[:k]


def evaluate(
    matcher: ProductMatcher,
    df_barcoded: pd.DataFrame,
    query_positions: List[int],
    debug_limit: int = 0,
) -> Tuple[Dict[str, float], List[Dict[str, Any]], List[Dict[str, Any]]]:
    """Run all three approaches on the held-out queries and collect metrics.

    When ``debug_limit`` > 0, also collects cases where TF-IDF retrieved the
    correct barcode at rank 1 but the two-stage reranker pushed it out of the
    top 3 — i.e. where reranking actively hurt.
    """
    totals = {
        "tfidf_r1": 0, "tfidf_r3": 0,
        "embed_r1": 0, "embed_r3": 0,
        "two_stage_r1": 0, "two_stage_r3": 0,
    }
    confidence_records: List[Dict[str, Any]] = []
    regressions: List[Dict[str, Any]] = []
    # Reference name per barcode, to show the answer the reranker missed.
    reference_df = matcher.tfidf.reference_df
    name_by_barcode = dict(zip(reference_df["barcode"].astype(str), reference_df["name"]))
    n = len(query_positions)

    start = time.perf_counter()
    for i, pos in enumerate(query_positions, start=1):
        row = df_barcoded.iloc[pos]
        true_barcode = str(row["barcode"])
        query_clean = str(row["name_clean"])

        # TF-IDF only (Stage 1 ranking).
        tfidf_hits = matcher.tfidf.search(query_clean, top_k=3)
        tfidf_barcodes = [str(b) for b in tfidf_hits["barcode"].tolist()]
        tfidf_r1 = _recall_at_k(tfidf_barcodes, true_barcode, 1)
        totals["tfidf_r1"] += tfidf_r1
        totals["tfidf_r3"] += _recall_at_k(tfidf_barcodes, true_barcode, 3)

        # Embedding only (direct FAISS).
        faiss_hits = matcher.embedder.search_faiss(query_clean, top_k=3)
        faiss_barcodes = [str(b) for b in faiss_hits["barcode"].tolist()]
        totals["embed_r1"] += _recall_at_k(faiss_barcodes, true_barcode, 1)
        totals["embed_r3"] += _recall_at_k(faiss_barcodes, true_barcode, 3)

        # Two-stage pipeline (the production path).
        hits = matcher.match(row["name"])
        ts_barcodes = [str(h["barcode"]) for h in hits]
        ts_r3 = _recall_at_k(ts_barcodes, true_barcode, 3)
        totals["two_stage_r1"] += _recall_at_k(ts_barcodes, true_barcode, 1)
        totals["two_stage_r3"] += ts_r3

        if hits:
            confidence_records.append(
                {
                    "confidence": hits[0]["confidence_score"],
                    "correct": ts_barcodes[0] == true_barcode,
                }
            )
            if debug_limit and tfidf_r1 and not ts_r3 and len(regressions) < debug_limit:
                regressions.append(
                    {
                        "query": str(row["name"]),
                        "correct_answer": name_by_barcode.get(true_barcode, "(?)"),
                        "reranker_top": str(hits[0]["name"]),
                        "embedding_score": float(hits[0]["embedding_score"]),
                        "confidence": float(hits[0]["confidence_score"]),
                    }
                )

        if i % 100 == 0 or i == n:
            rate = i / (time.perf_counter() - start)
            logger.info("Evaluated %s/%s queries (%.1f/s)", i, n, rate)

    metrics = {key: value / n for key, value in totals.items()}
    metrics["n_queries"] = n
    return metrics, confidence_records, regressions


def threshold_sweep(
    records: List[Dict[str, Any]], target_precision: float
) -> Tuple[pd.DataFrame, Optional[float]]:
    """Precision and coverage at each confidence cutoff; recommend a cutoff."""
    df = pd.DataFrame(records)
    total = len(df)
    rows: List[Dict[str, Any]] = []
    recommended: Optional[float] = None

    for threshold in [round(0.50 + 0.05 * i, 2) for i in range(10)]:  # 0.50 → 0.95
        kept = df[df["confidence"] >= threshold]
        coverage = len(kept) / total if total else 0.0
        precision = kept["correct"].mean() if len(kept) else float("nan")
        rows.append(
            {
                "threshold": threshold,
                "auto_approved": len(kept),
                "coverage": coverage,
                "precision": precision,
            }
        )
        if recommended is None and len(kept) and precision >= target_precision:
            recommended = threshold

    return pd.DataFrame(rows), recommended


def _print_report(
    metrics: Dict[str, float],
    sweep: pd.DataFrame,
    recommended: Optional[float],
    target_precision: float,
) -> None:
    print("\n" + "=" * 64)
    print("  RETRIEVAL ACCURACY (held-out ground truth)")
    print("=" * 64)
    print(f"  Queries evaluated: {int(metrics['n_queries']):,}\n")
    print(f"  {'Approach':<22}{'Recall@1':>12}{'Recall@3':>12}")
    print("  " + "-" * 44)
    print(f"  {'TF-IDF only':<22}{metrics['tfidf_r1']:>11.1%}{metrics['tfidf_r3']:>12.1%}")
    print(f"  {'Embedding only':<22}{metrics['embed_r1']:>11.1%}{metrics['embed_r3']:>12.1%}")
    print(f"  {'Two-stage (prod)':<22}{metrics['two_stage_r1']:>11.1%}{metrics['two_stage_r3']:>12.1%}")

    print("\n" + "=" * 64)
    print("  CONFIDENCE THRESHOLD SWEEP (rank-1)")
    print("=" * 64)
    print(f"  {'Cutoff':>8}{'Auto-approved':>16}{'Coverage':>12}{'Precision':>12}")
    print("  " + "-" * 48)
    for _, r in sweep.iterrows():
        precision = "n/a" if pd.isna(r["precision"]) else f"{r['precision']:.1%}"
        print(
            f"  {r['threshold']:>8.2f}{int(r['auto_approved']):>16,}"
            f"{r['coverage']:>11.1%}{precision:>12}"
        )

    print("\n" + "=" * 64)
    print("  (precision = share of auto-approved whose top barcode is correct)")
    print("=" * 64)
    if recommended is not None:
        print(
            f"  Recommended auto-approve cutoff for ≥{target_precision:.0%} precision: "
            f"{recommended:.2f}"
        )
    else:
        print(
            f"  No cutoff reached ≥{target_precision:.0%} precision — "
            "inspect the sweep above."
        )
    print("=" * 64 + "\n")


def main() -> int:
    parser = argparse.ArgumentParser(description="Evaluate the two-stage matcher.")
    parser.add_argument("--max-queries", type=int, default=1000, help="Held-out query cap.")
    parser.add_argument("--target-precision", type=float, default=0.95, help="Desired auto-approve precision.")
    parser.add_argument("--seed", type=int, default=42, help="Sampling seed.")
    parser.add_argument(
        "--debug-examples",
        type=int,
        default=0,
        help="Show N cases where reranking pushed the correct answer out of top 3.",
    )
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")

    print("Loading and cleaning catalogue…")
    df_barcoded, _ = load_and_clean(str(DATA_CSV))

    query_positions = build_ground_truth(df_barcoded, args.max_queries, args.seed)
    if not query_positions:
        print("No multi-spelling barcode groups found — cannot evaluate.")
        return 1
    print(f"Held out {len(query_positions):,} queries from {len(df_barcoded):,} reference products.")

    matcher = build_holdout_matcher(df_barcoded, query_positions)
    metrics, records, regressions = evaluate(
        matcher, df_barcoded, query_positions, debug_limit=args.debug_examples
    )
    sweep, recommended = threshold_sweep(records, args.target_precision)
    _print_report(metrics, sweep, recommended, args.target_precision)

    if regressions:
        print("=" * 64)
        print("  WHERE RERANKING HURT (TF-IDF rank-1 correct, two-stage missed top-3)")
        print("=" * 64)
        for ex in regressions:
            print(f"\n  Query        : {ex['query'][:70]}")
            print(f"  Correct (TF-IDF): {ex['correct_answer'][:70]}")
            print(
                f"  Reranker #1  : {ex['reranker_top'][:70]} "
                f"(emb={ex['embedding_score']:.3f}, conf={ex['confidence']:.3f})"
            )
        print("\n" + "=" * 64 + "\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
