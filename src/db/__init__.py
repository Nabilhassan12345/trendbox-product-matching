"""Database package: ORM models, sessions, catalog load, matches, analytics."""

from src.db.analytics import (
    OUTCOME_STATUSES,
    get_confidence_scores,
    get_daily_outcome_counts,
    get_pipeline_stats,
    get_recent_activity,
    get_recent_decisions,
    get_recent_matches_by_outcome,
    get_stats,
)
from src.db.catalog import dedupe_barcoded, dedupe_unmatched, load_products
from src.db.matches import (
    get_next_pending,
    reopen_auto_rejected,
    replace_matches,
    save_decision,
    save_matches,
)
from src.db.models import (
    OPEN_STATUSES,
    STATUS_ALTERNATIVE,
    STATUS_APPROVED,
    STATUS_AUTO_APPROVED,
    STATUS_AUTO_REJECTED,
    STATUS_PENDING,
    STATUS_REJECTED,
    STATUS_SUPERSEDED,
    Base,
    Decision,
    Match,
    Product,
)
from src.db.session import get_session, init_db

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
    "dedupe_barcoded",
    "dedupe_unmatched",
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
