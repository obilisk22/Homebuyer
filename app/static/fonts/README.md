# Homebuy fonts

## Creato Display (body / UI / prices)

- Source: https://www.dafont.com/creato-display.font
- License: SIL Open Font License 1.1 (see `OFL-CreatoDisplay.txt` when present)
- Expected layout: `creato_display/CreatoDisplay-Regular.otf` (plus other weights)
- Flat `CreatoDisplay-*.otf` in this folder also works
- Used for body text, UI chrome, and list prices
- Safe to commit to the repo

## Akira Expanded (street address / brand)

- Source: https://www.dafont.com/akira-expanded.font
- License: free for **personal** use only (demo on DaFont). Commercial use requires a Creative Market license from Typologic.
- Expected layout: `akira_expanded/Akira Expanded Demo.otf`
- Used for street addresses and the Homebuy wordmark — not prices
- **Do not commit** Akira binaries (gitignored). Keep a local copy on your machine.

After adding files, restart the app (`python -m app.main`). Until files are present, the UI falls back to system fonts.
