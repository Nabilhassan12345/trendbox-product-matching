#!/usr/bin/env python3
"""Unit tests for src/preprocess.py normalisation and feature extraction.

Pure, deterministic, no network or model required. Prints PASS/FAIL per case;
exit code 0 when all pass, 1 otherwise.
"""

from __future__ import annotations

from src.preprocess import extract_brand, extract_weight, normalize
from tests.helpers import check_eq as check


def test_normalize() -> None:
    """15 cases: Turkish folding, unit standardisation, and edge cases."""
    print("=== normalize() ===\n")
    cases: list[tuple[str, str]] = [
        ("NUTELLA 400GR", "nutella 400 g"),
        ("Ülker Hanimeller 150g", "ulker hanimeller 150 g"),
        ("Şeker  500   gr", "seker 500 g"),
        ("Çikolata 1KG", "cikolata 1 kg"),
        ("KAHVE 100ML", "kahve 100 ml"),
        ("Süt 1 litre", "sut 1 l"),
        ("Su 2 lt", "su 2 l"),
        ("Un 500 gram", "un 500 g"),
        ("Yağ 1L", "yag 1 l"),
        ("İĞÜŞÖÇ ığüşöç", "igusoc igusoc"),
        ("  Çay!!!  %50   indirim  ", "cay 50 indirim"),
        ("", ""),
        ("12345", "12345"),
        ("Bal   150    g", "bal 150 g"),
        ("ÇİKOLATALI GofRET 35 Gr", "cikolatali gofret 35 g"),
    ]
    for raw, expected in cases:
        check(f"normalize({raw!r})", expected, normalize(raw))

    # Extra robustness edges (not counted among the 15 product cases).
    print()
    check("normalize(None) handles non-str", "", normalize(None))  # type: ignore[arg-type]
    check("normalize whitespace-only", "", normalize("     "))
    long_name = ("kahve " * 200).strip()
    check("normalize very long name has no double spaces", True, "  " not in normalize(long_name))


def test_extract_weight() -> None:
    """All unit variations plus decimal handling."""
    print("\n=== extract_weight() ===\n")
    cases: list[tuple[str, str]] = [
        ("NUTELLA 400GR", "400 g"),
        ("Çikolata 1KG", "1 kg"),
        ("KAHVE 100ML", "100 ml"),
        ("Sut 1 litre", "1 l"),
        ("Su 2 lt", "2 l"),
        ("Un 500 gram", "500 g"),
        ("Yag 1L", "1 l"),
        ("Ayran 0,5 lt", "0.5 l"),
        ("Bal 150 g", "150 g"),
        ("urun adi yok", ""),
    ]
    for raw, expected in cases:
        check(f"extract_weight({raw!r})", expected, extract_weight(raw))


def test_extract_brand() -> None:
    """First-token brand extraction and empty handling."""
    print("\n=== extract_brand() ===\n")
    check("extract_brand normal", "ulker", extract_brand("ulker hanimeller 150 g"))
    check("extract_brand empty", "", extract_brand(""))
    check("extract_brand leading spaces", "nutella", extract_brand("  nutella 400 g"))
