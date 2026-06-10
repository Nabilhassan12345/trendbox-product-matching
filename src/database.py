"""SQLite persistence layer for products, matches, and human review decisions."""

from __future__ import annotations

import logging
from contextlib import contextmanager
from datetime import datetime, timezone
from typing import Any, Dict, Generator, List, Optional

import pandas as pd
from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    create_engine,
    func,
)
from sqlalchemy.orm import Session, declarative_base, relationship, sessionmaker

logger = logging.getLogger(__name__)

Base = declarative_base()

_engine = None
_SessionLocal: Optional[sessionmaker] = None


def _utcnow() -> datetime:
    """Return the current UTC timestamp."""
    return datetime.now(timezone.utc)


class Product(Base):
    """A catalogue product — barcoded reference or unmatched item."""

    __tablename__ = "products"

    id = Column(Integer, primary_key=True, autoincrement=True)
    barcode = Column(String, nullable=True, index=True)
    name = Column(String, nullable=False)
    name_clean = Column(String, nullable=False)
    brand = Column(String, nullable=True)
    weight = Column(String, nullable=True)
    has_barcode = Column(Boolean, nullable=False, default=False)
    created_at = Column(DateTime, nullable=False, default=_utcnow)

    unmatched_matches = relationship(
        "Match",
        foreign_keys="Match.unmatched_product_id",
        back_populates="unmatched_product",
    )
    suggested_matches = relationship(
        "Match",
        foreign_keys="Match.suggested_product_id",
        back_populates="suggested_product",
    )

    def to_dict(self) -> Dict[str, Any]:
        """Serialize the product to a plain dictionary."""
        return {
            "id": self.id,
            "barcode": self.barcode,
            "name": self.name,
            "name_clean": self.name_clean,
            "brand": self.brand,
            "weight": self.weight,
            "has_barcode": self.has_barcode,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }


class Match(Base):
    """A suggested link between an unmatched product and a reference product."""

    __tablename__ = "matches"

    id = Column(Integer, primary_key=True, autoincrement=True)
    unmatched_product_id = Column(Integer, ForeignKey("products.id"), nullable=False, index=True)
    suggested_product_id = Column(Integer, ForeignKey("products.id"), nullable=False, index=True)
    tfidf_score = Column(Float, nullable=False)
    embedding_score = Column(Float, nullable=False)
    confidence_score = Column(Float, nullable=False)
    confidence_label = Column(String, nullable=False)
    rank = Column(Integer, nullable=False)
    status = Column(String, nullable=False, default="pending", index=True)
    created_at = Column(DateTime, nullable=False, default=_utcnow)

    unmatched_product = relationship(
        "Product",
        foreign_keys=[unmatched_product_id],
        back_populates="unmatched_matches",
    )
    suggested_product = relationship(
        "Product",
        foreign_keys=[suggested_product_id],
        back_populates="suggested_matches",
    )
    decisions = relationship("Decision", back_populates="match", cascade="all, delete-orphan")

    def to_dict(self, include_products: bool = False) -> Dict[str, Any]:
        """Serialize the match to a plain dictionary."""
        data: Dict[str, Any] = {
            "id": self.id,
            "unmatched_product_id": self.unmatched_product_id,
            "suggested_product_id": self.suggested_product_id,
            "tfidf_score": self.tfidf_score,
            "embedding_score": self.embedding_score,
            "confidence_score": self.confidence_score,
            "confidence_label": self.confidence_label,
            "rank": self.rank,
            "status": self.status,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }
        if include_products:
            data["unmatched_product"] = self.unmatched_product.to_dict()
            data["suggested_product"] = self.suggested_product.to_dict()
        return data


class Decision(Base):
    """Human operator approval or rejection of a match suggestion."""

    __tablename__ = "decisions"

    id = Column(Integer, primary_key=True, autoincrement=True)
    match_id = Column(Integer, ForeignKey("matches.id"), nullable=False, index=True)
    decision = Column(String, nullable=False)
    operator_note = Column(String, nullable=True)
    decided_at = Column(DateTime, nullable=False, default=_utcnow)

    match = relationship("Match", back_populates="decisions")

    def to_dict(self, include_match: bool = False) -> Dict[str, Any]:
        """Serialize the decision to a plain dictionary."""
        data: Dict[str, Any] = {
            "id": self.id,
            "match_id": self.match_id,
            "decision": self.decision,
            "operator_note": self.operator_note,
            "decided_at": self.decided_at.isoformat() if self.decided_at else None,
        }
        if include_match and self.match:
            data["match"] = self.match.to_dict(include_products=True)
        return data


def _require_session_factory() -> sessionmaker:
    """Return the configured session factory or raise."""
    if _SessionLocal is None:
        raise RuntimeError("Database not initialised — call init_db() first")
    return _SessionLocal


