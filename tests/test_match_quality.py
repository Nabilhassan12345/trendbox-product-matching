#!/usr/bin/env python3
"""Unit tests for src/match_quality.py."""

from __future__ import annotations

from src.match_quality import (
    SIZE_CONFLICT,
    SIZE_UNKNOWN,
    SIZE_VERIFIED,
    build_guardrail_explanation,
    classify_brand_match,
    classify_pack_from_names,
    classify_size,
    should_block_auto_approve,
)
from tests.helpers import check_eq as check


def test_classify_size() -> None:
    print("=== classify_size() ===\n")
    check("equal weights", SIZE_VERIFIED, classify_size("150 g", "150 g"))
    check("different weights", SIZE_CONFLICT, classify_size("150 g", "300 g"))
    check("missing query", SIZE_UNKNOWN, classify_size("", "300 g"))
    check("missing candidate", SIZE_UNKNOWN, classify_size("150 g", ""))
    check("both missing", SIZE_UNKNOWN, classify_size("", ""))


def test_should_block_auto_approve() -> None:
    print("\n=== should_block_auto_approve() ===\n")
    check("conflict blocks", True, should_block_auto_approve(SIZE_CONFLICT))
    check("verified does not block", False, should_block_auto_approve(SIZE_VERIFIED))
    check("unknown does not block", False, should_block_auto_approve(SIZE_UNKNOWN))


def test_build_guardrail_explanation() -> None:
    print("\n=== build_guardrail_explanation() ===\n")
    check(
        "verified message",
        "Pack size verified (400 g).",
        build_guardrail_explanation(SIZE_VERIFIED, "400 g", "400 g"),
    )
    check(
        "conflict message",
        "Pack size conflict: source 150 g vs suggestion 300 g.",
        build_guardrail_explanation(SIZE_CONFLICT, "150 g", "300 g"),
    )
    check(
        "unknown message",
        "Pack size unknown on one or both sides — size guardrail not applied.",
        build_guardrail_explanation(SIZE_UNKNOWN, "", "300 g"),
    )


def test_classify_brand_match_delegates() -> None:
    print("\n=== classify_brand_match() ===\n")
    check("exact brand", True, classify_brand_match("ulker", "ulker"))
    check("different brand", False, classify_brand_match("ulker", "eti"))
    check("fresh fuzzy", True, classify_brand_match("maydonoz", "maydanoz", "fresh"))
