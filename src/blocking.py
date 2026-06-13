"""Stage 0 deterministic resolver — exact and fuzzy name blocking before ML."""

from __future__ import annotations

import logging
from difflib import SequenceMatcher
from typing import Any, Dict, List, Optional, Set

import pandas as pd

from src.confidence import get_confidence_color, get_confidence_label, triage
from src.preprocess import extract_brand, extract_weight, normalize
from src.reference_catalog import build_barcode_lookup, build_name_to_barcodes

logger = logging.getLogger(__name__)

FUZZY_CUTOFF = 0.92
CONFIDENCE_EXACT_SINGLE = 1.0
CONFIDENCE_EXACT_MULTI = 0.85
CONFIDENCE_FUZZY_SINGLE = 0.92
CONFIDENCE_FUZZY_MULTI = 0.85


def _token_edit_distance_leq(a: str, b: str, max_distance: int) -> bool:
    """Levenshtein check for short tokens (Turkish spelling variants)."""
    if a == b:
        return True
    if abs(len(a) - len(b)) > max_distance:
        return False
    if len(a) < len(b):
        a, b = b, a
    previous = list(range(len(b) + 1))
    for i, char_a in enumerate(a, start=1):
        current = [i]
        row_min = current[0]
        for j, char_b in enumerate(b, start=1):
            value = min(current[j - 1] + 1, previous[j] + 1, previous[j - 1] + (char_a != char_b))
            current.append(value)
            row_min = min(row_min, value)
        if row_min > max_distance:
            return False
        previous = current
    return previous[-1] <= max_distance


def names_fuzzy_match(query: str, candidate: str) -> bool:
    """Return True when two normalised names are the same product spelling variant."""
    if query == candidate:
        return True
    if SequenceMatcher(None, query, candidate).ratio() >= FUZZY_CUTOFF:
        return True

    q_tokens = query.split()
    c_tokens = candidate.split()
    if len(q_tokens) != len(c_tokens) or not q_tokens:
        return False

    for left, right in zip(q_tokens, c_tokens):
        if left == right:
            continue
        if _token_edit_distance_leq(left, right, 1):
            continue
        if SequenceMatcher(None, left, right).ratio() < 0.85:
            return False
    return True


class Stage0Resolver:
    """Resolve unmatched products by exact or high-similarity name blocking."""

    def __init__(self, df_index: pd.DataFrame) -> None:
        self.name_to_barcodes = build_name_to_barcodes(df_index)
        self.barcode_lookup = build_barcode_lookup(df_index)
        self._name_keys = list(self.name_to_barcodes.keys())
        self._by_last_token: Dict[str, List[str]] = {}
        self._by_shape: Dict[tuple[int, str], List[str]] = {}
        for name in self._name_keys:
            parts = name.split()
            if not parts:
                continue
            last = parts[-1]
            self._by_last_token.setdefault(last, []).append(name)
            shape_key = (len(parts), last)
            self._by_shape.setdefault(shape_key, []).append(name)
        logger.info(
            "Stage 0 resolver ready (%s name keys, %s barcodes)",
            f"{len(self._name_keys):,}",
            f"{len(self.barcode_lookup):,}",
        )

    def _fuzzy_candidates(self, query: str) -> List[str]:
        """Narrow fuzzy search: same token count, same last token, same weight if present."""
        parts = query.split()
        if not parts:
            return []

        query_weight = extract_weight(query)
        shape_key = (len(parts), parts[-1])
        pool = self._by_shape.get(shape_key, [])

        if not query_weight:
            return pool

        return [name for name in pool if extract_weight(name) == query_weight]

    def resolve_query(self, query: str) -> Optional[List[Dict[str, Any]]]:
        """Resolve a pre-normalised query string."""
        if not query:
            return None

        barcodes = self.name_to_barcodes.get(query)
        if barcodes:
            return self._build_hits(query, barcodes, method="exact")

        for matched_name in self._fuzzy_candidates(query):
            if not names_fuzzy_match(query, matched_name):
                continue
            barcodes = self.name_to_barcodes[matched_name]
            return self._build_hits(query, barcodes, method="fuzzy", matched_name=matched_name)

        return None

    def resolve_many(self, queries: List[str]) -> List[Optional[List[Dict[str, Any]]]]:
        """Bulk Stage 0: O(1) exact dict lookups, fuzzy only for remaining rows."""
        results: List[Optional[List[Dict[str, Any]]]] = [None] * len(queries)
        fuzzy_indices: List[int] = []

        for index, query in enumerate(queries):
            if not query:
                continue
            barcodes = self.name_to_barcodes.get(query)
            if barcodes:
                results[index] = self._build_hits(query, barcodes, method="exact")
            else:
                fuzzy_indices.append(index)

        for index in fuzzy_indices:
            query = queries[index]
            results[index] = self.resolve_query(query)

        return results

    def resolve(self, product_name: str) -> Optional[List[Dict[str, Any]]]:
        """Return synthetic matcher hits or ``None`` to fall through to ML."""
        return self.resolve_query(normalize(product_name))

    def _build_hits(
        self,
        query: str,
        barcodes: Set[str],
        *,
        method: str,
        matched_name: str | None = None,
    ) -> List[Dict[str, Any]]:
        ordered = sorted(barcodes)
        barcode = ordered[0]
        ref = self.barcode_lookup[barcode]
        ambiguous = len(ordered) > 1

        if method == "exact":
            confidence = CONFIDENCE_EXACT_MULTI if ambiguous else CONFIDENCE_EXACT_SINGLE
            explanation = (
                f"Stage 0 exact name match ({len(ordered)} barcodes — review required)"
                if ambiguous
                else "Stage 0 exact name match"
            )
        else:
            confidence = CONFIDENCE_FUZZY_MULTI if ambiguous else CONFIDENCE_FUZZY_SINGLE
            explanation = (
                f"Stage 0 fuzzy name match ({matched_name!r}, {len(ordered)} barcodes — review required)"
                if ambiguous
                else f"Stage 0 fuzzy name match ({matched_name!r})"
            )

        label = get_confidence_label(confidence)
        candidate_clean = str(ref["name_clean"])
        brand_match = bool(
            extract_brand(query)
            and extract_brand(candidate_clean)
            and extract_brand(query) == extract_brand(candidate_clean)
        )
        weight_match = bool(
            extract_weight(query)
            and extract_weight(candidate_clean)
            and extract_weight(query) == extract_weight(candidate_clean)
        )
        hit = {
            "rank": 1,
            "barcode": barcode,
            "name": ref["name"],
            "name_clean": ref["name_clean"],
            "tfidf_score": confidence,
            "embedding_score": confidence,
            "confidence_score": round(confidence, 4),
            "confidence_label": label,
            "confidence_color": get_confidence_color(confidence),
            "explanation": explanation,
            "triage": triage(
                confidence,
                brand_match,
                weight_match,
                query,
                candidate_clean,
            ),
        }
        return [hit]
