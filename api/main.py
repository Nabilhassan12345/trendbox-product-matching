"""FastAPI service for product matching and human review."""

from __future__ import annotations

import logging
import os
import time
from typing import Any

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import RedirectResponse
from sqlalchemy import func

from api.schemas import (
    BatchProcessResponse,
    DecisionRequest,
    DecisionResponse,
    HealthResponse,
    MatchResponse,
    MatchSuggestion,
    StatsResponse,
)
from src.confidence import get_confidence_color, triage
from src.database import Decision, Match, Product, get_session, get_stats, init_db, save_decision, save_matches
from src.matcher import ProductMatcher

logger = logging.getLogger(__name__)

DB_PATH = os.getenv("TRENDBOX_DB_PATH", "data/matching.db")
MATCHER_INDEX_PATH = os.getenv("TRENDBOX_MATCHER_INDEX", "data/matcher_index")
TOP_SUGGESTIONS = 3

app = FastAPI(title="Trendbox Product Matching API", version="1.0.0")
matcher: ProductMatcher | None = None

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:8501"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.middleware("http")
async def log_requests(request: Request, call_next):
    """Log every incoming request and its response status."""
    start = time.perf_counter()
    logger.info("→ %s %s", request.method, request.url.path)
    try:
        response = await call_next(request)
    except Exception:
        logger.exception("Unhandled error on %s %s", request.method, request.url.path)
        raise
    elapsed_ms = (time.perf_counter() - start) * 1000
    logger.info(
        "← %s %s %s (%.1fms)",
        request.method,
        request.url.path,
        response.status_code,
        elapsed_ms,
    )
    return response


def _require_matcher() -> ProductMatcher:
    """Return the loaded matcher or raise HTTP 503."""
    if matcher is None or not matcher._built:
        raise HTTPException(status_code=503, detail="Matcher not loaded — build or cache the index first")
    return matcher


def _triage_status(confidence_score: float) -> str:
    """Map a confidence score to a persisted match status."""
    action = triage(confidence_score)
    if action == "auto_approve":
        return "auto_approved"
    if action == "auto_reject":
        return "auto_rejected"
    return "pending"


def _get_pending_matches_for_product(unmatched_product_id: int) -> list[dict[str, Any]]:
    """Return all pending match rows for an unmatched product, ordered by rank."""
    with get_session() as session:
        matches = (
            session.query(Match)
            .filter(Match.unmatched_product_id == unmatched_product_id, Match.status == "pending")
            .order_by(Match.rank)
            .limit(TOP_SUGGESTIONS)
            .all()
        )
        return [m.to_dict(include_products=True) for m in matches]


def _get_next_pending_product_id() -> int | None:
    """Return the unmatched product id for the next review queue item."""
    with get_session() as session:
        match = (
            session.query(Match)
            .filter(Match.status == "pending")
            .order_by(Match.rank, Match.id)
            .first()
        )
        return match.unmatched_product_id if match else None


def _build_match_response(unmatched_product_id: int) -> MatchResponse:
    """Assemble a review payload for one unmatched product."""
    pending_matches = _get_pending_matches_for_product(unmatched_product_id)
    if not pending_matches:
        raise HTTPException(status_code=404, detail="No pending matches for this product")

    unmatched = pending_matches[0]["unmatched_product"]
    product_name = unmatched["name"]

    explanation_by_barcode: dict[str, str] = {}
    try:
        active_matcher = _require_matcher()
        for hit in active_matcher.match(product_name)[:TOP_SUGGESTIONS]:
            explanation_by_barcode[str(hit["barcode"])] = hit["explanation"]
    except HTTPException:
        pass

    suggestions: list[MatchSuggestion] = []
    for row in pending_matches:
        suggested = row["suggested_product"]
        barcode = str(suggested["barcode"] or "")
        confidence = float(row["confidence_score"])
        suggestions.append(
            MatchSuggestion(
                match_id=row["id"],
                rank=row["rank"],
                barcode=barcode,
                name=suggested["name"],
                confidence_score=confidence,
                confidence_label=row["confidence_label"],
                confidence_color=get_confidence_color(confidence),
                explanation=explanation_by_barcode.get(barcode, ""),
            )
        )

    return MatchResponse(
        product_id=unmatched["id"],
        product_name=product_name,
        brand=unmatched.get("brand"),
        weight=unmatched.get("weight"),
        suggestions=suggestions,
    )


