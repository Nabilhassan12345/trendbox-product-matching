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

from src.blocking import Stage0Resolver
from src.confidence import triage
from src.config import TOP_SUGGESTIONS
from src.database import (
    STATUS_ALTERNATIVE,
    STATUS_AUTO_APPROVED,
    STATUS_AUTO_REJECTED,
    STATUS_PENDING,
    STATUS_SUPERSEDED,
    Product,
    get_session,
    replace_matches,
)
from src.match_quality import SIZE_CONFLICT, classify_pack_from_names, pack_label_from_name
from src.preprocess import extract_brand, extract_weight, normalize, normalize_batch

logger = logging.getLogger(__name__)

_PRIMARY_STATUS = {
    "auto_approve": STATUS_AUTO_APPROVED,
    "auto_reject": STATUS_AUTO_REJECTED,
    "review": STATUS_PENDING,
}


def _match_state(query_value: str, candidate_value: str) -> bool:
    """Return True when both sides are present and equal."""
    return bool(query_value and candidate_value and query_value == candidate_value)


def _quality_fields_for_hit(hit: Dict[str, Any], query_clean: str) -> Dict[str, Any]:
    """Derive persisted match-quality metadata from a hit and query name."""
    candidate_clean = str(hit.get("name_clean", ""))
    query_weight = str(hit.get("query_weight") or pack_label_from_name(query_clean) or extract_weight(query_clean))
    suggested_weight = str(
        hit.get("suggested_weight") or pack_label_from_name(candidate_clean) or extract_weight(candidate_clean)
    )
    size_verdict = str(hit.get("size_verdict") or classify_pack_from_names(query_clean, candidate_clean))
    brand_match = hit.get("brand_match")
    if brand_match is None:
        query_brand = extract_brand(query_clean)
        candidate_brand = extract_brand(candidate_clean)
        if not query_brand or not candidate_brand:
            brand_match = None
        else:
            brand_match = query_brand == candidate_brand
    return {
        "query_weight": query_weight or None,
        "suggested_weight": suggested_weight or None,
        "size_verdict": size_verdict,
        "brand_match": brand_match,
        "guardrail_applied": size_verdict == SIZE_CONFLICT,
    }


def primary_status(primary_hit: Dict[str, Any], query_clean: str) -> str:
    """Map a rank-1 hit to the product-level match status."""
    candidate_clean = str(primary_hit.get("name_clean", ""))
    brand_match = _match_state(
        extract_brand(query_clean),
        extract_brand(candidate_clean),
    )
    weight_match = _match_state(
        extract_weight(query_clean),
        extract_weight(candidate_clean),
    )
    return _PRIMARY_STATUS[
        triage(
            float(primary_hit["confidence_score"]),
            brand_match,
            weight_match,
            query_clean,
            candidate_clean,
        )
    ]


def build_records_for_product(
    hits: Sequence[Dict[str, Any]],
    unmatched_product_id: int,
    barcode_to_id: Dict[str, int],
    query_clean: str = "",
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
    product_status = primary_status(primary_hit, query_clean)
    sibling_status = (
        STATUS_ALTERNATIVE if product_status == STATUS_PENDING else STATUS_SUPERSEDED
    )

    records: List[Dict[str, Any]] = []
    for hit, suggested_id in resolved:
        status = product_status if hit is primary_hit else sibling_status
        quality = _quality_fields_for_hit(hit, query_clean)
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
                **quality,
            }
        )
    return records, product_status


