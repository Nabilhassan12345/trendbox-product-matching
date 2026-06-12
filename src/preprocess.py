"""Turkish product-name cleaning and enrichment for the matching pipeline."""

from __future__ import annotations

import logging
import re
import unicodedata
from typing import List, Tuple

import pandas as pd

logger = logging.getLogger(__name__)

# Turkish character folding to ASCII equivalents (upper and lower case).
_TURKISH_MAP = str.maketrans(
    {
        "ı": "i",
        "İ": "i",
        "ş": "s",
        "Ş": "s",
        "ğ": "g",
        "Ğ": "g",
        "ü": "u",
        "Ü": "u",
        "ö": "o",
        "Ö": "o",
        "ç": "c",
        "Ç": "c",
    }
)

# Number + unit token; \s* allows attached forms like "400gr".
_UNIT_PATTERN = re.compile(
    r"(\d+(?:[.,]\d+)?)\s*(gr|gram|g|kg|ml|lt|l|litre)\b",
    re.IGNORECASE,
)

_NON_ALNUM_SPACE = re.compile(r"[^a-z0-9\s]")
_MULTI_SPACE = re.compile(r"\s+")

# Pack/count tokens common on fresh produce (not FMCG pack sizes).
_FRESH_COUNT_TOKENS = frozenset({"adet", "demet", "paket", "buketi", "demeti"})

ProductKind = str  # "branded" | "fresh" | "unknown"


def _canonical_unit(unit: str) -> str:
    """Map a raw unit token to its canonical short form."""
    token = unit.lower().strip()
    if token in ("gr", "gram", "g"):
        return "g"
    if token == "kg":
        return "kg"
    if token == "ml":
        return "ml"
    if token in ("lt", "l", "litre"):
        return "l"
    return token


def _standardize_units(text: str) -> str:
    """Rewrite weight/volume tokens to canonical ``'<number> <unit>'`` form."""

    def _replace(match: re.Match[str]) -> str:
        number = match.group(1).replace(",", ".")
        unit = _canonical_unit(match.group(2))
        return f"{number} {unit}"

    return _UNIT_PATTERN.sub(_replace, text)


def normalize(text: str) -> str:
    """Normalise a single Turkish product name for matching.

    Steps: lowercase, strip, Turkish character folding, unit standardisation,
    remove non-alphanumeric characters, collapse whitespace.

    Args:
        text: Raw product name.

    Returns:
        Cleaned, normalised product name.
    """
    if not text or not isinstance(text, str):
        return ""

    # NFKC first so composed characters behave consistently.
    cleaned = unicodedata.normalize("NFKC", text)
    cleaned = cleaned.translate(_TURKISH_MAP).lower().strip()
    cleaned = _standardize_units(cleaned)
    cleaned = _NON_ALNUM_SPACE.sub(" ", cleaned)
    cleaned = _MULTI_SPACE.sub(" ", cleaned).strip()
    return cleaned


def normalize_batch(names: List[str]) -> List[str]:
    """Apply :func:`normalize` to a list of product names.

    Logs progress every 10,000 items.

    Args:
        names: List of raw product names.

    Returns:
        List of normalised names in the same order.
    """
    total = len(names)
    logger.info("Normalising %s product names", f"{total:,}")

    results: List[str] = []
    for index, name in enumerate(names, start=1):
        results.append(normalize(name))
        if index % 10_000 == 0:
            logger.info("Normalised %s / %s names", f"{index:,}", f"{total:,}")

    logger.info("Finished normalising %s names", f"{total:,}")
    return results


def extract_brand(name: str) -> str:
    """Return the first word of a product name as the brand token.

    Args:
        name: Product name (preferably already normalised).

    Returns:
        First whitespace-delimited token, or an empty string.
    """
    if not name or not isinstance(name, str):
        return ""
    parts = name.strip().split()
    return parts[0] if parts else ""


def classify_product_kind(
    name_clean: str,
    brand: str = "",
    weight: str = "",
) -> ProductKind:
    """Classify a product as branded FMCG, fresh produce, or unknown.

    Fresh produce is detected from count tokens (``adet``, ``demet``, ``paket``)
    without a parsed pack weight — the first word is usually the item name, not
    a manufacturer brand.
    """
    if not name_clean or not isinstance(name_clean, str):
        return "unknown"

    parts = name_clean.strip().split()
    if not parts:
        return "unknown"

    if parts[-1] in _FRESH_COUNT_TOKENS and not weight:
        return "fresh"

    if weight:
        return "branded"

    if len(parts) >= 3:
        return "branded"

    return "unknown"


def extract_weight(name: str) -> str:
    """Extract a weight/volume phrase such as ``'400 g'`` or ``'1 kg'``.

    Accepts all unit variants handled by :func:`normalize` — ``gr``, ``gram``,
    ``g``, ``kg``, ``ml``, ``lt``, ``l``, and ``litre`` — on raw or cleaned
    names.

    Args:
        name: Product name (raw or normalised).

    Returns:
        Canonical ``'<number> <unit>'`` string, or empty if not found.
    """
    if not name or not isinstance(name, str):
        return ""

    match = _UNIT_PATTERN.search(name)
    if not match:
        return ""

    number = match.group(1).replace(",", ".")
    unit = _canonical_unit(match.group(2))
    return f"{number} {unit}"


