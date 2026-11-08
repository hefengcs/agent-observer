import fnmatch
import json
import os
import re
import stat
from pathlib import Path

EXCLUDED_DIRS = {
    ".git",
    ".venv",
    "venv",
    "node_modules",
    "__pycache__",
    ".cache",
    ".pytest_cache",
    ".mypy_cache",
    ".ruff_cache",
    ".tox",
    ".next",
    ".ssh",
    ".aws",
    ".gnupg",
}
SENSITIVE = (
    ".env",
    ".env.*",
    "*.pem",
    "*.key",
    "*.p12",
    "*.pfx",
    "*.keystore",
    "id_rsa*",
    "id_ed25519*",
    "*credentials*",
    "*secrets*",
    "*.sqlite*",
    "*.db",
    ".netrc",
    ".npmrc",
    ".pypirc",
    "auth.json",
    "token.json",
    "tokens.json",
    "config.local.*",
)
_PRIVATE = re.compile(r"-----BEGIN [^-\n]*PRIVATE KEY-----.*?(?:-----END [^-\n]*PRIVATE KEY-----|\Z)", re.S)
_ASSIGN = re.compile(
    r"""(?im)(?<![\w.-])(["']?(?:[\w.-]{0,128}(?:api[_-]?key|access[_-]?key|secret|token|password|passwd|authorization)[\w.-]{0,128})["']?\s*[:=]\s*)("[^"\n]*"|'[^'\n]*'|[^\s,;\n}]+)"""
)
_BEARER = re.compile(r"(?i)\b(Bearer|Basic)\s+[A-Za-z0-9._~+/=-]+")
_KNOWN = re.compile(
    r"\b(?:sk-(?:proj-|ant-)?[A-Za-z0-9_-]{12,}|gh[pousr]_[A-Za-z0-9_]{16,}|github_pat_[A-Za-z0-9_]{16,}|AKIA[A-Z0-9]{16}|xox[baprs]-[A-Za-z0-9-]{12,}|eyJ[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+)\b"
)
_URL_AUTH = re.compile(r"(https?://)[^\s/@:]+:[^\s/@]+@")


def redact(text: str) -> str:
    # Preserve newline counts so source line references remain meaningful.
    text = _PRIVATE.sub(lambda m: "[REDACTED PRIVATE KEY]" + "\n" * m[0].count("\n"), text)
    text = _BEARER.sub(lambda m: m[1] + " [REDACTED]", text)
    text = _ASSIGN.sub(lambda m: m[1] + '"[REDACTED]"', text)
    text = _KNOWN.sub("[REDACTED]", text)
    return _URL_AUTH.sub(r"\1[REDACTED]@", text)


def sanitize(value):
    if isinstance(value, str):
        return redact(value)
    if isinstance(value, dict):
        return {
            k: ("[REDACTED]" if re.search(r"(?i)secret|password|api.?key|access.?token", k) else sanitize(v))
            for k, v in value.items()
        }
    if isinstance(value, list):
        return [sanitize(v) for v in value]
    return value


def allowed(relative: str | Path) -> bool:
    path = Path(relative)
    return not (
        path.is_absolute()
        or ".." in path.parts
        or any(
            part in EXCLUDED_DIRS or any(fnmatch.fnmatch(part.lower(), pat) for pat in SENSITIVE)
            for part in path.parts
        )
    )


def safe_path(root: Path, relative: str, *, directory: bool = False) -> Path:
    if not allowed(relative) or "\x00" in relative:
        raise ValueError("Path is excluded or outside the project")
    path = root / relative
    current = root
    for part in Path(relative).parts:
        current = current / part
        if current.is_symlink():
            raise ValueError("Symlink access is disabled")
    resolved = path.resolve(strict=True)
    if not resolved.is_relative_to(root) or (not directory and not resolved.is_file()):
        raise ValueError("Path is outside the project or not a regular file")
    return resolved


def read_bytes(root: Path, relative: str, max_bytes: int) -> bytes:
    """Walk with dirfd/O_NOFOLLOW to prevent symlink swaps between check and open."""
    safe_path(root, relative)
    parts = Path(relative).parts
    fd = os.open(root, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        for part in parts[:-1]:
            child = os.open(part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=fd)
            os.close(fd)
            fd = child
        file_fd = os.open(parts[-1], os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=fd)
        with os.fdopen(file_fd, "rb") as stream:
            st = os.fstat(stream.fileno())
            if not stat.S_ISREG(st.st_mode) or st.st_size > max_bytes:
                raise ValueError("Not a regular file or file exceeds size limit")
            data = stream.read(max_bytes + 1)
            if len(data) > max_bytes:
                raise ValueError("File exceeds size limit")
            return data
    finally:
        os.close(fd)


def read_text(root: Path, relative: str, max_bytes: int) -> str:
    data = read_bytes(root, relative, max_bytes)
    if b"\x00" in data:
        raise ValueError("Binary files are excluded")
    try:
        text = data.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise ValueError("Only UTF-8 text is supported") from exc
    if any(ord(c) < 9 or 13 < ord(c) < 32 for c in text):
        raise ValueError("Binary files are excluded")
    return redact(text)


def bounded(value, maximum: int) -> dict:
    """Bound an opaque Git payload, with explicit truncation."""
    text = redact(value if isinstance(value, str) else json.dumps(sanitize(value), ensure_ascii=False))
    return {"text": text[:maximum], "truncated": len(text) > maximum, "total_chars": len(text)}
