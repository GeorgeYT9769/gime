"""Tests for gime_core — run with:  python -m unittest -v test_gime_core"""

from __future__ import annotations

import os
import shutil
import tempfile
import unittest
from datetime import datetime
from pathlib import Path

import gime_core as core


class TempDirCase(unittest.TestCase):
    """Every test gets a scratch folder that is removed afterwards."""

    def setUp(self) -> None:
        self.root = Path(tempfile.mkdtemp(prefix="gime-test-"))
        self.addCleanup(shutil.rmtree, self.root, ignore_errors=True)

        # Give git an identity without touching the real global config.
        saved = {k: os.environ.get(k) for k in (
            "GIT_AUTHOR_NAME", "GIT_AUTHOR_EMAIL",
            "GIT_COMMITTER_NAME", "GIT_COMMITTER_EMAIL")}
        os.environ.update({
            "GIT_AUTHOR_NAME": "Gime Test",
            "GIT_AUTHOR_EMAIL": "gime@example.com",
            "GIT_COMMITTER_NAME": "Gime Test",
            "GIT_COMMITTER_EMAIL": "gime@example.com",
        })

        def restore() -> None:
            for key, value in saved.items():
                if value is None:
                    os.environ.pop(key, None)
                else:
                    os.environ[key] = value

        self.addCleanup(restore)

    def repo(self, name: str = "save") -> Path:
        path = self.root / name
        path.mkdir(parents=True, exist_ok=True)
        core.git(path, "init")
        return path

    def bare_origin(self, name: str = "origin.git") -> Path:
        path = self.root / name
        core.git(self.root, "init", "--bare", str(path))
        return path

    def write(self, repo: Path, name: str, text: str) -> Path:
        target = repo / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(text, encoding="utf-8")
        return target


# --------------------------------------------------------------------------- #
# Store (remembers the picked games)
# --------------------------------------------------------------------------- #
class StoreTests(TempDirCase):
    def test_theme_defaults_to_light(self) -> None:
        self.assertEqual(core.Store(self.root / "gime.json").theme, "light")

    def test_theme_round_trips_through_the_config_file(self) -> None:
        path = self.root / "gime.json"
        store = core.Store(path)
        store.theme = "dark"
        store.save()
        self.assertEqual(core.Store(path).theme, "dark")

        # Older config files simply have no theme key.
        path.write_text('{"games": []}', encoding="utf-8")
        self.assertEqual(core.Store(path).theme, "light")

    def test_unknown_theme_falls_back_to_light(self) -> None:
        path = self.root / "gime.json"
        path.write_text('{"theme": "neon"}', encoding="utf-8")
        self.assertEqual(core.Store(path).theme, "light")

    def test_starts_empty(self) -> None:
        store = core.Store(self.root / "gime.json")
        self.assertEqual(store.games, [])
        self.assertEqual(store.last_id, "")

    def test_remembered_across_restarts(self) -> None:
        path = self.root / "gime.json"
        store = core.Store(path)
        store.add("Elden Ring", str(self.root / "er"), "{datetime} {game}")
        store.add("Hades", str(self.root / "hades"))
        store.last_id = store.games[1].id
        store.save()

        reopened = core.Store(path)
        self.assertEqual([g.name for g in reopened.games], ["Elden Ring", "Hades"])
        self.assertEqual(reopened.games[0].pattern, "{datetime} {game}")
        self.assertEqual(reopened.last_id, store.games[1].id)

    def test_remove_keeps_other_games(self) -> None:
        path = self.root / "gime.json"
        store = core.Store(path)
        a = store.add("A", str(self.root / "a"))
        store.add("B", str(self.root / "b"))
        store.last_id = a.id
        store.save()

        store.remove(a.id)
        self.assertEqual([g.name for g in core.Store(path).games], ["B"])

    def test_update_persists(self) -> None:
        path = self.root / "gime.json"
        store = core.Store(path)
        game = store.add("Old", str(self.root / "old"))
        store.update(game, name="New", path=str(self.root / "new"), pattern="x")
        reopened = core.Store(path)
        self.assertEqual(reopened.games[0].name, "New")
        self.assertEqual(reopened.games[0].path, str(self.root / "new"))

    def test_corrupt_config_does_not_crash(self) -> None:
        path = self.root / "gime.json"
        path.write_text("{ not json", encoding="utf-8")
        store = core.Store(path)
        self.assertEqual(store.games, [])

    def test_entries_without_name_or_path_are_skipped(self) -> None:
        path = self.root / "gime.json"
        path.write_text('{"games": [{"name": "", "path": "/x"}, '
                        '{"name": "ok", "path": "/y"}]}', encoding="utf-8")
        self.assertEqual([g.name for g in core.Store(path).games], ["ok"])


