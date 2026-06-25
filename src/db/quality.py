"""Read-only match-quality queries for API audit and export endpoints."""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple

from sqlalchemy import func, or_

from src.db.models import Match
from src.db.session import get_session
from src.match_metadata import infer_match_source
from src.match_quality import SIZE_CONFLICT, SIZE_UNKNOWN, SIZE_VERIFIED

VALID_SIZE_VERDICTS = frozenset({SIZE_VERIFIED, SIZE_CONFLICT, SIZE_UNKNOWN})


def _verdict_filter(verdict: str):
    """SQLAlchemy filter for a size verdict (unknown includes NULL legacy rows)."""
    if verdict == SIZE_UNKNOWN:
        return or_(Match.size_verdict == SIZE_UNKNOWN, Match.size_verdict.is_(None))
    return Match.size_verdict == verdict


def _match_weight(match: Match, *, side: str) -> Optional[str]:
    """Prefer persisted match weight, then fall back to product catalogue weight."""
    if side == "query":
        stored = match.query_weight
        product = match.unmatched_product
    else:
        stored = match.suggested_weight
        product = match.suggested_product
    if stored:
        return str(stored)
    if product and product.weight:
        return str(product.weight)
    return None


def _row_from_match(match: Match) -> Dict[str, Any]:
    """Serialize one rank-1 match for quality list/export consumers."""
    unmatched = match.unmatched_product
    suggested = match.suggested_product
    verdict = match.size_verdict or SIZE_UNKNOWN
    return {
        "match_id": int(match.id),
        "status": str(match.status),
        "confidence_score": float(match.confidence_score),
        "size_verdict": verdict,
        "guardrail_applied": bool(match.guardrail_applied),
        "query_product": {
            "id": int(unmatched.id),
            "name": str(unmatched.name),
            "weight": _match_weight(match, side="query"),
        },
        "suggested_product": {
            "id": int(suggested.id),
            "name": str(suggested.name),
            "weight": _match_weight(match, side="suggested"),
            "barcode": str(suggested.barcode or ""),
        },
        "match_source": infer_match_source(
            float(match.tfidf_score),
            float(match.embedding_score),
            float(match.confidence_score),
        ),
        "tfidf_score": float(match.tfidf_score),
        "embedding_score": float(match.embedding_score),
        "created_at": match.created_at.isoformat() if match.created_at else "",
    }


def get_quality_summary() -> Dict[str, Any]:
    """Aggregate rank-1 size verdict counts and guardrail metrics."""
    with get_session() as session:
        verified = (
            session.query(func.count(Match.id))
            .filter(Match.rank == 1, Match.size_verdict == SIZE_VERIFIED)
            .scalar()
            or 0
        )
        conflict = (
            session.query(func.count(Match.id))
            .filter(Match.rank == 1, Match.size_verdict == SIZE_CONFLICT)
            .scalar()
            or 0
        )
        unknown = (
            session.query(func.count(Match.id))
            .filter(
                Match.rank == 1,
                or_(Match.size_verdict == SIZE_UNKNOWN, Match.size_verdict.is_(None)),
            )
            .scalar()
            or 0
        )
        guardrail_blocked = (
            session.query(func.count(Match.id))
            .filter(Match.rank == 1, Match.guardrail_applied.is_(True))
            .scalar()
            or 0
        )

    resolved = int(verified) + int(conflict)
    integrity = round(int(verified) / resolved, 4) if resolved > 0 else 0.0

    return {
        "size_verified_count": int(verified),
        "size_conflict_count": int(conflict),
        "size_unknown_count": int(unknown),
        "catalog_integrity_pct": integrity,
        "guardrail_blocked_count": int(guardrail_blocked),
    }


def get_quality_matches(
    verdict: str,
    status: Optional[List[str]] = None,
    limit: int = 50,
    offset: int = 0,
) -> Tuple[List[Dict[str, Any]], int]:
    """Return paginated rank-1 matches filtered by size verdict and optional status."""
    if verdict not in VALID_SIZE_VERDICTS:
        raise ValueError(
            f"verdict must be one of {sorted(VALID_SIZE_VERDICTS)}"
        )

    with get_session() as session:
        query = session.query(Match).filter(Match.rank == 1, _verdict_filter(verdict))
        if status:
            query = query.filter(Match.status.in_(status))

        total = int(query.count())
        matches = (
            query.order_by(Match.id)
            .offset(offset)
            .limit(limit)
            .all()
        )
        rows = [_row_from_match(match) for match in matches]

    return rows, total
