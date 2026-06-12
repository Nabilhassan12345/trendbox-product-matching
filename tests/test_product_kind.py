#!/usr/bin/env python3
"""Tests for product kind classification and kind-aware confidence scoring."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.confidence import compute_confidence, resolve_brand_match, triage
from src.preprocess import classify_product_kind, normalize

RESULTS: list[bool] = []


def check(name: str, expected: object, actual: object) -> None:
    ok = expected == actual
    status = "PASS" if ok else "FAIL"
    detail = "" if ok else f"  (expected {expected!r}, got {actual!r})"
    print(f"[{status}] {name}{detail}")
    RESULTS.append(ok)


def test_classify_product_kind() -> None:
    print("=== classify_product_kind() ===\n")
    check(
        "fresh produce adet",
        "fresh",
        classify_product_kind("maydonoz adet", "maydonoz", ""),
    )
    check(
        "branded with weight",
        "branded",
        classify_product_kind("ulker hanimeller 150 g", "ulker", "150 g"),
    )
    check(
        "empty name",
        "unknown",
        classify_product_kind("", "", ""),
    )
    check(
        "long FMCG name without weight",
        "branded",
        classify_product_kind("ulker cikolatali gofret findikli", "ulker", ""),
    )


def test_resolve_brand_match_fresh() -> None:
    print("\n=== resolve_brand_match() fresh ===\n")
    check(
        "maydonoz vs maydanoz fuzzy",
        True,
        resolve_brand_match("maydonoz", "maydanoz", "fresh"),
    )
    check(
        "unrelated fresh tokens neutral",
        None,
        resolve_brand_match("maydonoz", "domates", "fresh"),
    )


def test_maydonoz_confidence() -> None:
    print("\n=== Maydonoz scenario confidence ===\n")
    score = compute_confidence(
        tfidf_score=0.5718,
        embedding_score=0.7524,
        brand_match=False,
        weight_match=None,
        product_kind="fresh",
        query_brand="maydonoz",
        candidate_brand="maydanoz",
    )
    check("score enters review band", "review", triage(score))
    check("score above 0.60", True, score >= 0.60)


def main() -> int:
    test_classify_product_kind()
    test_resolve_brand_match_fresh()
    test_maydonoz_confidence()

    passed = sum(RESULTS)
    total = len(RESULTS)
    print(f"\n=== Summary: {passed}/{total} passed ===")
    return 0 if passed == total else 1


if __name__ == "__main__":
    sys.exit(main())