@contextmanager
def get_session() -> Generator[Session, None, None]:
    """Provide a transactional database session."""
    session_factory = _require_session_factory()
    session = session_factory()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def init_db(db_path: str) -> None:
    """Create the SQLite engine, tables, and session factory.

    Args:
        db_path: Filesystem path to the ``.db`` file, or a full SQLAlchemy URL.
    """
    global _engine, _SessionLocal

    if db_path.startswith("sqlite"):
        url = db_path
    else:
        url = f"sqlite:///{db_path}"

    logger.info("Initialising database at %s", url)
    _engine = create_engine(url, echo=False, future=True)
    Base.metadata.create_all(_engine)
    _SessionLocal = sessionmaker(bind=_engine, autoflush=False, autocommit=False, future=True)
    logger.info("Database tables ready")


def _dedupe_barcoded(df: pd.DataFrame) -> pd.DataFrame:
    """Drop duplicate barcodes, keeping the first occurrence."""
    before = len(df)
    deduped = df.drop_duplicates(subset=["barcode"], keep="first").reset_index(drop=True)
    dropped = before - len(deduped)
    if dropped:
        logger.warning("Dropped %s duplicate barcoded products (kept first per barcode)", f"{dropped:,}")
    return deduped


def _dedupe_unmatched(df: pd.DataFrame) -> pd.DataFrame:
    """Drop duplicate unmatched names, keeping the first occurrence."""
    before = len(df)
    deduped = df.drop_duplicates(subset=["name_clean"], keep="first").reset_index(drop=True)
    dropped = before - len(deduped)
    if dropped:
        logger.warning("Dropped %s duplicate unmatched products (kept first per name)", f"{dropped:,}")
    return deduped


def _product_from_row(row: pd.Series, has_barcode: bool) -> Product:
    """Build a :class:`Product` ORM instance from a DataFrame row."""
    barcode = row.get("barcode") or None
    if barcode == "":
        barcode = None
    brand = row.get("brand") or None
    weight = row.get("weight") or None
    return Product(
        barcode=barcode,
        name=str(row["name"]),
        name_clean=str(row["name_clean"]),
        brand=brand if brand else None,
        weight=weight if weight else None,
        has_barcode=has_barcode,
    )


def load_products(df_barcoded: pd.DataFrame, df_unmatched: pd.DataFrame) -> Dict[str, int]:
    """Load barcoded and unmatched products into the database.

    Replaces any existing products (and cascaded matches/decisions).

    Args:
        df_barcoded: Reference products with ``name_clean``, ``brand``, ``weight``.
        df_unmatched: Products to match with the same enrichment columns.

    Returns:
        Dict with ``barcoded`` and ``unmatched`` insert counts.
    """
    required = {"name", "name_clean"}
    for label, frame in (("df_barcoded", df_barcoded), ("df_unmatched", df_unmatched)):
        missing = required - set(frame.columns)
        if missing:
            raise ValueError(f"{label} missing columns: {sorted(missing)}")

    df_barcoded = _dedupe_barcoded(df_barcoded)
    df_unmatched = _dedupe_unmatched(df_unmatched)

    with get_session() as session:
        session.query(Decision).delete()
        session.query(Match).delete()
        deleted = session.query(Product).delete()
        if deleted:
            logger.info("Cleared %s existing products (and related rows)", f"{deleted:,}")

        barcoded_rows = [_product_from_row(row, has_barcode=True) for _, row in df_barcoded.iterrows()]
        unmatched_rows = [_product_from_row(row, has_barcode=False) for _, row in df_unmatched.iterrows()]

        session.add_all(barcoded_rows + unmatched_rows)
        session.flush()

        counts = {"barcoded": len(barcoded_rows), "unmatched": len(unmatched_rows)}
        logger.info(
            "Loaded %s barcoded and %s unmatched products",
            f"{counts['barcoded']:,}",
            f"{counts['unmatched']:,}",
        )
        return counts


def save_matches(matches: List[Dict[str, Any]]) -> int:
    """Persist a batch of match suggestions.

    Each dict must contain:
    ``unmatched_product_id``, ``suggested_product_id``, ``tfidf_score``,
    ``embedding_score``, ``confidence_score``, ``confidence_label``,
    ``rank``, and ``status``.

    Args:
        matches: List of match record dictionaries.

    Returns:
        Number of rows inserted.
    """
    if not matches:
        logger.warning("save_matches called with empty list")
        return 0

    required_keys = {
        "unmatched_product_id",
        "suggested_product_id",
        "tfidf_score",
        "embedding_score",
        "confidence_score",
        "confidence_label",
        "rank",
        "status",
    }

    records: List[Match] = []
    for item in matches:
        missing = required_keys - item.keys()
        if missing:
            raise ValueError(f"Match record missing keys: {sorted(missing)}")

        records.append(
            Match(
                unmatched_product_id=int(item["unmatched_product_id"]),
                suggested_product_id=int(item["suggested_product_id"]),
                tfidf_score=float(item["tfidf_score"]),
                embedding_score=float(item["embedding_score"]),
                confidence_score=float(item["confidence_score"]),
                confidence_label=str(item["confidence_label"]),
                rank=int(item["rank"]),
                status=str(item["status"]),
            )
        )

    with get_session() as session:
        session.add_all(records)

    logger.info("Saved %s match records", f"{len(records):,}")
    return len(records)


