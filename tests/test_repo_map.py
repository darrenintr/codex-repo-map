from __future__ import annotations

import sqlite3
import subprocess
import tempfile
import unittest
from pathlib import Path

from codex_repo_map.indexer import db_path, update_index
from codex_repo_map.retrieval import build_context
from codex_repo_map.stats import read_stats
from codex_repo_map.summaries import cache_summary


class RepoFixture:
    def __init__(self, root: Path):
        self.root = root

    def git(self, *args: str) -> str:
        proc = subprocess.run(
            ["git", "-C", str(self.root), *args],
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=True,
        )
        return proc.stdout

    def write(self, path: str, content: str) -> None:
        target = self.root / path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8")


class RepoMapTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.repo = RepoFixture(self.root)
        self.repo.git("init", "-q")
        self.repo.git("config", "user.email", "tests@example.com")
        self.repo.git("config", "user.name", "Tests")
        self.repo.write(
            "pubspec.yaml",
            """name: sample_app\ndependencies:\n  flutter:\n    sdk: flutter\n  go_router: ^1.0.0\nflutter:\n  uses-material-design: true\n""",
        )
        self.repo.write(
            "lib/navigation/shared_transition.dart",
            """import '../player/inline_player.dart';\n\nclass SharedTransitionController {\n  void reverseTransition() {}\n}\n""",
        )
        self.repo.write(
            "lib/player/inline_player.dart",
            """class InlinePlayer {\n  void enterFullscreen() {}\n}\n""",
        )
        self.repo.write("README.md", "# Sample\n")
        self.repo.git("add", ".")
        self.repo.git("commit", "-qm", "initial")

    def tearDown(self) -> None:
        self.temp.cleanup()

    def test_index_lives_under_git_and_detects_flutter(self) -> None:
        result = update_index(self.root)
        self.assertGreaterEqual(result.updated, 4)
        db = db_path(self.root)
        self.assertTrue(db.is_file())
        self.assertTrue(str(db).startswith(str(self.root / ".git")))
        stats = read_stats(self.root)
        self.assertTrue(stats["indexed"])
        self.assertEqual(stats["project"]["type"], "flutter")
        self.assertGreaterEqual(stats["symbols"], 3)

    def test_context_finds_transition_file(self) -> None:
        update_index(self.root)
        context = build_context(
            self.root,
            "fix flicker when fullscreen player returns to inline player shared transition",
            budget=1400,
            refresh=False,
        )
        paths = [item["path"] for item in context["relevant"]["files"]]
        self.assertIn("lib/navigation/shared_transition.dart", paths[:3])
        self.assertIn("lib/player/inline_player.dart", paths[:4])
        symbols = {item["name"] for item in context["relevant"]["symbols"]}
        self.assertIn("SharedTransitionController", symbols)
        self.assertLessEqual(context["budget"]["estimated_tokens"], 1400)

    def test_changed_file_is_boosted(self) -> None:
        update_index(self.root)
        self.repo.write("lib/player/inline_player.dart", "class InlinePlayer { void returnHome() {} }\n")
        context = build_context(self.root, "fix return home animation", budget=1200, refresh=True)
        first = context["relevant"]["files"][0]
        self.assertEqual(first["path"], "lib/player/inline_player.dart")
        self.assertIn("changed-in-worktree", first["reasons"])

    def test_incremental_update_does_not_reparse_unchanged_files(self) -> None:
        first = update_index(self.root)
        second = update_index(self.root)
        self.assertGreater(first.updated, 0)
        self.assertEqual(second.updated, 0)
        self.assertGreaterEqual(second.unchanged, 4)

    def test_cached_summary_participates_in_retrieval_and_invalidates(self) -> None:
        update_index(self.root)
        cache_summary(
            self.root,
            "lib/navigation/shared_transition.dart",
            "Coordinates reverse hero animation between video card, inline player, and fullscreen player.",
        )
        context = build_context(self.root, "hero animation fullscreen", refresh=False, budget=1200)
        self.assertEqual(context["relevant"]["files"][0]["path"], "lib/navigation/shared_transition.dart")
        self.assertIsNotNone(context["relevant"]["files"][0]["summary"])

        self.repo.write(
            "lib/navigation/shared_transition.dart",
            "class SharedTransitionController { void completelyChanged() {} }\n",
        )
        update_index(self.root)
        conn = sqlite3.connect(db_path(self.root))
        try:
            count = conn.execute("SELECT COUNT(*) FROM summaries").fetchone()[0]
        finally:
            conn.close()
        self.assertEqual(count, 0)


if __name__ == "__main__":
    unittest.main()