def enrich_dataframe(df: pd.DataFrame) -> pd.DataFrame:
    """Add ``brand`` and ``weight`` columns derived from product names.

    Uses ``name_clean`` when present, otherwise ``name``.

    Args:
        df: DataFrame with at least a ``name`` column.

    Returns:
        Copy of ``df`` with ``brand`` and ``weight`` columns added.
    """
    if "name" not in df.columns:
        raise ValueError("DataFrame must contain a 'name' column")

    source_col = "name_clean" if "name_clean" in df.columns else "name"
    logger.info("Enriching %s rows from column '%s'", f"{len(df):,}", source_col)

    enriched = df.copy()
    enriched["brand"] = enriched[source_col].apply(extract_brand)
    enriched["weight"] = enriched[source_col].apply(extract_weight)
    enriched["product_kind"] = enriched.apply(
        lambda row: classify_product_kind(
            str(row[source_col]),
            str(row.get("brand", "") or ""),
            str(row.get("weight", "") or ""),
        ),
        axis=1,
    )
    return enriched


def load_and_clean(filepath: str) -> Tuple[pd.DataFrame, pd.DataFrame]:
    """Load the raw CSV, clean names, and split into barcoded / unmatched sets.

    Args:
        filepath: Path to the pipe-separated ``mix_products.csv`` file.

    Returns:
        Tuple of ``(df_barcoded, df_unmatched)`` with ``name_clean``, ``brand``,
        and ``weight`` columns on both frames.
    """
    logger.info("Loading product data from %s", filepath)

    df_raw = pd.read_csv(
        filepath,
        sep="|",
        dtype=str,
        keep_default_na=False,
    )
    df_raw.columns = ["barcode", "name"]
    df_raw["barcode"] = df_raw["barcode"].str.replace("^", "", regex=False).str.strip()
    df_raw["name"] = df_raw["name"].str.replace("^", "", regex=False).str.strip()

    if df_raw["barcode"].str.contains("^", regex=False).any():
        raise ValueError("Failed to strip '^' from barcode column")
    if df_raw["name"].str.contains("^", regex=False).any():
        raise ValueError("Failed to strip '^' from name column")

    # Drop the literal header row when it is read as data.
    df = df_raw[df_raw["barcode"] != "barcode"].reset_index(drop=True)
    logger.info("Loaded %s rows after header removal", f"{len(df):,}")

    df_barcoded = df[df["barcode"] != ""].reset_index(drop=True)
    df_unmatched = df[df["barcode"] == ""].reset_index(drop=True)
    logger.info(
        "Split: %s barcoded, %s unmatched",
        f"{len(df_barcoded):,}",
        f"{len(df_unmatched):,}",
    )

    for frame in (df_barcoded, df_unmatched):
        frame["name_clean"] = normalize_batch(frame["name"].tolist())

    df_barcoded = enrich_dataframe(df_barcoded)
    df_unmatched = enrich_dataframe(df_unmatched)

    logger.info("Cleaning and enrichment complete")
    return df_barcoded, df_unmatched


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )

    DATA_PATH = "data/mix_products.csv"

    df_barcoded, df_unmatched = load_and_clean(DATA_PATH)

    print("\n=== Before / After (10 real products) ===\n")
    sample = pd.concat(
        [
            df_barcoded[["name", "name_clean", "brand", "weight"]].head(5),
            df_unmatched[["name", "name_clean", "brand", "weight"]].head(5),
        ],
        ignore_index=True,
    )
    for _, row in sample.iterrows():
        print(f"  BEFORE : {row['name']}")
        print(f"  AFTER  : {row['name_clean']}")
        print(f"  BRAND  : {row['brand'] or '(none)'}")
        print(f"  WEIGHT : {row['weight'] or '(none)'}")
        print()

    print("=== Normalisation Tests ===\n")
    test_cases = {
        "NUTELLA 400GR": "nutella 400 g",
        "Ülker Hanimeller 150g": "ulker hanimeller 150 g",
        "Şeker  500   gr": "seker 500 g",
        "Çikolata 1KG": "cikolata 1 kg",
        "KAHVE 100ML": "kahve 100 ml",
    }

    for raw, expected in test_cases.items():
        result = normalize(raw)
        status = "PASS" if result == expected else "FAIL"
        print(f"  [{status}] {raw!r}")
        print(f"         expected: {expected!r}")
        if status == "FAIL":
            print(f"         got     : {result!r}")
        print()

    print("=== extract_weight Unit Variation Tests ===\n")
    weight_cases = {
        "NUTELLA 400GR": "400 g",
        "Çikolata 1KG": "1 kg",
        "KAHVE 100ML": "100 ml",
        "Sut 1 litre": "1 l",
        "Su 2 lt": "2 l",
        "Un 500 gram": "500 g",
        "Bal 150 g": "150 g",
        "Yag 1L": "1 l",
    }

    for raw, expected in weight_cases.items():
        result = extract_weight(raw)
        status = "PASS" if result == expected else "FAIL"
        print(f"  [{status}] {raw!r}")
        print(f"         expected: {expected!r}")
        if status == "FAIL":
            print(f"         got     : {result!r}")
        print()

    print(
        f"Dataset summary — barcoded: {len(df_barcoded):,}, "
        f"unmatched: {len(df_unmatched):,}"
    )
