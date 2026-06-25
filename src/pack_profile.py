"""Structured pack-size parsing and comparison for Turkish retail product names."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Optional

from src.preprocess import _canonical_unit, extract_weight, normalize

# 10*18 g, 10x18g, 10×18 gr
_MULTIPACK_PATTERN = re.compile(
    r"(\d+)\s*[*xX×]\s*(\d+(?:[.,]\d+)?)\s*(gr|gram|g|kg|ml|lt|l|litre)\b",
    re.IGNORECASE,
)
# 10'lu, 10 lu, 10lu
_PACK_LU_PATTERN = re.compile(r"(\d+)\s*['']?lu\b", re.IGNORECASE)
# 56 adet (prefer the last occurrence when multiple numbers exist)
_ADET_PATTERN = re.compile(r"(\d+)\s+adet\b", re.IGNORECASE)


@dataclass(frozen=True)
class PackProfile:
    """Parsed pack descriptor extracted from a product name."""

    unit_weight: str = ""
    pack_count: Optional[int] = None
    count_label: str = ""
    multipack: str = ""
    total_weight_g: Optional[float] = None

    def has_comparable_signal(self) -> bool:
        """True when at least one field can be used for guardrail comparison."""
        return bool(self.unit_weight or self.pack_count is not None or self.total_weight_g is not None)


def _parse_number(raw: str) -> float:
    return float(raw.replace(",", "."))


def _grams_from_weight_token(number: str, unit: str) -> Optional[float]:
    value = _parse_number(number)
    token = unit.lower().strip()
    if token in ("gr", "gram", "g"):
        return value
    if token == "kg":
        return value * 1000.0
    return None


def parse_pack_profile(name: str) -> PackProfile:
    """Extract unit weight, pack count, multipack, and total grams from a name."""
    if not name or not isinstance(name, str):
        return PackProfile()

    raw_text = name
    text = normalize(name)
    if not text:
        return PackProfile()

    unit_weight = ""
    pack_count: Optional[int] = None
    count_label = ""
    multipack = ""
    total_weight_g: Optional[float] = None

    multipack_match = _MULTIPACK_PATTERN.search(raw_text) or _MULTIPACK_PATTERN.search(text)
    if multipack_match:
        count = int(multipack_match.group(1))
        unit_number = multipack_match.group(2).replace(",", ".")
        unit_token = multipack_match.group(3)
        unit = _canonical_unit(unit_token)
        unit_weight = f"{unit_number} {unit}"
        pack_count = count
        count_label = "pack"
        multipack = f"{count}x{unit_number} {unit}"
        grams = _grams_from_weight_token(unit_number, unit_token)
        if grams is not None:
            total_weight_g = round(count * grams, 4)

    if not unit_weight:
        unit_weight = extract_weight(text)

    lu_match = _PACK_LU_PATTERN.search(raw_text) or _PACK_LU_PATTERN.search(text)
    if lu_match:
        lu_count = int(lu_match.group(1))
        if pack_count is None:
            pack_count = lu_count
            count_label = "lu"

    adet_matches = list(_ADET_PATTERN.finditer(text))
    if adet_matches:
        adet_count = int(adet_matches[-1].group(1))
        if pack_count is None or adet_count != pack_count:
            pack_count = adet_count
            count_label = "adet"

    if total_weight_g is None and unit_weight and pack_count and unit_weight.endswith(" g"):
        try:
            per_unit = float(unit_weight.split()[0])
            total_weight_g = round(per_unit * pack_count, 4)
        except ValueError:
            pass

    return PackProfile(
        unit_weight=unit_weight,
        pack_count=pack_count,
        count_label=count_label,
        multipack=multipack,
        total_weight_g=total_weight_g,
    )


def format_pack_label(profile: PackProfile) -> str:
    """Human-readable pack summary for UI and persistence."""
    parts: list[str] = []
    if profile.unit_weight:
        parts.append(profile.unit_weight)
    if profile.multipack:
        parts.append(f"({profile.multipack})")
    elif profile.pack_count is not None:
        label = profile.count_label or "pack"
        parts.append(f"× {profile.pack_count} {label}")
    if profile.total_weight_g is not None and profile.pack_count and profile.pack_count > 1:
        parts.append(f"[{profile.total_weight_g:g} g total]")
    return " ".join(parts) if parts else ""


def _totals_conflict(left: Optional[float], right: Optional[float], *, tolerance: float = 0.5) -> bool:
    if left is None or right is None:
        return False
    return abs(left - right) > tolerance


def pack_profiles_conflict(left: PackProfile, right: PackProfile) -> bool:
    """Return True when any known pack dimension disagrees."""
    if left.unit_weight and right.unit_weight and left.unit_weight != right.unit_weight:
        return True
    if (
        left.pack_count is not None
        and right.pack_count is not None
        and left.pack_count != right.pack_count
    ):
        return True
    if _totals_conflict(left.total_weight_g, right.total_weight_g):
        return True
    return False


def pack_profiles_verified(left: PackProfile, right: PackProfile) -> bool:
    """Return True when comparable fields are present and all agree."""
    compared = False
    if left.unit_weight and right.unit_weight:
        compared = True
        if left.unit_weight != right.unit_weight:
            return False
    if left.pack_count is not None and right.pack_count is not None:
        compared = True
        if left.pack_count != right.pack_count:
            return False
    if left.total_weight_g is not None and right.total_weight_g is not None:
        compared = True
        if _totals_conflict(left.total_weight_g, right.total_weight_g):
            return False
    return compared


def pack_pool_eligible(query: PackProfile, candidate: PackProfile) -> bool:
    """Retrieval filter: exclude candidates with a definite pack mismatch."""
    if not query.has_comparable_signal():
        return True
    if not candidate.has_comparable_signal():
        return True
    return not pack_profiles_conflict(query, candidate)


def compare_pack_profiles(left: PackProfile, right: PackProfile) -> str:
    """Map two profiles to a size verdict string."""
    if pack_profiles_conflict(left, right):
        return "size_conflict"
    if pack_profiles_verified(left, right):
        return "size_verified"
    return "size_unknown"
