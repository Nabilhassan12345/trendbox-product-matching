#!/usr/bin/env python3
"""Run batch matching only (no API/UI). Use when match records are missing."""

from __future__ import annotations

import logging
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from src.batch import run_full_batch
from src.config import DATA_CSV, DB_PATH, apply_runtime_env
from src.database import init_db, load_products
from src.index_builder import build_or_load_faiss, build_or_load_tfidf
from src.matcher import ProductMatcher
from src.preprocess import load_and_clean
from src.reference_catalog import (
    canonical_barcoded,
    canonical_unmatched,
    prepare_reference_index,
)


def main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )
    apply_runtime_env()

    df_barcoded, df_unmatched = load_and_clean(str(DATA_CSV))
    df_index = prepare_reference_index(df_barcoded)
    df_canonical_b = canonical_barcoded(df_barcoded)
    df_canonical_u = canonical_unmatched(df_unmatched)

    init_db(str(DB_PATH))
    load_products(df_canonical_b, df_canonical_u)

    matcher = ProductMatcher()
    build_or_load_tfidf(matcher, df_index, rebuild=False)
    build_or_load_faiss(matcher, df_index, rebuild=False)

    _records, counts = run_full_batch(matcher, stage0_df=df_index)
    print(
        f"Batch finished: {counts.get('stage0_resolved', 0):,} stage-0, "
        f"{counts['auto_approved']:,} auto-approved, "
        f"{counts['pending']:,} pending, {counts['auto_rejected']:,} auto-rejected"
    )


if __name__ == "__main__":
    main()
