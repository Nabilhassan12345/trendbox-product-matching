"""Reference catalogue preparation: canonical DB rows vs full alias search index."""

from __future__ import annotations

import logging
from typing import Dict, List, Set

import pandas as pd

from src.database import _dedupe_barcoded, _dedupe_unmatched
from src.preprocess import enrich_dataframe

logger = logging.getLogger(__name__)


def canonical_barcoded(df_barcoded: pd.DataFrame) -> pd.DataFrame:
    """Return one row per barcode for SQLite persistence."""
    return _dedupe_barcoded(df_barcoded)


def canonical_unmatched(df_unmatched: pd.DataFrame) -> pd.DataFrame:
    """Return one row per cleaned unmatched name for SQLite persistence."""
    return _dedupe_unmatched(df_unmatched)


def prepare_reference_index(df_barcoded: pd.DataFrame) -> pd.DataFrame:
    """Return all barcoded alias rows for TF-IDF / FAISS indexing.

    Every ERP spelling of the same barcode remains searchable. Rows must already
    carry ``name_clean``, ``brand``, ``weight``, and ``product_kind``.
    """
    required = {"barcode", "name", "name_clean"}
    missing = required - set(df_barcoded.columns)
    if missing:
        raise ValueError(f"df_barcoded missing columns: {sorted(missing)}")
    if (df_barcoded["barcode"] == "").any():
        raise ValueError("Reference index must not contain empty barcodes")

    index_df = df_barcoded.reset_index(drop=True).copy()
    if "brand" not in index_df.columns or "weight" not in index_df.columns:
        index_df = enrich_dataframe(index_df)

    logger.info(
        "Prepared reference index with %s alias rows (%s unique barcodes)",
        f"{len(index_df):,}",
        f"{index_df['barcode'].nunique():,}",
    )
    return index_df


def build_name_to_barcodes(df_index: pd.DataFrame) -> Dict[str, Set[str]]:
    """Map normalised names to the set of barcodes that use that spelling."""
    mapping: Dict[str, Set[str]] = {}
    for name_clean, barcode in zip(df_index["name_clean"], df_index["barcode"]):
        key = str(name_clean)
        code = str(barcode)
        if not key or not code:
            continue
        mapping.setdefault(key, set()).add(code)
    return mapping


def build_barcode_lookup(df_index: pd.DataFrame) -> Dict[str, dict]:
    """Map barcode to a representative row (first alias) for Stage 0 hits."""
    lookup: Dict[str, dict] = {}
    for row in df_index.itertuples(index=False):
        code = str(row.barcode)
        if code not in lookup:
            lookup[code] = {
                "barcode": code,
                "name": str(row.name),
                "name_clean": str(row.name_clean),
            }
    return lookup
