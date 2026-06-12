"""Catalogue data-quality profiling for Trendbox product matching."""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any, Dict

import pandas as pd

from src.db.catalog import dedupe_barcoded, dedupe_unmatched
from src.preprocess import load_and_clean

logger = logging.getLogger(__name__)


def profile_catalog(filepath: str) -> Dict[str, Any]:
    """Compute data-quality metrics for a pipe-separated product CSV.

    Args:
        filepath: Path to ``mix_products.csv``.

    Returns:
        Nested dict of counts and percentages suitable for JSON export.
    """
    df_barcoded, df_unmatched = load_and_clean(filepath)

    total_rows = len(df_barcoded) + len(df_unmatched)
    barcoded_rows = len(df_barcoded)
    unmatched_rows = len(df_unmatched)

    dup_barcode_mask = df_barcoded.duplicated(subset=["barcode"], keep=False)
    duplicate_barcode_rows = int(dup_barcode_mask.sum())
    barcodes_with_multiple_rows = int(
        df_barcoded.groupby("barcode").size().gt(1).sum()
    )
    barcodes_with_multiple_spellings = int(
        df_barcoded.groupby("barcode")["name_clean"].nunique().gt(1).sum()
    )

    name_to_barcodes = df_barcoded.groupby("name_clean")["barcode"].nunique()
    name_clean_multi_barcode = int(name_to_barcodes.gt(1).sum())

    overlap_exact = int(
        len(set(df_unmatched["name_clean"]) & set(df_barcoded["name_clean"]))
    )

    unmatched_missing_weight = int(
        df_unmatched["weight"].isna().sum()
        + (df_unmatched["weight"] == "").sum()
    )
    barcoded_missing_weight = int(
        df_barcoded["weight"].isna().sum() + (df_barcoded["weight"] == "").sum()
    )

    unmatched_short_names = int(df_unmatched["name_clean"].str.len().lt(8).sum())
    unmatched_short_first_token = int(
        df_unmatched["name_clean"].str.split().str[0].str.len().le(3).sum()
    )

    empty_barcoded_names = int((df_barcoded["name"].str.strip() == "").sum())
    empty_unmatched_names = int((df_unmatched["name"].str.strip() == "").sum())

    canonical_barcoded = dedupe_barcoded(df_barcoded)
    canonical_unmatched = dedupe_unmatched(df_unmatched)
    barcoded_rows_dropped = barcoded_rows - len(canonical_barcoded)
    unmatched_rows_dropped = unmatched_rows - len(canonical_unmatched)

    return {
        "source_file": str(Path(filepath).resolve()),
        "row_counts": {
            "total": total_rows,
            "barcoded": barcoded_rows,
            "unmatched": unmatched_rows,
        },
        "barcode_duplicates": {
            "duplicate_barcode_rows": duplicate_barcode_rows,
            "barcodes_with_multiple_rows": barcodes_with_multiple_rows,
            "barcodes_with_multiple_spellings": barcodes_with_multiple_spellings,
        },
        "name_collisions": {
            "name_clean_mapping_to_multiple_barcodes": name_clean_multi_barcode,
            "unmatched_barcoded_exact_name_clean_overlap": overlap_exact,
        },
        "enrichment_gaps": {
            "unmatched_missing_weight": unmatched_missing_weight,
            "unmatched_missing_weight_pct": round(
                100.0 * unmatched_missing_weight / max(unmatched_rows, 1), 2
            ),
            "barcoded_missing_weight": barcoded_missing_weight,
            "barcoded_missing_weight_pct": round(
                100.0 * barcoded_missing_weight / max(barcoded_rows, 1), 2
            ),
            "unmatched_short_names_lt_8_chars": unmatched_short_names,
            "unmatched_short_first_token_le_3_chars": unmatched_short_first_token,
        },
        "empty_names": {
            "barcoded": empty_barcoded_names,
            "unmatched": empty_unmatched_names,
        },
        "dedupe_impact": {
            "barcoded_rows_before": barcoded_rows,
            "barcoded_rows_after": len(canonical_barcoded),
            "barcoded_rows_dropped": barcoded_rows_dropped,
            "unmatched_rows_before": unmatched_rows,
            "unmatched_rows_after": len(canonical_unmatched),
            "unmatched_rows_dropped": unmatched_rows_dropped,
            "total_rows_after_dedupe": len(canonical_barcoded) + len(canonical_unmatched),
        },
    }


def save_profile_report(profile: Dict[str, Any], output_path: str | Path) -> Path:
    """Write a profile dict to JSON, creating parent directories if needed."""
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(profile, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    logger.info("Wrote catalogue profile to %s", path)
    return path


def format_profile_summary(profile: Dict[str, Any]) -> str:
    """Return a human-readable multi-line summary of key metrics."""
    rc = profile["row_counts"]
    bd = profile["barcode_duplicates"]
    nc = profile["name_collisions"]
    eg = profile["enrichment_gaps"]
    dd = profile["dedupe_impact"]

    lines = [
        "Trendbox catalogue profile",
        f"  Total rows       : {rc['total']:,}",
        f"  Barcoded         : {rc['barcoded']:,}",
        f"  Unmatched        : {rc['unmatched']:,}",
        "",
        "Barcode duplicates",
        f"  Duplicate rows   : {bd['duplicate_barcode_rows']:,}",
        f"  Multi-row codes  : {bd['barcodes_with_multiple_rows']:,}",
        f"  Multi-spell codes: {bd['barcodes_with_multiple_spellings']:,}",
        "",
        "Name collisions",
        f"  name_clean → N barcodes : {nc['name_clean_mapping_to_multiple_barcodes']:,}",
        f"  Exact unmatched overlap : {nc['unmatched_barcoded_exact_name_clean_overlap']:,}",
        "",
        "Enrichment gaps",
        f"  Unmatched missing weight: {eg['unmatched_missing_weight']:,} ({eg['unmatched_missing_weight_pct']}%)",
        "",
        "Dedupe impact (current load_products)",
        f"  Barcoded dropped : {dd['barcoded_rows_dropped']:,}",
        f"  Unmatched dropped: {dd['unmatched_rows_dropped']:,}",
        f"  Rows after dedupe: {dd['total_rows_after_dedupe']:,}",
    ]
    return "\n".join(lines)
