from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from .database import connect
from .git import find_root
from .indexer import db_path
from .retrieval import estimate_tokens


def cache_summary(path: str | Path, source_path: str, summary: str) -> None:
    root = find_root(path)
    conn = connect(db_path(root))
    try:
        row = conn.execute("SELECT sha256 FROM files WHERE path=?", (source_path,)).fetchone()
        if row is None:
            raise ValueError(f"file is not indexed: {source_path}")
        conn.execute(
            """
            INSERT INTO summaries(path, source_hash, summary, estimated_tokens, updated_at)
            VALUES(?,?,?,?,?)
            ON CONFLICT(path) DO UPDATE SET
              source_hash=excluded.source_hash,
              summary=excluded.summary,
              estimated_tokens=excluded.estimated_tokens,
              updated_at=excluded.updated_at
            """,
            (
                source_path,
                row["sha256"],
                summary.strip(),
                estimate_tokens(summary),
                datetime.now(timezone.utc).isoformat(),
            ),
        )
        conn.commit()
    finally:
        conn.close()
