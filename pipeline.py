#!/usr/bin/env python3
"""Single entry point for the Trendbox product matching system."""

from __future__ import annotations

import argparse
import logging
import socket
import subprocess
import sys
import threading
import time
import webbrowser
from pathlib import Path
from typing import Any

# Ensure project root is on sys.path when run as `python pipeline.py`.
ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.config import (
    API_PORT,
    DATA_CSV,
    REQUIRED_PATHS,
    UI_APP,
    UI_PORT,
    apply_runtime_env,
)

from src.batch import run_full_batch
from src.config import DB_PATH
from src.database import init_db, load_products
from src.index_builder import build_or_load_faiss, build_or_load_tfidf
from src.matcher import ProductMatcher
from src.preprocess import load_and_clean
from src.reference_catalog import (
    canonical_barcoded,
    canonical_unmatched,
    prepare_reference_index,
)

BANNER = """\
╔════════════════════════════════════╗
║  Trendbox Product Matching System  ║
╚════════════════════════════════════╝\
"""


def _configure_logging() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )


def _step(label: str) -> float:
    """Print a step header and return a timer start."""
    print(f"\n▶ {label}")
    return time.perf_counter()


def _done(start: float, message: str = "done") -> None:
    """Print step completion with elapsed time."""
    print(f"  ✓ {message} ({time.perf_counter() - start:.1f}s)")


def _fail(message: str, hint: str = "") -> None:
    """Print a fatal error and exit."""
    print(f"\n❌ ERROR: {message}", file=sys.stderr)
    if hint:
        print(f"   Hint: {hint}", file=sys.stderr)
    sys.exit(1)


def _check_required_files() -> None:
    start = _step("Step 2 — Checking required files")
    missing = [path for path in REQUIRED_PATHS if not path.exists()]
    if missing:
        lines = "\n".join(f"     • {path.relative_to(ROOT)}" for path in missing)
        _fail(
            f"Missing required file(s):\n{lines}",
            "Ensure you are in the project root and data/mix_products.csv is present.",
        )
    _done(start, f"All {len(REQUIRED_PATHS)} required paths found")


def _load_data() -> tuple[Any, Any]:
    start = _step("Step 3 — Loading and cleaning data")
    try:
        df_barcoded, df_unmatched = load_and_clean(str(DATA_CSV))
    except FileNotFoundError:
        _fail(f"Data file not found: {DATA_CSV}", "Place mix_products.csv in data/.")
    except Exception as exc:
        _fail(f"Failed to load CSV: {exc}", "Check the file uses pipe | separators.")

    total = len(df_barcoded) + len(df_unmatched)
    _done(start, f"Loaded {total:,} rows ({len(df_barcoded):,} barcoded, {len(df_unmatched):,} unmatched)")
    return df_barcoded, df_unmatched


def _prepare_catalog(
    df_barcoded: Any,
    df_unmatched: Any,
) -> tuple[Any, Any, Any, Any]:
    """Split raw frames into alias index (search) and canonical rows (SQLite)."""
    df_index = prepare_reference_index(df_barcoded)
    df_canonical_b = canonical_barcoded(df_barcoded)
    df_canonical_u = canonical_unmatched(df_unmatched)
    return df_index, df_canonical_b, df_canonical_u, df_barcoded


def _init_database(df_barcoded: Any, df_unmatched: Any) -> dict[str, int]:
    start = _step("Step 4 — Initializing database")
    apply_runtime_env()

    try:
        init_db(str(DB_PATH))
        counts = load_products(df_barcoded, df_unmatched)
    except Exception as exc:
        _fail(f"Database initialization failed: {exc}", "Delete data/matching.db and retry.")

    _done(start, f"Inserted {counts['barcoded']:,} barcoded + {counts['unmatched']:,} unmatched products")
    return counts


def _run_batch_processing(matcher: ProductMatcher, df_index: Any) -> dict[str, int]:
    start = _step("Step 7 — Batch processing (match + triage)")
    try:
        print("  Matching unmatched products (this may take a while)…")
        batch_start = time.perf_counter()
        _records, counts = run_full_batch(matcher, stage0_df=df_index)
        elapsed = time.perf_counter() - batch_start
        print(
            f"  ✓ Batch complete in {elapsed:.1f}s — "
            f"{counts['stage0_resolved']:,} stage-0, "
            f"{counts['auto_approved']:,} auto-approved, "
            f"{counts['pending']:,} pending, "
            f"{counts['auto_rejected']:,} auto-rejected"
        )
        _done(start, f"{counts['auto_approved'] + counts['pending'] + counts['auto_rejected']:,} products triaged")
        return counts
    except RuntimeError as exc:
        _fail(str(exc))


def _print_summary(products_loaded: int, counts: dict[str, int]) -> None:
    print("\n✅ System Ready")
    print(f"   Products loaded:  {products_loaded:,}")
    print(f"   Auto-approved:    {counts['auto_approved']:,}")
    print(f"   Pending review:   {counts['pending']:,}")
    print(f"   Auto-rejected:    {counts['auto_rejected']:,}")
    print("   Starting server…")


