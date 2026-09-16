# Codex Repo Map

A token-efficient, local-first codebase structure index designed for AI coding routers and agents.

`codex-repo-map` turns a Git working tree into a compact, task-specific structural context so a cheap classifier can understand project scope without re-reading the repository on every request.

The first integration target is [`darrenintr/codex-auto-router`](https://github.com/darrenintr/codex-auto-router).

## Goal

Instead of this on every route:

```text
Task -> Luna Low -> explore repo -> read several files -> choose tier
```

use a persistent incremental map:

```text
Git + manifests + symbols + imports
              |
              v
      local incremental index
              |
Task ----------+----> compact context (fixed budget)
                        |
                        v
                     Luna Low
                        |
                        v
                 choose Codex tier
```

The index lives under `.git/codex-repo-map/`, so it does not pollute the project tree or need to be committed.

## Planned CLI

```bash
codex-repo-map init .
codex-repo-map update
codex-repo-map stats
codex-repo-map context --task "fix fullscreen to inline player flicker" --budget 3000 --json
```

The `context` command is the stable integration surface for `codex-auto-router`.

## Design principles

- **Local first:** repository source stays local.
- **Incremental:** unchanged files are not reparsed.
- **Deterministic before AI:** Git metadata, manifests, symbols, imports and dependency signals cost no model tokens.
- **Task-specific retrieval:** return only the files and symbols relevant to the current task.
- **Hard context budget:** output is constrained to an estimated token budget.
- **Source remains truth:** summaries and structural hints never replace source inspection when confidence is low.
- **Router agnostic:** usable by Codex Auto Router and other coding agents.

## Status

Early development. The initial MVP will support Python, Dart/Flutter, TypeScript/JavaScript, Rust, Java and Kotlin, with a stable JSON schema for router integration.

## License

MIT.