# --------------------------------------------------------------------------- #
# Commit message patterns
# --------------------------------------------------------------------------- #
class PatternTests(unittest.TestCase):
    def values(self) -> dict:
        return {
            "datetime": datetime(2026, 10, 6, 14, 32, 5),
            "date": datetime(2026, 10, 6, 14, 32, 5),
            "time": datetime(2026, 10, 6, 14, 32, 5),
            "game": "Elden Ring",
            "count": 3,
            "files": "save00.dat, save01.dat (+1 more)",
            "branch": "main",
            "host": "DESKTOP-1",
            "user": "juraj",
            "path": "D:/Games/ER",
        }

    def test_datetime_and_text(self) -> None:
        out = core.render_pattern("{datetime}: {game} ({count})", self.values())
        self.assertEqual(out, "2026-10-06 14:32:05: Elden Ring (3)")

    def test_format_specifiers(self) -> None:
        self.assertEqual(core.render_pattern("{datetime:%Y%m%d-%H%M%S}",
                                             self.values()),
                         "20261006-143205")
        self.assertEqual(core.render_pattern("{date:%d.%m.%Y}", self.values()),
                         "06.10.2026")
        self.assertEqual(core.render_pattern("{count:03d}", self.values()), "003")

    def test_unknown_token_left_alone(self) -> None:
        self.assertEqual(core.render_pattern("{nope} {game}", self.values()),
                         "{nope} Elden Ring")

    def test_literal_braces_survive(self) -> None:
        self.assertEqual(core.render_pattern("keep { } {game}", self.values()),
                         "keep { } Elden Ring")

    def test_build_uses_game_pattern_then_default(self) -> None:
        game = core.Game.new("Elden Ring", "/tmp/er")
        info = core.RepoInfo(branch="main")

        self.assertEqual(
            core.build_commit_message(game, info, "{game} on {branch}"),
            "Elden Ring on main")

        game.pattern = "custom {count}"
        self.assertEqual(core.build_commit_message(game, info, "{game}"),
                         "custom 0")


# --------------------------------------------------------------------------- #
# Repo inspection (.git detection, versions)
# --------------------------------------------------------------------------- #
class RepoInfoTests(TempDirCase):
    def test_missing_folder_reports_error(self) -> None:
        info = core.read_repo(self.root / "nope")
        self.assertFalse(info.exists)
        self.assertFalse(info.is_repo)
        self.assertIn("not found", info.error.lower())

    def test_plain_folder_is_not_a_repo(self) -> None:
        plain = self.root / "plain"
        plain.mkdir()
        info = core.read_repo(plain)
        self.assertTrue(info.exists)
        self.assertFalse(info.is_repo)
        self.assertEqual(info.error, "")

    def test_git_detection_after_init(self) -> None:
        repo = self.repo()
        info = core.read_repo(repo)
        self.assertTrue(info.is_repo)
        self.assertFalse(info.has_commits)
        self.assertIsNone(info.local)
        self.assertEqual(info.changes, [])

    def test_commit_is_reported_as_mine(self) -> None:
        repo = self.repo()
        self.write(repo, "save00.dat", "v1")
        core.commit_all(repo, "first save")

        info = core.read_repo(repo)
        self.assertTrue(info.has_commits)
        self.assertEqual(info.local.subject, "first save")
        self.assertEqual(len(info.local.hash), 40)
        self.assertEqual(info.changes, [])
        self.assertEqual(info.branch, core._clean(
            core.git(repo, "symbolic-ref", "--short", "HEAD")[1]))

    def test_uncommitted_changes_are_listed(self) -> None:
        repo = self.repo()
        self.write(repo, "save00.dat", "v1")
        core.commit_all(repo, "first save")

        self.write(repo, "save00.dat", "v2")   # modified
        self.write(repo, "notes.cfg", "x")      # untracked
        (repo / "save00.dat").unlink()          # then re-add below for delete

        info = core.read_repo(repo)
        codes = {c.path: c.code for c in info.changes}
        self.assertIn("notes.cfg", codes)
        self.assertEqual(core.describe_status(codes["notes.cfg"]), "untracked")
        self.assertEqual(codes["save00.dat"], " D")
        self.assertEqual(core.describe_status(codes["save00.dat"]), "deleted")

    def test_real_rename_is_parsed(self) -> None:
        """Guards the -z rename field order against a real git repo."""
        repo = self.repo()
        self.write(repo, "old.dat", "v1")
        core.commit_all(repo, "first")
        code, _, err = core.git(repo, "mv", "old.dat", "new.dat")
        self.assertEqual(code, 0, err)

        changes = core.read_repo(repo).changes
        self.assertEqual(len(changes), 1)
        self.assertIn("R", changes[0].code)
        self.assertEqual(changes[0].path, "new.dat")
        self.assertEqual(changes[0].old_path, "old.dat")
        self.assertEqual(core.describe_status(changes[0].code), "renamed")

    def test_no_remote_until_configured(self) -> None:
        repo = self.repo()
        info = core.read_repo(repo)
        self.assertFalse(info.has_remote)
        self.assertFalse(info.in_sync)

    def test_origin_reported_once_set(self) -> None:
        origin = self.bare_origin()
        repo = self.repo()
        core.set_remote(repo, str(origin))
        self.assertEqual(core.read_repo(repo).origin, str(origin))


