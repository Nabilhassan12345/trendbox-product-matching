"""Pydantic request/response models for the product-matching API."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class MatchSuggestion(BaseModel):
    """A single ranked match suggestion for an unmatched product."""

    match_id: int
    rank: int
    barcode: str
    name: str
    confidence_score: float
    confidence_label: str
    confidence_color: str
    explanation: str
    match_source: Literal["stage0_exact", "stage0_fuzzy", "ml"] = "ml"
    tfidf_score: float = 0.0
    embedding_score: float = 0.0
    size_verdict: Literal["size_verified", "size_conflict", "size_unknown"] = "size_unknown"
    query_weight: str | None = None
    suggested_weight: str | None = None


class MatchResponse(BaseModel):
    """Next pending product with its top match suggestions."""

    product_id: int
    product_name: str
    brand: str | None = None
    weight: str | None = None
    product_kind: Literal["fresh", "branded", "unknown"] = "unknown"
    size_verdict: Literal["size_verified", "size_conflict", "size_unknown"] = "size_unknown"
    query_weight: str | None = None
    suggested_weight: str | None = None
    suggestions: list[MatchSuggestion]


class DecisionRequest(BaseModel):
    """Operator approval or rejection of a match suggestion."""

    decision: Literal["approved", "rejected"]
    note: str | None = None


class DecisionResponse(BaseModel):
    """Result of recording an operator decision."""

    success: bool
    next_pending_count: int


class StatsResponse(BaseModel):
    """Aggregate pipeline and review statistics."""

    total_products: int
    barcoded: int
    unmatched: int
    matched: int
    pending: int
    auto_approved: int
    operator_approved: int
    rejected: int
    match_rate: float
    avg_confidence: float


class HealthResponse(BaseModel):
    """Service health and queue snapshot."""

    status: str
    products_indexed: int
    pending_reviews: int


class BatchProcessResponse(BaseModel):
    """Counts from a full auto-triage batch run.

    Triage is decided per product from its best (rank-1) candidate, so the band
    counts are *products*, not individual suggestions.
    """

    auto_approved: int = Field(description="Products whose best match scored > 0.90")
    auto_rejected: int = Field(description="Products whose best match scored < 0.60")
    pending: int = Field(description="Products whose best match is in the 0.60–0.90 review band")
    total_products: int = Field(description="Products triaged (sum of the three bands)")
    total_suggestions: int = Field(description="Total suggestion rows persisted (incl. alternatives)")


class ConfidenceBuckets(BaseModel):
    """Match counts per confidence band (rank-1 suggestions)."""

    high: int = Field(description="Scores >= 0.90")
    medium: int = Field(description="Scores 0.60–0.90")
    low: int = Field(description="Scores < 0.60")


class DailyOutcomePoint(BaseModel):
    """Outcome counts for one calendar day (from real DB timestamps)."""

    day: str
    approved: int
    rejected: int
    auto_approved: int = 0
    auto_rejected: int = 0
    operator_approved: int = 0
    operator_rejected: int = 0


class RecentDecisionRow(BaseModel):
    """Flattened row for the recent decisions table."""

    product_name: str
    matched_to: str
    confidence: float
    decision: str
    time: str
    source: str = Field(default="operator", description="auto or operator")


class RecentMatchRow(BaseModel):
    """Flattened row for the review history tabs."""

    match_id: int
    product_name: str
    matched_to: str
    barcode: str
    confidence: float
    confidence_label: str
    status: str
    source: str
    time: str
    match_source: Literal["stage0_exact", "stage0_fuzzy", "ml"] = "ml"
    tfidf_score: float = 0.0
    embedding_score: float = 0.0


class PipelineStats(BaseModel):
    """Live rank-1 resolution and triage breakdown from the database."""

    stage0_exact: int
    stage0_fuzzy: int
    stage0_total: int
    ml_resolved: int
    auto_approved: int
    auto_rejected: int
    pending: int
    operator_approved: int
    operator_rejected: int
    canonical_barcoded: int
    alias_index_rows: int | None = None
    unmatched_triaged: int


class CatalogProfileResponse(BaseModel):
    """Catalog quality profile merged with live database counts."""

    profile: dict
    live_stats: StatsResponse
    pipeline_stats: PipelineStats


class ReopenResponse(BaseModel):
    """Result of re-queuing an auto-rejected match."""

    success: bool
    match_id: int
    next_pending_count: int


class AnalyticsResponse(BaseModel):
    """Full analytics payload for the Streamlit dashboard."""

    stats: StatsResponse
    catalog_total: int = Field(description="Total products in catalogue (from DB)")
    auto_rejected: int
    confidence_scores: list[float]
    confidence_buckets: ConfidenceBuckets
    daily_outcomes: list[DailyOutcomePoint]
    manual_minutes_per_match: int = Field(
        default=2,
        description="Assumed manual review minutes per match (efficiency estimate only)",
    )
    recent_decisions: list[RecentDecisionRow]
    pipeline_stats: PipelineStats


class QualityProductSummary(BaseModel):
    """Minimal product fields for quality audit rows."""

    id: int
    name: str
    weight: str | None = None


class QualitySuggestedProductSummary(QualityProductSummary):
    """Suggested reference product including barcode."""

    barcode: str = ""


class QualityMatchRow(BaseModel):
    """One rank-1 match row for quality inspection."""

    match_id: int
    status: str
    confidence_score: float
    size_verdict: Literal["size_verified", "size_conflict", "size_unknown"]
    query_product: QualityProductSummary
    suggested_product: QualitySuggestedProductSummary
    match_source: Literal["stage0_exact", "stage0_fuzzy", "ml"] = "ml"


class QualitySummaryResponse(BaseModel):
    """Aggregate size-verdict metrics for rank-1 matches."""

    size_verified_count: int
    size_conflict_count: int
    size_unknown_count: int
    catalog_integrity_pct: float = Field(
        description="verified / (verified + conflict) among rank-1 with known verdict"
    )
    guardrail_blocked_count: int


class QualityMatchesResponse(BaseModel):
    """Paginated quality match rows for a single size verdict."""

    items: list[QualityMatchRow]
    total: int
    limit: int
    offset: int
    verdict: Literal["size_verified", "size_conflict", "size_unknown"]


class QualityResolveRequest(BaseModel):
    """Operator action on a rank-1 quality conflict."""

    action: Literal["reject", "reopen"]
    note: str | None = None


class QualityResolveResponse(BaseModel):
    """Result of resolving a quality conflict."""

    success: bool
    match_id: int
    action: str
    next_pending_count: int
