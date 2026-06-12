#!/usr/bin/env python3
"""Unit tests for match source inference from stored scores."""

from __future__ import annotations

from src.match_metadata import (
    explanation_from_stored,
    infer_match_source,
    match_source_label,
)
from tests.helpers import check_true as check


def test_infer_match_source() -> None:
    check("stage0 exact single", infer_match_source(1.0, 1.0, 1.0) == "stage0_exact")
    check("stage0 fuzzy single", infer_match_source(0.92, 0.92, 0.92) == "stage0_fuzzy")
    check("stage0 multi collision", infer_match_source(0.85, 0.85, 0.85) == "stage0_exact")
    check("ml path", infer_match_source(0.72, 0.81, 0.76) == "ml")


def test_match_source_label() -> None:
    check("label for ml", match_source_label("ml") == "ML match")


def test_explanation_from_stored() -> None:
    exact = explanation_from_stored(
        "stage0_exact",
        query="maydanoz adet",
        candidate_name_clean="maydanoz adet",
        tfidf_score=1.0,
        embedding_score=1.0,
        confidence_score=1.0,
    )
    check("stage0 exact explanation", "Stage 0 exact" in exact)

    ml = explanation_from_stored(
        "ml",
        query="nutella 400g",
        candidate_name_clean="nutella 400 g",
        tfidf_score=0.72,
        embedding_score=0.81,
        confidence_score=0.76,
    )
    check("ml fallback explanation mentions scores", "TF-IDF" in ml)