# --------------------------------------------------------------------------- #
# commit / push / pull
# --------------------------------------------------------------------------- #
class ActionsTests(TempDirCase):
    def test_commit_then_clean(self) -> None:
        repo = self.repo()
        self.write(repo, "save00.dat", "v1")
        code, _ = core.commit_all(repo, "first")
        self.assertEqual(code, 0)
        self.assertEqual(core.read_repo(repo).changes, [])

    def test_commit_with_nothing_staged(self) -> None:
        repo = self.repo()
        code, text = core.commit_all(repo, "nothing here")
        self.assertNotEqual(code, 0)
        self.assertIn("nothing to commit", text.lower())

    def test_commit_message_with_quotes_and_unicode(self) -> None:
        repo = self.repo()
        self.write(repo, "uložené.dat", "dátum")
        message = 'he said "save" — ćććžžž\nsecond line'
        code, _ = core.commit_all(repo, message)
        self.assertEqual(code, 0)
        # git's %s collapses the first paragraph onto one line; the stored
        # message keeps both lines.
        self.assertEqual(core.read_repo(repo).local.subject,
                         'he said "save" — ćććžžž second line')

    def test_push_needs_a_remote(self) -> None:
        repo = self.repo()
        self.write(repo, "a.txt", "1")
        core.commit_all(repo, "first")
        code, text = core.push(repo, core.read_repo(repo))
        self.assertEqual(code, 1)
        self.assertIn("No remote", text)

    def test_push_needs_commits(self) -> None:
        origin = self.bare_origin()
        repo = self.repo()
        core.set_remote(repo, str(origin))
        code, text = core.push(repo, core.read_repo(repo))
        self.assertEqual(code, 1)
        self.assertIn("no commits", text)

    def test_pull_needs_a_remote(self) -> None:
        repo = self.repo()
        code, text = core.pull(repo, core.read_repo(repo))
        self.assertEqual(code, 1)
        self.assertIn("No remote", text)

    def test_push_then_pull_roundtrip(self) -> None:
        origin = self.bare_origin()
        writer = self.repo("writer")
        core.set_remote(writer, str(origin))
        self.write(writer, "save00.dat", "v1")
        core.commit_all(writer, "first save")

        code, text = core.push(writer, core.read_repo(writer))
        self.assertEqual(code, 0, text)

        # A second machine clones the same saves.
        reader = self.root / "reader"
        code, out, err = core.git(self.root, "clone", str(origin), str(reader))
        self.assertEqual(code, 0, err)

        writer_info = core.read_repo(writer)
        self.assertTrue(writer_info.in_sync)
        self.assertEqual(writer_info.ahead, 0)
        self.assertEqual(writer_info.behind, 0)

        # Remote advances; local must see "uploaded is ahead" then catch up.
        self.write(reader, "save00.dat", "v2")
        core.commit_all(reader, "second save")
        core.git(reader, "push")

        # The remote-tracking ref only moves when we fetch.
        core.fetch(writer)
        before = core.read_repo(writer)
        self.assertEqual(before.behind, 1)
        self.assertEqual(before.ahead, 0)
        self.assertEqual(before.remote.subject, "second save")

        lines: list[str] = []
        code, text = core.pull(writer, before, lines.append)
        self.assertEqual(code, 0, text + "\n".join(lines))

        after = core.read_repo(writer)
        self.assertTrue(after.in_sync)
        self.assertEqual(after.local.subject, "second save")
        self.assertEqual((writer / "save00.dat").read_text(encoding="utf-8"),
                         "v2")

    def test_push_includes_new_commits_and_sets_upstream(self) -> None:
        origin = self.bare_origin()
        repo = self.repo()
        core.set_remote(repo, str(origin))
        self.write(repo, "a.txt", "1")
        code, _ = core.commit_all(repo, "first")

        info = core.read_repo(repo)
        self.assertEqual(info.tracking, "")  # not linked yet

        code, text = core.push(repo, info)
        self.assertEqual(code, 0, text)

        linked = core.read_repo(repo)
        self.assertTrue(linked.tracking)
        self.assertTrue(linked.in_sync)

        self.write(repo, "a.txt", "2")
        core.commit_all(repo, "second")
        code, text = core.push(repo, core.read_repo(repo))
        self.assertEqual(code, 0, text)
        self.assertTrue(core.read_repo(repo).in_sync)

    def test_pull_with_dirty_working_tree(self) -> None:
        """Autostash keeps uncommitted save files alive during a pull."""
        origin = self.bare_origin()
        writer = self.repo("writer")
        core.set_remote(writer, str(origin))
        self.write(writer, "save00.dat", "v1")
        core.commit_all(writer, "first save")
        core.push(writer, core.read_repo(writer))

        reader = self.root / "reader"
        core.git(self.root, "clone", str(origin), str(reader))
        self.write(reader, "save01.dat", "v2")
        core.commit_all(reader, "second")
        core.git(reader, "push")

        # Local edit that is not committed yet (game still running).
        self.write(writer, "save00.dat", "locally-edited")

        code, text = core.pull(writer, core.read_repo(writer))
        self.assertEqual(code, 0, text)
        self.assertEqual((writer / "save00.dat").read_text(encoding="utf-8"),
                         "locally-edited")
        self.assertTrue(core.read_repo(writer).in_sync)

    def test_fetch_updates_the_uploaded_version(self) -> None:
        origin = self.bare_origin()
        writer = self.repo("writer")
        core.set_remote(writer, str(origin))
        self.write(writer, "save00.dat", "v1")
        core.commit_all(writer, "first save")
        core.push(writer, core.read_repo(writer))

        reader = self.root / "reader"
        core.git(self.root, "clone", str(origin), str(reader))
        self.write(reader, "save00.dat", "v2")
        core.commit_all(reader, "second save")
        core.git(reader, "push")

        # Without fetching, the remote still looks unchanged.
        self.assertEqual(core.read_repo(writer).behind, 0)

        code, text = core.fetch(writer)
        self.assertEqual(code, 0, text)
        self.assertEqual(core.read_repo(writer).behind, 1)

    def test_fetch_without_remote_fails_cleanly(self) -> None:
        repo = self.repo()
        self.write(repo, "a.txt", "1")
        core.commit_all(repo, "first")
        code, text = core.fetch(repo)
        self.assertNotEqual(code, 0)
        self.assertTrue(text)

    def test_rebase_not_in_progress_normally(self) -> None:
        self.assertFalse(core.rebase_in_progress(self.repo()))


