#!/usr/bin/env python3
"""Tests for Stage 0 deterministic blocking."""

from __future__ import annotations

import pandas as pd

from src.blocking import Stage0Resolver
from src.confidence import triage
from src.config import DATA_CSV
from src.preprocess import load_and_clean
from src.reference_catalog import prepare_reference_index

from tests.helpers import check_eq as check


def _make_index() -> pd.DataFrame:
    df_barcoded, _ = load_and_clean(str(DATA_CSV))
    return prepare_reference_index(df_barcoded)


def test_exact_single_barcode() -> None:
    print("=== exact single barcode ===\n")
    resolver = Stage0Resolver(_make_index())
    overlap_name = "filiz tel sehriye 500 g"
    hits = resolver.resolve(overlap_name)
    check("returns hits", True, hits is not None and len(hits) == 1)
    if hits:
        check("auto-approve triage", "auto_approve", hits[0]["triage"])
        check("confidence 1.0", 1.0, hits[0]["confidence_score"])


def test_exact_multi_barcode_pending() -> None:
    print("\n=== exact multi-barcode collision ===\n")
    df = pd.DataFrame(
        [
            {"barcode": "111", "name": "Alpha X", "name_clean": "alpha x", "brand": "alpha", "weight": ""},
            {"barcode": "222", "name": "Alpha X Alt", "name_clean": "alpha x", "brand": "alpha", "weight": ""},
        ]
    )
    resolver = Stage0Resolver(df)
    hits = resolver.resolve("Alpha X")
    check("returns hits", True, hits is not None)
    if hits:
        check("pending triage", "review", hits[0]["triage"])
        check("confidence 0.85", 0.85, hits[0]["confidence_score"])


def test_fuzzy_spelling() -> None:
    print("\n=== fuzzy spelling ===\n")
    df = pd.DataFrame(
        [
            {
                "barcode": "999",
                "name": "Maydanoz Adet",
                "name_clean": "maydanoz adet",
                "brand": "maydanoz",
                "weight": "",
            },
        ]
    )
    resolver = Stage0Resolver(df)
    hits = resolver.resolve("Maydonoz Adet")
    check("returns fuzzy hits", True, hits is not None)
    if hits:
        check("auto-approve fuzzy single", "auto_approve", triage(hits[0]["confidence_score"]))


def test_no_match() -> None:
    print("\n=== no match ===\n")
    resolver = Stage0Resolver(_make_index())
    check("unknown product", None, resolver.resolve("zzzzzzzzzzzzzzzz product 99999"))
