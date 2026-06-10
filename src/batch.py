"""Shared batch triage logic for matching all unmatched products.

Triage is decided per *product* from its rank-1 (best) candidate, not per
suggestion. This guarantees a product is in exactly one state — auto-approved,
auto-rejected, or pending review — instead of being simultaneously
auto-approved on one suggestion and pending on another.

Used by both ``api/main.py`` (POST /batch_process) and ``pipeline.py`` so the
two never diverge.
"""

from __future__ import annotations

import logging
import time
from typing import Any, Dict, List, Optional, Sequence, Tuple

from src.confidence import triage
from src.database import (
    STATUS_ALTERNATIVE,
    STATUS_AUTO_APPROVED,
    STATUS_AUTO_REJECTED,
    STATUS_PENDING,
    STATUS_SUPERSEDED,
)

logger = logging.getLogger(__name__)

TOP_SUGGESTIONS = 3

_PRIMARY_STATUS = {
    "auto_approve": STATUS_AUTO_APPROVED,
    "auto_reject": STATUS_AUTO_REJECTED,
    "review": STATUS_PENDING,
}


def primary_status(confidence_score: float) -> str:
    """Map a rank-1 confidence score to the product-level match status."""
    return _PRIMARY_STATUS[triage(confidence_score)]


def build_records_for_product(
    hits: Sequence[Dict[str, Any]],
    unmatched_product_id: int,
    barcode_to_id: Dict[str, int],
) -> Tuple[List[Dict[str, Any]], Optional[str]]:
    """Build persistable match rows for a single unmatched product.

    The first hit that maps to a known reference product becomes the *primary*
    suggestion and decides the product's status. Remaining hits are stored as
    ``alternative`` (when the product is pending review) or ``superseded`` (when
    the product was auto-resolved and the alternatives are never surfaced).

    Args:
        hits: Ranked match dicts from :meth:`ProductMatcher.match` (rank 1 first).
        unmatched_product_id: Database id of the product being matched.
        barcode_to_id: Map from reference barcode to its product id.

    Returns:
        Tuple of ``(records, product_status)``. ``product_status`` is ``None``
        when no hit could be resolved to a reference product (no records).
    """
    resolved = [
        (hit, barcode_to_id.get(str(hit["barcode"])))
        for hit in hits[:TOP_SUGGESTIONS]
    ]
    resolved = [(hit, sid) for hit, sid in resolved if sid is not None]
    if not resolved:
        return [], None

    primary_hit = resolved[0][0]
    product_status = primary_status(primary_hit["confidence_score"])
    sibling_status = (
        STATUS_ALTERNATIVE if product_status == STATUS_PENDING else STATUS_SUPERSEDED
    )

    records: List[Dict[str, Any]] = []
    for hit, suggested_id in resolved:
        status = product_status if hit is primary_hit else sibling_status
        records.append(
            {
                "unmatched_product_id": unmatched_product_id,
                "suggested_product_id": suggested_id,
                "tfidf_score": hit["tfidf_score"],
                "embedding_score": hit["embedding_score"],
                "confidence_score": hit["confidence_score"],
                "confidence_label": hit["confidence_label"],
                "rank": hit["rank"],
                "status": status,
            }
        )
    return records, product_status


def process_unmatched(
    matcher: Any,
    unmatched_products: Sequence[Tuple[int, str]],
    barcode_to_id: Dict[str, int],
    *,
    progress_every: int = 500,
) -> Tuple[List[Dict[str, Any]], Dict[str, int]]:
    """Match every unmatched product and triage each one at the product level.

    Args:
        matcher: A built :class:`ProductMatcher`.
        unmatched_products: Iterable of ``(product_id, product_name)``.
        barcode_to_id: Map from reference barcode to its product id.
        progress_every: Log progress every N products (0 to disable).

    Returns:
        Tuple of ``(records, counts)`` where ``counts`` tallies *products* by
        outcome: ``auto_approved``, ``auto_rejected``, ``pending``.
    """
    records: List[Dict[str, Any]] = []
    counts = {"auto_approved": 0, "auto_rejected": 0, "pending": 0}

    total = len(unmatched_products)
    start = time.perf_counter()

    for index, (product_id, product_name) in enumerate(unmatched_products, start=1):
        hits = matcher.match(product_name)
        product_records, status = build_records_for_product(
            hits, product_id, barcode_to_id
        )
        records.extend(product_records)
        if status == STATUS_PENDING:
            counts["pending"] += 1
        elif status == STATUS_AUTO_APPROVED:
            counts["auto_approved"] += 1
        elif status == STATUS_AUTO_REJECTED:
            counts["auto_rejected"] += 1

        if progress_every and (index % progress_every == 0 or index == total):
            elapsed = time.perf_counter() - start
            rate = index / elapsed if elapsed else 0.0
            logger.info("Matched %s/%s products (%.1f/s)", f"{index:,}", f"{total:,}", rate)

    return records, counts
