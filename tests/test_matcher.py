#!/usr/bin/env python3
"""End-to-end checks for the two-stage ProductMatcher."""

from __future__ import annotations

import tempfile
from pathlib import Path

import pytest

from src.confidence import get_confidence_label, triage
from src.config import DATA_CSV
from src.matcher import MATCH_RESULT_KEYS, ProductMatcher
from src.preprocess import load_and_clean
from tests.helpers import check_true as check

N_BARCODED = 60
N_QUERIES = 10


def _build_matcher(df_barcoded) -> ProductMatcher | None:
    """Build a matcher on a sample; return None (skip) if the model is unavailable."""
    try:
        matcher = ProductMatcher()
        embeddings_path = str(Path(tempfile.mkdtemp()) / "test_embeddings.npy")
        matcher.build(df_barcoded, embeddings_path=embeddings_path)
        return matcher
    except Exception as exc:  # noqa: BLE001
        pytest.skip(f"Could not build matcher (model unavailable?): {exc}")


def test_matcher_end_to_end() -> None:
    df_barcoded, df_unmatched = load_and_clean(str(DATA_CSV))
    sample_barcoded = df_barcoded.sample(N_BARCODED, random_state=42).reset_index(drop=True)
    queries = df_unmatched["name"].head(N_QUERIES).tolist()

    matcher = _build_matcher(sample_barcoded)
    if matcher is None:
        pytest.skip("matcher unavailable")

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
            f"triage is valid action for {raw_name[:30]!r}",
            all(h["triage"] in ("auto_approve", "review", "auto_reject") for h in hits),
        )

    check("at least one query produced matches", any_results)
