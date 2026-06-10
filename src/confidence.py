"""Ensemble confidence scoring for the two-stage product-matching pipeline."""

from __future__ import annotations

# Weighted blend of Stage 1 (TF-IDF) and Stage 2 (embedding) scores.
TFIDF_WEIGHT = 0.3
EMBEDDING_WEIGHT = 0.7

# Exact-match bonuses applied on top of the blended base score.
BRAND_MATCH_BONUS = 0.05
WEIGHT_MATCH_BONUS = 0.05

# Confidence band thresholds (aligned with project auto-triage rules).
HIGH_THRESHOLD = 0.90
MEDIUM_THRESHOLD = 0.60

# UI colour tokens for Streamlit review pages.
COLOR_HIGH = "#2ECC71"
COLOR_MEDIUM = "#F39C12"
COLOR_LOW = "#E74C3C"


def compute_confidence(
    tfidf_score: float,
    embedding_score: float,
    brand_match: bool,
    weight_match: bool,
) -> float:
    """Compute an ensemble confidence score from retrieval and reranking signals.

    The base score is a weighted blend favouring semantic embeddings (70%)
    over character-level TF-IDF (30%).  Small bonuses reward exact brand and
    weight agreement.

    Args:
        tfidf_score: Raw TF-IDF cosine score from Stage 1 (``tfidf_score``
            column, 0–1).  Do **not** pass ``tfidf_score_adjusted`` — brand and
            weight bonuses are applied once here, not in Stage 1.
        embedding_score: Cosine similarity from Stage 2 embeddings (0–1).
        brand_match: ``True`` when query and candidate share the same brand token.
        weight_match: ``True`` when query and candidate share the same weight/volume.

    Returns:
        Final confidence in ``[0.0, 1.0]``.
    """
    # Clamp TF-IDF to [0, 1] — cosine similarity range (guards against accidental
    # use of tfidf_score_adjusted which can exceed 1.0 after Stage-1 bonuses).
    tfidf_clamped = max(0.0, min(1.0, tfidf_score))
    embedding_clamped = max(0.0, min(1.0, embedding_score))
    base = (tfidf_clamped * TFIDF_WEIGHT) + (embedding_clamped * EMBEDDING_WEIGHT)

    if brand_match:
        base += BRAND_MATCH_BONUS
    if weight_match:
        base += WEIGHT_MATCH_BONUS

    return max(0.0, min(1.0, base))


def get_confidence_label(score: float) -> str:
    """Map a confidence score to a human-readable label.

    Args:
        score: Confidence value in ``[0.0, 1.0]``.

    Returns:
        ``"HIGH"`` (auto-approve), ``"MEDIUM"`` (needs review), or ``"LOW"``
        (auto-reject).
    """
    if score >= HIGH_THRESHOLD:
        return "HIGH"
    if score >= MEDIUM_THRESHOLD:
        return "MEDIUM"
    return "LOW"


def get_confidence_color(score: float) -> str:
    """Return a hex colour for UI display based on confidence band.

    Args:
        score: Confidence value in ``[0.0, 1.0]``.

    Returns:
        Hex colour string — green (HIGH), yellow (MEDIUM), or red (LOW).
    """
    label = get_confidence_label(score)
    if label == "HIGH":
        return COLOR_HIGH
    if label == "MEDIUM":
        return COLOR_MEDIUM
    return COLOR_LOW


def triage(score: float) -> str:
    """Return the pipeline action for a confidence score.

    Args:
        score: Confidence value in ``[0.0, 1.0]``.

    Returns:
        ``"auto_approve"``, ``"review"``, or ``"auto_reject"``.
    """
    label = get_confidence_label(score)
    if label == "HIGH":
        return "auto_approve"
    if label == "MEDIUM":
        return "review"
    return "auto_reject"


if __name__ == "__main__":
    print("=== Confidence Scoring Tests ===\n")

    test_cases = [
        # (tfidf, embedding, brand, weight, description)
        (0.95, 0.92, True, True, "Strong match, brand+weight agree"),
        (0.80, 0.85, True, False, "Good match, brand only"),
        (0.70, 0.75, False, True, "Decent match, weight only"),
        (0.50, 0.55, False, False, "Weak match, no bonuses"),
        (0.30, 0.40, False, False, "Poor match"),
        (1.10, 0.95, True, True, "TF-IDF >1 clamped to 1.0 in blend"),
        (0.00, 0.00, False, False, "Zero scores"),
        (0.90, 0.90, True, True, "Borderline HIGH"),
        (0.60, 0.60, False, False, "Borderline MEDIUM"),
        (0.59, 0.59, False, False, "Just below MEDIUM"),
    ]

    print(f"{'Description':<40} {'TF-IDF':>7} {'Embed':>7} {'Brand':>6} {'Wt':>4} "
          f"{'Score':>7} {'Label':>7} {'Triage':>14} {'Color':>10}")
    print("-" * 110)

    for tfidf, embed, brand, weight, desc in test_cases:
        score = compute_confidence(tfidf, embed, brand, weight)
        label = get_confidence_label(score)
        action = triage(score)
        color = get_confidence_color(score)
        print(
            f"{desc:<40} {tfidf:>7.2f} {embed:>7.2f} "
            f"{'Y' if brand else 'N':>6} {'Y' if weight else 'N':>4} "
            f"{score:>7.4f} {label:>7} {action:>14} {color:>10}"
        )

    print("\n=== Threshold boundary checks ===\n")
    boundaries = [0.0, 0.59, 0.60, 0.89, 0.90, 1.0]
    for s in boundaries:
        print(
            f"  score={s:.2f}  label={get_confidence_label(s):>6}  "
            f"triage={triage(s):>14}  color={get_confidence_color(s)}"
        )

    print("\nAll tests complete.")
