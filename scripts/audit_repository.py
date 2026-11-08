#!/usr/bin/env python3
"""Check the Git index for accidental private files and common literal credentials."""

import re
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PRIVATE_PARTS = {
    ".venv",
    "venv",
    ".codex",
    ".claude",
    ".generated",
    "sessions",
    "history",
    "local",
    "runtime",
}
KEY = re.compile(
    r"\b(?:sk-(?:proj-|ant-)?[A-Za-z0-9_-]{12,}|gh[pousr]_[A-Za-z0-9_]{16,}|github_pat_[A-Za-z0-9_]{16,}|AKIA[A-Z0-9]{16}|xox[baprs]-[A-Za-z0-9-]{12,})\b"
)
# Deliberate fake secret used by the existing redaction test, never a live credential.
SYNTHETIC_KEYS = {"sk-proj-abcdefghijklmnop"}


def public_files(root=ROOT):
    output = subprocess.check_output(["git", "-C", str(root), "ls-files", "--cached", "-z"])
    return [Path(p) for p in output.decode().split("\0") if p]


def audit(root=ROOT):
    errors = []
    paths = public_files(root)
    if not paths:
        raise ValueError(
            "Git index is empty; stage the intended public source files before auditing/building"
        )
    for relative in paths:
        path = root / relative
        if (
            any(p in PRIVATE_PARTS for p in relative.parts)
            or relative.suffix in (".jsonl", ".db", ".pem", ".key", ".log")
            or (relative.parts[0] == "reports" and relative.suffix != ".md")
            or relative.name.startswith(".env")
            or path.is_symlink()
        ):
            errors.append(f"Private or generated file: {relative}")
            continue
        text = path.read_text(errors="replace")
        if any(m[0] not in SYNTHETIC_KEYS for m in KEY.finditer(text)):
            errors.append(f"Possible literal credential: {relative}")
        if re.search(r"/(?:Users|home)/(?!example\b|user\b|USER\b|runner\b)[A-Za-z0-9_.-]+/", text):
            errors.append(f"Personal absolute path: {relative}")
    if errors:
        raise ValueError("\n".join(errors))
    return paths


if __name__ == "__main__":
    print(f"Repository privacy audit passed: {len(audit())} public files")
