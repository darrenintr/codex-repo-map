from __future__ import annotations

import sqlite3
from pathlib import Path

SCHEMA_VERSION = "1"


def connect(path: Path) -> sqlite3.Connection:
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    ensure_schema(conn)
    return conn


def ensure_schema(conn: sqlite3.Connection) -> None:
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS meta (
            key TEXT PRIMARY KEY,
            value TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS files (
            path TEXT PRIMARY KEY,
            sha256 TEXT NOT NULL,
            size INTEGER NOT NULL,
            mtime_ns INTEGER NOT NULL,
            language TEXT NOT NULL,
            module TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS symbols (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            path TEXT NOT NULL REFERENCES files(path) ON DELETE CASCADE,
            name TEXT NOT NULL,
            kind TEXT NOT NULL,
            line INTEGER NOT NULL
        );

        CREATE INDEX IF NOT EXISTS idx_symbols_path ON symbols(path);
        CREATE INDEX IF NOT EXISTS idx_symbols_name ON symbols(name);

        CREATE TABLE IF NOT EXISTS imports (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            path TEXT NOT NULL REFERENCES files(path) ON DELETE CASCADE,
            target TEXT NOT NULL
        );

        CREATE INDEX IF NOT EXISTS idx_imports_path ON imports(path);
        CREATE INDEX IF NOT EXISTS idx_imports_target ON imports(target);

        CREATE TABLE IF NOT EXISTS summaries (
            path TEXT PRIMARY KEY,
            source_hash TEXT NOT NULL,
            summary TEXT NOT NULL,
            estimated_tokens INTEGER NOT NULL,
            updated_at TEXT NOT NULL
        );
        """
    )
    conn.execute(
        "INSERT INTO meta(key, value) VALUES('schema_version', ?) "
        "ON CONFLICT(key) DO UPDATE SET value=excluded.value",
        (SCHEMA_VERSION,),
    )
    conn.commit()
