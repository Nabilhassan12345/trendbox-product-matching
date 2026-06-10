#!/usr/bin/env python3
"""Run batch matching only (no API/UI). Use when match records are missing."""

from __future__ import annotations

import logging
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from pipeline import (  # noqa: E402
    DB_PATH,
    MATCHER_INDEX_DIR,
    _build_or_load_faiss,
    _build_or_load_tfidf,
    _init_database,
    _load_data,
    _run_batch_processing,
)
from src.database import init_db  # noqa: E402
from src.matcher import ProductMatcher  # noqa: E402


def main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )
    os.environ["TRENDBOX_DB_PATH"] = str(DB_PATH)
    os.environ["TRENDBOX_MATCHER_INDEX"] = str(MATCHER_INDEX_DIR)

    init_db(str(DB_PATH))
    df_barcoded, df_unmatched = _load_data()
    _init_database(df_barcoded, df_unmatched)

    matcher = ProductMatcher()
    _build_or_load_tfidf(matcher, df_barcoded, rebuild=False)
    _build_or_load_faiss(matcher, df_barcoded, rebuild=False)

    counts = _run_batch_processing(matcher)
    print(
        f"Batch finished: {counts['auto_approved']:,} auto-approved, "
        f"{counts['pending']:,} pending, {counts['auto_rejected']:,} auto-rejected"
    )


if __name__ == "__main__":
    main()
