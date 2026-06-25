#!/usr/bin/env python3
"""Read-only audit of rank-1 pack-size quality metrics in matching.db."""

from __future__ import annotations

import argparse
import csv
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.config import DB_PATH
from src.database import STATUS_AUTO_APPROVED, init_db
from src.db.models import Match
from src.db.quality import get_quality_summary
from src.db.session import get_session
from src.match_quality import SIZE_CONFLICT, SIZE_UNKNOWN, SIZE_VERIFIED


def _audit_rows(conflicts: list[Match]) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    for match in conflicts:
        unmatched = match.unmatched_product
        suggested = match.suggested_product
        rows.append(
            {
                "match_id": match.id,
                "status": match.status,
                "confidence_score": round(float(match.confidence_score), 4),
                "query_name": unmatched.name if unmatched else "",
                "query_weight": match.query_weight or (unmatched.weight if unmatched else ""),
                "suggested_name": suggested.name if suggested else "",
                "suggested_weight": match.suggested_weight or (suggested.weight if suggested else ""),
                "size_verdict": match.size_verdict or SIZE_UNKNOWN,
            }
        )
    return rows


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Audit rank-1 size verdicts and guardrail integrity in matching.db",
    )
    parser.add_argument(
        "--db",
        type=Path,
        default=DB_PATH,
        help=f"SQLite database path (default: {DB_PATH.relative_to(ROOT)})",
    )
    parser.add_argument(
        "--csv",
        type=Path,
        default=None,
        help="Optional path to write conflict-auto-approved rows as CSV",
    )
    args = parser.parse_args()

    if not args.db.is_file():
        print(f"ERROR: database not found: {args.db}", file=sys.stderr)
        return 1

    os.environ["TRENDBOX_DB_PATH"] = str(args.db.resolve())
    init_db(str(args.db))

    summary = get_quality_summary()
    verified = int(summary["size_verified_count"])
    conflict = int(summary["size_conflict_count"])
    unknown = int(summary["size_unknown_count"])
    integrity = float(summary["catalog_integrity_pct"])
    guardrails = int(summary["guardrail_blocked_count"])

    with get_session() as session:
        conflicts_auto = (
            session.query(Match)
            .filter(
                Match.rank == 1,
                Match.size_verdict == SIZE_CONFLICT,
                Match.status == STATUS_AUTO_APPROVED,
            )
            .order_by(Match.confidence_score.desc())
            .limit(20)
            .all()
        )

    conflict_rows = _audit_rows(conflicts_auto)

    print("=== Size quality audit ===")
    print(f"Database: {args.db}")
    print()
    print("Rank-1 matches by size_verdict:")
    print(f"  size_verified : {verified:,}")
    print(f"  size_conflict : {conflict:,}")
    print(f"  size_unknown  : {unknown:,}")
    print()
    print(f"catalog_integrity_pct : {integrity * 100:.2f}%")
    print(f"guardrail_blocked     : {guardrails:,}")
    print()
    print(
        f"size_conflict + auto_approved (expect 0 after Phase 1): "
        f"{len(conflicts_auto):,}"
    )

    if conflict_rows:
        print()
        print("Top size_conflict still auto_approved:")
        for row in conflict_rows:
            print(
                f"  #{row['match_id']} conf={row['confidence_score']} "
                f"{row['query_weight']!r} vs {row['suggested_weight']!r} "
                f"— {row['query_name'][:40]!r} → {row['suggested_name'][:40]!r}"
            )
    else:
        print("  (none — OK)")

    if args.csv:
        args.csv.parent.mkdir(parents=True, exist_ok=True)
        fieldnames = list(conflict_rows[0].keys()) if conflict_rows else [
            "match_id",
            "status",
            "confidence_score",
            "query_name",
            "query_weight",
            "suggested_name",
            "suggested_weight",
            "size_verdict",
        ]
        with args.csv.open("w", newline="", encoding="utf-8") as handle:
            writer = csv.DictWriter(handle, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(conflict_rows)
        print()
        print(f"Wrote CSV: {args.csv}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
