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


class MatchResponse(BaseModel):
    """Next pending product with its top match suggestions."""

    product_id: int
    product_name: str
    brand: str | None = None
    weight: str | None = None
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

    product_name: str
    matched_to: str
    barcode: str
    confidence: float
    confidence_label: str
    status: str
    source: str
    time: str


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
