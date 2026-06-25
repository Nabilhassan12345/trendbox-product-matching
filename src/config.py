"""Central configuration: paths, ports, and runtime defaults.

All values can be overridden via environment variables (see `.env.example`).
Paths are resolved relative to the project root unless an absolute path is given.
"""

from __future__ import annotations

import os
from pathlib import Path

# Project root (parent of `src/`).
ROOT = Path(__file__).resolve().parents[1]


def _path(env_var: str, default: Path) -> Path:
    raw = os.getenv(env_var)
    return Path(raw) if raw else default


# ── Data & persistence ───────────────────────────────────────────────────────
DATA_CSV = _path("TRENDBOX_DATA_CSV", ROOT / "data" / "mix_products.csv")
DB_PATH = _path("TRENDBOX_DB_PATH", ROOT / "data" / "matching.db")
CATALOG_PROFILE_PATH = _path(
    "TRENDBOX_CATALOG_PROFILE",
    ROOT / "data" / "reports" / "catalog_profile.json",
)
EVALUATION_SUMMARY_PATH = ROOT / "data" / "reports" / "evaluation_summary.json"

# ── Matcher index (single canonical cache directory) ───────────────────────────
# pipeline.py builds here; FastAPI loads from here on startup.
#   tfidf.joblib
#   embedding_index.faiss + embedding_index_meta.joblib
#   reference_embeddings.npy
MATCHER_INDEX_DIR = _path("TRENDBOX_MATCHER_INDEX", ROOT / "data" / "matcher_index")
TFIDF_CACHE_FILE = MATCHER_INDEX_DIR / "tfidf.joblib"
FAISS_INDEX_BASE = MATCHER_INDEX_DIR / "embedding_index"
EMBEDDINGS_CACHE = MATCHER_INDEX_DIR / "reference_embeddings.npy"

# Legacy paths kept for evaluate.py when upgrading from older cache layouts.
LEGACY_EMBEDDING_PATHS = (
    ROOT / "data" / "faiss_cache" / "reference_embeddings.npy",
    ROOT / "data" / "reference_embeddings.npy",
)

# ── Services ───────────────────────────────────────────────────────────────────
API_PORT = int(os.getenv("TRENDBOX_API_PORT", "8000"))
UI_PORT = int(os.getenv("TRENDBOX_UI_PORT", "8501"))
API_URL = os.getenv("TRENDBOX_API_URL", f"http://localhost:{API_PORT}")
TOP_SUGGESTIONS = 3

# ── Match quality guardrails ───────────────────────────────────────────────────
_raw_size_policy = os.getenv("TRENDBOX_SIZE_CONFLICT_POLICY", "review").lower().strip()
SIZE_CONFLICT_POLICY = _raw_size_policy if _raw_size_policy in {"review", "reject"} else "review"

UI_APP = ROOT / "ui" / "app.py"

# ── Smoke-test file checklist (pipeline startup + run_all_tests.py) ────────────
REQUIRED_PATHS: tuple[Path, ...] = (
    DATA_CSV,
    ROOT / "api" / "main.py",
    ROOT / "api" / "schemas.py",
    ROOT / "src" / "config.py",
    ROOT / "src" / "db" / "models.py",
    ROOT / "src" / "database.py",
    ROOT / "src" / "preprocess.py",
    ROOT / "src" / "tfidf_retriever.py",
    ROOT / "src" / "embedding_reranker.py",
    ROOT / "src" / "confidence.py",
    ROOT / "src" / "matcher.py",
    ROOT / "ui" / "app.py",
    ROOT / "ui" / "pages" / "01_Review.py",
    ROOT / "ui" / "pages" / "02_Analytics.py",
    ROOT / "ui" / "pages" / "03_Pipeline.py",
    ROOT / "notebooks" / "01_exploration.ipynb",
    ROOT / "notebooks" / "02_experiments.ipynb",
    ROOT / "tests" / "conftest.py",
    ROOT / "tests" / "test_api.py",
    ROOT / "requirements.txt",
)


def apply_runtime_env() -> None:
    """Publish path overrides so API and UI subprocesses see the same config."""
    os.environ.setdefault("TRENDBOX_DB_PATH", str(DB_PATH))
    os.environ.setdefault("TRENDBOX_MATCHER_INDEX", str(MATCHER_INDEX_DIR))
