from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv
from nicegui import app, core, ui

from app.core.db import DATA_DIR, init_db
from app.core.module_registry import discover_modules
from app.seed import seed_demo_if_empty
from app.ui.pages import library_page, property_page  # noqa: F401 — registers routes
from app.ui.theme import COLORS, NEON

STATIC_DIR = Path(__file__).resolve().parent / "static"

# Zoning GeoJSON near an LA pin can be ~10–20 MB. NiceGUI/engineio defaults to a
# 1 MB max_http_buffer_size, which silently drops those Map overlay payloads.
# Raise before ui.run() so Socket.IO negotiates a larger maxPayload with the browser.
WS_MAX_HTTP_BUFFER_BYTES = 32 * 1024 * 1024  # 32 MiB


def main() -> None:
    load_dotenv()
    core.sio.eio.max_http_buffer_size = WS_MAX_HTTP_BUFFER_BYTES
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    init_db()
    discover_modules()
    seed_demo_if_empty()

    host = os.getenv("HOMEBUY_HOST", "127.0.0.1")
    port = int(os.getenv("HOMEBUY_PORT", "8080"))

    # Expose uploaded photos to the browser
    uploads = DATA_DIR / "uploads"
    uploads.mkdir(parents=True, exist_ok=True)
    app.add_static_files("/uploads", str(uploads))

    # Theme fonts and other static assets
    STATIC_DIR.mkdir(parents=True, exist_ok=True)
    (STATIC_DIR / "fonts").mkdir(parents=True, exist_ok=True)
    app.add_static_files("/static", str(STATIC_DIR))

    # App-wide Quasar brand colors (page CSS/dark mode still applied in page_header)
    app.colors(
        primary=NEON["cyan"],
        secondary=NEON["magenta"],
        accent=NEON["lime"],
        dark=COLORS["bg_elevated"],
        dark_page=COLORS["bg"],
        positive="#3DFF9A",
        negative="#FF4D6D",
        info=NEON["cyan"],
        warning=NEON["amber"],
    )

    ui.run(
        title="Homebuy",
        host=host,
        port=port,
        reload=False,
        show=True,
        dark=True,
        favicon="🏠",
    )


if __name__ in {"__main__", "__mp_main__"}:
    main()
