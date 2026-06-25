#!/usr/bin/env python3
"""Unit tests for structured pack profile parsing."""

from __future__ import annotations

from src.match_quality import classify_pack_from_names
from src.pack_profile import (
    compare_pack_profiles,
    format_pack_label,
    pack_pool_eligible,
    parse_pack_profile,
)
from tests.helpers import check_eq as check, check_true as check_true


def test_nescafe_vs_lezzcafe_conflict() -> None:
    print("=== Nescafe vs Lezzcafe ===\n")
    nescafe = "Nescafe 3 ü 1 Arada Orginal 17 Gr 56 Adet"
    lezzcafe = "Lezzcafe 3'ü 1 Arada 10'lu 10*18 g."

    left = parse_pack_profile(nescafe)
    right = parse_pack_profile(lezzcafe)

    check("Nescafe unit weight", "17 g", left.unit_weight)
    check("Nescafe pack count", 56, left.pack_count)
    check("Nescafe count label", "adet", left.count_label)

    check("Lezzcafe unit weight", "18 g", right.unit_weight)
    check("Lezzcafe pack count", 10, right.pack_count)
    check_true("Lezzcafe multipack", "10x18 g" in right.multipack)
    check("Lezzcafe total grams", 180.0, right.total_weight_g)

    check("verdict conflict", "size_conflict", compare_pack_profiles(left, right))
    check(
        "classify from names",
        "size_conflict",
        classify_pack_from_names(nescafe, lezzcafe),
    )


def test_same_unit_different_adet_conflict() -> None:
    print("\n=== same unit, different adet ===\n")
    a = "Brand Coffee 17 g 56 Adet"
    b = "Brand Coffee 17 g 48 Adet"
    check(
        "count mismatch conflicts",
        "size_conflict",
        classify_pack_from_names(a, b),
    )


def test_multipack_parsing() -> None:
    print("\n=== multipack parsing ===\n")
    profile = parse_pack_profile("Sample 10*18 g")
    check("unit", "18 g", profile.unit_weight)
    check("count", 10, profile.pack_count)
    check("total", 180.0, profile.total_weight_g)


def test_pack_pool_eligible() -> None:
    print("\n=== pack_pool_eligible ===\n")
    query = parse_pack_profile("Product 150 g 24 Adet")
    ok = parse_pack_profile("Other 150 g 24 Adet")
    bad = parse_pack_profile("Other 150 g 12 Adet")
    check_true("same pack eligible", pack_pool_eligible(query, ok))
    check_true("different count ineligible", not pack_pool_eligible(query, bad))


def test_format_pack_label() -> None:
    print("\n=== format_pack_label ===\n")
    label = format_pack_label(parse_pack_profile("Nescafe 17 Gr 56 Adet"))
    check_true("label mentions adet", "adet" in label)
    check_true("label mentions 17 g", "17 g" in label)
