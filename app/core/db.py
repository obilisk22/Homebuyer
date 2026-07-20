from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv
from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from app.core.paths import DATA_DIR, ROOT, UPLOADS_DIR, env_file

load_dotenv(env_file())
# Dev: also load repo `.env` when present (no-op / non-override if same path).
load_dotenv(ROOT / ".env", override=False)


class Base(DeclarativeBase):
    pass


_engine = None
_SessionLocal: sessionmaker[Session] | None = None


def _resolve_db_path() -> Path:
    raw = (os.getenv("HOMEBUY_DB_PATH") or "data/homebuy.db").strip()
    path = Path(raw)
    if path.is_absolute():
        return path
    parts = path.parts
    if parts and parts[0] == "data":
        return DATA_DIR.joinpath(*parts[1:])
    return DATA_DIR / path


def _db_url() -> str:
    path = _resolve_db_path()
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
    _reselect_unlocked_thumbnails()


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


def _reselect_unlocked_thumbnails() -> None:
    """Re-run auto thumb pick once for unlocked homes (picks up scoring improvements)."""
    from sqlalchemy import select
    from sqlalchemy.orm import joinedload

    from app.core.models import Property
    from app.core.property_service import PropertyService

    assert _SessionLocal is not None
    with _SessionLocal() as session:
        stmt = (
            select(Property)
            .where(Property.thumbnail_locked.is_(False))
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
                "nearby_signals",
                "ALTER TABLE properties ADD COLUMN nearby_signals TEXT NOT NULL DEFAULT ''",
            ),
            (
                "nearby_signals_at",
                "ALTER TABLE properties ADD COLUMN nearby_signals_at VARCHAR(64) NOT NULL DEFAULT ''",
            ),
            (
                "permits_activity",
                "ALTER TABLE properties ADD COLUMN permits_activity TEXT NOT NULL DEFAULT ''",
            ),
            (
                "permits_activity_at",
                "ALTER TABLE properties ADD COLUMN permits_activity_at VARCHAR(64) NOT NULL DEFAULT ''",
            ),
            (
                "broadband_status",
                "ALTER TABLE properties ADD COLUMN broadband_status TEXT NOT NULL DEFAULT ''",
            ),
            (
                "broadband_at",
                "ALTER TABLE properties ADD COLUMN broadband_at VARCHAR(64) NOT NULL DEFAULT ''",
            ),
            (
                "market_activity",
                "ALTER TABLE properties ADD COLUMN market_activity TEXT NOT NULL DEFAULT ''",
            ),
            (
                "market_activity_at",
                "ALTER TABLE properties ADD COLUMN market_activity_at VARCHAR(64) NOT NULL DEFAULT ''",
            ),
            (
                "townhome_position",
                "ALTER TABLE properties ADD COLUMN townhome_position VARCHAR(32) NOT NULL DEFAULT ''",
            ),
            (
                "thumbnail_photo_id",
                "ALTER TABLE properties ADD COLUMN thumbnail_photo_id INTEGER",
            ),
            (
                "thumbnail_locked",
                "ALTER TABLE properties ADD COLUMN thumbnail_locked BOOLEAN NOT NULL DEFAULT 0",
            ),
            (
                "neighborhood_name",
                "ALTER TABLE properties ADD COLUMN neighborhood_name VARCHAR(256) NOT NULL DEFAULT ''",
            ),
            (
                "neighborhood_source",
                "ALTER TABLE properties ADD COLUMN neighborhood_source VARCHAR(64) NOT NULL DEFAULT ''",
            ),
            (
                "neighborhood_override",
                "ALTER TABLE properties ADD COLUMN neighborhood_override VARCHAR(256) NOT NULL DEFAULT ''",
            ),
            (
                "neighborhood_notes",
                "ALTER TABLE properties ADD COLUMN neighborhood_notes TEXT NOT NULL DEFAULT ''",
            ),
            (
                "neighborhood_gemini",
                "ALTER TABLE properties ADD COLUMN neighborhood_gemini TEXT NOT NULL DEFAULT ''",
            ),
            (
                "neighborhood_gemini_for",
                "ALTER TABLE properties ADD COLUMN neighborhood_gemini_for VARCHAR(256) NOT NULL DEFAULT ''",
            ),
            (
                "neighborhood_things_to_do",
                "ALTER TABLE properties ADD COLUMN neighborhood_things_to_do TEXT NOT NULL DEFAULT ''",
            ),
            (
                "neighborhood_things_to_do_for",
                "ALTER TABLE properties ADD COLUMN neighborhood_things_to_do_for VARCHAR(256) NOT NULL DEFAULT ''",
            ),
            ("sqft", "ALTER TABLE properties ADD COLUMN sqft FLOAT"),
            ("hoa_fee", "ALTER TABLE properties ADD COLUMN hoa_fee FLOAT"),
            ("year_built", "ALTER TABLE properties ADD COLUMN year_built INTEGER"),
            (
                "home_type",
                "ALTER TABLE properties ADD COLUMN home_type VARCHAR(64) NOT NULL DEFAULT ''",
            ),
            (
                "cooling",
                "ALTER TABLE properties ADD COLUMN cooling VARCHAR(256) NOT NULL DEFAULT ''",
            ),
            (
                "has_central_ac",
                "ALTER TABLE properties ADD COLUMN has_central_ac BOOLEAN",
            ),
            (
                "financial_gemini",
                "ALTER TABLE properties ADD COLUMN financial_gemini TEXT NOT NULL DEFAULT ''",
            ),
            (
                "financial_gemini_for",
                "ALTER TABLE properties ADD COLUMN financial_gemini_for VARCHAR(256) NOT NULL DEFAULT ''",
            ),
            (
                "photos_gemini",
                "ALTER TABLE properties ADD COLUMN photos_gemini TEXT NOT NULL DEFAULT ''",
            ),
            (
                "photos_gemini_for",
                "ALTER TABLE properties ADD COLUMN photos_gemini_for VARCHAR(256) NOT NULL DEFAULT ''",
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
            if "property_tax_source" not in fin_cols:
                conn.exec_driver_sql(
                    "ALTER TABLE financial_assumptions ADD COLUMN property_tax_source VARCHAR(64) NOT NULL DEFAULT ''"
                )
            if "insurance_source" not in fin_cols:
                conn.exec_driver_sql(
                    "ALTER TABLE financial_assumptions ADD COLUMN insurance_source VARCHAR(64) NOT NULL DEFAULT ''"
                )
            if "monthly_rent" not in fin_cols:
                conn.exec_driver_sql(
                    "ALTER TABLE financial_assumptions ADD COLUMN monthly_rent FLOAT NOT NULL DEFAULT 5300"
                )
            if "rent_source" not in fin_cols:
                conn.exec_driver_sql(
                    "ALTER TABLE financial_assumptions ADD COLUMN rent_source VARCHAR(64) NOT NULL DEFAULT 'Default'"
                )
            if "rent_control" not in fin_cols:
                conn.exec_driver_sql(
                    "ALTER TABLE financial_assumptions ADD COLUMN rent_control BOOLEAN NOT NULL DEFAULT 0"
                )
            if "rent_growth_pct" not in fin_cols:
                conn.exec_driver_sql(
                    "ALTER TABLE financial_assumptions ADD COLUMN rent_growth_pct FLOAT NOT NULL DEFAULT 3"
                )
            if "rent_growth_source" not in fin_cols:
                conn.exec_driver_sql(
                    "ALTER TABLE financial_assumptions ADD COLUMN rent_growth_source VARCHAR(64) NOT NULL DEFAULT ''"
                )
            if "appreciation_pct" not in fin_cols:
                conn.exec_driver_sql(
                    "ALTER TABLE financial_assumptions ADD COLUMN appreciation_pct FLOAT NOT NULL DEFAULT 3"
                )
            if "appreciation_source" not in fin_cols:
                conn.exec_driver_sql(
                    "ALTER TABLE financial_assumptions ADD COLUMN appreciation_source VARCHAR(64) NOT NULL DEFAULT ''"
                )
            if "appreciation_fhfa_pct" not in fin_cols:
                conn.exec_driver_sql(
                    "ALTER TABLE financial_assumptions ADD COLUMN appreciation_fhfa_pct FLOAT"
                )
            if "appreciation_zillow_pct" not in fin_cols:
                conn.exec_driver_sql(
                    "ALTER TABLE financial_assumptions ADD COLUMN appreciation_zillow_pct FLOAT"
                )
            if "interest_rate_source" not in fin_cols:
                conn.exec_driver_sql(
                    "ALTER TABLE financial_assumptions ADD COLUMN interest_rate_source "
                    "VARCHAR(96) NOT NULL DEFAULT ''"
                )
            if "invest_return_pct" not in fin_cols:
                conn.exec_driver_sql(
                    "ALTER TABLE financial_assumptions ADD COLUMN invest_return_pct "
                    "FLOAT NOT NULL DEFAULT 10"
                )
            if "selling_cost_pct" not in fin_cols:
                conn.exec_driver_sql(
                    "ALTER TABLE financial_assumptions ADD COLUMN selling_cost_pct "
                    "FLOAT NOT NULL DEFAULT 6"
                )
            if "monthly_maintenance" not in fin_cols:
                conn.exec_driver_sql(
                    "ALTER TABLE financial_assumptions ADD COLUMN monthly_maintenance "
                    "FLOAT NOT NULL DEFAULT 0"
                )
            if "maintenance_source" not in fin_cols:
                conn.exec_driver_sql(
                    "ALTER TABLE financial_assumptions ADD COLUMN maintenance_source "
                    "VARCHAR(96) NOT NULL DEFAULT ''"
                )
            if "monthly_budget" not in fin_cols:
                conn.exec_driver_sql(
                    "ALTER TABLE financial_assumptions ADD COLUMN monthly_budget "
                    "FLOAT NOT NULL DEFAULT 13000"
                )
            if "marginal_tax_pct" not in fin_cols:
                conn.exec_driver_sql(
                    "ALTER TABLE financial_assumptions ADD COLUMN marginal_tax_pct "
                    "FLOAT NOT NULL DEFAULT 41"
                )
            if "cg_tax_pct" not in fin_cols:
                conn.exec_driver_sql(
                    "ALTER TABLE financial_assumptions ADD COLUMN cg_tax_pct "
                    "FLOAT NOT NULL DEFAULT 24"
                )
            if "cg_exclusion" not in fin_cols:
                conn.exec_driver_sql(
                    "ALTER TABLE financial_assumptions ADD COLUMN cg_exclusion "
                    "FLOAT NOT NULL DEFAULT 500000"
                )
            if "salt_cap" not in fin_cols:
                conn.exec_driver_sql(
                    "ALTER TABLE financial_assumptions ADD COLUMN salt_cap "
                    "FLOAT NOT NULL DEFAULT 10000"
                )
            if "monthly_utilities" not in fin_cols:
                conn.exec_driver_sql(
                    "ALTER TABLE financial_assumptions ADD COLUMN monthly_utilities "
                    "FLOAT NOT NULL DEFAULT 0"
                )
            if "utilities_source" not in fin_cols:
                conn.exec_driver_sql(
                    "ALTER TABLE financial_assumptions ADD COLUMN utilities_source "
                    "VARCHAR(96) NOT NULL DEFAULT ''"
                )
