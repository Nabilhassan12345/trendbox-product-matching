"""Backward-compatible facade over ``src.db`` submodules.

New code should import from ``src.db`` directly; this module preserves the
original ``from src.database import ...`` surface area.
"""

from __future__ import annotations

from src.db import *  # noqa: F403
from src.db.catalog import dedupe_barcoded as _dedupe_barcoded
from src.db.catalog import dedupe_unmatched as _dedupe_unmatched

__all__ = [
    "OPEN_STATUSES",
    "OUTCOME_STATUSES",
    "STATUS_ALTERNATIVE",
    "STATUS_APPROVED",
    "STATUS_AUTO_APPROVED",
    "STATUS_AUTO_REJECTED",
    "STATUS_PENDING",
    "STATUS_REJECTED",
    "STATUS_SUPERSEDED",
    "Base",
    "Decision",
    "Match",
    "Product",
    "_dedupe_barcoded",
    "_dedupe_unmatched",
    "get_confidence_scores",
    "get_daily_outcome_counts",
    "get_next_pending",
    "get_pipeline_stats",
    "get_recent_activity",
    "get_recent_decisions",
    "get_recent_matches_by_outcome",
    "get_session",
    "get_stats",
    "init_db",
    "load_products",
    "reopen_auto_rejected",
    "replace_matches",
    "save_decision",
    "save_matches",
]
