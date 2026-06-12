"""Infer match resolution method and explanations from stored DB scores."""

from __future__ import annotations

from typing import Any, Literal, Optional

MatchSource = Literal["stage0_exact", "stage0_fuzzy", "ml"]

_STAGE0_CONFIDENCES = {1.0, 0.92, 0.85}
_SCORE_EPS = 1e-4


def infer_match_source(
    tfidf_score: float,
    embedding_score: float,
    confidence_score: float,
) -> MatchSource:
    """Classify how a match was resolved from persisted score fingerprints."""
    tfidf = float(tfidf_score)
    embedding = float(embedding_score)
    confidence = float(confidence_score)

    if (
        abs(tfidf - embedding) <= _SCORE_EPS
        and abs(tfidf - confidence) <= _SCORE_EPS
        and round(confidence, 2) in _STAGE0_CONFIDENCES
    ):
        if round(confidence, 2) == 0.92:
            return "stage0_fuzzy"
        return "stage0_exact"
    return "ml"


def match_source_label(source: MatchSource) -> str:
    """Human-readable label for UI chips."""
    labels = {
        "stage0_exact": "Stage 0 · Exact",
        "stage0_fuzzy": "Stage 0 · Fuzzy",
        "ml": "ML match",
    }
    return labels.get(source, "ML match")


def explanation_from_stored(
    match_source: MatchSource,
    *,
    query: str,
    candidate_name_clean: str,
    tfidf_score: float,
    embedding_score: float,
    confidence_score: float,
    embedder: Optional[Any] = None,
) -> str:
    """Build an explanation from stored scores — no live re-matching."""
    if match_source == "stage0_exact":
        if round(confidence_score, 2) == 0.85:
            return "Stage 0 exact name match (multiple barcodes — review required)"
        return "Stage 0 exact name match"
    if match_source == "stage0_fuzzy":
        if round(confidence_score, 2) == 0.85:
            return "Stage 0 fuzzy name match (multiple barcodes — review required)"
        return "Stage 0 fuzzy name match"

    if embedder is not None:
        try:
            from src.preprocess import normalize

            query_norm = normalize(query)
            candidate_norm = normalize(candidate_name_clean)
            return embedder.build_explanation(
                query_norm, candidate_norm, embedding_score
            )["explanation"]
        except Exception:
            pass

    return (
        f"TF-IDF: {tfidf_score:.3f} | Embedding: {embedding_score:.3f} | "
        f"Combined confidence: {confidence_score:.3f}"
    )
