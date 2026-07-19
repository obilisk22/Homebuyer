"""Thin entrypoint for PyInstaller / nicegui-pack (Windows desktop build)."""

from __future__ import annotations

from multiprocessing import freeze_support

# Native window args must be applied before freeze_support intercepts subprocesses.
from nicegui import app

app.native.window_args["title"] = "Homebuy"
app.native.window_args["min_size"] = (960, 640)

if __name__ == "__main__":
    freeze_support()
    # Packaged builds default to native via is_frozen(); allow --browser override.
    from app.main import main

    main()