def _build_stats_response() -> StatsResponse:
    """Transform database stats into the API schema."""
    raw = get_stats()
    status_counts = raw.get("matches_by_status", {})

    auto_approved = int(status_counts.get("auto_approved", 0))
    operator_approved = int(status_counts.get("approved", 0))
    auto_rejected = int(status_counts.get("auto_rejected", 0))
    operator_rejected = int(status_counts.get("rejected", 0))
    pending = int(status_counts.get("pending", 0))
    unmatched = int(raw["products_unmatched"])

    matched = auto_approved + operator_approved
    match_rate = round(matched / unmatched, 4) if unmatched else 0.0

    with get_session() as session:
        avg_confidence = (
            session.query(func.avg(Match.confidence_score))
            .filter(Match.rank == 1)
            .scalar()
        )
    avg_confidence = round(float(avg_confidence or 0.0), 4)

    return StatsResponse(
        total_products=int(raw["products_total"]),
        barcoded=int(raw["products_barcoded"]),
        unmatched=unmatched,
        matched=matched,
        pending=pending,
        auto_approved=auto_approved,
        operator_approved=operator_approved,
        rejected=auto_rejected + operator_rejected,
        match_rate=match_rate,
        avg_confidence=avg_confidence,
    )


def _pending_review_count() -> int:
    """Count matches awaiting human review."""
    return int(get_stats().get("pending_review", 0))


@app.on_event("startup")
def startup_load_matcher() -> None:
    """Initialise the database and load the matcher index from cache."""
    global matcher

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )

    init_db(DB_PATH)
    logger.info("Database initialised at %s", DB_PATH)

    matcher = ProductMatcher()
    index_path = MATCHER_INDEX_PATH
    if os.path.isdir(index_path):
        matcher.load(index_path)
        logger.info("Matcher loaded from %s", index_path)
    else:
        logger.warning(
            "Matcher index not found at %s — run matcher.build() and save before matching",
            index_path,
        )


@app.get("/", include_in_schema=False)
def root() -> RedirectResponse:
    """Send browser visitors to the interactive API docs."""
    return RedirectResponse(url="/docs")


@app.get("/health", response_model=HealthResponse)
def health() -> HealthResponse:
    """Return service status and queue depth."""
    with get_session() as session:
        products_indexed = session.query(func.count(Product.id)).scalar() or 0

    matcher_ready = matcher is not None and matcher._built
    return HealthResponse(
        status="ok" if matcher_ready else "degraded",
        products_indexed=int(products_indexed),
        pending_reviews=_pending_review_count(),
    )


@app.get("/match/next", response_model=MatchResponse)
def match_next() -> MatchResponse:
    """Return the next unmatched product pending human review."""
    product_id = _get_next_pending_product_id()
    if product_id is None:
        raise HTTPException(status_code=404, detail="No pending products in review queue")
    return _build_match_response(product_id)


@app.post("/decision/{match_id}", response_model=DecisionResponse)
def record_decision(match_id: int, body: DecisionRequest) -> DecisionResponse:
    """Persist an operator approval or rejection."""
    try:
        save_decision(match_id, body.decision, note=body.note or "")
    except ValueError as exc:
        message = str(exc)
        if "not found" in message:
            raise HTTPException(status_code=404, detail=message) from exc
        raise HTTPException(status_code=422, detail=message) from exc
    except Exception as exc:
        logger.exception("Failed to save decision for match_id=%s", match_id)
        raise HTTPException(status_code=500, detail="Failed to save decision") from exc

    return DecisionResponse(success=True, next_pending_count=_pending_review_count())


@app.get("/stats", response_model=StatsResponse)
def stats() -> StatsResponse:
    """Return aggregate matching and review statistics."""
    return _build_stats_response()


@app.post("/batch_process", response_model=BatchProcessResponse)
def batch_process() -> BatchProcessResponse:
    """Run matching for all unmatched products and auto-triage by confidence."""
    active_matcher = _require_matcher()

    with get_session() as session:
        session.query(Decision).delete()
        session.query(Match).delete()

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

    records: list[dict[str, Any]] = []
    counts = {"auto_approved": 0, "auto_rejected": 0, "pending": 0}

    for product_id, product_name in unmatched_products:
        hits = active_matcher.match(product_name)[:TOP_SUGGESTIONS]
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

    save_matches(records)
    logger.info(
        "Batch process complete: %s suggestions (%s auto-approved, %s auto-rejected, %s pending)",
        len(records),
        counts["auto_approved"],
        counts["auto_rejected"],
        counts["pending"],
    )

    return BatchProcessResponse(
        auto_approved=counts["auto_approved"],
        auto_rejected=counts["auto_rejected"],
        pending=counts["pending"],
        total_suggestions=len(records),
    )
