from __future__ import annotations

import argparse
import os
import sys
from multiprocessing import freeze_support

from dotenv import load_dotenv
from nicegui import app, core, ui

from app.core.db import DATA_DIR, init_db
from app.core.module_registry import discover_modules
from app.core.paths import env_file, is_frozen, static_dir
from app.seed import seed_demo_if_empty
from app.ui.pages import library_page, property_page  # noqa: F401 — registers routes
from app.ui.theme import COLORS, NEON

# Zoning GeoJSON near an LA pin can be ~10–20 MB. NiceGUI/engineio defaults to a
# 1 MB max_http_buffer_size, which silently drops those Map overlay payloads.
# Raise before ui.run() so Socket.IO negotiates a larger maxPayload with the browser.
WS_MAX_HTTP_BUFFER_BYTES = 32 * 1024 * 1024  # 32 MiB

# Must be set outside the main guard so PyInstaller subprocesses see them
# (NiceGUI native / freeze_support packaging requirement).
app.native.window_args["title"] = "Homebuy"
app.native.window_args["min_size"] = (960, 640)


def _env_flag(name: str) -> str | None:
    raw = (os.getenv(name) or "").strip().lower()
    return raw or None


def want_native(argv: list[str] | None = None) -> bool:
    """Browser by default in dev; native by default when frozen.

    Overrides: ``--native`` / ``--browser``, or ``HOMEBUY_NATIVE=1|0``.
    """
    args = list(sys.argv[1:] if argv is None else argv)
    if "--browser" in args:
        return False
    if "--native" in args:
        return True
    flag = _env_flag("HOMEBUY_NATIVE")
    if flag in {"1", "true", "yes", "on"}:
        return True
    if flag in {"0", "false", "no", "off"}:
        return False
    return is_frozen()


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Homebuy — local home research app")
    parser.add_argument(
        "--native",
        action="store_true",
        help="Open in a native desktop window (pywebview)",
    )
    parser.add_argument(
        "--browser",
        action="store_true",
        help="Open in the system browser (default when not packaged)",
    )
    # Ignore unknown so NiceGUI / multiprocessing extras do not break launch.
    ns, _unknown = parser.parse_known_args(argv)
    return ns


def main() -> None:
    _parse_args()
    load_dotenv(env_file())
    load_dotenv(override=False)

    core.sio.eio.max_http_buffer_size = WS_MAX_HTTP_BUFFER_BYTES
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    init_db()
    discover_modules()
    seed_demo_if_empty()

    host = os.getenv("HOMEBUY_HOST", "127.0.0.1")
    port_raw = (os.getenv("HOMEBUY_PORT") or "").strip()
    native = want_native()

    # Expose uploaded photos to the browser / webview
    uploads = DATA_DIR / "uploads"
    uploads.mkdir(parents=True, exist_ok=True)
    app.add_static_files("/uploads", str(uploads))

    # Theme fonts and other static assets
    static = static_dir()
    static.mkdir(parents=True, exist_ok=True)
    (static / "fonts").mkdir(parents=True, exist_ok=True)
    app.add_static_files("/static", str(static))

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

    run_kwargs: dict = {
        "title": "Homebuy",
        "reload": False,
        "dark": True,
        "favicon": "🏠",
    }

    if native:
        run_kwargs.update(
            native=True,
            window_size=(1280, 800),
            show=False,
        )
        # Optional fixed port; otherwise NiceGUI picks a free local port.
        if port_raw:
            run_kwargs["port"] = int(port_raw)
        run_kwargs["host"] = host
    else:
        port = int(port_raw or "8080")
        run_kwargs.update(
            native=False,
            host=host,
            port=port,
            show=True,
        )

    ui.run(**run_kwargs)


if __name__ in {"__main__", "__mp_main__"}:
    freeze_support()  # first statement — required for frozen native packaging
    main()
