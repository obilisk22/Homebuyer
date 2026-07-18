# Homebuy fonts

## Creato Display (body / UI)

- Source: https://www.dafont.com/creato-display.font
- License: SIL Open Font License 1.1 (see `OFL-CreatoDisplay.txt` when present)
- Expected layout: `creato_display/CreatoDisplay-Regular.otf` (plus other weights)
- Flat `CreatoDisplay-*.otf` in this folder also works
- Safe to commit to the repo

## Akira Expanded (L1 prices / key figures)

- Source: https://www.dafont.com/akira-expanded.font
- License: free for **personal** use only (demo on DaFont). Commercial use requires a Creative Market license from Typologic.
- Expected layout: `akira_expanded/Akira Expanded Demo.otf`
- **Do not commit** Akira binaries (gitignored). Keep a local copy on your machine.

After adding files, restart the app (`python -m app.main`). Until files are present, the UI falls back to system fonts.
