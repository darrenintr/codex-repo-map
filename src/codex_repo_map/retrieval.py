from __future__ import annotations

import json
import math
import re
from collections import defaultdict
from pathlib import Path
from typing import Any

from .database import connect
from .git import branch, changed_files, find_root, head
from .indexer import db_path, update_index
from .manifests import detect_project

TOKEN_RE = re.compile(r"[A-Za-z_][A-Za-z0-9_]{1,}|[\u3400-\u9fff]{2,}")
CAMEL_RE = re.compile(r"(?<!^)(?=[A-Z])")


def estimate_tokens(value: Any) -> int:
    if not isinstance(value, str):
        value = json.dumps(value, ensure_ascii=False, separators=(",", ":"))
    ascii_chars = sum(1 for ch in value if ord(ch) < 128)
    non_ascii = len(value) - ascii_chars
    return max(1, math.ceil(ascii_chars / 3.6 + non_ascii / 1.5))


def terms(text: str) -> set[str]:
    out: set[str] = set()
    for token in TOKEN_RE.findall(text):
        lower = token.lower()
        if len(lower) >= 2:
            out.add(lower)
        if token.isascii():
            for part in re.split(r"[_\-./:]|\s+", token):
                for camel in CAMEL_RE.split(part):
                    if len(camel) >= 2:
                        out.add(camel.lower())
    return out


def _overlap(query: set[str], text: str) -> int:
    if not query:
        return 0
    return len(query & terms(text))


def _reasons(changed: bool, path_overlap: int, symbol_overlap: int, import_overlap: int) -> list[str]:
    reasons: list[str] = []
    if changed:
        reasons.append("changed-in-worktree")
    if path_overlap:
        reasons.append("task-path-match")
    if symbol_overlap:
        reasons.append("task-symbol-match")
    if import_overlap:
        reasons.append("task-import-match")
    if not reasons:
        reasons.append("structural-neighbor")
    return reasons


