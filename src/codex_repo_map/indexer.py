from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

from . import __version__
from .database import connect
from .git import find_root, git_dir, head, list_files
from .languages import language_for, parse_file
from .manifests import detect_project
from .models import IndexResult

MAX_FILE_BYTES = 1_000_000
SKIP_PARTS = {
    ".git",
    ".dart_tool",
    ".gradle",
    ".idea",
    ".venv",
    "venv",
    "node_modules",
    "build",
    "dist",
    "target",
    "vendor",
    "coverage",
}


def db_path(root: Path) -> Path:
    return git_dir(root) / "codex-repo-map" / "index.sqlite3"


def module_for(path: str) -> str:
    parts = Path(path).parts
    if len(parts) <= 1:
        return "."
    if parts[0] in {"src", "lib", "app", "packages", "crates"} and len(parts) >= 3:
        return "/".join(parts[:2])
    return parts[0]


def _skip(path: str) -> bool:
    parts = set(Path(path).parts)
    return bool(parts & SKIP_PARTS)


def _read_text(path: Path) -> tuple[str, bytes] | None:
    try:
        raw = path.read_bytes()
    except OSError:
        return None
    if len(raw) > MAX_FILE_BYTES or b"\0" in raw[:8192]:
        return None
    return raw.decode("utf-8", errors="replace"), raw


def update_index(path: str | Path = ".") -> IndexResult:
    root = find_root(path)
    result = IndexResult(root=str(root))
    db = db_path(root)
    conn = connect(db)
    try:
        existing = {
            row["path"]: (row["size"], row["mtime_ns"], row["sha256"])
            for row in conn.execute("SELECT path, size, mtime_ns, sha256 FROM files")
        }
        discovered = set(list_files(root))
        indexable: set[str] = set()

        for rel in sorted(discovered):
            result.scanned += 1
            if _skip(rel):
                result.skipped += 1
                continue
            full = root / rel
            if not full.is_file():
                result.skipped += 1
                continue
            try:
                stat = full.stat()
            except OSError as exc:
                result.errors.append(f"{rel}: {exc}")
                continue
            if stat.st_size > MAX_FILE_BYTES:
                result.skipped += 1
                continue

            old = existing.get(rel)
            if old and old[0] == stat.st_size and old[1] == stat.st_mtime_ns:
                indexable.add(rel)
                result.unchanged += 1
                continue

            payload = _read_text(full)
            if payload is None:
                result.skipped += 1
                continue
            text, raw = payload
            digest = hashlib.sha256(raw).hexdigest()
            if old and old[2] == digest:
                conn.execute(
                    "UPDATE files SET size=?, mtime_ns=? WHERE path=?",
                    (stat.st_size, stat.st_mtime_ns, rel),
                )
                indexable.add(rel)
                result.unchanged += 1
                continue

            language = language_for(rel)
            parsed = parse_file(text, language)
            conn.execute("DELETE FROM files WHERE path=?", (rel,))
            conn.execute(
                "INSERT INTO files(path, sha256, size, mtime_ns, language, module) VALUES(?,?,?,?,?,?)",
                (rel, digest, stat.st_size, stat.st_mtime_ns, language, module_for(rel)),
            )
            conn.executemany(
                "INSERT INTO symbols(path, name, kind, line) VALUES(?,?,?,?)",
                [(rel, s.name, s.kind, s.line) for s in parsed.symbols],
            )
            conn.executemany(
                "INSERT INTO imports(path, target) VALUES(?,?)",
                [(rel, target) for target in parsed.imports],
            )
            conn.execute("DELETE FROM summaries WHERE path=? AND source_hash<>?", (rel, digest))
            indexable.add(rel)
            result.updated += 1

        stale = set(existing) - indexable
        for rel in stale:
            conn.execute("DELETE FROM files WHERE path=?", (rel,))
            conn.execute("DELETE FROM summaries WHERE path=?", (rel,))
            result.deleted += 1

        meta = {
            "root": str(root),
            "head": head(root) or "",
            "indexed_at": datetime.now(timezone.utc).isoformat(),
            "project": json.dumps(detect_project(root), separators=(",", ":")),
            "version": __version__,
        }
        conn.executemany(
            "INSERT INTO meta(key, value) VALUES(?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value",
            list(meta.items()),
        )
        conn.commit()
    finally:
        conn.close()
    return result
