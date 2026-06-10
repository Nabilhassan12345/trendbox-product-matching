#!/usr/bin/env python3
"""Single entry point for the Trendbox product matching system."""

from __future__ import annotations

import argparse
import logging
import os
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

from src.confidence import triage
from src.database import Match, Product, get_session, init_db, load_products, replace_matches
from src.matcher import ProductMatcher
from src.preprocess import load_and_clean

# ── Paths ────────────────────────────────────────────────────────────────────
DATA_CSV = ROOT / "data" / "mix_products.csv"
DB_PATH = ROOT / "data" / "matching.db"
TFIDF_CACHE_DIR = ROOT / "data" / "tfidf_cache"
FAISS_CACHE_DIR = ROOT / "data" / "faiss_cache"
TFIDF_CACHE_FILE = TFIDF_CACHE_DIR / "tfidf.joblib"
FAISS_INDEX_BASE = FAISS_CACHE_DIR / "embedding_index"
EMBEDDINGS_CACHE = FAISS_CACHE_DIR / "reference_embeddings.npy"
MATCHER_INDEX_DIR = ROOT / "data" / "matcher_index"
UI_APP = ROOT / "ui" / "app.py"

API_PORT = 8000
UI_PORT = 8501
TOP_SUGGESTIONS = 3
CATALOG_TOTAL = 100_585