def _port_in_use(port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.settimeout(0.5)
        return sock.connect_ex(("127.0.0.1", port)) == 0


def _start_api_background() -> None:
    start = _step(f"Step 9 — Starting FastAPI on port {API_PORT}")

    if _port_in_use(API_PORT):
        print(f"  ⚠ Port {API_PORT} already in use — assuming API is running")
        _done(start, "Skipped (port busy)")
        return

    def _run() -> None:
        import uvicorn

        uvicorn.run(
            "api.main:app",
            host="127.0.0.1",
            port=API_PORT,
            log_level="info",
            reload=False,
        )

    thread = threading.Thread(target=_run, name="fastapi-server", daemon=True)
    thread.start()

    import requests

    for _ in range(30):
        try:
            response = requests.get(f"http://127.0.0.1:{API_PORT}/health", timeout=1)
            if response.status_code == 200:
                _done(start, f"API listening on http://localhost:{API_PORT}")
                return
        except requests.RequestException:
            pass
        time.sleep(1)

    _fail(
        f"API did not start on port {API_PORT} within 30 seconds.",
        "Check logs above for import or model-loading errors.",
    )


def _open_browser() -> None:
    start = _step("Step 11 — Opening browser")
    time.sleep(2)
    url = f"http://localhost:{UI_PORT}"
    try:
        webbrowser.open(url)
        _done(start, f"Opened {url}")
    except Exception as exc:
        print(f"  ⚠ Could not open browser automatically: {exc}")
        print(f"    Open manually: {url}")


def _start_streamlit() -> None:
    start = _step(f"Step 12 — Starting Streamlit on port {UI_PORT}")

    if _port_in_use(UI_PORT):
        print(f"  ⚠ Port {UI_PORT} already in use — assuming Streamlit is running")
        _done(start, "Skipped (port busy)")
        print(f"\n  UI → http://localhost:{UI_PORT}")
        print(f"  API → http://localhost:{API_PORT}/docs\n")
        return

    _done(start, "Launching UI (Ctrl+C to stop)")
    print(f"\n  UI → http://localhost:{UI_PORT}")
    print(f"  API → http://localhost:{API_PORT}/docs\n")

    import os

    env = os.environ.copy()
    env["PYTHONPATH"] = str(ROOT)

    subprocess.run(
        [
            sys.executable,
            "-m",
            "streamlit",
            "run",
            str(UI_APP),
            "--server.port",
            str(UI_PORT),
            "--server.headless",
            "true",
        ],
        cwd=str(ROOT),
        env=env,
        check=False,
    )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run the Trendbox product matching pipeline.")
    parser.add_argument(
        "--rebuild",
        action="store_true",
        help="Force rebuild of TF-IDF and FAISS indexes (ignore cache).",
    )
    parser.add_argument(
        "--skip-batch",
        action="store_true",
        help="Skip batch matching (use existing match records in DB).",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    _configure_logging()

    try:
        from dotenv import load_dotenv

        load_dotenv()
    except ImportError:
        pass

    print(BANNER)
    if args.rebuild:
        print("  ↳ --rebuild: indexes will be rebuilt from scratch\n")

    pipeline_start = time.perf_counter()

    _check_required_files()
    df_barcoded, df_unmatched = _load_data()
    df_index, df_canonical_b, df_canonical_u, _df_raw_barcoded = _prepare_catalog(
        df_barcoded, df_unmatched
    )
    db_counts = _init_database(df_canonical_b, df_canonical_u)
    products_loaded = db_counts["barcoded"] + db_counts["unmatched"]

    matcher = ProductMatcher()
    tfidf_start = _step("Step 5 — TF-IDF index")
    try:
        tfidf_msg = build_or_load_tfidf(matcher, df_index, rebuild=args.rebuild)
        _done(tfidf_start, tfidf_msg)
    except Exception as exc:
        _fail(f"TF-IDF build failed: {exc}", "Check that barcoded products have valid name_clean values.")

    faiss_start = _step("Step 6 — FAISS embedding index")
    try:
        faiss_msg = build_or_load_faiss(matcher, df_index, rebuild=args.rebuild)
        _done(faiss_start, faiss_msg)
    except Exception as exc:
        _fail(
            f"FAISS build failed: {exc}",
            "Ensure sentence-transformers and faiss-cpu are installed; first run downloads the model.",
        )

    if args.skip_batch:
        counts = {"auto_approved": 0, "auto_rejected": 0, "pending": 0}
        print("\n▶ Step 7 — Batch processing skipped (--skip-batch)")
    else:
        counts = _run_batch_processing(matcher, df_index)

    _print_summary(products_loaded, counts)
    _start_api_background()
    _open_browser()
    _start_streamlit()

    print(f"\nTotal pipeline setup time: {time.perf_counter() - pipeline_start:.1f}s")


if __name__ == "__main__":
    main()
