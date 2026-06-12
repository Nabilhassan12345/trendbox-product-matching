#!/usr/bin/env python3
"""Run all pre-submission verification checks for trendbox-product-matching."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

REQUIRED_FILES = (
    "src/preprocess.py",
    "src/tfidf_retriever.py",
    "src/embedding_reranker.py",
    "src/confidence.py",
    "src/matcher.py",
    "src/database.py",
    "api/main.py",
    "api/schemas.py",
    "ui/pages/01_Review.py",
    "ui/pages/02_Analytics.py",
    "notebooks/01_exploration.ipynb",
    "notebooks/02_experiments.ipynb",
    "pipeline.py",
    "tests/run_all_tests.py",
    "tests/test_preprocess.py",
    "tests/test_matcher.py",
    "tests/test_api.py",
    "tests/test_match_metadata.py",
    "tests/test_blocking.py",
    "tests/test_product_kind.py",
    "data/mix_products.csv",
    "requirements.txt",
)

IMPORT_MODULES = (
    "src.preprocess",
    "src.tfidf_retriever",
    "src.embedding_reranker",
    "src.confidence",
    "src.matcher",
    "src.database",
    "api.main",
    "api.schemas",
)


def check_files() -> bool:
    """Verify required submission files exist and are non-empty."""
    print("=== Required files ===\n")
    ok = True
    for rel in REQUIRED_FILES:
        path = ROOT / rel
        exists = path.is_file()
        size = path.stat().st_size if exists else 0
        valid = exists and size > 0
        status = "PASS" if valid else "FAIL"
        print(f"[{status}] {rel} ({size:,} bytes)")
        ok = ok and valid
    return ok


def check_imports() -> bool:
    """Verify core modules import without error."""
    print("\n=== Module imports ===\n")
    sys.path.insert(0, str(ROOT))
    ok = True
    for module in IMPORT_MODULES:
        try:
            __import__(module)
            print(f"[PASS] import {module}")
        except Exception as exc:
            print(f"[FAIL] import {module} — {exc}")
            ok = False
    return ok


def check_data_load() -> bool:
    """Verify CSV loads with expected row counts."""
    print("\n=== Data load smoke test ===\n")
    sys.path.insert(0, str(ROOT))
    try:
        from src.preprocess import load_and_clean

        df_barcoded, df_unmatched = load_and_clean(str(ROOT / "data" / "mix_products.csv"))
        total = len(df_barcoded) + len(df_unmatched)
        checks = [
            ("total rows == 100,585", total == 100_585),
            ("barcoded rows == 58,434", len(df_barcoded) == 58_434),
            ("unmatched rows > 0", len(df_unmatched) > 0),
        ]
        ok = True
        for name, passed in checks:
            status = "PASS" if passed else "FAIL"
            print(f"[{status}] {name}")
            ok = ok and passed
        print(f"  barcoded={len(df_barcoded):,}, unmatched={len(df_unmatched):,}")
        return ok
    except Exception as exc:
        print(f"[FAIL] load_and_clean — {exc}")
        return False


def _run_test_file(filename: str, header: str) -> bool:
    """Run a standalone test file as a subprocess; pass on exit code 0."""
    print(f"\n=== {header} ===\n")
    result = subprocess.run(
        [sys.executable, str(ROOT / "tests" / filename)],
        cwd=str(ROOT),
    )
    return result.returncode == 0


def main() -> int:
    """Run all checks and return a process exit code."""
    results = [
        check_files(),
        check_imports(),
        check_data_load(),
        _run_test_file("test_preprocess.py", "Preprocessing unit tests"),
        _run_test_file("test_match_metadata.py", "Match metadata unit tests"),
        _run_test_file("test_blocking.py", "Stage 0 blocking tests"),
        _run_test_file("test_product_kind.py", "Product kind tests"),
        _run_test_file("test_matcher.py", "Matcher end-to-end tests"),
        _run_test_file("test_api.py", "API integration tests"),
    ]
    passed = sum(results)
    total = len(results)
    print(f"\n=== Verification summary: {passed}/{total} suites passed ===")
    return 0 if all(results) else 1


if __name__ == "__main__":
    sys.exit(main())
