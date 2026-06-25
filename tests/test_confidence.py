#!/usr/bin/env python3
"""Tests for confidence scoring and triage guardrails."""

from __future__ import annotations

from unittest import mock

from src.confidence import triage
from tests.helpers import check_eq as check


def test_size_conflict_never_auto_approves_review_policy() -> None:
    print("=== size_conflict triage (review policy) ===\n")
    with mock.patch("src.match_quality.SIZE_CONFLICT_POLICY", "review"):
        action = triage(
            0.95,
            brand_match=True,
            weight_match=False,
            query_clean="nutella 400 g",
            candidate_clean="nutella 800 g",
        )
        check("high confidence blocked from auto_approve", "review", action)


def test_size_conflict_reject_policy() -> None:
    print("\n=== size_conflict triage (reject policy) ===\n")
    with mock.patch("src.match_quality.SIZE_CONFLICT_POLICY", "reject"):
        action = triage(
            0.95,
            brand_match=True,
            weight_match=False,
            query_clean="nutella 400 g",
            candidate_clean="nutella 800 g",
        )
        check("reject policy auto_rejects", "auto_reject", action)


def test_size_unknown_allows_high_confidence_auto_approve() -> None:
    print("\n=== size_unknown allows auto_approve ===\n")
    action = triage(
        0.95,
        brand_match=False,
        weight_match=False,
        query_clean="nutella",
        candidate_clean="nutella",
    )
    check("no weights on either side", "auto_approve", action)


def test_exact_name_still_auto_approves() -> None:
    print("\n=== exact name auto_approve ===\n")
    action = triage(
        0.50,
        brand_match=False,
        weight_match=False,
        query_clean="nutella 400 g",
        candidate_clean="nutella 400 g",
    )
    check("exact name wins before size guardrail", "auto_approve", action)
