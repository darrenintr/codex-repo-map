from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class Symbol:
    name: str
    kind: str
    line: int


@dataclass(frozen=True)
class ParsedFile:
    symbols: tuple[Symbol, ...] = ()
    imports: tuple[str, ...] = ()


@dataclass(frozen=True)
class ChangedFile:
    path: str
    status: str
    additions: int | None = None
    deletions: int | None = None


@dataclass
class IndexResult:
    root: str
    scanned: int = 0
    updated: int = 0
    unchanged: int = 0
    deleted: int = 0
    skipped: int = 0
    errors: list[str] = field(default_factory=list)

    def as_dict(self) -> dict[str, Any]:
        return {
            "root": self.root,
            "scanned": self.scanned,
            "updated": self.updated,
            "unchanged": self.unchanged,
            "deleted": self.deleted,
            "skipped": self.skipped,
            "errors": self.errors,
        }