def build_context(
    path: str | Path,
    task: str,
    budget: int = 3000,
    refresh: bool = True,
) -> dict[str, Any]:
    root = find_root(path)
    if refresh or not db_path(root).exists():
        update_index(root)

    changes = changed_files(root)
    changed_paths = {item.path for item in changes}
    q = terms(task)
    conn = connect(db_path(root))
    try:
        symbols_by_path: dict[str, list[dict[str, Any]]] = defaultdict(list)
        for row in conn.execute("SELECT path, name, kind, line FROM symbols ORDER BY path, line"):
            symbols_by_path[row["path"]].append(
                {"name": row["name"], "kind": row["kind"], "line": row["line"]}
            )
        imports_by_path: dict[str, list[str]] = defaultdict(list)
        for row in conn.execute("SELECT path, target FROM imports ORDER BY path, target"):
            imports_by_path[row["path"]].append(row["target"])
        summaries = {
            row["path"]: row["summary"]
            for row in conn.execute("SELECT path, summary FROM summaries")
        }

        ranked: list[dict[str, Any]] = []
        for row in conn.execute("SELECT path, language, module, size FROM files ORDER BY path"):
            rel = row["path"]
            path_overlap = _overlap(q, rel)
            symbol_overlap = sum(_overlap(q, s["name"]) for s in symbols_by_path.get(rel, ()))
            import_overlap = sum(_overlap(q, imp) for imp in imports_by_path.get(rel, ()))
            summary_overlap = _overlap(q, summaries.get(rel, ""))
            changed = rel in changed_paths
            score = (
                path_overlap * 5.0
                + symbol_overlap * 6.0
                + import_overlap * 2.0
                + summary_overlap * 3.0
                + (8.0 if changed else 0.0)
            )
            if row["language"] not in {"text", "manifest"}:
                score += 0.25
            ranked.append(
                {
                    "path": rel,
                    "language": row["language"],
                    "module": row["module"],
                    "size_bytes": row["size"],
                    "score": round(score, 2),
                    "reasons": _reasons(changed, path_overlap, symbol_overlap, import_overlap),
                    "summary": summaries.get(rel),
                }
            )

        ranked.sort(key=lambda item: (-item["score"], item["path"]))
        top = ranked[:12]
        selected_paths = {item["path"] for item in top}
        stems = {Path(p).stem.lower() for p in selected_paths}
        if stems:
            neighbors: list[dict[str, Any]] = []
            for item in ranked[12:]:
                imports = imports_by_path.get(item["path"], ())
                if any(any(stem in imp.lower() for stem in stems) for imp in imports):
                    copy = dict(item)
                    copy["score"] = round(copy["score"] + 1.5, 2)
                    copy["reasons"] = list(dict.fromkeys(copy["reasons"] + ["imports-relevant-file"]))
                    neighbors.append(copy)
            top = sorted(top + neighbors[:3], key=lambda item: (-item["score"], item["path"]))[:12]

        top_paths = {item["path"] for item in top}
        relevant_symbols: list[dict[str, Any]] = []
        for rel in top_paths:
            for symbol in symbols_by_path.get(rel, ()):
                item = dict(symbol)
                item["path"] = rel
                item["match"] = _overlap(q, item["name"])
                relevant_symbols.append(item)
        relevant_symbols.sort(key=lambda item: (-item["match"], item["path"], item["line"]))
        relevant_symbols = relevant_symbols[:24]
        for item in relevant_symbols:
            item.pop("match", None)

        module_scores: dict[str, float] = defaultdict(float)
        for item in top:
            module_scores[item["module"]] += item["score"]
        modules = [
            {"name": name, "score": round(score, 2)}
            for name, score in sorted(module_scores.items(), key=lambda pair: (-pair[1], pair[0]))[:8]
        ]

        worktree = [
            {
                "path": item.path,
                "status": item.status,
                "additions": item.additions,
                "deletions": item.deletions,
            }
            for item in changes[:30]
        ]
        context: dict[str, Any] = {
            "schema_version": 1,
            "task": task,
            "project": detect_project(root),
            "git": {
                "branch": branch(root),
                "head": head(root),
                "dirty": bool(changes),
                "changed_files": worktree,
            },
            "relevant": {
                "modules": modules,
                "files": top,
                "symbols": relevant_symbols,
            },
            "source_fallback": [item["path"] for item in top[:3]],
            "budget": {
                "requested_tokens": budget,
                "estimated_tokens": 0,
                "truncated": False,
            },
        }
        _enforce_budget(context, budget)
        return context
    finally:
        conn.close()


def _enforce_budget(context: dict[str, Any], budget: int) -> None:
    budget = max(250, int(budget))

    def current() -> int:
        clone = json.loads(json.dumps(context))
        clone["budget"]["estimated_tokens"] = 0
        return estimate_tokens(clone)

    while current() > budget and context["relevant"]["symbols"]:
        context["relevant"]["symbols"].pop()
        context["budget"]["truncated"] = True
    while current() > budget and len(context["git"]["changed_files"]) > 8:
        context["git"]["changed_files"].pop()
        context["budget"]["truncated"] = True
    while current() > budget and len(context["relevant"]["files"]) > 3:
        context["relevant"]["files"].pop()
        context["budget"]["truncated"] = True
        allowed = {item["path"] for item in context["relevant"]["files"]}
        context["relevant"]["symbols"] = [
            item for item in context["relevant"]["symbols"] if item["path"] in allowed
        ]
        context["source_fallback"] = [p for p in context["source_fallback"] if p in allowed][:3]
    while current() > budget and len(context["relevant"]["modules"]) > 2:
        context["relevant"]["modules"].pop()
        context["budget"]["truncated"] = True
    while current() > budget and len(context["project"]["dependencies"]) > 8:
        context["project"]["dependencies"].pop()
        context["budget"]["truncated"] = True

    context["budget"]["estimated_tokens"] = current()
