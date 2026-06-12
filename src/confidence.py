"""Ensemble confidence scoring for the two-stage product-matching pipeline."""

from __future__ import annotations

from typing import Optional

ProductKind = str  # "branded" | "fresh" | "unknown"

# Weighted blend of Stage 1 (TF-IDF) and Stage 2 (embedding) scores.
#
# Tuning note: evaluation on held-out same-barcode spelling variants
# (scripts/evaluate.py) showed the multilingual embedding model assigns very
# high similarity (0.92–0.98) to brand/size/flavour-swapped near-duplicates,
# overriding the correct barcode. Character-level TF-IDF is the stronger signal
# for *exact* product identity on this catalogue, so the blend favours it and
# explicit brand/weight *mismatch* penalties demote near-duplicates.
TFIDF_WEIGHT = 0.5
EMBEDDING_WEIGHT = 0.5

# Exact-match bonuses applied on top of the blended base score.
BRAND_MATCH_BONUS = 0.05
WEIGHT_MATCH_BONUS = 0.05

# Mismatch penalties: a different brand or pack size almost always means a
# different barcode, so penalise these much more strongly than the match bonus.
BRAND_MISMATCH_PENALTY = 0.30
WEIGHT_MISMATCH_PENALTY = 0.20

# Confidence band thresholds (aligned with project auto-triage rules).
HIGH_THRESHOLD = 0.90
MEDIUM_THRESHOLD = 0.60

# UI colour tokens for Streamlit review pages.
COLOR_HIGH = "#2ECC71"
COLOR_MEDIUM = "#F39C12"
COLOR_LOW = "#E74C3C"


def _edit_distance_leq(a: str, b: str, max_distance: int) -> bool:
    """Return True when Levenshtein distance between *a* and *b* is at most *max_distance*."""
    if a == b:
        return True
    if max_distance < 0:
        return False
    if abs(len(a) - len(b)) > max_distance:
        return False

    if len(a) < len(b):
        a, b = b, a
    previous = list(range(len(b) + 1))
    for i, char_a in enumerate(a, start=1):
        current = [i]
        row_min = current[0]
        for j, char_b in enumerate(b, start=1):
            insert_cost = current[j - 1] + 1
            delete_cost = previous[j] + 1
            replace_cost = previous[j - 1] + (char_a != char_b)
            value = min(insert_cost, delete_cost, replace_cost)
            current.append(value)
            row_min = min(row_min, value)
        if row_min > max_distance:
            return False
        previous = current
    return previous[-1] <= max_distance


def resolve_brand_match(
    query_brand: str,
    candidate_brand: str,
    product_kind: ProductKind = "unknown",
) -> Optional[bool]:
    """Tri-state brand agreement with fresh-produce spelling tolerance."""
    if not query_brand or not candidate_brand:
        return None
    if query_brand == candidate_brand:
        return True
    if product_kind == "fresh" and _edit_distance_leq(query_brand, candidate_brand, 1):
        return True
    if product_kind == "fresh":
        return None
    return False


def compute_confidence(
    tfidf_score: float,
    embedding_score: float,
    brand_match: Optional[bool],
    weight_match: Optional[bool],
    product_kind: ProductKind = "unknown",
    query_brand: str = "",
    candidate_brand: str = "",
) -> float:
    """Compute an ensemble confidence score from retrieval and reranking signals.

    The base score is a weighted blend of character-level TF-IDF and semantic
    embeddings.  Brand and weight agreement adjust the score: an exact match
    adds a small bonus, an explicit mismatch subtracts a larger penalty (a
    different brand or size almost always means a different barcode).

    Args:
        tfidf_score: Raw TF-IDF cosine score from Stage 1 (``tfidf_score``
            column, 0–1).  Do **not** pass ``tfidf_score_adjusted`` — brand and
            weight effects are applied once here, not in Stage 1.
        embedding_score: Cosine similarity from Stage 2 embeddings (0–1).
        brand_match: ``True`` if query and candidate share the same brand,
            ``False`` if they have *different* brands, ``None`` if either brand
            is unknown (neutral).
        weight_match: ``True`` / ``False`` / ``None`` for weight/volume, with the
            same meaning as ``brand_match``.
        product_kind: ``branded``, ``fresh``, or ``unknown`` — adjusts brand penalties.
        query_brand: Optional explicit query brand token (overrides *brand_match* when set).
        candidate_brand: Optional candidate brand token.

    Returns:
        Final confidence in ``[0.0, 1.0]``.
    """
    if query_brand or candidate_brand:
        brand_match = resolve_brand_match(query_brand, candidate_brand, product_kind)
    elif brand_match is False and product_kind == "fresh":
        brand_match = None
    # Clamp TF-IDF to [0, 1] — cosine similarity range (guards against accidental
    # use of tfidf_score_adjusted which can exceed 1.0 after Stage-1 bonuses).
    tfidf_clamped = max(0.0, min(1.0, tfidf_score))
    embedding_clamped = max(0.0, min(1.0, embedding_score))
    base = (tfidf_clamped * TFIDF_WEIGHT) + (embedding_clamped * EMBEDDING_WEIGHT)

    if brand_match is True:
        base += BRAND_MATCH_BONUS
    elif brand_match is False:
        base -= BRAND_MISMATCH_PENALTY

    if weight_match is True:
        base += WEIGHT_MATCH_BONUS
    elif weight_match is False:
        base -= WEIGHT_MISMATCH_PENALTY

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
        (0.80, 0.85, True, None, "Good match, brand agrees, weight unknown"),
        (0.70, 0.75, None, True, "Decent match, weight agrees, brand unknown"),
        (0.50, 0.55, None, None, "Weak match, no brand/weight info"),
        (0.55, 0.98, False, True, "Brand SWAP: high embedding, wrong brand"),
        (0.60, 0.95, True, False, "Size SWAP: same brand, wrong weight"),
        (1.10, 0.95, True, True, "TF-IDF >1 clamped to 1.0 in blend"),
        (0.00, 0.00, None, None, "Zero scores"),
        (0.90, 0.90, True, True, "Borderline HIGH"),
        (0.62, 0.62, None, None, "Borderline MEDIUM"),
    ]

    print(f"{'Description':<40} {'TF-IDF':>7} {'Embed':>7} {'Brand':>6} {'Wt':>4} "
          f"{'Score':>7} {'Label':>7} {'Triage':>14} {'Color':>10}")
    print("-" * 110)

    def _flag(value: object) -> str:
        return {True: "Y", False: "N", None: "-"}[value]  # type: ignore[index]

    for tfidf, embed, brand, weight, desc in test_cases:
        score = compute_confidence(tfidf, embed, brand, weight)
        label = get_confidence_label(score)
        action = triage(score)
        color = get_confidence_color(score)
        print(
            f"{desc:<40} {tfidf:>7.2f} {embed:>7.2f} "
            f"{_flag(brand):>6} {_flag(weight):>4} "
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
