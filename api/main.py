"""FastAPI service for product matching and human review."""

from __future__ import annotations

import json
import logging
import os
import time
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import RedirectResponse
from sqlalchemy import func

from api.schemas import (
    AnalyticsResponse,
    BatchProcessResponse,
    CatalogProfileResponse,
    ConfidenceBuckets,
    DecisionRequest,
    DecisionResponse,
    HealthResponse,
    MatchResponse,
    MatchSuggestion,
    PipelineStats,
    RecentDecisionRow,
    DailyOutcomePoint,
    RecentMatchRow,
    ReopenResponse,
    StatsResponse,
)
from src.batch import run_full_batch
from src.confidence import HIGH_THRESHOLD, MEDIUM_THRESHOLD, get_confidence_color
from src.config import CATALOG_PROFILE_PATH, ROOT, TOP_SUGGESTIONS
from src.database import (
    OPEN_STATUSES,
    STATUS_APPROVED,
    STATUS_AUTO_APPROVED,
    STATUS_AUTO_REJECTED,
    STATUS_PENDING,
    STATUS_REJECTED,
    Decision,
    Match,
    Product,
    get_confidence_scores,
    get_daily_outcome_counts,
    get_pipeline_stats,
    get_recent_activity,
    get_recent_decisions,
    get_recent_matches_by_outcome,
    get_session,
    get_stats,
    init_db,
    reopen_auto_rejected,
    save_decision,
)
from src.match_metadata import explanation_from_stored, infer_match_source
from src.matcher import ProductMatcher
from src.preprocess import classify_product_kind

logger = logging.getLogger(__name__)

# Load variables from a local .env file if present (no-op when absent; never
# overrides values already set in the environment, e.g. by pipeline.py or tests).
load_dotenv()

matcher: ProductMatcher | None = None


def _runtime_db_path() -> str:
    """Resolve DB path at startup so tests and subprocesses can override via env."""
    return os.getenv("TRENDBOX_DB_PATH", str(ROOT / "data" / "matching.db"))


def _runtime_matcher_index() -> Path:
    raw = os.getenv("TRENDBOX_MATCHER_INDEX")
    return Path(raw) if raw else ROOT / "data" / "matcher_index"


@asynccontextmanager
async def lifespan(_app: FastAPI):
    """Initialise the database and load the matcher index from cache on startup."""
    global matcher

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )

    db_path = _runtime_db_path()
    matcher_index = _runtime_matcher_index()

    init_db(db_path)
    logger.info("Database initialised at %s", db_path)

    matcher = ProductMatcher()
    if matcher_index.is_dir():
        matcher.load(str(matcher_index))
        logger.info("Matcher loaded from %s", matcher_index)
    else:
        logger.warning(
            "Matcher index not found at %s — run matcher.build() and save before matching",
            matcher_index,
        )

    yield


app = FastAPI(
    title="Trendbox Product Matching API",
    version="1.0.0",
    lifespan=lifespan,
)

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


def _get_open_matches_for_product(unmatched_product_id: int) -> list[dict[str, Any]]:
    """Return all still-open suggestions for a product (primary + alternatives)."""
    with get_session() as session:
        matches = (
            session.query(Match)
            .filter(
                Match.unmatched_product_id == unmatched_product_id,
                Match.status.in_(OPEN_STATUSES),
            )
            .order_by(Match.rank)
            .limit(TOP_SUGGESTIONS)
            .all()
        )
        return [m.to_dict(include_products=True) for m in matches]


def _get_next_pending_product_id() -> int | None:
    """Return the unmatched product id for the next review queue item.

    Only primary (rank-1) suggestions carry the ``pending`` status, so each
    pending product appears in the queue exactly once.
    """
    with get_session() as session:
        match = (
            session.query(Match)
            .filter(Match.status == STATUS_PENDING)
            .order_by(Match.rank, Match.id)
            .first()
        )
        return match.unmatched_product_id if match else None


def _alias_index_row_count() -> int | None:
    """Return matcher index row count when the FAISS/TF-IDF cache is loaded."""
    if matcher is None or not matcher._built:
        return None
    ref_df = matcher.tfidf.reference_df
    if ref_df is None or ref_df.empty:
        return None
    return len(ref_df)