REQUIRED_PATHS = (
    DATA_CSV,
    ROOT / "api" / "main.py",
    ROOT / "api" / "schemas.py",
    ROOT / "src" / "preprocess.py",
    ROOT / "src" / "tfidf_retriever.py",
    ROOT / "src" / "embedding_reranker.py",
    ROOT / "src" / "confidence.py",
    ROOT / "src" / "matcher.py",
    ROOT / "src" / "database.py",
    ROOT / "ui" / "pages" / "01_Review.py",
    ROOT / "ui" / "pages" / "02_Analytics.py",
    ROOT / "notebooks" / "01_exploration.ipynb",
    ROOT / "notebooks" / "02_experiments.ipynb",
    ROOT / "tests" / "run_all_tests.py",
    ROOT / "tests" / "test_api.py",
    UI_APP,
    ROOT / "requirements.txt",
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


def _init_database(df_barcoded: Any, df_unmatched: Any) -> dict[str, int]:
    start = _step("Step 4 — Initializing database")
    os.environ["TRENDBOX_DB_PATH"] = str(DB_PATH)
    os.environ["TRENDBOX_MATCHER_INDEX"] = str(MATCHER_INDEX_DIR)

    try:
        init_db(str(DB_PATH))
        counts = load_products(df_barcoded, df_unmatched)
    except Exception as exc:
        _fail(f"Database initialization failed: {exc}", "Delete data/matching.db and retry.")

    _done(start, f"Inserted {counts['barcoded']:,} barcoded + {counts['unmatched']:,} unmatched products")
    return counts


def _faiss_cache_ready() -> bool:
    return FAISS_INDEX_BASE.with_suffix(".faiss").exists() and Path(
        f"{FAISS_INDEX_BASE}_meta.joblib"
    ).exists()


def _build_or_load_tfidf(matcher: ProductMatcher, df_barcoded: Any, rebuild: bool) -> None:
    start = _step("Step 5 — TF-IDF index")
    TFIDF_CACHE_DIR.mkdir(parents=True, exist_ok=True)

    if not rebuild and TFIDF_CACHE_FILE.exists():
        try:
            matcher.tfidf.load(str(TFIDF_CACHE_FILE))
            _done(start, "Loaded TF-IDF from cache")
            return
        except Exception as exc:
            print(f"  ⚠ Cache load failed ({exc}) — rebuilding…")

    try:
        build_start = time.perf_counter()
        matcher.tfidf.fit(df_barcoded)
        matcher.tfidf.save(str(TFIDF_CACHE_FILE))
        elapsed = time.perf_counter() - build_start
        print(f"  ✓ Built TF-IDF index in {elapsed:.1f}s")
    except Exception as exc:
        _fail(f"TF-IDF build failed: {exc}", "Check that barcoded products have valid name_clean values.")


def _build_or_load_faiss(matcher: ProductMatcher, df_barcoded: Any, rebuild: bool) -> None:
    start = _step("Step 6 — FAISS embedding index")
    FAISS_CACHE_DIR.mkdir(parents=True, exist_ok=True)

    if not rebuild and _faiss_cache_ready():
        try:
            matcher.embedder.load_index(str(FAISS_INDEX_BASE))
            matcher._built = True
            _done(start, "Loaded FAISS from cache")
            _sync_matcher_index(matcher)
            return
        except Exception as exc:
            print(f"  ⚠ Cache load failed ({exc}) — rebuilding…")

    try:
        build_start = time.perf_counter()
        matcher.embedder.build_faiss_index(df_barcoded, embeddings_path=str(EMBEDDINGS_CACHE))
        matcher.embedder.save_index(str(FAISS_INDEX_BASE))
        matcher._built = True
        elapsed = time.perf_counter() - build_start
        print(f"  ✓ Built FAISS index in {elapsed:.1f}s")
        _sync_matcher_index(matcher)
    except Exception as exc:
        _fail(
            f"FAISS build failed: {exc}",
            "Ensure sentence-transformers and faiss-cpu are installed; first run downloads the model.",
        )


def _sync_matcher_index(matcher: ProductMatcher) -> None:
    """Write a unified index snapshot for the FastAPI startup loader."""
    MATCHER_INDEX_DIR.mkdir(parents=True, exist_ok=True)
    matcher.save(str(MATCHER_INDEX_DIR))


def _triage_status(confidence_score: float) -> str:
    action = triage(confidence_score)
    if action == "auto_approve":
        return "auto_approved"
    if action == "auto_reject":
        return "auto_rejected"
    return "pending"


def _run_batch_processing(matcher: ProductMatcher) -> dict[str, int]:
    start = _step("Step 7 — Batch processing (match + triage)")
    if not matcher._built:
        _fail("Matcher is not built — cannot run batch processing.")

    with get_session() as session:
        unmatched_products = [
            (product.id, product.name)
            for product in session.query(Product)
            .filter(Product.has_barcode.is_(False))
            .order_by(Product.id)
            .all()
        ]
        barcode_rows = (
            session.query(Product.id, Product.barcode)
            .filter(Product.has_barcode.is_(True), Product.barcode.isnot(None))
            .order_by(Product.id)
            .all()
        )
        barcode_to_id: dict[str, int] = {}
        for product_id, barcode in barcode_rows:
            if barcode not in barcode_to_id:
                barcode_to_id[barcode] = product_id

    total = len(unmatched_products)
    if total == 0:
        _fail("No unmatched products in database.", "Check data/mix_products.csv has rows without barcodes.")

    print(f"  Matching {total:,} unmatched products (this may take a while)…")
    records: list[dict[str, Any]] = []
    counts = {"auto_approved": 0, "auto_rejected": 0, "pending": 0}
    batch_start = time.perf_counter()

    for index, (product_id, product_name) in enumerate(unmatched_products, start=1):
        hits = matcher.match(product_name)[:TOP_SUGGESTIONS]
        for hit in hits:
            suggested_id = barcode_to_id.get(str(hit["barcode"]))
            if suggested_id is None:
                continue

            status = _triage_status(hit["confidence_score"])
            counts[status] += 1
            records.append(
                {
                    "unmatched_product_id": product_id,
                    "suggested_product_id": suggested_id,
                    "tfidf_score": hit["tfidf_score"],
                    "embedding_score": hit["embedding_score"],
                    "confidence_score": hit["confidence_score"],
                    "confidence_label": hit["confidence_label"],
                    "rank": hit["rank"],
                    "status": status,
                }
            )

        if index % 500 == 0 or index == total:
            elapsed = time.perf_counter() - batch_start
            rate = index / elapsed if elapsed else 0
            print(f"  … {index:,}/{total:,} products ({rate:.1f}/s)")

    replace_matches(records)
    elapsed = time.perf_counter() - batch_start
    print(
        f"  ✓ Batch complete in {elapsed:.1f}s — "
        f"{counts['auto_approved']:,} auto-approved, "
        f"{counts['pending']:,} pending, "
        f"{counts['auto_rejected']:,} auto-rejected"
    )
    _done(start, f"{len(records):,} suggestions saved")
    return counts


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

    # Wait until health endpoint responds (max 30s).
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

    print(BANNER)
    if args.rebuild:
        print("  ↳ --rebuild: indexes will be rebuilt from scratch\n")

    pipeline_start = time.perf_counter()

    _check_required_files()
    df_barcoded, df_unmatched = _load_data()
    db_counts = _init_database(df_barcoded, df_unmatched)
    products_loaded = db_counts["barcoded"] + db_counts["unmatched"]

    matcher = ProductMatcher()
    _build_or_load_tfidf(matcher, df_barcoded, rebuild=args.rebuild)
    _build_or_load_faiss(matcher, df_barcoded, rebuild=args.rebuild)

    if args.skip_batch:
        counts = {"auto_approved": 0, "auto_rejected": 0, "pending": 0}
        print("\n▶ Step 7 — Batch processing skipped (--skip-batch)")
    else:
        counts = _run_batch_processing(matcher)

    _print_summary(products_loaded, counts)
    _start_api_background()
    _open_browser()
    _start_streamlit()

    print(f"\nTotal pipeline setup time: {time.perf_counter() - pipeline_start:.1f}s")


if __name__ == "__main__":
    main()
