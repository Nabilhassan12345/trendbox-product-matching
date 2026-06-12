"""Read-only analytics queries for dashboards and API endpoints."""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from sqlalchemy import func

from src.db.models import (
    STATUS_APPROVED,
    STATUS_AUTO_APPROVED,
    STATUS_AUTO_REJECTED,
    STATUS_PENDING,
    STATUS_REJECTED,
    Decision,
    Match,
    Product,
)
from src.db.session import get_session

OUTCOME_STATUSES: Dict[str, tuple[str, ...]] = {
    "approved": (STATUS_AUTO_APPROVED, STATUS_APPROVED),
    "rejected": (STATUS_AUTO_REJECTED, STATUS_REJECTED),
    "pending": (STATUS_PENDING,),
}


def get_stats() -> Dict[str, Any]:
    """Return aggregate counts for dashboard and monitoring."""
    with get_session() as session:
        total_products = session.query(func.count(Product.id)).scalar() or 0
        barcoded = (
            session.query(func.count(Product.id)).filter(Product.has_barcode.is_(True)).scalar() or 0
        )
        unmatched = total_products - barcoded

        match_total = session.query(func.count(Match.id)).scalar() or 0
        status_rows = session.query(Match.status, func.count(Match.id)).group_by(Match.status).all()
        matches_by_status = {status: count for status, count in status_rows}

        decision_total = session.query(func.count(Decision.id)).scalar() or 0
        approved = (
            session.query(func.count(Decision.id)).filter(Decision.decision == "approved").scalar() or 0
        )
        rejected = (
            session.query(func.count(Decision.id)).filter(Decision.decision == "rejected").scalar() or 0
        )

        return {
            "products_total": int(total_products),
            "products_barcoded": int(barcoded),
            "products_unmatched": int(unmatched),
            "matches_total": int(match_total),
            "matches_by_status": matches_by_status,
            "decisions_total": int(decision_total),
            "decisions_approved": int(approved),
            "decisions_rejected": int(rejected),
            "pending_review": int(matches_by_status.get("pending", 0)),
        }


def get_recent_matches_by_outcome(
    outcome: str,
    limit: int = 50,
    offset: int = 0,
) -> List[Dict[str, Any]]:
    """Return recent rank-1 matches for an outcome band."""
    statuses = OUTCOME_STATUSES.get(outcome)
    if statuses is None:
        raise ValueError(f"outcome must be one of {sorted(OUTCOME_STATUSES)}")

    with get_session() as session:
        latest_decision = (
            session.query(
                Decision.match_id.label("match_id"),
                func.max(Decision.decided_at).label("decided_at"),
            )
            .group_by(Decision.match_id)
            .subquery()
        )
        event_time = func.coalesce(latest_decision.c.decided_at, Match.created_at)
        matches = (
            session.query(Match)
            .outerjoin(latest_decision, latest_decision.c.match_id == Match.id)
            .filter(Match.rank == 1, Match.status.in_(statuses))
            .order_by(event_time.desc())
            .offset(offset)
            .limit(limit)
            .all()
        )
        rows: List[Dict[str, Any]] = []
        for match in matches:
            data = match.to_dict(include_products=True)
            if match.status in (STATUS_APPROVED, STATUS_REJECTED) and match.decisions:
                decided = [
                    record.decided_at
                    for record in match.decisions
                    if record.decided_at is not None
                ]
                ts = max(decided) if decided else match.created_at
            else:
                ts = match.created_at
            data["event_time"] = ts.isoformat() if ts else (data.get("created_at") or "")
            rows.append(data)
        return rows


def get_recent_activity(limit: int = 20) -> List[Dict[str, Any]]:
    """Return a mixed feed of auto-triage outcomes and operator decisions."""
    rows: List[Dict[str, Any]] = []

    with get_session() as session:
        auto_matches = (
            session.query(Match)
            .filter(
                Match.rank == 1,
                Match.status.in_((STATUS_AUTO_APPROVED, STATUS_AUTO_REJECTED)),
            )
            .order_by(Match.created_at.desc())
            .limit(limit * 3)
            .all()
        )
        for match in auto_matches:
            unmatched = match.unmatched_product
            suggested = match.suggested_product
            approved = match.status == STATUS_AUTO_APPROVED
            rows.append(
                {
                    "product_name": unmatched.name,
                    "matched_to": suggested.name if approved else "—",
                    "confidence": float(match.confidence_score),
                    "decision": "approved" if approved else "rejected",
                    "time": match.created_at.isoformat() if match.created_at else "",
                    "source": "auto",
                }
            )

        decisions = (
            session.query(Decision)
            .order_by(Decision.decided_at.desc())
            .limit(limit * 3)
            .all()
        )
        for record in decisions:
            match = record.match
            if match is None:
                continue
            unmatched = match.unmatched_product
            suggested = match.suggested_product
            rows.append(
                {
                    "product_name": unmatched.name,
                    "matched_to": suggested.name if record.decision == "approved" else "—",
                    "confidence": float(match.confidence_score),
                    "decision": record.decision,
                    "time": record.decided_at.isoformat() if record.decided_at else "",
                    "source": "operator",
                }
            )

    rows.sort(key=lambda item: item.get("time", ""), reverse=True)
    return rows[:limit]


