import os
import re
import selectors
import shutil
import subprocess
import time
from pathlib import Path

from .config import Limits, Project
from .security import allowed, bounded


class GitReader:
    def __init__(self, project: Project, limits: Limits):
        self.project, self.root, self.limits = project, project.absolute_path, limits
        self.executable = shutil.which("git")
        if not self.executable:
            raise ValueError("Git is unavailable")

    def run(self, args: list[str], cap: int = 2_000_000) -> str:
        # No shell, inherited GIT_* env, hooks, pager, fsmonitor, external diff or textconv.
        env = {
            "PATH": "/usr/bin:/bin:/usr/local/bin:/opt/homebrew/bin",
            "HOME": str(Path.home()),
            "LC_ALL": "C",
            "GIT_OPTIONAL_LOCKS": "0",
            "GIT_CONFIG_NOSYSTEM": "1",
            "GIT_CONFIG_GLOBAL": os.devnull,
            "GIT_PAGER": "cat",
            "GIT_TERMINAL_PROMPT": "0",
        }
        overrides = []
        if args and args[0] in ("status", "diff", "show"):
            # Working-tree comparison may run clean/process filters even with --no-ext-diff.
            keys = self.run(["config", "--null", "--list", "--name-only"]).split("\x00")
            for key in keys:
                if re.fullmatch(r"filter\..+\.(clean|smudge|process|required)", key, flags=re.IGNORECASE):
                    value = "false" if key.lower().endswith(".required") else ""
                    overrides += ["-c", key + "=" + value]
        cmd = [
            self.executable,
            "--no-pager",
            "--no-optional-locks",
            "-c",
            "core.fsmonitor=false",
            "-c",
            "core.hooksPath=/dev/null",
            "-c",
            "core.quotePath=false",
            *overrides,
            "-C",
            str(self.root),
            *args,
        ]
        process = subprocess.Popen(cmd, env=env, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
        output = bytearray()
        deadline = time.monotonic() + 10
        try:
            with selectors.DefaultSelector() as selector:
                selector.register(process.stdout, selectors.EVENT_READ)
                while True:
                    if time.monotonic() > deadline:
                        raise ValueError("Git read timed out")
                    if not selector.select(timeout=0.1):
                        continue
                    chunk = os.read(process.stdout.fileno(), 65536)
                    if not chunk:
                        break
                    output.extend(chunk)
                    if len(output) > cap:
                        raise ValueError(
                            "Git result exceeds internal size limit; select a file or fewer commits"
                        )
            if process.wait(timeout=1) != 0:
                raise ValueError("Git read failed (repository, revision or object unavailable)")
        finally:
            if process.poll() is None:
                process.kill()
            process.wait()
            process.stdout.close()
        return output.decode("utf-8", errors="replace")

    def check(self):
        gitdir = self.root / ".git"
        if gitdir.is_symlink() or not gitdir.is_dir():
            raise ValueError(
                "Phase 1 requires an in-project .git directory; external Git metadata is excluded"
            )
        for name in ("commondir", "objects/info/alternates", "objects/info/http-alternates"):
            if (gitdir / name).exists():
                raise ValueError("External Git object stores are excluded")
        for name in ("objects", "refs", "config"):
            path = gitdir / name
            if path.is_symlink():
                raise ValueError("Symlink Git metadata is excluded")
        top = self.run(["rev-parse", "--show-toplevel"]).strip()
        if Path(top).resolve() != self.root:
            raise ValueError("Project root must match Git repository root exactly")

    @staticmethod
    def revision(value: str) -> str:
        if value != "HEAD" and not re.fullmatch(r"[a-fA-F0-9]{7,64}", value):
            raise ValueError("Use HEAD or a commit hash (7..64 hex characters)")
        return value

    def path(self, value: str) -> str:
        if not allowed(value) or "\x00" in value or not value or value.startswith(":"):
            raise ValueError("Excluded Git path")
        path = self.root / value
        # Historical deleted files may be absent; existing ancestors must never be symlinks.
        cur = self.root
        for part in Path(value).parts:
            cur /= part
            if cur.is_symlink():
                raise ValueError("Symlink Git path is excluded")
        if not path.resolve().is_relative_to(self.root):
            raise ValueError("Git path outside project")
        return value

    def status(self):
        self.check()
        raw = self.run(["status", "--porcelain=v1", "-z", "--untracked-files=normal"])
        records = raw.split("\x00")
        items, i = [], 0
        while i < len(records):
            record = records[i]
            i += 1
            if len(record) < 4:
                continue
            code, path = record[:2], record[3:]
            origin = None
            if "R" in code or "C" in code:
                origin = records[i] if i < len(records) else ""
                i += 1
            if allowed(path) and (origin is None or allowed(origin)):
                items.append({"status": code, "path": path, "original_path": origin})
        try:
            branch = self.run(["symbolic-ref", "--quiet", "--short", "HEAD"]).strip()
        except ValueError:
            branch = "detached:" + self.run(["rev-parse", "--short", "HEAD"]).strip()
        return {"branch": branch, "changes": items, "excluded_paths_omitted": True}

    def log(self, limit=10, offset=0, path=None):
        self.check()
        if not 1 <= limit <= 100 or offset < 0 or offset > 100000:
            raise ValueError("Invalid log pagination")
        args = [
            "log",
            "--no-show-signature",
            "--no-patch",
            f"--max-count={limit}",
            f"--skip={offset}",
            "--format=%H%x09%aI%x09%s",
        ]
        if path:
            args += ["--", ":(literal)" + self.path(path)]
        return bounded(self.run(args), self.limits.max_output_chars // 2) | {
            "offset": offset,
            "requested_count": limit,
            "next_offset": offset + limit,
            "note": "Continue until an empty page; reduce limit if truncated",
        }

    def diff(self, commit=None, base=None, path=None, staged=False, char_offset=0):
        self.check()
        if char_offset < 0 or (commit and base):
            raise ValueError("Invalid diff arguments")
        if staged and (commit or base):
            raise ValueError("staged cannot be combined with commit/base")
        args = ["show", "--format=", "--no-show-signature"] if commit else ["diff"]
        args += ["--no-ext-diff", "--no-textconv", "--no-color", "--no-renames"]
        if commit:
            args.append(self.revision(commit))
        elif base:
            args += [self.revision(base)]
        elif staged:
            args.append("--cached")
        # Discover changed paths first, then explicitly allowlist paths before requesting patch bytes.
        names = self.run([*args, "--name-only", "-z", "--"]).split("\x00")
        paths = []
        for name in names:
            if not name or (path and name != path):
                continue
            try:
                paths.append(self.path(name))
            except ValueError:
                continue
        if path:
            self.path(path)
        if not paths:
            return {"text": "", "truncated": False, "next_char_offset": None}
        # Avoid OS argv limits, without accidentally defaulting to an unrestricted diff.
        if len(paths) > 1000:
            raise ValueError("Too many changed files; select path")
        raw = self.run([*args, "--", *[":(literal)" + p for p in paths]])
        data = bounded(raw, 2_000_000)["text"]
        size = self.limits.max_output_chars // 4
        part = data[char_offset : char_offset + size]
        next_pos = char_offset + len(part)
        return {
            "text": part,
            "char_offset": char_offset,
            "total_chars": len(data),
            "truncated": next_pos < len(data),
            "next_char_offset": next_pos if next_pos < len(data) else None,
            "excluded_paths_omitted": True,
        }
