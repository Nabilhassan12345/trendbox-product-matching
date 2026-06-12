"""Catalog ingestion: deduplication and bulk product load."""

from __future__ import annotations

import logging
from typing import Any, Dict

import pandas as pd

from src.db.models import Decision, Match, Product
from src.db.session import get_session

logger = logging.getLogger(__name__)


def dedupe_barcoded(df: pd.DataFrame) -> pd.DataFrame:
    """Drop duplicate barcodes, keeping the first occurrence."""
    before = len(df)
    deduped = df.drop_duplicates(subset=["barcode"], keep="first").reset_index(drop=True)
    dropped = before - len(deduped)
    if dropped:
        logger.warning("Dropped %s duplicate barcoded products (kept first per barcode)", f"{dropped:,}")
    return deduped


def dedupe_unmatched(df: pd.DataFrame) -> pd.DataFrame:
    """Drop duplicate unmatched names, keeping the first occurrence."""
    before = len(df)
    deduped = df.drop_duplicates(subset=["name_clean"], keep="first").reset_index(drop=True)
    dropped = before - len(deduped)
    if dropped:
        logger.warning("Dropped %s duplicate unmatched products (kept first per name)", f"{dropped:,}")
    return deduped


def _product_from_row(row: pd.Series, has_barcode: bool) -> Product:
    barcode = row.get("barcode") or None
    if barcode == "":
        barcode = None
    brand = row.get("brand") or None
    weight = row.get("weight") or None
    return Product(
        barcode=barcode,
        name=str(row["name"]),
        name_clean=str(row["name_clean"]),
        brand=brand if brand else None,
        weight=weight if weight else None,
        has_barcode=has_barcode,
    )


def load_products(df_barcoded: pd.DataFrame, df_unmatched: pd.DataFrame) -> Dict[str, int]:
    """Load barcoded and unmatched products into the database."""
    required = {"name", "name_clean"}
    for label, frame in (("df_barcoded", df_barcoded), ("df_unmatched", df_unmatched)):
        missing = required - set(frame.columns)
        if missing:
            raise ValueError(f"{label} missing columns: {sorted(missing)}")

    df_barcoded = dedupe_barcoded(df_barcoded)
    df_unmatched = dedupe_unmatched(df_unmatched)

    with get_session() as session:
        session.query(Decision).delete()
        session.query(Match).delete()
        deleted = session.query(Product).delete()
        if deleted:
            logger.info("Cleared %s existing products (and related rows)", f"{deleted:,}")

        barcoded_rows = [_product_from_row(row, has_barcode=True) for _, row in df_barcoded.iterrows()]
        unmatched_rows = [_product_from_row(row, has_barcode=False) for _, row in df_unmatched.iterrows()]

        session.add_all(barcoded_rows + unmatched_rows)
        session.flush()

        counts = {"barcoded": len(barcoded_rows), "unmatched": len(unmatched_rows)}
        logger.info(
            "Loaded %s barcoded and %s unmatched products",
            f"{counts['barcoded']:,}",
            f"{counts['unmatched']:,}",
        )
        return counts
