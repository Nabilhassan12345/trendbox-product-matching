#!/usr/bin/env python3
"""Profile Trendbox catalogue data quality and write a JSON report."""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.config import CATALOG_PROFILE_PATH, DATA_CSV
from src.data_profile import format_profile_summary, profile_catalog, save_profile_report

DEFAULT_CSV = DATA_CSV
DEFAULT_OUT = CATALOG_PROFILE_PATH


def main() -> None:
    parser = argparse.ArgumentParser(description="Profile mix_products.csv data quality")
    parser.add_argument(
        "--csv",
        type=Path,
        default=DEFAULT_CSV,
        help=f"Input CSV path (default: {DEFAULT_CSV.relative_to(ROOT)})",
    )
    parser.add_argument(
        "--out",
        type=Path,
        default=DEFAULT_OUT,
        help=f"Output JSON path (default: {DEFAULT_OUT.relative_to(ROOT)})",
    )
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")

    if not args.csv.exists():
        print(f"ERROR: CSV not found: {args.csv}", file=sys.stderr)
        sys.exit(1)

    profile = profile_catalog(str(args.csv))
    out_path = save_profile_report(profile, args.out)
    print(format_profile_summary(profile))
    print(f"\nReport written to: {out_path}")


if __name__ == "__main__":
    main()