def process_unmatched(
    matcher: Any,
    unmatched_products: Sequence[Tuple[int, str]],
    barcode_to_id: Dict[str, int],
    *,
    stage0: Optional[Any] = None,
    progress_every: int = 500,
) -> Tuple[List[Dict[str, Any]], Dict[str, int]]:
    """Match every unmatched product and triage each one at the product level.

    Args:
        matcher: A built :class:`ProductMatcher`.
        unmatched_products: Iterable of ``(product_id, product_name)``.
        barcode_to_id: Map from reference barcode to its product id.
        stage0: Optional :class:`Stage0Resolver` for deterministic pre-ML matching.
        progress_every: Log progress every N products (0 to disable).

    Returns:
        Tuple of ``(records, counts)`` where ``counts`` tallies *products* by
        outcome: ``auto_approved``, ``auto_rejected``, ``pending``.
    """
    records: List[Dict[str, Any]] = []
    counts = {
        "auto_approved": 0,
        "auto_rejected": 0,
        "pending": 0,
        "stage0_resolved": 0,
    }

    total = len(unmatched_products)
    start = time.perf_counter()

    names = [product_name for _, product_name in unmatched_products]
    queries = normalize_batch(names)
    all_hits: List[Optional[List[Dict[str, Any]]]] = [None] * total
    unresolved_indices: List[int] = []

    if stage0 is not None:
        stage0_results = stage0.resolve_many(queries)
        for index, hits in enumerate(stage0_results):
            if hits:
                all_hits[index] = hits
                counts["stage0_resolved"] += 1
            else:
                unresolved_indices.append(index)
    else:
        unresolved_indices = list(range(total))

    if unresolved_indices:
        unresolved_queries = [queries[index] for index in unresolved_indices]
        ml_results = matcher.match_many(
            [names[index] for index in unresolved_indices],
            queries=unresolved_queries,
        )
        for index, hits in zip(unresolved_indices, ml_results):
            all_hits[index] = hits

    for (product_id, _), query, hits in zip(unmatched_products, queries, all_hits):
        if not hits:
            continue
        product_records, status = build_records_for_product(
            hits, product_id, barcode_to_id, query_clean=query
        )
        records.extend(product_records)
        if status == STATUS_PENDING:
            counts["pending"] += 1
        elif status == STATUS_AUTO_APPROVED:
            counts["auto_approved"] += 1
        elif status == STATUS_AUTO_REJECTED:
            counts["auto_rejected"] += 1

    elapsed = time.perf_counter() - start
    rate = total / elapsed if elapsed else 0.0
    logger.info(
        "Triaged %s products in %.1fs (%.1f/s); stage0 resolved %s",
        f"{total:,}",
        elapsed,
        rate,
        f"{counts['stage0_resolved']:,}",
    )

    return records, counts


def _load_batch_inputs() -> tuple[list[tuple[int, str]], dict[str, int]]:
    """Read unmatched products and barcode→id map from the database."""
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
    return unmatched_products, barcode_to_id


def _resolve_stage0(matcher: Any, stage0_df: Optional[Any]) -> Optional[Stage0Resolver]:
    """Build a Stage 0 resolver from an explicit frame or the matcher's reference index."""
    if stage0_df is not None:
        return Stage0Resolver(stage0_df)
    ref_df = matcher.tfidf.reference_df
    if ref_df is not None and not ref_df.empty:
        return Stage0Resolver(ref_df)
    return None


def run_full_batch(
    matcher: Any,
    *,
    stage0_df: Optional[Any] = None,
    progress_every: int = 500,
) -> tuple[list[dict[str, Any]], dict[str, int]]:
    """Match all unmatched products, persist suggestions, and return outcome counts.

    Shared entry point for ``pipeline.py``, ``scripts/run_batch.py``, and the
    API ``POST /batch_process`` endpoint so batch behaviour never diverges.

    Raises:
        RuntimeError: When the matcher index is not built or no unmatched rows exist.
    """
    if not matcher._built:
        raise RuntimeError("Matcher is not built — cannot run batch processing.")

    unmatched_products, barcode_to_id = _load_batch_inputs()
    if not unmatched_products:
        raise RuntimeError("No unmatched products in database.")

    stage0 = _resolve_stage0(matcher, stage0_df)
    records, counts = process_unmatched(
        matcher,
        unmatched_products,
        barcode_to_id,
        stage0=stage0,
        progress_every=progress_every,
    )
    replace_matches(records)
    return records, counts
