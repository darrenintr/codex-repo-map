from __future__ import annotations

import os
import subprocess
from pathlib import Path

from .models import ChangedFile


class GitError(RuntimeError):
    pass


def _run(root: Path, *args: str, check: bool = True) -> str:
    proc = subprocess.run(
        ["git", "-C", str(root), *args],
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    if check and proc.returncode != 0:
        raise GitError(proc.stderr.strip() or f"git {' '.join(args)} failed")
    return proc.stdout


def find_root(path: str | os.PathLike[str] = ".") -> Path:
    start = Path(path).expanduser().resolve()
    proc = subprocess.run(
        ["git", "-C", str(start), "rev-parse", "--show-toplevel"],
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    if proc.returncode != 0:
        raise GitError(f"not inside a Git repository: {start}")
    return Path(proc.stdout.strip()).resolve()


def git_dir(root: Path) -> Path:
    raw = _run(root, "rev-parse", "--git-dir").strip()
    path = Path(raw)
    if not path.is_absolute():
        path = root / path
    return path.resolve()


def list_files(root: Path) -> list[str]:
    # Tracked + untracked, while respecting .gitignore.
    out = _run(root, "ls-files", "-co", "--exclude-standard", "-z")
    return sorted({p for p in out.split("\0") if p})


def branch(root: Path) -> str:
    out = _run(root, "branch", "--show-current", check=False).strip()
    return out or "DETACHED"


def head(root: Path) -> str | None:
    out = _run(root, "rev-parse", "HEAD", check=False).strip()
    return out if len(out) == 40 else None


def _numstat(root: Path, cached: bool) -> dict[str, tuple[int | None, int | None]]:
    args = ["diff"]
    if cached:
        args.append("--cached")
    args += ["--numstat"]
    result: dict[str, tuple[int | None, int | None]] = {}
    for line in _run(root, *args, check=False).splitlines():
        parts = line.split("\t")
        if len(parts) < 3:
            continue
        a, d, path = parts[0], parts[1], parts[-1]
        av = int(a) if a.isdigit() else None
        dv = int(d) if d.isdigit() else None
        result[path] = (av, dv)
    return result


def changed_files(root: Path) -> list[ChangedFile]:
    stat = _numstat(root, False)
    for path, values in _numstat(root, True).items():
        if path in stat:
            a0, d0 = stat[path]
            a1, d1 = values
            stat[path] = (
                (a0 or 0) + (a1 or 0) if a0 is not None and a1 is not None else None,
                (d0 or 0) + (d1 or 0) if d0 is not None and d1 is not None else None,
            )
        else:
            stat[path] = values

    out = _run(root, "status", "--porcelain=v1", "--untracked-files=normal", check=False)
    files: list[ChangedFile] = []
    for line in out.splitlines():
        if len(line) < 4:
            continue
        status = line[:2].strip() or "?"
        path = line[3:]
        if " -> " in path:
            path = path.split(" -> ", 1)[1]
        additions, deletions = stat.get(path, (None, None))
        files.append(ChangedFile(path=path, status=status, additions=additions, deletions=deletions))
    return files