def get_next_pending() -> Optional[Dict[str, Any]]:
    """Return the oldest pending match for human review.

    Prioritises ``rank=1`` suggestions (top candidate per unmatched product).

    Returns:
        Match dictionary with nested ``unmatched_product`` and
        ``suggested_product``, or ``None`` when the queue is empty.
    """
    with get_session() as session:
        match = (
            session.query(Match)
            .filter(Match.status == "pending")
            .order_by(Match.rank, Match.id)
            .first()
        )
        if match is None:
            return None
        return match.to_dict(include_products=True)


def save_decision(match_id: int, decision: str, note: str = "") -> Dict[str, Any]:
    """Record an operator decision and update the match status.

    Args:
        match_id: Primary key of the :class:`Match` row.
        decision: ``"approved"`` or ``"rejected"``.
        note: Optional free-text operator note.

    Returns:
        Serialised :class:`Decision` dictionary.

    Raises:
        ValueError: If the match does not exist or decision is invalid.
    """
    decision = decision.lower().strip()
    if decision not in {"approved", "rejected"}:
        raise ValueError("decision must be 'approved' or 'rejected'")

    with get_session() as session:
        match = session.get(Match, match_id)
        if match is None:
            raise ValueError(f"Match id={match_id} not found")

        match.status = decision
        record = Decision(
            match_id=match_id,
            decision=decision,
            operator_note=note or None,
        )
        session.add(record)
        session.flush()
        logger.info("Match %s marked %s", match_id, decision)
        return record.to_dict()


def get_stats() -> Dict[str, Any]:
    """Return aggregate counts for dashboard and monitoring.

    Returns:
        Dict with product, match, and decision statistics.
    """
    with get_session() as session:
        total_products = session.query(func.count(Product.id)).scalar() or 0
        barcoded = (
            session.query(func.count(Product.id)).filter(Product.has_barcode.is_(True)).scalar() or 0
        )
        unmatched = total_products - barcoded

        match_total = session.query(func.count(Match.id)).scalar() or 0
        status_rows = session.query(Match.status, func.count(Match.id)).group_by(Match.status).all()
        matches_by_status = {status: count for status, count in status_rows}

        decision_total = session.query(func.count(Decision.id)).scalar() or 0
        approved = (
            session.query(func.count(Decision.id)).filter(Decision.decision == "approved").scalar() or 0
        )
        rejected = (
            session.query(func.count(Decision.id)).filter(Decision.decision == "rejected").scalar() or 0
        )

        return {
            "products_total": int(total_products),
            "products_barcoded": int(barcoded),
            "products_unmatched": int(unmatched),
            "matches_total": int(match_total),
            "matches_by_status": matches_by_status,
            "decisions_total": int(decision_total),
            "decisions_approved": int(approved),
            "decisions_rejected": int(rejected),
            "pending_review": int(matches_by_status.get("pending", 0)),
        }


def get_recent_decisions(limit: int = 20) -> List[Dict[str, Any]]:
    """Return the most recent operator decisions.

    Args:
        limit: Maximum number of decisions to return.

    Returns:
        List of decision dicts with nested match and product details.
    """
    with get_session() as session:
        decisions = (
            session.query(Decision)
            .order_by(Decision.decided_at.desc())
            .limit(limit)
            .all()
        )
        return [d.to_dict(include_match=True) for d in decisions]


if __name__ == "__main__":
    import tempfile
    from pathlib import Path

    from src.confidence import compute_confidence, get_confidence_label
    from src.preprocess import load_and_clean

    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")

    db_file = Path(tempfile.mkdtemp()) / "test_matching.db"
    init_db(str(db_file))

    df_barcoded, df_unmatched = load_and_clean("data/mix_products.csv")
    load_products(df_barcoded.head(100), df_unmatched.head(50))

    with get_session() as session:
        unmatched_id = (
            session.query(Product.id).filter(Product.has_barcode.is_(False)).first()[0]
        )
        suggested_id = (
            session.query(Product.id).filter(Product.has_barcode.is_(True)).first()[0]
        )

    sample_matches = []
    for rank in (1, 2, 3):
        conf = compute_confidence(0.75, 0.88 - rank * 0.05, True, rank == 1)
        sample_matches.append(
            {
                "unmatched_product_id": unmatched_id,
                "suggested_product_id": suggested_id,
                "tfidf_score": 0.75,
                "embedding_score": 0.88 - rank * 0.05,
                "confidence_score": conf,
                "confidence_label": get_confidence_label(conf),
                "rank": rank,
                "status": "pending",
            }
        )

    save_matches(sample_matches)
    print("Stats:", get_stats())
    print("Next pending:", get_next_pending())
    save_decision(1, "approved", note="Looks correct in spot check")
    print("Recent decisions:", len(get_recent_decisions(5)))
