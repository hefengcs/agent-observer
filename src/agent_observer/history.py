"""Version-tolerant adapters. Directory encodings and filenames never authorize sessions."""

import io
import json
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Protocol

from .config import Limits, Project
from .security import read_bytes, redact, sanitize


@dataclass
class Event:
    kind: str
    text: str
    source_line: int
    timestamp: str = ""
    call_id: str = ""
    name: str = ""


@dataclass
class Session:
    provider: str
    session_id: str
    cwd: str
    source: str
    timestamp: str
    metadata: dict
    events: list[Event] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


class HistoryProvider(Protocol):
    name: str
    root: Path

    def discover(self, limits: Limits) -> tuple[list[Path], list[str]]: ...
    def parse(self, path: Path, project: Project, limits: Limits) -> Session | None: ...


def text_of(value) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value
    if isinstance(value, list):
        return "\n".join(text_of(v) for v in value)
    if isinstance(value, dict):
        # Exclude base64 images, opaque signatures and encrypted reasoning.
        if value.get("type") in ("image", "input_image", "document"):
            return "[non-text attachment omitted]"
        for key in ("text", "content", "summary"):
            if key in value:
                return text_of(value[key])
        return json.dumps(sanitize(value), ensure_ascii=False)
    return str(value)


class Adapter:
    name = ""

    def __init__(self, root: Path):
        self.root = root.expanduser().resolve()

    def discover(self, limits: Limits) -> tuple[list[Path], list[str]]:
        found = []
        if not self.root.is_dir():
            return [], [f"{self.name} history store is unavailable"]
        for base, dirs, files in os.walk(self.root, followlinks=False):
            dirs[:] = sorted(d for d in dirs if not Path(base, d).is_symlink())
            for name in sorted(files):
                path = Path(base, name)
                if name.endswith(".jsonl") and not path.is_symlink():
                    found.append(path)
                    if len(found) >= limits.max_history_files:
                        return found, [f"{self.name} history discovery limit reached"]
        return found, []

    def identity(self, record: dict) -> tuple[str | None, str | None, dict]:
        raise NotImplementedError

    def events(self, record: dict, line: int) -> list[Event]:
        raise NotImplementedError

    def parse(self, path: Path, project: Project, limits: Limits) -> Session | None:
        raw = read_bytes(self.root, path.relative_to(self.root).as_posix(), limits.max_session_bytes)
        ids, cwds, metadata = set(), set(), {}
        warnings = []
        timestamp = ""

        def records():
            for line, data in enumerate(io.BytesIO(raw), 1):
                if len(data) > limits.max_jsonl_line_bytes:
                    # Cannot prove that an oversized record did not change cwd.
                    raise ValueError("Session has an oversized JSONL record")
                if not data.strip():
                    continue
                try:
                    record = json.loads(data)
                except (ValueError, UnicodeError) as exc:
                    raise ValueError("Session has malformed JSONL; identity cannot be verified") from exc
                if not isinstance(record, dict):
                    raise ValueError("Invalid JSONL record")
                yield line, record

        for _, record in records():
            sid, cwd, meta = self.identity(record)
            if sid:
                ids.add(str(sid))
            # Check every supported alias, including conflicts within the same record.
            candidates = [cwd, record.get("cwd"), record.get("projectDirectory")]
            for key in ("session_id", "sessionId"):
                if record.get(key):
                    ids.add(str(record[key]))
            payload = record.get("payload")
            if record.get("type") in ("session_meta", "turn_context") and isinstance(payload, dict):
                candidates.append(payload.get("cwd"))
                if record.get("type") == "session_meta":
                    for key in ("id", "session_id"):
                        if payload.get(key):
                            ids.add(str(payload[key]))
            for candidate in candidates:
                if not candidate:
                    continue
                p = Path(candidate)
                if not p.is_absolute():
                    return None
                cwds.add(str(p.resolve()))
            metadata.update(meta)
            if not timestamp and isinstance(record.get("timestamp"), str):
                timestamp = record["timestamp"]
        if len(ids) != 1 or cwds != {str(project.absolute_path)}:
            return None
        sid = next(iter(ids))
        if len(sid) > 200:
            return None
        result = Session(
            self.name,
            sid,
            str(project.absolute_path),
            path.relative_to(self.root).as_posix(),
            timestamp,
            sanitize(metadata),
            warnings=warnings,
        )
        for line, record in records():
            result.events.extend(self.events(record, line))
        for event in result.events:
            event.text = redact(event.text)
            event.name = redact(event.name)[:200]
            event.call_id = redact(event.call_id)[:200]
        return result


