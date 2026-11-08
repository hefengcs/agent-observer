import hashlib
import json
from typing import Literal

from .config import Config
from .files import FileReader
from .git import GitReader
from .history import ClaudeCodeAdapter, CodexAdapter
from .index import SearchIndex, page
from .security import sanitize

Provider = Literal["codex", "claude"]


class Observer:
    def __init__(self, config: Config):
        self.config = config
        self.providers = [
            CodexAdapter(config.history.codex_root),
            ClaudeCodeAdapter(config.history.claude_root),
        ]

    def project(self, project_id):
        return self.config.project(project_id)

    def list_projects(self, project_id: str, offset: int = 0, limit: int = 20):
        """List enabled registrations only; require a known project id and never discover machine paths."""
        self.project(project_id)
        registrations = [p.model_dump(mode="json") for p in self.config.projects if p.enabled]
        return page(registrations, offset, limit, self.config.limits.max_output_chars)

    def reader(self, project_id):
        return FileReader(self.project(project_id), self.config.limits)

    def sessions(self, project_id, provider=None):
        project = self.project(project_id)
        if provider is not None and provider not in ("codex", "claude"):
            raise ValueError("Unknown provider")
        result, warnings = [], []
        for adapter in self.providers:
            if provider and provider != adapter.name:
                continue
            sources, notices = adapter.discover(self.config.limits)
            warnings.extend(notices)
            rejected = 0
            for source in sources:
                try:
                    session = adapter.parse(source, project, self.config.limits)
                    if session:
                        result.append(session)
                except (OSError, ValueError, TypeError, RecursionError):
                    rejected += 1
            if rejected:
                # Counts only; never reveal other projects' filenames, cwd or identifiers.
                warnings.append(
                    f"{adapter.name}: some source files could not be verified; results may be incomplete"
                )
        counts = {}
        for session in result:
            key = (session.provider, session.session_id)
            counts[key] = counts.get(key, 0) + 1
        if any(v > 1 for v in counts.values()):
            warnings.append("Duplicate session identities quarantined")
        result = [s for s in result if counts[s.provider, s.session_id] == 1]
        return sorted(result, key=lambda s: (s.timestamp, s.provider, s.session_id), reverse=True), warnings

    def get_project_overview(self, project_id: str):
        project = self.project(project_id)
        files, warnings = self.reader(project_id).scan()
        sessions, notices = self.sessions(project_id)
        try:
            git = self.get_git_status(project_id)
        except ValueError as exc:
            git = {"available": False, "reason": str(exc)}
        return {
            "project": project.model_dump(mode="json"),
            "file_count": len(files),
            "tree_sample": [f["path"] for f in files[:40]],
            "git": git,
            "session_counts": {p: sum(s.provider == p for s in sessions) for p in ("codex", "claude")},
            "warnings": warnings + notices,
        }

    def list_project_files(self, project_id: str, directory: str = ".", offset: int = 0, limit: int = 50):
        from .security import safe_path

        reader = self.reader(project_id)
        safe_path(reader.root, directory, directory=True)
        files, warnings = reader.scan()
        from pathlib import Path

        prefix = Path(directory).as_posix()
        prefix = "" if prefix == "." else prefix
        selected = [
            {"path": f["path"], "size": f["size"]}
            for f in files
            if not prefix or f["path"].startswith(prefix + "/")
        ]
        return page(selected, offset, limit, self.config.limits.max_output_chars) | {"warnings": warnings}

    def search_project_files(self, project_id: str, keyword: str, offset: int = 0, limit: int = 50):
        if not keyword or len(keyword) > 500:
            raise ValueError("keyword must contain 1..500 characters")
        files, warnings = self.reader(project_id).scan()
        selected = [
            {"path": f["path"], "size": f["size"]}
            for f in files
            if keyword.casefold() in f["path"].casefold()
        ]
        return page(selected, offset, limit, self.config.limits.max_output_chars) | {"warnings": warnings}

    def search_project_content(
        self, project_id: str, query: str, path: str | None = None, offset: int = 0, limit: int = 20
    ):
        reader = self.reader(project_id)
        if path:
            files, warnings = [{"path": path, "text": reader.read(path)["text"]}], []
            # Index the complete bounded source, rather than a read-output page.
            from .security import read_text

            files[0]["text"] = read_text(reader.root, path, self.config.limits.max_file_bytes)
        else:
            files, warnings = reader.scan()
        index = SearchIndex()
        try:
            for file in files:
                for line, text in enumerate(file["text"].splitlines(), 1):
                    index.add(project_id, "file", file["path"], line, text)
            return self._search(index, project_id, "file", query, offset, limit) | {"warnings": warnings}
        finally:
            index.close()

    def read_project_file(
        self,
        project_id: str,
        path: str,
        start_line: int = 1,
        end_line: int | None = None,
        char_offset: int = 0,
    ):
        return self.reader(project_id).read(path, start_line, end_line, char_offset)

    def get_git_status(self, project_id: str, offset: int = 0, limit: int = 50):
        result = GitReader(self.project(project_id), self.config.limits).status()
        result["changes"] = page(result["changes"], offset, limit, self.config.limits.max_output_chars)
        return result

    def get_git_log(self, project_id: str, limit: int = 10, offset: int = 0, path: str | None = None):
        return GitReader(self.project(project_id), self.config.limits).log(limit, offset, path)

    def get_git_diff(
        self,
        project_id: str,
        commit: str | None = None,
        base: str | None = None,
        path: str | None = None,
        staged: bool = False,
        char_offset: int = 0,
    ):
        return GitReader(self.project(project_id), self.config.limits).diff(
            commit, base, path, staged, char_offset
        )

    def list_agent_sessions(
        self, project_id: str, provider: Provider | None = None, offset: int = 0, limit: int = 20
    ):
        sessions, warnings = self.sessions(project_id, provider)
        selected = [
            {
                "provider": s.provider,
                "session_id": s.session_id,
                "cwd": s.cwd,
                "timestamp": s.timestamp,
                "source": s.source,
                "event_count": len(s.events),
            }
            for s in sessions
        ]
        return page(selected, offset, limit, self.config.limits.max_output_chars) | {"warnings": warnings}

    def _search(self, index, project_id, category, query, offset, limit, provider=None, session_id=None):
        if offset < 0 or not 1 <= limit <= 100:
            raise ValueError("Invalid pagination")
        result = index.search(project_id, category, query, provider, session_id, offset, limit)
        # Budget after excerpts and metadata, retaining correct next_offset.
        selected = page(result["items"], 0, limit, self.config.limits.max_output_chars)
        result["items"] = selected["items"]
        nxt = offset + len(result["items"])
        return result | {
            "next_offset": nxt if nxt < result["total"] else None,
            "truncated": nxt < result["total"],
        }

    def search_agent_history(
        self,
        project_id: str,
        query: str,
        provider: Provider | None = None,
        session_id: str | None = None,
        offset: int = 0,
        limit: int = 20,
    ):
        sessions, warnings = self.sessions(project_id, provider)
        index = SearchIndex()
        try:
            for session in sessions:
                if session_id is not None and session.session_id != session_id:
                    continue
                for i, event in enumerate(session.events):
                    index.add(
                        project_id,
                        "history",
                        session.source,
                        event.source_line,
                        event.text,
                        session.provider,
                        session.session_id,
                        i,
                        event.kind,
                    )
            return self._search(index, project_id, "history", query, offset, limit, provider, session_id) | {
                "warnings": warnings
            }
        finally:
            index.close()

    def get_agent_session(
        self,
        project_id: str,
        session_id: str,
        provider: Provider,
        offset: int = 0,
        limit: int = 20,
        include_tools: bool = True,
        char_offset: int = 0,
        snapshot: str | None = None,
    ):
        if offset < 0 or char_offset < 0 or not 1 <= limit <= 100:
            raise ValueError("Invalid pagination")
        sessions, warnings = self.sessions(project_id, provider)
        session = next((s for s in sessions if s.session_id == session_id), None)
        if not session:
            raise ValueError("Session not found in the authorized project")
        events = [e for e in session.events if include_tools or e.kind not in ("tool_call", "tool_output")]
        digest = hashlib.sha256(
            json.dumps([(e.kind, e.text, e.source_line) for e in events], ensure_ascii=False).encode()
        ).hexdigest()
        if snapshot and snapshot != digest:
            raise ValueError("Session changed; restart pagination from offset=0")
        items, next_offset, next_char = [], offset, char_offset
        budget = self.config.limits.max_output_chars
        for i in range(offset, min(offset + limit, len(events))):
            event = events[i]
            start = char_offset if i == offset else 0
            if start > len(event.text):
                raise ValueError("char_offset exceeds event length")
            chunk_size = max(32, (budget - 900) // 8)
            chunk = event.text[start : start + chunk_size]
            item = {
                "event_index": i,
                "kind": event.kind,
                "timestamp": event.timestamp,
                "source_line": event.source_line,
                "call_id": event.call_id,
                "name": event.name,
                "text": chunk,
                "char_offset": start,
                "text_chars": len(event.text),
            }
            if len(json.dumps(items + [item], ensure_ascii=False)) > budget - 1000 and items:
                break
            items.append(item)
            end = start + len(chunk)
            if end < len(event.text):
                next_offset, next_char = i, end
                break
            next_offset, next_char = i + 1, 0
        more = next_offset < len(events)
        return {
            "provider": provider,
            "session_id": session_id,
            "source": session.source,
            "cwd": session.cwd,
            "metadata": session.metadata if offset == 0 and char_offset == 0 else {},
            "snapshot": digest,
            "items": items,
            "total_events": len(events),
            "offset": offset,
            "next_offset": next_offset if more else None,
            "next_char_offset": next_char if more else None,
            "truncated": more,
            "warnings": warnings,
        }

    def call(self, name: str, **kwargs):
        # Final shared egress filter also covers names, Git, metadata and registry descriptions.
        result = sanitize(getattr(self, name)(**kwargs))
        if len(json.dumps(result, ensure_ascii=False)) > self.config.limits.max_output_chars:
            raise ValueError("Output limit exceeded; use a narrower request or smaller page")
        return result
