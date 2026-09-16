# Codex Repo Map

Token-efficient, local-first codebase structure maps for AI coding routers and agents.

`codex-repo-map` incrementally indexes a Git working tree and returns a compact, task-specific structural context. The first integration target is [`darrenintr/codex-auto-router`](https://github.com/darrenintr/codex-auto-router): Luna Low can classify a task from a few thousand tokens of relevant project structure instead of rediscovering the repository for every route.

## Why

Without a persistent map, a cheap classifier still has to spend context on repository discovery:

```text
Task -> Luna Low -> ls/rg/read files -> understand project -> choose tier
```

With Repo Map:

```text
                 Git + manifests + symbols + imports
                              |
                              v
                    incremental local index
                              |
Task -------------------------+----> compact context
                                      |
                                      v
                                   Luna Low
                                      |
                                      v
                               choose Codex tier
```

The index is stored under `.git/codex-repo-map/index.sqlite3`. Nothing is added to the project's tracked tree.

## Current MVP

- Incremental indexing using file size/mtime and SHA-256 validation.
- Git-aware discovery: tracked and untracked files are indexed while `.gitignore` is respected.
- Project detection for Flutter/Dart, Node/TypeScript/JavaScript, Python, Rust and JVM projects.
- Symbol/import extraction for Python, Dart, TypeScript/JavaScript, Rust, Java, Kotlin, Go and C/C++.
- Worktree-aware ranking: modified files are strongly boosted for routing context.
- Task-to-file and task-to-symbol relevance scoring.
- One-hop structural neighbor discovery from imports.
- Hard approximate token budget for context output.
- Optional hash-bound summary cache. Cached summaries are automatically invalidated when the source file changes.
- Stable JSON schema (`schema_version: 1`) for `codex-auto-router` integration.
- No model/API dependency in the indexer itself.

## Install

```bash
pipx install git+https://github.com/darrenintr/codex-repo-map.git
```

For development:

```bash
git clone https://github.com/darrenintr/codex-repo-map.git
cd codex-repo-map
python -m pip install -e .
```

Python 3.11+ is required.

## Usage

Initialize or refresh the index from anywhere inside a Git repository:

```bash
codex-repo-map init .
```

Later updates are incremental:

```bash
codex-repo-map update
```

Inspect index statistics:

```bash
codex-repo-map stats --json
```

Generate a compact routing context:

```bash
codex-repo-map context \
  --task "fix fullscreen to inline player flicker" \
  --budget 3000 \
  --json
```

The task can also come from stdin:

```bash
printf '%s\n' 'fix the return animation flicker' | \
  codex-repo-map context --budget 3000 --json
```

Example output shape:

```json
{
  "schema_version": 1,
  "task": "fix fullscreen to inline player flicker",
  "project": {
    "name": "sample_app",
    "type": "flutter",
    "languages": ["dart"],
    "frameworks": ["flutter"]
  },
  "git": {
    "branch": "main",
    "dirty": true,
    "changed_files": []
  },
  "relevant": {
    "modules": [],
    "files": [],
    "symbols": []
  },
  "source_fallback": [
    "lib/navigation/shared_transition.dart"
  ],
  "budget": {
    "requested_tokens": 3000,
    "estimated_tokens": 950,
    "truncated": false
  }
}
```

`source_fallback` is deliberately small. A router can ask Luna Low to inspect those source files only when the structural context is not sufficient for a confident classification.

## Summary cache

Repo Map does not require an LLM to build its core index. An external process can optionally cache a concise semantic summary for a high-value file:

```bash
cat summary.txt | codex-repo-map cache-summary lib/navigation/shared_transition.dart
```

The summary is bound to the indexed source hash. If that file changes, Repo Map deletes the stale summary automatically.

This is the intended foundation for an LLM-Wiki-style layer without making every route pay the summarization cost again.

## Codex Auto Router integration

The integration contract is intentionally narrow:

```bash
codex-repo-map context \
  --task "$TASK" \
  --budget 3000 \
  --json
```

A router should:

1. Collect the user's task.
2. Ask Repo Map for a small task-specific context.
3. Send only the task + Repo Map JSON to Luna Low.
4. If confidence is high, choose the tier immediately.
5. If confidence is low, allow bounded read-only inspection of only `source_fallback` files.
6. Launch the real Codex task with the selected model and reasoning effort.

This keeps repository understanding amortized across tasks instead of paying for full discovery every time.

## Storage and privacy

All index data stays under the repository's Git directory:

```text
.git/
└── codex-repo-map/
    └── index.sqlite3
```

Source code is not uploaded by Repo Map. The database stores file metadata, symbols, imports and optional user-provided summaries, not complete source files.

## Design principles

- **Local first.** Source stays on the workstation.
- **Deterministic before AI.** Git metadata and structural extraction cost zero model tokens.
- **Incremental.** Unchanged files are not reparsed.
- **Task-specific.** Return only context likely to matter for the current request.
- **Budgeted.** Context generation has a hard approximate token ceiling.
- **Source remains truth.** Structural maps and summaries are hints, not authority.
- **Router agnostic.** The JSON contract can be consumed by Codex Auto Router or other agents.

## Development

```bash
python -m pip install -e .
python -m unittest discover -s tests -v
python -m compileall -q src tests
```

## Roadmap

- Tree-sitter-backed parsers where they materially improve symbol accuracy.
- Import resolution into an explicit dependency graph instead of raw import strings.
- Module-level summaries and summary ROI accounting.
- Benchmark harness comparing raw Luna repo inspection vs Repo Map-assisted routing.
- Direct optional integration package for `codex-auto-router`.

## License

MIT.