# --------------------------------------------------------------------------- #
# Porcelain parsing
# --------------------------------------------------------------------------- #
class GitVersionTests(TempDirCase):
    def test_reports_the_installed_version(self) -> None:
        version = core.git_version()
        if core.which_git() is None:
            self.assertEqual(version, "")
        else:
            self.assertTrue(version.startswith("git version"), version)

    def test_git_runs_without_a_working_directory(self) -> None:
        """git_version() passes cwd=None, which must not blow up."""
        if core.which_git() is None:
            self.skipTest("git not installed")
        code, out, _ = core.git(None, "--version")
        self.assertEqual(code, 0)
        self.assertIn("git version", out)


class StatusParsingTests(unittest.TestCase):
    def test_mixed_entries(self) -> None:
        # With -z a rename is "<XY> <new path>" NUL "<orig path>".
        raw = " M save00.dat\0?? notes.cfg\0R  new.dat\0old.dat\0A  added.dat\0"
        changes = core.parse_status_z(raw)
        self.assertEqual([(c.code, c.path, c.old_path) for c in changes],
                         [(" M", "save00.dat", ""),
                          ("??", "notes.cfg", ""),
                          ("R ", "new.dat", "old.dat"),
                          ("A ", "added.dat", "")])

    def test_leading_space_is_preserved(self) -> None:
        """A leading space means 'unchanged in the index' — never strip it."""
        self.assertEqual(core.parse_status_z(" M a.txt\0")[0].code, " M")

    def test_describe_status_words(self) -> None:
        cases = {
            "??": "untracked", "!!": "ignored", " M": "modified",
            "MM": "modified", "A ": "added", " D": "deleted",
            "R ": "renamed", "UU": "conflict", "T ": "type change",
        }
        for code, expected in cases.items():
            with self.subTest(code=code):
                self.assertEqual(core.describe_status(code), expected)

    def test_trailing_nul_is_ignored(self) -> None:
        self.assertEqual(len(core.parse_status_z(" M a.txt\0")), 1)
        self.assertEqual(len(core.parse_status_z("")), 0)


if __name__ == "__main__":
    unittest.main(verbosity=2)
