from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .database import connect
from .git import find_root
from .indexer import db_path


def read_stats(path: str | Path = ".") -> dict[str, Any]:
    root = find_root(path)
    db = db_path(root)
    if not db.exists():
        return {"root": str(root), "indexed": False}
    conn = connect(db)
    try:
        file_count = conn.execute("SELECT COUNT(*) FROM files").fetchone()[0]
        symbol_count = conn.execute("SELECT COUNT(*) FROM symbols").fetchone()[0]
        import_count = conn.execute("SELECT COUNT(*) FROM imports").fetchone()[0]
        summary_count = conn.execute("SELECT COUNT(*) FROM summaries").fetchone()[0]
        languages = {
            row["language"]: row["count"]
            for row in conn.execute(
                "SELECT language, COUNT(*) AS count FROM files GROUP BY language ORDER BY count DESC, language"
            )
        }
        meta = {row["key"]: row["value"] for row in conn.execute("SELECT key, value FROM meta")}
        project = {}
        try:
            project = json.loads(meta.get("project", "{}"))
        except json.JSONDecodeError:
            pass
        return {
            "root": str(root),
            "indexed": True,
            "database": str(db),
            "files": file_count,
            "symbols": symbol_count,
            "imports": import_count,
            "summaries": summary_count,
            "languages": languages,
            "project": project,
            "head": meta.get("head") or None,
            "indexed_at": meta.get("indexed_at"),
            "schema_version": meta.get("schema_version"),
        }
    finally:
        conn.close()
