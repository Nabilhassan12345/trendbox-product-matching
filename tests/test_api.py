#!/usr/bin/env python3
"""Integration tests for the FastAPI product-matching API.

Runs every endpoint and prints PASS/FAIL for each check.
Exit code 0 when all checks pass, 1 otherwise.
"""

from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path

import pandas as pd
from fastapi.testclient import TestClient
from sqlalchemy import inspect

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

RESULTS: list[bool] = []


def check(name: str, condition: bool, detail: str = "") -> bool:
    """Record and print a single PASS/FAIL result."""
    status = "PASS" if condition else "FAIL"
    suffix = f" — {detail}" if detail else ""
    print(f"[{status}] {name}{suffix}")
    RESULTS.append(condition)
    return condition


def _make_hit(rank: int, barcode: str, name: str, confidence: float) -> dict:
    """Build a single match-result dict with consistent confidence metadata."""
    from src.confidence import get_confidence_color, get_confidence_label, triage

    confidence = max(0.0, min(1.0, confidence))
    return {
        "rank": rank,
        "barcode": barcode,
        "name": name,
        "tfidf_score": round(confidence, 4),
        "embedding_score": round(confidence, 4),
        "confidence_score": round(confidence, 4),
        "confidence_label": get_confidence_label(confidence),
        "confidence_color": get_confidence_color(confidence),
        "explanation": f"Mock explanation for {name}",
        "triage": triage(confidence),
    }


def _hits_for_band(primary_confidence: float) -> list[dict]:
    """Three ranked suggestions; rank-1 confidence decides the product band."""
    return [
        _make_hit(1, "8681558240180", "Ref Product A", primary_confidence),
        _make_hit(2, "8681558240181", "Ref Product B", primary_confidence - 0.2),
        _make_hit(3, "8681558240182", "Ref Product C", primary_confidence - 0.4),
    ]


def _make_mock_hits() -> list[dict]:
    """Return three suggestions spanning all triage bands (rank-1 = HIGH)."""
    return _hits_for_band(0.95)


class FakeMatcher:
    """Stand-in for ProductMatcher; rank-1 confidence varies by product name."""

    _built = True

    def match(self, product_name: str) -> list[dict]:
        name = product_name.lower()
        if "reject" in name:
            return _hits_for_band(0.40)
        if "review" in name:
            return _hits_for_band(0.75)
        return _hits_for_band(0.95)

    def match_many(self, product_names: list[str]) -> list[list[dict]]:
        return [self.match(name) for name in product_names]


def _seed_products(db_path: str) -> None:
    """Load a minimal barcoded + unmatched catalogue into the test database."""
    from src.database import init_db, load_products

    init_db(db_path)

    df_barcoded = pd.DataFrame(
        {
            "barcode": ["8681558240180", "8681558240181", "8681558240182", "8681558240180"],
            "name": ["Ref A", "Ref B", "Ref C", "Ref A duplicate"],
            "name_clean": ["ref a", "ref b", "ref c", "ref a dup"],
            "brand": ["ref", "ref", "ref", "ref"],
            "weight": ["100 g", "100 g", "100 g", "100 g"],
        }
    )
    # Three distinct products so per-product triage exercises all three bands.
    df_unmatched = pd.DataFrame(
        {
            "barcode": ["", "", ""],
            "name": ["Approve Product", "Review Product", "Reject Product"],
            "name_clean": ["approve product", "review product", "reject product"],
            "brand": ["approve", "review", "reject"],
            "weight": ["150 g", "150 g", "150 g"],
        }
    )
    load_products(df_barcoded, df_unmatched)


def test_database_layer(db_path: str) -> None:
    """Checks 1–3: tables, duplicate handling, empty pending queue."""
    from src.database import Base, get_next_pending, init_db, load_products

    init_db(db_path)
    engine = None
    import src.database as db_module

    engine = db_module._engine
    tables = set(inspect(engine).get_table_names())
    check(
        "Database creates products, matches, decisions tables",
        tables >= {"products", "matches", "decisions"},
        f"found={sorted(tables)}",
    )

    df_barcoded = pd.DataFrame(
        {
            "barcode": ["111", "111", "222"],
            "name": ["A", "A dup", "B"],
            "name_clean": ["a", "a dup", "b"],
        }
    )
    df_unmatched = pd.DataFrame(
        {
            "barcode": ["", ""],
            "name": ["X", "X"],
            "name_clean": ["x", "x"],
        }
    )
    counts = load_products(df_barcoded, df_unmatched)
    check(
        "load_products deduplicates barcoded rows",
        counts["barcoded"] == 2,
        f"barcoded={counts['barcoded']}",
    )
    check(
        "load_products deduplicates unmatched rows",
        counts["unmatched"] == 1,
        f"unmatched={counts['unmatched']}",
    )
    check(
        "get_next_pending returns None when queue is empty",
        get_next_pending() is None,
    )


def test_matcher_format() -> None:
    """Check 4: matcher.match() result shape."""
    from src.matcher import MATCH_RESULT_KEYS

    hits = _make_mock_hits()
    check("matcher result has 3 suggestions", len(hits) == 3)
    check(
        "matcher.match() returns all required keys",
        all(set(hit.keys()) == MATCH_RESULT_KEYS for hit in hits),
    )
    check(
        "matcher.match() triage covers all three bands",
        {hit["triage"] for hit in hits} == {"auto_approve", "review", "auto_reject"},
    )


