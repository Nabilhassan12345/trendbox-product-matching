"""SQLAlchemy ORM models and match-status vocabulary."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict

from sqlalchemy import Boolean, Column, DateTime, Float, ForeignKey, Integer, String
from sqlalchemy.orm import declarative_base, relationship

Base = declarative_base()

# ── Match status vocabulary ───────────────────────────────────────────────────
STATUS_PENDING = "pending"
STATUS_AUTO_APPROVED = "auto_approved"
STATUS_AUTO_REJECTED = "auto_rejected"
STATUS_ALTERNATIVE = "alternative"
STATUS_SUPERSEDED = "superseded"
STATUS_APPROVED = "approved"
STATUS_REJECTED = "rejected"

OPEN_STATUSES = (STATUS_PENDING, STATUS_ALTERNATIVE)


def _utcnow() -> datetime:
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
    query_weight = Column(String, nullable=True)
    suggested_weight = Column(String, nullable=True)
    size_verdict = Column(String, nullable=True, index=True)
    brand_match = Column(Boolean, nullable=True)
    guardrail_applied = Column(Boolean, nullable=False, default=False)
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
            "query_weight": self.query_weight,
            "suggested_weight": self.suggested_weight,
            "size_verdict": self.size_verdict,
            "brand_match": self.brand_match,
            "guardrail_applied": self.guardrail_applied,
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
