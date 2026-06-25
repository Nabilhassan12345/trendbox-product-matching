#!/usr/bin/env python3
"""Unit tests for pack-size consistency filters in retrieval."""

from __future__ import annotations

import pandas as pd

from src.preprocess import extract_weight, filter_candidates_by_weight, weight_pool_eligible
from src.tfidf_retriever import TFIDFRetriever
from tests.helpers import check_true as check


def _sample_barcoded() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "barcode": ["111", "222", "333", "444"],
            "name": [
                "Sample Product 150 g",
                "Sample Product 500 g",
                "Sample Product 150 g Alt",
                "Sample Product No Weight",
            ],
            "name_clean": [
                "sample product 150 g",
                "sample product 500 g",
                "sample product 150 g alt",
                "sample product no weight",
            ],
            "brand": ["sample", "sample", "sample", "sample"],
            "weight": ["150 g", "500 g", "150 g", ""],
        }
    )


def test_weight_pool_eligible_rules() -> None:
    check("unknown query keeps all", weight_pool_eligible("", "500 g"))
    check("unknown candidate kept", weight_pool_eligible("150 g", ""))
    check("matching weights kept", weight_pool_eligible("150 g", "150 g"))
    check("mismatch excluded", not weight_pool_eligible("150 g", "500 g"))


def test_filter_candidates_by_weight_dataframe() -> None:
    candidates = _sample_barcoded()
    filtered = filter_candidates_by_weight("sample product 150 g", candidates)
    barcodes = set(filtered["barcode"].tolist())
    check("150 g rows kept", barcodes >= {"111", "333"})
    check("500 g row dropped", "222" not in barcodes)
    check("unknown-weight row kept", "444" in barcodes)

    unchanged = filter_candidates_by_weight("sample product no weight", candidates)
    check("no filter when query weight unknown", len(unchanged) == len(candidates))


def test_tfidf_excludes_weight_mismatch_from_top_k() -> None:
    retriever = TFIDFRetriever()
    retriever.fit(_sample_barcoded())

    hits = retriever.search("sample product 150 g", top_k=3)
    barcodes = hits["barcode"].tolist()
    check("top-k excludes 500 g mismatch", "222" not in barcodes)
    check("top-k includes 150 g variant", "111" in barcodes or "333" in barcodes)

    query_weight = extract_weight("sample product 150 g")
    mask = retriever._weight_eligible_mask("sample product 150 g")
    check("mask marks 500 g ineligible", not mask[1])
    check("mask marks 150 g eligible", mask[0] and mask[2])
