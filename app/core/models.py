from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import DateTime, Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.db import Base


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Property(Base):
    __tablename__ = "properties"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    address: Mapped[str] = mapped_column(String(512), nullable=False)
    zillow_url: Mapped[str] = mapped_column(String(1024), nullable=False)
    notes: Mapped[str] = mapped_column(Text, default="", nullable=False)
    list_price: Mapped[float | None] = mapped_column(Float, nullable=True)
    beds: Mapped[float | None] = mapped_column(Float, nullable=True)
    baths: Mapped[float | None] = mapped_column(Float, nullable=True)
    city: Mapped[str] = mapped_column(String(128), default="", nullable=False)
    state: Mapped[str] = mapped_column(String(32), default="", nullable=False)
    zip_code: Mapped[str] = mapped_column(String(16), default="", nullable=False)
    latitude: Mapped[float | None] = mapped_column(Float, nullable=True)
    longitude: Mapped[float | None] = mapped_column(Float, nullable=True)
    # Soft reference to photos.id (avoid circular FK with SQLite).
    thumbnail_photo_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    # Cached neighborhood label + optional manual override / notes for Reviews tab.
    neighborhood_name: Mapped[str] = mapped_column(String(256), default="", nullable=False)
    neighborhood_source: Mapped[str] = mapped_column(String(64), default="", nullable=False)
    neighborhood_override: Mapped[str] = mapped_column(String(256), default="", nullable=False)
    neighborhood_notes: Mapped[str] = mapped_column(Text, default="", nullable=False)
    neighborhood_gemini: Mapped[str] = mapped_column(Text, default="", nullable=False)
    neighborhood_gemini_for: Mapped[str] = mapped_column(String(256), default="", nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow
    )

    photos: Mapped[list[Photo]] = relationship(
        back_populates="property", cascade="all, delete-orphan", order_by="Photo.sort_order"
    )
    financial: Mapped[FinancialAssumptions | None] = relationship(
        back_populates="property", cascade="all, delete-orphan", uselist=False
    )


class Photo(Base):
    __tablename__ = "photos"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    property_id: Mapped[int] = mapped_column(ForeignKey("properties.id", ondelete="CASCADE"))
    path: Mapped[str] = mapped_column(String(1024), nullable=False)
    source_url: Mapped[str] = mapped_column(String(2048), default="", nullable=False)
    caption: Mapped[str] = mapped_column(String(512), default="", nullable=False)
    sort_order: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    property: Mapped[Property] = relationship(back_populates="photos")


class FinancialAssumptions(Base):
    __tablename__ = "financial_assumptions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    property_id: Mapped[int] = mapped_column(
        ForeignKey("properties.id", ondelete="CASCADE"), unique=True
    )
    # Offer drives mortgage math; list is the asking/comp reference.
    # purchase_price is kept in sync with effective price for older rows/callers.
    list_price: Mapped[float] = mapped_column(Float, default=500_000.0)
    offer_price: Mapped[float] = mapped_column(Float, default=0.0)
    purchase_price: Mapped[float] = mapped_column(Float, default=500_000.0)
    down_payment_pct: Mapped[float] = mapped_column(Float, default=20.0)
    interest_rate_pct: Mapped[float] = mapped_column(Float, default=6.5)
    loan_term_years: Mapped[int] = mapped_column(Integer, default=30)
    annual_property_tax: Mapped[float] = mapped_column(Float, default=6_000.0)
    annual_insurance: Mapped[float] = mapped_column(Float, default=1_800.0)
    monthly_hoa: Mapped[float] = mapped_column(Float, default=0.0)
    closing_cost_pct: Mapped[float] = mapped_column(Float, default=3.0)

    property: Mapped[Property] = relationship(back_populates="financial")