class CodexAdapter(Adapter):
    name = "codex"

    def identity(self, record):
        payload = record.get("payload")
        payload = payload if isinstance(payload, dict) else {}
        typ = record.get("type")
        sid = (payload.get("session_id") or payload.get("id")) if typ == "session_meta" else None
        sid = sid or record.get("session_id")
        cwd = record.get("cwd") or (payload.get("cwd") if typ in ("session_meta", "turn_context") else None)
        meta = (
            {
                k: payload[k]
                for k in ("cli_version", "originator", "model_provider", "source")
                if k in payload and isinstance(payload[k], (str, int, bool))
            }
            if typ == "session_meta"
            else {}
        )
        return sid, cwd, meta

    def events(self, record, line):
        typ = record.get("type")
        p = record.get("payload", record)
        if not isinstance(p, dict):
            return []
        kind, text = "", ""
        sub = p.get("type", typ)
        if (typ == "response_item" and sub == "message") or typ in ("user", "assistant"):
            kind, text = str(p.get("role", typ)), text_of(p.get("content", p.get("message")))
        elif sub in ("function_call", "custom_tool_call", "tool_call"):
            kind, text = "tool_call", text_of(p.get("arguments", p.get("input")))
        elif sub in ("function_call_output", "custom_tool_call_output", "tool_result"):
            kind, text = "tool_output", text_of(p.get("output", p.get("content")))
        elif sub == "reasoning":
            kind, text = "analysis_summary", text_of(p.get("summary") or p.get("content"))
        elif typ == "event_msg" and sub in ("user_message", "agent_message"):
            # SDK rollouts also store response_item messages; suppress duplicate event mirrors below.
            kind, text = (
                "user_mirror" if sub == "user_message" else "assistant_mirror",
                text_of(p.get("message")),
            )
        elif typ == "event_msg" and sub in ("context_compacted", "task_complete"):
            kind, text = "metadata", text_of(p.get("message", p.get("last_agent_message")))
        elif typ == "compacted":
            kind, text = "compaction", text_of(p.get("message"))
        if not kind or not text:
            return []
        return [
            Event(
                kind,
                text,
                line,
                str(record.get("timestamp", "")),
                str(p.get("call_id", "")),
                str(p.get("name", "")),
            )
        ]

    def parse(self, path, project, limits):
        session = super().parse(path, project, limits)
        if session:
            canonical = {(e.kind, e.text) for e in session.events if e.kind in ("user", "assistant")}
            session.events = [
                e
                for e in session.events
                if not (e.kind.endswith("_mirror") and (e.kind.removesuffix("_mirror"), e.text) in canonical)
            ]
            for event in session.events:
                event.kind = event.kind.removesuffix("_mirror")
        return session


class ClaudeCodeAdapter(Adapter):
    name = "claude"

    def identity(self, record):
        meta = {k: record[k] for k in ("version", "gitBranch", "isSidechain") if k in record}
        return (
            record.get("sessionId") or record.get("session_id"),
            record.get("cwd") or record.get("projectDirectory"),
            meta,
        )

    def events(self, record, line):
        message = record.get("message", {})
        if not isinstance(message, dict):
            return []
        role = message.get("role", record.get("type"))
        if role not in ("user", "assistant"):
            return []
        content = message.get("content", [])
        if isinstance(content, str):
            content = [{"type": "text", "text": content}]
        if not isinstance(content, list):
            return []
        result = []
        for block in content:
            if not isinstance(block, dict):
                continue
            typ = block.get("type")
            if typ == "tool_use":
                kind, text = "tool_call", text_of(block.get("input"))
            elif typ == "tool_result":
                kind, text = "tool_output", text_of(block.get("content"))
            elif typ == "thinking":
                kind, text = "recorded_analysis", text_of(block.get("thinking"))
            elif typ == "text":
                kind, text = role, text_of(block.get("text"))
            else:
                continue
            result.append(
                Event(
                    kind,
                    text,
                    line,
                    str(record.get("timestamp", "")),
                    str(block.get("tool_use_id", block.get("id", ""))),
                    str(block.get("name", "")),
                )
            )
        return result
