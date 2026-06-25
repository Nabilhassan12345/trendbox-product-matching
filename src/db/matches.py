"""Match persistence and operator review actions."""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from src.db.models import (
    OPEN_STATUSES,
    STATUS_ALTERNATIVE,
    STATUS_APPROVED,
    STATUS_AUTO_REJECTED,
    STATUS_PENDING,
    STATUS_REJECTED,
    STATUS_SUPERSEDED,
    Decision,
    Match,
)
from src.db.session import get_session

logger = logging.getLogger(__name__)

_MATCH_REQUIRED_KEYS = {
    "unmatched_product_id",
    "suggested_product_id",
    "tfidf_score",
    "embedding_score",
    "confidence_score",
    "confidence_label",
    "rank",
    "status",
}


def _records_from_dicts(matches: List[Dict[str, Any]]) -> List[Match]:
    records: List[Match] = []
    for item in matches:
        missing = _MATCH_REQUIRED_KEYS - item.keys()
        if missing:
            raise ValueError(f"Match record missing keys: {sorted(missing)}")
        records.append(
            Match(
                unmatched_product_id=int(item["unmatched_product_id"]),
                suggested_product_id=int(item["suggested_product_id"]),
                tfidf_score=float(item["tfidf_score"]),
                embedding_score=float(item["embedding_score"]),
                confidence_score=float(item["confidence_score"]),
                confidence_label=str(item["confidence_label"]),
                rank=int(item["rank"]),
                status=str(item["status"]),
                query_weight=item.get("query_weight"),
                suggested_weight=item.get("suggested_weight"),
                size_verdict=item.get("size_verdict"),
                brand_match=item.get("brand_match"),
                guardrail_applied=bool(item.get("guardrail_applied", False)),
            )
        )
    return records


def save_matches(matches: List[Dict[str, Any]]) -> int:
    """Persist a batch of match suggestions."""
    if not matches:
        logger.warning("save_matches called with empty list")
        return 0

    records = _records_from_dicts(matches)
    with get_session() as session:
        session.add_all(records)

    logger.info("Saved %s match records", f"{len(records):,}")
    return len(records)


def replace_matches(matches: List[Dict[str, Any]]) -> int:
    """Replace all match suggestions in a single transaction."""
    if not matches:
        logger.warning("replace_matches called with empty list — keeping existing matches")
        return 0

    records = _records_from_dicts(matches)
    with get_session() as session:
        session.query(Decision).delete()
        session.query(Match).delete()
        session.add_all(records)

    logger.info("Replaced match table with %s records", f"{len(records):,}")
    return len(records)


def get_next_pending() -> Optional[Dict[str, Any]]:
    """Return the oldest pending match for human review."""
    with get_session() as session:
        match = (
            session.query(Match)
            .filter(Match.status == "pending")
            .order_by(Match.rank, Match.id)
            .first()
        )
        if match is None:
            return None
        return match.to_dict(include_products=True)


def save_decision(match_id: int, decision: str, note: str = "") -> Dict[str, Any]:
    """Record an operator decision and update the match status."""
    decision = decision.lower().strip()
    if decision not in {"approved", "rejected"}:
        raise ValueError("decision must be 'approved' or 'rejected'")

    with get_session() as session:
        match = session.get(Match, match_id)
        if match is None:
            raise ValueError(f"Match id={match_id} not found")

        match.status = STATUS_APPROVED if decision == "approved" else STATUS_REJECTED
        record = Decision(
            match_id=match_id,
            decision=decision,
            operator_note=note or None,
        )
        session.add(record)

        superseded = (
            session.query(Match)
            .filter(
                Match.unmatched_product_id == match.unmatched_product_id,
                Match.id != match_id,
                Match.status.in_(OPEN_STATUSES),
            )
            .update({Match.status: STATUS_SUPERSEDED}, synchronize_session=False)
        )

        session.flush()
        logger.info(
            "Match %s marked %s (%s sibling suggestion(s) superseded)",
            match_id,
            decision,
            superseded,
        )
        return record.to_dict()


def reopen_auto_rejected(match_id: int) -> Dict[str, Any]:
    """Move an auto-rejected rank-1 match back into the pending review queue."""
    with get_session() as session:
        match = session.get(Match, match_id)
        if match is None:
            raise ValueError(f"Match id={match_id} not found")
        if match.rank != 1:
            raise ValueError("Only rank-1 matches can be re-queued")
        if match.status != STATUS_AUTO_REJECTED:
            raise ValueError("Only auto-rejected matches can be re-queued")

        match.status = STATUS_PENDING
        restored = (
            session.query(Match)
            .filter(
                Match.unmatched_product_id == match.unmatched_product_id,
                Match.id != match_id,
                Match.status == STATUS_SUPERSEDED,
            )
            .update({Match.status: STATUS_ALTERNATIVE}, synchronize_session=False)
        )
        session.flush()
        logger.info(
            "Match %s re-queued for review (%s sibling suggestion(s) restored)",
            match_id,
            restored,
        )
        return match.to_dict(include_products=True)