def _embedder_for_explanations() -> Any | None:
    """Return the loaded embedder, if any, for ML explanation text."""
    if matcher is None or not matcher._built:
        return None
    return getattr(matcher, "embedder", None)


def _build_pipeline_stats_response() -> PipelineStats:
    """Build pipeline stats from the live database and optional index size."""
    raw = get_pipeline_stats(alias_index_rows=_alias_index_row_count())
    return PipelineStats(**raw)


def _build_match_response(unmatched_product_id: int) -> MatchResponse:
    """Assemble a review payload for one unmatched product."""
    pending_matches = _get_open_matches_for_product(unmatched_product_id)
    if not pending_matches:
        raise HTTPException(status_code=404, detail="No pending matches for this product")

    unmatched = pending_matches[0]["unmatched_product"]
    product_name = unmatched["name"]
    product_kind = classify_product_kind(
        product_name,
        unmatched.get("brand"),
        unmatched.get("weight"),
    )
    embedder = _embedder_for_explanations()

    suggestions: list[MatchSuggestion] = []
    for row in pending_matches:
        suggested = row["suggested_product"]
        barcode = str(suggested["barcode"] or "")
        confidence = float(row["confidence_score"])
        tfidf = float(row["tfidf_score"])
        embedding = float(row["embedding_score"])
        source = infer_match_source(tfidf, embedding, confidence)
        explanation = explanation_from_stored(
            source,
            query=product_name,
            candidate_name_clean=str(suggested.get("name_clean") or suggested["name"]),
            tfidf_score=tfidf,
            embedding_score=embedding,
            confidence_score=confidence,
            embedder=embedder,
        )
        suggestions.append(
            MatchSuggestion(
                match_id=row["id"],
                rank=row["rank"],
                barcode=barcode,
                name=suggested["name"],
                confidence_score=confidence,
                confidence_label=row["confidence_label"],
                confidence_color=get_confidence_color(confidence),
                explanation=explanation,
                match_source=source,
                tfidf_score=tfidf,
                embedding_score=embedding,
            )
        )

    return MatchResponse(
        product_id=unmatched["id"],
        product_name=product_name,
        brand=unmatched.get("brand"),
        weight=unmatched.get("weight"),
        product_kind=product_kind,
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


def _confidence_buckets(scores: list[float]) -> ConfidenceBuckets:
    """Tally rank-1 confidence scores into triage bands."""
    high = sum(1 for score in scores if score >= HIGH_THRESHOLD)
    medium = sum(1 for score in scores if MEDIUM_THRESHOLD <= score < HIGH_THRESHOLD)
    low = sum(1 for score in scores if score < MEDIUM_THRESHOLD)
    return ConfidenceBuckets(high=high, medium=medium, low=low)


def _match_source(status: str) -> str:
    """Classify a match status as auto- or operator-driven."""
    if status in {STATUS_AUTO_APPROVED, STATUS_AUTO_REJECTED}:
        return "auto"
    if status in {STATUS_APPROVED, STATUS_REJECTED}:
        return "operator"
    return "auto"


def _build_recent_decision_rows(limit: int = 20) -> list[RecentDecisionRow]:
    """Flatten recent auto-triage and operator activity for the analytics table."""
    return [
        RecentDecisionRow(
            product_name=str(item.get("product_name", "—")),
            matched_to=str(item.get("matched_to", "—")),
            confidence=float(item.get("confidence", 0.0)),
            decision=str(item.get("decision", "")),
            time=str(item.get("time", "")),
            source=str(item.get("source", "operator")),
        )
        for item in get_recent_activity(limit)
    ]


def _build_recent_match_rows(outcome: str, limit: int = 50) -> list[RecentMatchRow]:
    """Flatten recent resolved matches for the review history tabs."""
    rows: list[RecentMatchRow] = []
    for item in get_recent_matches_by_outcome(outcome, limit=limit):
        unmatched = item.get("unmatched_product") or {}
        suggested = item.get("suggested_product") or {}
        status = str(item.get("status", ""))
        tfidf = float(item.get("tfidf_score", 0.0))
        embedding = float(item.get("embedding_score", 0.0))
        confidence = float(item.get("confidence_score", 0.0))
        match_source = infer_match_source(tfidf, embedding, confidence)
        rows.append(
            RecentMatchRow(
                match_id=int(item.get("id", 0)),
                product_name=str(unmatched.get("name", "—")),
                matched_to=str(suggested.get("name", "—")),
                barcode=str(suggested.get("barcode") or ""),
                confidence=confidence,
                confidence_label=str(item.get("confidence_label", "")),
                status=status,
                source=_match_source(status),
                time=str(item.get("event_time") or item.get("created_at", "")),
                match_source=match_source,
                tfidf_score=tfidf,
                embedding_score=embedding,
            )
        )
    return rows


def _build_analytics_response() -> AnalyticsResponse:
    """Assemble the full analytics dashboard payload."""
    stats = _build_stats_response()
    raw = get_stats()
    status_counts = raw.get("matches_by_status", {})
    auto_rejected = int(status_counts.get("auto_rejected", 0))
    scores = get_confidence_scores(rank=1)
    daily_outcomes = [DailyOutcomePoint(**row) for row in get_daily_outcome_counts()]

    return AnalyticsResponse(
        stats=stats,
        catalog_total=int(raw["products_total"]),
        auto_rejected=auto_rejected,
        confidence_scores=scores,
        confidence_buckets=_confidence_buckets(scores),
        daily_outcomes=daily_outcomes,
        recent_decisions=_build_recent_decision_rows(20),
        pipeline_stats=_build_pipeline_stats_response(),
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


@app.get("/analytics", response_model=AnalyticsResponse)
def analytics() -> AnalyticsResponse:
    """Return full analytics data for the Streamlit dashboard."""
    return _build_analytics_response()


@app.get("/catalog/profile", response_model=CatalogProfileResponse)
def catalog_profile() -> CatalogProfileResponse:
    """Return catalog quality profile JSON merged with live database stats."""
    if not CATALOG_PROFILE_PATH.is_file():
        raise HTTPException(
            status_code=404,
            detail=f"Catalog profile not found at {CATALOG_PROFILE_PATH}",
        )
    try:
        profile = json.loads(CATALOG_PROFILE_PATH.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise HTTPException(status_code=500, detail="Invalid catalog profile JSON") from exc

    return CatalogProfileResponse(
        profile=profile,
        live_stats=_build_stats_response(),
        pipeline_stats=_build_pipeline_stats_response(),
    )


@app.post("/matches/{match_id}/reopen", response_model=ReopenResponse)
def reopen_match(match_id: int) -> ReopenResponse:
    """Re-queue an auto-rejected rank-1 match for operator review."""
    try:
        reopen_auto_rejected(match_id)
    except ValueError as exc:
        message = str(exc)
        if "not found" in message:
            raise HTTPException(status_code=404, detail=message) from exc
        raise HTTPException(status_code=422, detail=message) from exc
    except Exception as exc:
        logger.exception("Failed to reopen match_id=%s", match_id)
        raise HTTPException(status_code=500, detail="Failed to re-queue match") from exc

    return ReopenResponse(
        success=True,
        match_id=match_id,
        next_pending_count=_pending_review_count(),
    )


@app.get("/matches/recent", response_model=list[RecentMatchRow])
def matches_recent(outcome: str = "approved", limit: int = 50) -> list[RecentMatchRow]:
    """Return recent rank-1 matches for a review outcome band."""
    outcome = outcome.lower().strip()
    if outcome not in {"approved", "rejected", "pending"}:
        raise HTTPException(status_code=422, detail="outcome must be approved, rejected, or pending")
    limit = max(1, min(limit, 200))
    try:
        return _build_recent_match_rows(outcome, limit=limit)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@app.post("/batch_process", response_model=BatchProcessResponse)
def batch_process() -> BatchProcessResponse:
    """Run matching for all unmatched products and auto-triage by confidence."""
    active_matcher = _require_matcher()

    try:
        records, counts = run_full_batch(active_matcher)
    except RuntimeError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    logger.info(
        "Batch process complete: %s suggestions (%s stage-0, %s auto-approved, "
        "%s auto-rejected, %s pending)",
        len(records),
        counts.get("stage0_resolved", 0),
        counts["auto_approved"],
        counts["auto_rejected"],
        counts["pending"],
    )

    return BatchProcessResponse(
        auto_approved=counts["auto_approved"],
        auto_rejected=counts["auto_rejected"],
        pending=counts["pending"],
        total_products=counts["auto_approved"] + counts["auto_rejected"] + counts["pending"],
        total_suggestions=len(records),
    )
