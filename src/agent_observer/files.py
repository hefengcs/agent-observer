import os
from pathlib import Path

from .config import Limits, Project
from .security import allowed, read_text, safe_path


class FileReader:
    def __init__(self, project: Project, limits: Limits):
        self.root, self.limits = project.absolute_path, limits

    def scan(self) -> tuple[list[dict], list[str]]:
        result, warnings = [], []
        visited = 0
        for base, dirs, files in os.walk(self.root, followlinks=False):
            dirs[:] = sorted(
                d
                for d in dirs
                if allowed(Path(base, d).relative_to(self.root)) and not Path(base, d).is_symlink()
            )
            for name in sorted(files):
                path = Path(base, name)
                relative = path.relative_to(self.root).as_posix()
                visited += 1
                if visited > self.limits.max_files:
                    return result, ["File scan limit reached; inventory and search may be incomplete"]
                if not allowed(relative):
                    continue
                try:
                    safe_path(self.root, relative)
                    st = path.stat()
                    if st.st_size > self.limits.max_file_bytes:
                        continue
                    text = read_text(self.root, relative, self.limits.max_file_bytes)
                    result.append({"path": relative, "size": st.st_size, "text": text})
                except (OSError, ValueError):
                    continue
        return result, warnings

    def read(self, path: str, start_line: int = 1, end_line: int | None = None, char_offset: int = 0) -> dict:
        if start_line < 1 or char_offset < 0 or (end_line is not None and end_line < start_line):
            raise ValueError("Invalid line range or char_offset")
        text = read_text(self.root, path, self.limits.max_file_bytes)
        lines = text.splitlines(keepends=True)
        end = min(end_line if end_line is not None else len(lines), len(lines))
        selected = "".join(lines[start_line - 1 : end])
        page = selected[char_offset : char_offset + self.limits.max_output_chars // 2]
        consumed = char_offset + len(page)
        more = consumed < len(selected)
        return {
            "path": path,
            "start_line": start_line,
            "end_line": end,
            "total_lines": len(lines),
            "text": page,
            "char_offset": char_offset,
            "next_char_offset": consumed if more else None,
            "truncated": more,
        }
