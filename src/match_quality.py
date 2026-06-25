"""Match-quality guardrails: size verdicts and triage policy helpers."""

from __future__ import annotations

from typing import TYPE_CHECKING, Literal, Optional

from src.config import SIZE_CONFLICT_POLICY
from src.pack_profile import (
    compare_pack_profiles,
    format_pack_label,
    parse_pack_profile,
)

if TYPE_CHECKING:
    from src.confidence import ProductKind

SizeVerdict = Literal["size_verified", "size_conflict", "size_unknown"]

SIZE_VERIFIED: SizeVerdict = "size_verified"
SIZE_CONFLICT: SizeVerdict = "size_conflict"
SIZE_UNKNOWN: SizeVerdict = "size_unknown"


def classify_pack_from_names(query_name: str, candidate_name: str) -> SizeVerdict:
    """Classify pack agreement using unit weight, pack count, and multipack totals."""
    left = parse_pack_profile(query_name)
    right = parse_pack_profile(candidate_name)
    return compare_pack_profiles(left, right)  # type: ignore[return-value]


def classify_size(query_weight: str, candidate_weight: str) -> SizeVerdict:
    """Classify pack-size agreement between display weight tokens (legacy)."""
    query = (query_weight or "").strip()
    candidate = (candidate_weight or "").strip()
    if query and candidate:
        if query == candidate:
            return SIZE_VERIFIED
        return SIZE_CONFLICT
    return SIZE_UNKNOWN


def pack_label_from_name(name: str) -> str:
    """Formatted pack summary for persistence and UI."""
    return format_pack_label(parse_pack_profile(name))


def classify_brand_match(
    query_brand: str,
    candidate_brand: str,
    product_kind: "ProductKind" = "unknown",
) -> Optional[bool]:
    """Tri-state brand agreement; delegates to :func:`confidence.resolve_brand_match`."""
    from src.confidence import resolve_brand_match

    return resolve_brand_match(query_brand, candidate_brand, product_kind)


def should_block_auto_approve(verdict: SizeVerdict) -> bool:
    """Return True when auto-approve must be blocked (size mismatch)."""
    return verdict == SIZE_CONFLICT


def size_conflict_triage_action() -> str:
    """Map configured size-conflict policy to a triage action."""
    if SIZE_CONFLICT_POLICY == "reject":
        return "auto_reject"
    return "review"


def build_guardrail_explanation(
    verdict: SizeVerdict,
    query_weight: str,
    candidate_weight: str,
    *,
    query_name: str = "",
    candidate_name: str = "",
) -> str:
    """Human-readable guardrail text for operator UI."""
    if query_name or candidate_name:
        query_label = pack_label_from_name(query_name) if query_name else (query_weight or "unknown")
        candidate_label = (
            pack_label_from_name(candidate_name) if candidate_name else (candidate_weight or "unknown")
        )
    else:
        query_label = (query_weight or "").strip() or "unknown"
        candidate_label = (candidate_weight or "").strip() or "unknown"

    if verdict == SIZE_VERIFIED:
        if query_label != "unknown":
            return f"Pack size verified ({query_label})."
        return "Pack size verified."
    if verdict == SIZE_CONFLICT:
        return (
            f"Pack size conflict: source {query_label} vs suggestion {candidate_label}."
        )
    return "Pack size unknown on one or both sides — size guardrail not applied."
