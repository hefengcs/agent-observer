import json
import re
import sqlite3


class SearchIndex:
    """Ephemeral SQLite FTS5 index: only authorized, already-redacted data enters it."""

    def __init__(self):
        self.db = sqlite3.connect(":memory:")
        self.db.row_factory = sqlite3.Row
        self.db.execute("""CREATE VIRTUAL TABLE content USING fts5(
            project_id UNINDEXED, category UNINDEXED, provider UNINDEXED, session_id UNINDEXED,
            source UNINDEXED, line UNINDEXED, event_index UNINDEXED, kind UNINDEXED, text,
            tokenize='unicode61')""")

    def add(
        self, project_id, category, source, line, text, provider="", session_id="", event_index=-1, kind=""
    ):
        self.db.execute(
            "INSERT INTO content VALUES(?,?,?,?,?,?,?,?,?)",
            (project_id, category, provider, session_id, source, line, event_index, kind, text),
        )

    def search(self, project_id, category, query, provider=None, session_id=None, offset=0, limit=20):
        if not query.strip() or len(query) > 500:
            raise ValueError("Search query must contain 1..500 characters")
        where, args = ["project_id=?", "category=?"], [project_id, category]
        for key, value in (("provider", provider), ("session_id", session_id)):
            if value is not None:
                where.append(f"{key}=?")
                args.append(value)
        # Literal terms, never pass model-supplied FTS expressions through.
        terms = re.findall(r"\w+", query, re.UNICODE)
        cjk = bool(re.search(r"[\u3400-\u9fff]", query))
        if terms and not cjk:
            where.append("content MATCH ?")
            args.append(" AND ".join('"' + t.replace('"', '""') + '"' for t in terms))
        else:
            # unicode61 groups CJK text; literal substring fallback enables Chinese queries.
            where.append("instr(lower(text),lower(?))>0")
            args.append(query)
        clause = " AND ".join(where)
        total = self.db.execute("SELECT count(*) FROM content WHERE " + clause, args).fetchone()[0]
        rows = self.db.execute(
            "SELECT * FROM content WHERE " + clause + " ORDER BY rowid LIMIT ? OFFSET ?",
            [*args, limit, offset],
        ).fetchall()
        results = []
        for row in rows:
            item = dict(row)
            content = item.pop("text")
            positions = [content.lower().find(t.lower()) for t in terms or [query]]
            pos = min((p for p in positions if p >= 0), default=0)
            start = max(0, pos - 150)
            item.update(
                excerpt=content[start : start + 900], excerpt_char_offset=start, text_chars=len(content)
            )
            results.append(item)
        return {"items": results, "total": total, "offset": offset}

    def close(self):
        self.db.close()


def page(items: list, offset: int, limit: int, maximum: int) -> dict:
    if offset < 0 or not 1 <= limit <= 100:
        raise ValueError("offset must be >=0; limit must be 1..100")
    result = []
    for item in items[offset : offset + limit]:
        if len(json.dumps(result + [item], ensure_ascii=False)) > maximum - 800:
            if not result:
                raise ValueError("One result exceeds output limit; narrow the request")
            break
        result.append(item)
    nxt = offset + len(result)
    return {
        "items": result,
        "total": len(items),
        "offset": offset,
        "next_offset": nxt if nxt < len(items) else None,
        "truncated": nxt < len(items),
    }