def test_no_circular_imports() -> None:
    """Check 7: import graph is acyclic."""
    import importlib

    modules = [
        "src.confidence",
        "src.preprocess",
        "src.tfidf_retriever",
        "src.embedding_reranker",
        "src.matcher",
        "src.database",
        "api.schemas",
        "api.main",
    ]
    ok = True
    for name in modules:
        try:
            importlib.import_module(name)
        except Exception as exc:
            ok = False
            check(f"import {name}", False, str(exc))
    check("No circular imports across core modules", ok)


def test_api_endpoints(client: TestClient) -> int | None:
    """Checks 5–6, 8–9: schemas, CORS, startup matcher, batch triage, all routes."""
    import api.main as main
    from api.schemas import (
        BatchProcessResponse,
        DecisionResponse,
        HealthResponse,
        MatchResponse,
        StatsResponse,
    )

    check(
        "Startup event loads matcher (mock injected)",
        main.matcher is not None and main.matcher._built,
    )

    response = client.get("/health")
    check("GET /health status 200", response.status_code == 200, response.text)
    if response.status_code == 200:
        health = HealthResponse.model_validate(response.json())
        check("GET /health schema valid", health.status == "ok")
        check("GET /health products_indexed > 0", health.products_indexed > 0)

    cors = client.options(
        "/health",
        headers={
            "Origin": "http://localhost:8501",
            "Access-Control-Request-Method": "GET",
        },
    )
    check(
        "CORS allows localhost:8501",
        cors.headers.get("access-control-allow-origin") == "http://localhost:8501",
        cors.headers.get("access-control-allow-origin", "missing"),
    )

    response = client.get("/stats")
    check("GET /stats status 200", response.status_code == 200)
    if response.status_code == 200:
        stats = StatsResponse.model_validate(response.json())
        check("GET /stats schema valid", stats.total_products > 0)

    response = client.get("/match/next")
    check("GET /match/next 404 when queue empty", response.status_code == 404)

    response = client.post("/batch_process")
    check("POST /batch_process status 200", response.status_code == 200, response.text)
    pending_match_id = None
    if response.status_code == 200:
        batch = BatchProcessResponse.model_validate(response.json())
        check(
            "POST /batch_process applies auto_approved band",
            batch.auto_approved >= 1,
            f"auto_approved={batch.auto_approved}",
        )
        check(
            "POST /batch_process applies pending band",
            batch.pending >= 1,
            f"pending={batch.pending}",
        )
        check(
            "POST /batch_process applies auto_rejected band",
            batch.auto_rejected >= 1,
            f"auto_rejected={batch.auto_rejected}",
        )
        check(
            "POST /batch_process total_products equals band sum",
            batch.total_products
            == batch.auto_approved + batch.pending + batch.auto_rejected,
        )
        check(
            "POST /batch_process persists alternatives (rows >= products)",
            batch.total_suggestions >= batch.total_products,
            f"rows={batch.total_suggestions}, products={batch.total_products}",
        )

    response = client.get("/stats")
    if response.status_code == 200:
        stats = StatsResponse.model_validate(response.json())
        check("GET /stats reflects batch counts", stats.pending >= 1)

    response = client.get("/match/next")
    check("GET /match/next status 200 after batch", response.status_code == 200, response.text)
    if response.status_code == 200:
        match = MatchResponse.model_validate(response.json())
        check("GET /match/next schema valid", match.product_id > 0)
        check("GET /match/next has suggestions", len(match.suggestions) >= 1)
        check(
            "GET /match/next suggestions include match_id",
            all(s.match_id > 0 for s in match.suggestions),
        )
        pending_match_id = match.suggestions[0].match_id

    if pending_match_id is not None:
        response = client.post(
            f"/decision/{pending_match_id}",
            json={"decision": "approved", "note": "test approval"},
        )
        check("POST /decision/{id} status 200", response.status_code == 200, response.text)
        if response.status_code == 200:
            decision = DecisionResponse.model_validate(response.json())
            check("POST /decision schema valid", decision.success is True)

        # Deciding one product resolves it entirely (siblings superseded), so the
        # single pending product should leave the queue.
        response = client.get("/match/next")
        check(
            "GET /match/next 404 after the only pending product is resolved",
            response.status_code == 404,
            response.text,
        )

    response = client.post(
        "/decision/999999",
        json={"decision": "approved"},
    )
    check("POST /decision/{id} 404 for unknown match", response.status_code == 404)

    response = client.post(
        "/decision/1",
        json={"decision": "maybe"},
    )
    check("POST /decision/{id} 422 for invalid decision", response.status_code == 422)

    return pending_match_id


def main() -> int:
    """Run all checks and return process exit code."""
    db_path = tempfile.mktemp(suffix=".db")
    os.environ["TRENDBOX_DB_PATH"] = db_path
    os.environ["TRENDBOX_MATCHER_INDEX"] = str(ROOT / "nonexistent_matcher_index_for_tests")

    print("=== Layer checks (database, matcher, imports) ===\n")
    test_database_layer(db_path)
    test_matcher_format()
    test_no_circular_imports()

    print("\n=== API endpoint checks ===\n")
    _seed_products(db_path)

    import api.main as main

    with TestClient(main.app) as client:
        main.matcher = FakeMatcher()
        test_api_endpoints(client)

    passed = sum(RESULTS)
    total = len(RESULTS)
    print(f"\n=== Summary: {passed}/{total} passed ===")
    return 0 if passed == total else 1


if __name__ == "__main__":
    sys.exit(main())
