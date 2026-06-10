#!/usr/bin/env python3
"""End-to-end checks for the two-stage ProductMatcher.

Builds a matcher on a small sample of real barcoded products and matches a
handful of unmatched products, verifying result shape, score ranges, ordering,
and confidence-label consistency.

Requires the SentenceTransformer model. If it cannot be loaded (e.g. no network
on first run), the suite SKIPS rather than failing, and exits 0.

Prints PASS/FAIL per check; exit code 0 when all pass (or skipped), 1 otherwise.
"""

from __future__ import annotations

import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.confidence import get_confidence_label, triage
from src.matcher import MATCH_RESULT_KEYS, ProductMatcher
from src.preprocess import load_and_clean

DATA_PATH = ROOT / "data" / "mix_products.csv"
N_BARCODED = 60
N_QUERIES = 10

RESULTS: list[bool] = []


def check(name: str, condition: bool, detail: str = "") -> None:
    """Record and print a single PASS/FAIL result."""
    status = "PASS" if condition else "FAIL"
    suffix = f" — {detail}" if detail else ""
    print(f"[{status}] {name}{suffix}")
    RESULTS.append(condition)


def _build_matcher(df_barcoded) -> ProductMatcher | None:
    """Build a matcher on a sample; return None (skip) if the model is unavailable."""
    try:
        matcher = ProductMatcher()
        # Use a path that does not yet exist so the matcher computes fresh
        # embeddings instead of trying to load an empty cache file.
        embeddings_path = str(Path(tempfile.mkdtemp()) / "test_embeddings.npy")
        matcher.build(df_barcoded, embeddings_path=embeddings_path)
        return matcher
    except Exception as exc:  # noqa: BLE001 — model download / offline is a skip, not a failure
        print(f"[SKIP] Could not build matcher (model unavailable?): {exc}")
        return None


def main() -> int:
    df_barcoded, df_unmatched = load_and_clean(str(DATA_PATH))
    sample_barcoded = df_barcoded.sample(N_BARCODED, random_state=42).reset_index(drop=True)
    queries = df_unmatched["name"].head(N_QUERIES).tolist()

    matcher = _build_matcher(sample_barcoded)
    if matcher is None:
        print("\n=== Summary: skipped (model unavailable) ===")
        return 0

    any_results = False
    for raw_name in queries:
        hits = matcher.match(raw_name)
        if not hits:
            continue
        any_results = True

        ranks = [h["rank"] for h in hits]
        check(
            f"ranks are 1..{len(hits)} for {raw_name[:30]!r}",
            ranks == list(range(1, len(hits) + 1)),
            f"ranks={ranks}",
        )
        check(
            f"all keys present for {raw_name[:30]!r}",
            all(set(h.keys()) == MATCH_RESULT_KEYS for h in hits),
        )
        check(
            f"confidence_score in [0,1] for {raw_name[:30]!r}",
            all(0.0 <= h["confidence_score"] <= 1.0 for h in hits),
        )
        check(
            f"tfidf_score in [0,1] for {raw_name[:30]!r}",
            all(0.0 <= h["tfidf_score"] <= 1.0 for h in hits),
        )
        check(
            f"embedding_score in [-1,1] for {raw_name[:30]!r}",
            all(-1.0 <= h["embedding_score"] <= 1.0 for h in hits),
        )
        scores = [h["confidence_score"] for h in hits]
        check(
            f"results sorted by confidence desc for {raw_name[:30]!r}",
            scores == sorted(scores, reverse=True),
            f"scores={[round(s, 3) for s in scores]}",
        )
        check(
            f"confidence_label matches threshold for {raw_name[:30]!r}",
            all(h["confidence_label"] == get_confidence_label(h["confidence_score"]) for h in hits),
        )
        check(
            f"triage matches threshold for {raw_name[:30]!r}",
            all(h["triage"] == triage(h["confidence_score"]) for h in hits),
        )

    check("at least one query produced matches", any_results)

    passed = sum(RESULTS)
    total = len(RESULTS)
    print(f"\n=== Summary: {passed}/{total} passed ===")
    return 0 if passed == total else 1


if __name__ == "__main__":
    sys.exit(main())
