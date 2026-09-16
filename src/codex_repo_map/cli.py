from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from . import __version__
from .git import GitError, find_root
from .indexer import db_path, update_index
from .retrieval import build_context
from .stats import read_stats
from .summaries import cache_summary


def _dump(value: object) -> None:
    print(json.dumps(value, ensure_ascii=False, indent=2, sort_keys=False))


def _read_task(args: argparse.Namespace) -> str:
    if getattr(args, "task", None):
        return args.task.strip()
    if getattr(args, "task_file", None):
        return Path(args.task_file).read_text(encoding="utf-8").strip()
    if not sys.stdin.isatty():
        return sys.stdin.read().strip()
    raise ValueError("provide --task, --task-file, or pipe the task on stdin")


def parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="codex-repo-map",
        description="Build and query a compact local codebase map for AI routing.",
    )
    p.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    sub = p.add_subparsers(dest="command", required=True)

    init = sub.add_parser("init", help="create or refresh the local repository index")
    init.add_argument("path", nargs="?", default=".")
    init.add_argument("--json", action="store_true")

    update = sub.add_parser("update", help="incrementally refresh the local repository index")
    update.add_argument("path", nargs="?", default=".")
    update.add_argument("--json", action="store_true")

    stats = sub.add_parser("stats", help="show index statistics")
    stats.add_argument("path", nargs="?", default=".")
    stats.add_argument("--json", action="store_true")

    context = sub.add_parser("context", help="build a task-specific compact router context")
    context.add_argument("path", nargs="?", default=".")
    context.add_argument("--task")
    context.add_argument("--task-file")
    context.add_argument("--budget", type=int, default=3000, help="approximate output token budget")
    context.add_argument("--no-refresh", action="store_true", help="do not refresh the incremental index first")
    context.add_argument("--json", action="store_true")

    summary = sub.add_parser("cache-summary", help="cache an externally generated summary for an indexed file")
    summary.add_argument("source_path")
    summary.add_argument("path", nargs="?", default=".")
    summary.add_argument("--text")
    summary.add_argument("--file")

    doctor = sub.add_parser("doctor", help="verify that the current repository can be indexed")
    doctor.add_argument("path", nargs="?", default=".")
    doctor.add_argument("--json", action="store_true")
    return p


def main(argv: list[str] | None = None) -> int:
    args = parser().parse_args(argv)
    try:
        if args.command in {"init", "update"}:
            result = update_index(args.path).as_dict()
            if args.json:
                _dump(result)
            else:
                print(
                    f"indexed {result['scanned']} files: {result['updated']} updated, "
                    f"{result['unchanged']} unchanged, {result['deleted']} deleted, {result['skipped']} skipped"
                )
                if result["errors"]:
                    print(f"warnings: {len(result['errors'])}", file=sys.stderr)
            return 0

        if args.command == "stats":
            value = read_stats(args.path)
            if args.json:
                _dump(value)
            elif not value.get("indexed"):
                print("repository is not indexed; run: codex-repo-map init")
            else:
                print(f"files: {value['files']}")
                print(f"symbols: {value['symbols']}")
                print(f"imports: {value['imports']}")
                print(f"summaries: {value['summaries']}")
                print(f"database: {value['database']}")
            return 0

        if args.command == "context":
            task = _read_task(args)
            if not task:
                raise ValueError("task is empty")
            value = build_context(
                args.path,
                task=task,
                budget=args.budget,
                refresh=not args.no_refresh,
            )
            if args.json:
                _dump(value)
            else:
                print(f"project: {value['project']['name']} ({value['project']['type']})")
                print(f"branch: {value['git']['branch']}  dirty: {value['git']['dirty']}")
                print("relevant files:")
                for item in value["relevant"]["files"]:
                    print(f"  {item['score']:>5}  {item['path']}  [{', '.join(item['reasons'])}]")
                print(f"estimated context tokens: {value['budget']['estimated_tokens']}/{value['budget']['requested_tokens']}")
            return 0

        if args.command == "cache-summary":
            if args.text:
                text = args.text
            elif args.file:
                text = Path(args.file).read_text(encoding="utf-8")
            elif not sys.stdin.isatty():
                text = sys.stdin.read()
            else:
                raise ValueError("provide --text, --file, or pipe a summary on stdin")
            cache_summary(args.path, args.source_path, text)
            print(f"cached summary for {args.source_path}")
            return 0

        if args.command == "doctor":
            root = find_root(args.path)
            result = update_index(root)
            value = {
                "ok": not result.errors,
                "root": str(root),
                "database": str(db_path(root)),
                "index": result.as_dict(),
            }
            if args.json:
                _dump(value)
            else:
                print("ok" if value["ok"] else "ok with warnings")
                print(f"root: {root}")
                print(f"database: {value['database']}")
            return 0

        return 2
    except (GitError, OSError, ValueError) as exc:
        print(f"codex-repo-map: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
