#!/usr/bin/env python3
"""Cursor `stop` hook: auto-commit local changes. Never pushes."""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
from pathlib import Path

MAX_NEW_FILE_BYTES = 5 * 1024 * 1024

def _find_git() -> str | None:
    which = shutil.which("git")
    if which:
        return which
    candidates = [
        Path(r"C:\Program Files\Git\cmd\git.exe"),
        Path(r"C:\Program Files\Git\bin\git.exe"),
        Path(r"C:\Program Files (x86)\Git\cmd\git.exe"),
        Path.home() / "AppData/Local/Programs/Git/cmd/git.exe",
        Path("/usr/bin/git"),
        Path("/opt/homebrew/bin/git"),
    ]
    for path in candidates:
        if path.is_file():
            return str(path)
    return None


def _run(
    git: str,
    *args: str,
    cwd: Path,
    check: bool = True,
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [git, *args],
        cwd=cwd,
        check=check,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )


def _is_blocked(rel_path: str) -> bool:
    """Block secrets / venv / DB; allow committed templates like `.env.example`."""
    normalized = rel_path.replace("\\", "/").lower()
    name = Path(normalized).name.lower()
    if name == ".env":
        return True
    # `.env.local`, `.env.production`, etc. — but not `.env.example`
    if name.startswith(".env.") and name != ".env.example":
        return True
    if "homebuy.db" in normalized:
        return True
    if normalized == ".venv" or normalized.startswith(".venv/") or "/.venv/" in normalized:
        return True
    if "credentials" in name or name.endswith(".pem") or name.endswith(".p12"):
        return True
    if "secrets" in name and name != "secrets.example":
        return True
    return False


def _repo_root(payload: dict) -> Path:
    roots = payload.get("workspace_roots") or []
    if roots:
        return Path(roots[0]).resolve()
    # .cursor/hooks/auto-commit.py -> project root
    return Path(__file__).resolve().parents[2]


def _commit_message(files: list[str]) -> str:
    if not files:
        return "auto: checkpoint"
    basenames = [Path(f).name for f in files[:6]]
    summary = ", ".join(basenames)
    if len(files) > 6:
        summary += f" (+{len(files) - 6} more)"
    return f"auto: {summary}"


def _staged_names(git: str, cwd: Path) -> list[str]:
    return [
        line
        for line in _run(git, "diff", "--cached", "--name-only", cwd=cwd).stdout.splitlines()
        if line.strip()
    ]


def main() -> int:
    raw = sys.stdin.read()
    try:
        payload = json.loads(raw) if raw.strip() else {}
    except json.JSONDecodeError:
        payload = {}

    # Skip aborted / errored agent turns.
    status = (payload.get("status") or "completed").lower()
    if status in {"aborted", "error"}:
        print("{}")
        return 0

    repo = _repo_root(payload)
    if not (repo / ".git").exists():
        print("{}")
        return 0

    git = _find_git()
    if not git:
        print("{}")
        return 0

    porcelain = _run(git, "status", "--porcelain", cwd=repo)
    if not porcelain.stdout.strip():
        print("{}")
        return 0

    # Respect .gitignore; never force-add ignored paths.
    _run(git, "add", "-A", cwd=repo)

    staged = _staged_names(git, repo)
    for rel in list(staged):
        if _is_blocked(rel):
            _run(git, "reset", "HEAD", "--", rel, cwd=repo, check=False)

    # Unstage huge *new* files only (already-tracked large assets stay).
    added = [
        line
        for line in _run(
            git, "diff", "--cached", "--name-only", "--diff-filter=A", cwd=repo
        ).stdout.splitlines()
        if line.strip()
    ]
    for rel in added:
        full = repo / rel
        try:
            size = full.stat().st_size if full.is_file() else 0
        except OSError:
            size = 0
        if size > MAX_NEW_FILE_BYTES:
            _run(git, "reset", "HEAD", "--", rel, cwd=repo, check=False)

    staged = _staged_names(git, repo)
    if not staged:
        print("{}")
        return 0

    msg = _commit_message(staged)
    # Local commit only — never push / never amend / never touch git config.
    _run(git, "commit", "-m", msg, cwd=repo, check=False)

    print("{}")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception:
        # Fail open: never block the agent on auto-commit issues.
        print("{}")
        raise SystemExit(0)
