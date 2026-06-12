#!/usr/bin/env python3
"""Unit tests for match source inference from stored scores."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.match_metadata import (  # noqa: E402
    explanation_from_stored,
    infer_match_source,
    match_source_label,
)

RESULTS: list[bool] = []


def check(name: str, condition: bool) -> None:
    status = "PASS" if condition else "FAIL"
    print(f"[{status}] {name}")
    RESULTS.append(condition)


def main() -> int:
    print("=== infer_match_source() ===\n")

    check(
        "stage0 exact single",
        infer_match_source(1.0, 1.0, 1.0) == "stage0_exact",
    )
    check(
        "stage0 fuzzy single",
        infer_match_source(0.92, 0.92, 0.92) == "stage0_fuzzy",
    )
    check(
        "stage0 multi collision",
        infer_match_source(0.85, 0.85, 0.85) == "stage0_exact",
    )
    check(
        "ml path",
        infer_match_source(0.72, 0.81, 0.76) == "ml",
    )

    print("\n=== match_source_label() ===\n")
    check(
        "label for ml",
        match_source_label("ml") == "ML match",
    )

    print("\n=== explanation_from_stored() ===\n")
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

    passed = sum(RESULTS)
    total = len(RESULTS)
    print(f"\n=== Summary: {passed}/{total} passed ===")
    return 0 if passed == total else 1


if __name__ == "__main__":
    sys.exit(main())
