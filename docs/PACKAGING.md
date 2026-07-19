# Windows packaging (desktop app)

## Quick reference

| Mode | Command |
|------|---------|
| Dev (browser) | `.\.venv\Scripts\python.exe -m app.main` |
| Dev (native window) | `.\run-native.bat` or `HOMEBUY_NATIVE=1` + `--native` |
| Freeze onedir | `.\packaging\build_windows.ps1` |
| Freeze + Setup.exe | `.\packaging\build_windows.ps1 -Installer` (needs [Inno Setup 6](https://jrsoftware.org/isinfo.php)) |

Native mode **auto-picks a free port** (ignores `HOMEBUY_PORT` / 8080) so it can run while the browser session is up. Optional: `HOMEBUY_NATIVE_PORT`.

The native window uses a dark frame (`#0B0D10` background + Windows immersive dark title bar / caption / border) via `app/core/native_chrome.py`.

## Data & secrets (installed app)

Writable data lives in `%LOCALAPPDATA%\Homebuy\` (DB, uploads, caches).  
Optional keys: `%LOCALAPPDATA%\Homebuy\.env` (see `.env.example`).

Override data root anytime with `HOMEBUY_DATA_DIR`.

## Smoke checklist (packaged exe)

After `dist\Homebuy\Homebuy.exe` builds:

1. Window opens (WebView2 / Edge runtime)
2. Library page loads
3. Open an existing home (or add from Zillow URL)
4. Photos tab shows images
5. Map tab + one overlay toggle
6. Financials tab calculates
7. Confirm files under `%LOCALAPPDATA%\Homebuy\`

If the windowed exe fails silently, temporarily set `console=True` in `packaging/homebuy.spec` and rebuild.

## Notes

- Code signing / SmartScreen: not configured (personal use).
- Auto-update: reinstall via a new Setup.exe.
- Fonts: Creato ships in-repo; Akira is gitignored — copy into `app/static/fonts/` before packaging if you want it in the build.
