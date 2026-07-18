from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv
from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

load_dotenv()

ROOT = Path(__file__).resolve().parents[2]
DATA_DIR = ROOT / "data"
UPLOADS_DIR = DATA_DIR / "uploads"


class Base(DeclarativeBase):
    pass


_engine = None
_SessionLocal: sessionmaker[Session] | None = None


def _db_url() -> str:
    raw = os.getenv("HOMEBUY_DB_PATH", "data/homebuy.db")
    path = Path(raw)
    if not path.is_absolute():
        path = ROOT / path
    path.parent.mkdir(parents=True, exist_ok=True)
    return f"sqlite:///{path.as_posix()}"


def get_engine():
    global _engine, _SessionLocal
    if _engine is None:
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        UPLOADS_DIR.mkdir(parents=True, exist_ok=True)
        _engine = create_engine(
            _db_url(),
            connect_args={"check_same_thread": False},
            future=True,
        )
        _SessionLocal = sessionmaker(bind=_engine, autoflush=False, autocommit=False, future=True)
    return _engine


def get_session() -> Session:
    get_engine()
    assert _SessionLocal is not None
    return _SessionLocal()


def init_db() -> None:
    from app.core import models  # noqa: F401

    get_engine()
    Base.metadata.create_all(bind=_engine)
    _migrate_sqlite()
    _backfill_thumbnails()


def _backfill_thumbnails() -> None:
    """Set library thumbnails for homes that have photos but no choice yet."""
    from sqlalchemy import select
    from sqlalchemy.orm import joinedload

    from app.core.models import Property
    from app.core.property_service import PropertyService

    assert _SessionLocal is not None
    with _SessionLocal() as session:
        stmt = (
            select(Property)
            .where(Property.thumbnail_photo_id.is_(None))
            .options(joinedload(Property.photos))
        )
        props = list(session.scalars(stmt).unique())
        service = PropertyService(session)
        for prop in props:
            if prop.photos:
                service.select_thumbnail(prop.id)


def _migrate_sqlite() -> None:
    """Lightweight additive migrations for existing local DBs."""
    assert _engine is not None
    with _engine.begin() as conn:
        photo_cols = {
            row[1] for row in conn.exec_driver_sql("PRAGMA table_info(photos)").fetchall()
        }
        if "source_url" not in photo_cols:
            conn.exec_driver_sql(
                "ALTER TABLE photos ADD COLUMN source_url VARCHAR(2048) NOT NULL DEFAULT ''"
            )

        prop_cols = {
            row[1] for row in conn.exec_driver_sql("PRAGMA table_info(properties)").fetchall()
        }
        for name, ddl in (
            ("list_price", "ALTER TABLE properties ADD COLUMN list_price FLOAT"),
            ("beds", "ALTER TABLE properties ADD COLUMN beds FLOAT"),
            ("baths", "ALTER TABLE properties ADD COLUMN baths FLOAT"),
            ("city", "ALTER TABLE properties ADD COLUMN city VARCHAR(128) NOT NULL DEFAULT ''"),
            ("state", "ALTER TABLE properties ADD COLUMN state VARCHAR(32) NOT NULL DEFAULT ''"),
            (
                "zip_code",
                "ALTER TABLE properties ADD COLUMN zip_code VARCHAR(16) NOT NULL DEFAULT ''",
            ),
            ("latitude", "ALTER TABLE properties ADD COLUMN latitude FLOAT"),
            ("longitude", "ALTER TABLE properties ADD COLUMN longitude FLOAT"),
            (
                "thumbnail_photo_id",
                "ALTER TABLE properties ADD COLUMN thumbnail_photo_id INTEGER",
            ),
        ):
            if name not in prop_cols:
                conn.exec_driver_sql(ddl)

        fin_cols = {
            row[1]
            for row in conn.exec_driver_sql("PRAGMA table_info(financial_assumptions)").fetchall()
        }
        if fin_cols:
            added_price_cols = False
            if "list_price" not in fin_cols:
                conn.exec_driver_sql(
                    "ALTER TABLE financial_assumptions ADD COLUMN list_price FLOAT NOT NULL DEFAULT 500000"
                )
                added_price_cols = True
            if "offer_price" not in fin_cols:
                conn.exec_driver_sql(
                    "ALTER TABLE financial_assumptions ADD COLUMN offer_price FLOAT NOT NULL DEFAULT 0"
                )
                added_price_cols = True
            if added_price_cols and "purchase_price" in fin_cols:
                conn.exec_driver_sql(
                    """
                    UPDATE financial_assumptions
                    SET list_price = purchase_price,
                        offer_price = purchase_price
                    WHERE purchase_price IS NOT NULL AND purchase_price > 0
                    """
                )