def get_recent_decisions(limit: int = 20) -> List[Dict[str, Any]]:
    """Return the most recent operator decisions."""
    with get_session() as session:
        decisions = (
            session.query(Decision)
            .order_by(Decision.decided_at.desc())
            .limit(limit)
            .all()
        )
        return [d.to_dict(include_match=True) for d in decisions]


def get_confidence_scores(rank: int = 1) -> List[float]:
    """Return confidence scores for all match rows at the given rank."""
    with get_session() as session:
        rows = (
            session.query(Match.confidence_score)
            .filter(Match.rank == rank)
            .all()
        )
        return [float(row[0]) for row in rows]


def get_daily_outcome_counts() -> List[Dict[str, Any]]:
    """Per-calendar-day outcome counts from real event timestamps."""
    buckets: Dict[str, Dict[str, int]] = {}

    def _bucket(day: str) -> Dict[str, int]:
        if day not in buckets:
            buckets[day] = {
                "auto_approved": 0,
                "auto_rejected": 0,
                "operator_approved": 0,
                "operator_rejected": 0,
            }
        return buckets[day]

    with get_session() as session:
        auto_rows = (
            session.query(Match.created_at, Match.status)
            .filter(
                Match.rank == 1,
                Match.status.in_((STATUS_AUTO_APPROVED, STATUS_AUTO_REJECTED)),
            )
            .all()
        )
        for created_at, status in auto_rows:
            if not created_at:
                continue
            day = created_at.date().isoformat()
            if status == STATUS_AUTO_APPROVED:
                _bucket(day)["auto_approved"] += 1
            else:
                _bucket(day)["auto_rejected"] += 1

        for decided_at, decision in session.query(
            Decision.decided_at, Decision.decision
        ).all():
            if not decided_at:
                continue
            day = decided_at.date().isoformat()
            if decision == "approved":
                _bucket(day)["operator_approved"] += 1
            else:
                _bucket(day)["operator_rejected"] += 1

    rows: List[Dict[str, Any]] = []
    for day, counts in sorted(buckets.items()):
        approved = counts["auto_approved"] + counts["operator_approved"]
        rejected = counts["auto_rejected"] + counts["operator_rejected"]
        rows.append(
            {
                "day": day,
                "approved": approved,
                "rejected": rejected,
                **counts,
            }
        )
    return rows


def get_pipeline_stats(alias_index_rows: Optional[int] = None) -> Dict[str, Any]:
    """Aggregate rank-1 resolution method and triage counts from live matches."""
    from src.match_metadata import infer_match_source

    with get_session() as session:
        rank1_rows = (
            session.query(
                Match.tfidf_score,
                Match.embedding_score,
                Match.confidence_score,
                Match.status,
            )
            .filter(Match.rank == 1)
            .all()
        )

        stage0_exact = 0
        stage0_fuzzy = 0
        ml_resolved = 0
        for tfidf, embedding, confidence, _status in rank1_rows:
            source = infer_match_source(tfidf, embedding, confidence)
            if source == "stage0_exact":
                stage0_exact += 1
            elif source == "stage0_fuzzy":
                stage0_fuzzy += 1
            else:
                ml_resolved += 1

        status_rows = (
            session.query(Match.status, func.count(Match.id))
            .filter(Match.rank == 1)
            .group_by(Match.status)
            .all()
        )
        by_status = {status: int(count) for status, count in status_rows}

        canonical_barcoded = (
            session.query(func.count(Product.id))
            .filter(Product.has_barcode.is_(True))
            .scalar()
            or 0
        )

    return {
        "stage0_exact": stage0_exact,
        "stage0_fuzzy": stage0_fuzzy,
        "stage0_total": stage0_exact + stage0_fuzzy,
        "ml_resolved": ml_resolved,
        "auto_approved": by_status.get(STATUS_AUTO_APPROVED, 0),
        "auto_rejected": by_status.get(STATUS_AUTO_REJECTED, 0),
        "pending": by_status.get(STATUS_PENDING, 0),
        "operator_approved": by_status.get(STATUS_APPROVED, 0),
        "operator_rejected": by_status.get(STATUS_REJECTED, 0),
        "canonical_barcoded": int(canonical_barcoded),
        "alias_index_rows": int(alias_index_rows) if alias_index_rows is not None else None,
        "unmatched_triaged": len(rank1_rows),
    }
