"""Display-less smoke test for the Tkinter UI in gime.py.

Real tkinter needs a display (and this WSL box has none), so this installs a
stub that keeps just enough widget state to drive the real App code paths
against real git repositories.

Run with:  python -m unittest -v test_gime_ui
"""

from __future__ import annotations

import os
import queue
import shutil
import sys
import tempfile
import time
import types
import unittest
from pathlib import Path

import gime_core as core


# --------------------------------------------------------------------------- #
# Stub tkinter
# --------------------------------------------------------------------------- #
class _Widget:
    """Permissive widget: unknown methods are absorbed and return None."""

    #: Class-level default so a subclass that skips ``__init__`` still reads it.
    hidden = False

    def __init__(self, *args, **kwargs) -> None:
        pass

    def grid(self, *args, **kwargs):
        self.hidden = False

    def grid_remove(self, *args, **kwargs):
        self.hidden = True

    def grid_forget(self, *args, **kwargs):
        self.hidden = True

    def __getattr__(self, name):
        def absorb(*_args, **_kwargs):
            return None

        return absorb


class _Window:
    """Strict window base — deliberately has no permissive __getattr__.

    A widget the layout forgot to build therefore raises AttributeError
    instead of silently passing.
    """

    def __init__(self, *args, **kwargs) -> None:
        self._title = ""
        self._geometry = ""
        self.attributes: dict = {}

    def title(self, value=None):
        if value is None:
            return self._title
        self._title = value

    def geometry(self, value=None):
        if value is None:
            return self._geometry
        self._geometry = value

    def minsize(self, *_args):
        pass

    def resizable(self, *_args):
        pass

    def protocol(self, *_args):
        pass

    def config(self, **kwargs):
        self.attributes.update(kwargs)

    configure = config

    def bind(self, *_args, **_kwargs):
        pass

    def columnconfigure(self, *_args, **_kwargs):
        pass

    def rowconfigure(self, *_args, **_kwargs):
        pass

    def grid_propagate(self, *_args):
        pass

    def iconphoto(self, *_args, **_kwargs):
        pass

    def iconbitmap(self, *_args, **_kwargs):
        pass

    def after(self, _ms, _callback=None):
        # Never schedule: the real one would loop forever here.
        return None

    def grab_set(self):
        pass

    def grab_release(self):
        pass

    def transient(self, *_args):
        pass

    def focus_force(self):
        pass

    def wait_window(self, _other):
        pass

    def destroy(self):
        pass

    def mainloop(self, *_args):
        pass


class _Var:
    def __init__(self, master=None, value=None, name=None):
        self._value = value

    def get(self):
        return self._value

    def set(self, value):
        self._value = value

    def trace_add(self, *_args):
        pass


class _Label(_Widget):
    def __init__(self, *args, **kwargs):
        self._value = kwargs.get("text", "")

    def configure(self, **kwargs):
        if "text" in kwargs:
            self._value = kwargs["text"]

    config = configure


class _Button(_Widget):
    def __init__(self, *args, **kwargs):
        self.text = kwargs.get("text", "")
        self.state = kwargs.get("state", "normal")

    def configure(self, **kwargs):
        if "text" in kwargs:
            self.text = kwargs["text"]
        if "state" in kwargs:
            self.state = kwargs["state"]

    config = configure


class _Entry(_Widget):
    def __init__(self, *args, **kwargs):
        self._text = ""

    def delete(self, _first, _last=None):
        self._text = ""

    def insert(self, _index, value):
        self._text += str(value)

    def get(self):
        return self._text


class _Listbox(_Widget):
    def __init__(self, *args, **kwargs):
        self.items: list[str] = []
        self.selection: tuple = ()

    def delete(self, *_args):
        self.items.clear()

    def insert(self, _index, value):
        self.items.append(value)

    def selection_set(self, index):
        self.selection = (index,)

    def selection_clear(self, *_args):
        self.selection = ()

    def curselection(self):
        return self.selection


class _Text(_Widget):
    def __init__(self, *args, **kwargs):
        self.content = ""
        self.tags: list[str] = []

    def insert(self, _index, value, tag=None):
        self.content += str(value)
        if tag:
            self.tags.append(tag)

    def delete(self, *_args):
        self.content = ""

    def see(self, *_args):
        pass

    def tag_configure(self, *_args, **_kwargs):
        pass


class _Treeview(_Widget):
    def __init__(self, *args, **kwargs):
        self.rows: list = []

    def get_children(self):
        return tuple(range(len(self.rows)))

    def insert(self, _parent, _index, values=None, **_kwargs):
        self.rows.append(values)
        return f"item{len(self.rows)}"

    def delete(self, *_args):
        self.rows.clear()


class _Menu(_Widget):
    def __init__(self, *args, **kwargs):
        self.entries: list = []

    def add_command(self, **kwargs):
        self.entries.append(("command", kwargs.get("label")))

    def add_checkbutton(self, **kwargs):
        self.entries.append(("checkbutton", kwargs.get("label")))

    def add_cascade(self, **kwargs):
        self.entries.append(("cascade", kwargs.get("label")))

    def add_separator(self, **kwargs):
        self.entries.append(("separator", None))

    def delete(self, *_args):
        self.entries.clear()


class _Style:
    """Absorbs every ttk style call; remembers the active theme name."""

    def __init__(self, master=None):
        self._theme = None

    def theme_use(self, name=None):
        if name:
            self._theme = name
        return self._theme

    def configure(self, *_args, **_kwargs):
        pass

    def map(self, *_args, **_kwargs):
        pass


class _PhotoImage:
    def __init__(self, *args, **kwargs):
        self.file = kwargs.get("file")


def _record_into(calls, name, default=None):
    def fn(*args, **kwargs):
        calls.append((name, args, kwargs))
        return default

    return fn


def _build_stub() -> types.ModuleType:
    tk = types.ModuleType("tkinter")
    tk.Tk = type("Tk", (_Window,), {})
    tk.Toplevel = type("Toplevel", (_Window,), {})
    tk.Listbox = _Listbox
    tk.Text = _Text
    tk.Menu = _Menu
    tk.StringVar = _Var
    tk.BooleanVar = _Var
    tk.PhotoImage = _PhotoImage
    tk.TclError = type("TclError", (Exception,), {})
    tk.END = "end"
    tk.INSERT = "insert"

    ttk = types.ModuleType("tkinter.ttk")
    for name in ("Frame", "LabelFrame", "Scrollbar", "Checkbutton",
                 "Menubutton"):
        setattr(ttk, name, type(name, (_Widget,), {}))
    ttk.Label = _Label
    ttk.Button = _Button
    ttk.Entry = _Entry
    ttk.Treeview = _Treeview
    ttk.Style = _Style

    filedialog = types.ModuleType("tkinter.filedialog")
    filedialog.askdirectory = lambda **_k: ""

    calls: list = []

    messagebox = types.ModuleType("tkinter.messagebox")
    messagebox.showwarning = _record_into(calls, "showwarning")
    messagebox.showinfo = _record_into(calls, "showinfo")
    messagebox.showerror = _record_into(calls, "showerror")
    messagebox.askyesno = _record_into(calls, "askyesno", True)

    simpledialog = types.ModuleType("tkinter.simpledialog")
    simpledialog.askstring = lambda *_a, **k: k.get("initialvalue", "")

    tk.ttk = ttk
    tk.filedialog = filedialog
    tk.messagebox = messagebox
    tk.simpledialog = simpledialog
    tk.dialog_calls = calls

    for name, module in (("tkinter", tk), ("tkinter.ttk", ttk),
                         ("tkinter.filedialog", filedialog),
                         ("tkinter.messagebox", messagebox),
                         ("tkinter.simpledialog", simpledialog)):
        sys.modules[name] = module
    return tk


STUB_TK = _build_stub()

import gime  # noqa: E402  (must come after the stub is installed)


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #
def drain(app, timeout: float = 60.0) -> None:
    """Do what _poll_queue does, once, without rescheduling."""
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            item = app._queue.get(timeout=0.1)
        except queue.Empty:
            continue
        if item[0] == "line":
            app._append_log(item[1], item[2])
        elif item[0] == "done":
            app.busy = False
            app._set_busy(False)
            if app._pending_fetch:
                app._pending_fetch = False
                app.refresh(fetch=True)
            else:
                app.refresh(fetch=False)
            return
    raise TimeoutError("background git worker never finished")


class UITestCase(unittest.TestCase):
    def setUp(self) -> None:
        self.root = Path(tempfile.mkdtemp(prefix="gime-ui-"))
        self.addCleanup(shutil.rmtree, self.root, ignore_errors=True)

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

        # Keep the app away from the real gime.json.
        self.saved_config = gime.CONFIG_PATH
        gime.CONFIG_PATH = self.root / "gime.json"
        self.addCleanup(setattr, gime, "CONFIG_PATH", self.saved_config)

        self.app = gime.App()
        self.addCleanup(self.app.destroy)

    def repo(self, name: str = "savegame") -> Path:
        path = self.root / name
        path.mkdir(parents=True, exist_ok=True)
        core.git(path, "init")
        return path

    def add_game(self, repo: Path, name: str = "Elden Ring",
                 pattern: str = "") -> core.Game:
        game = self.app.store.add(name, str(repo), pattern)
        self.app._select_game(game)
        self.settle()
        return game

    def settle(self) -> None:
        """Let any background fetch/commit/pull finish and render its result."""
        while self.app.busy:
            drain(self.app)

    def run_action(self, method) -> None:
        method()
        self.settle()

    def log_text(self) -> str:
        return self.app.log.content


# --------------------------------------------------------------------------- #
class ConstructionTests(UITestCase):
    def test_window_builds_from_scratch(self) -> None:
        self.assertEqual(self.app.title(), "Gime — game save backup")
        self.assertEqual(self.app.games_list.items, [])
        self.assertEqual(self.app.info, core.RepoInfo())
        self.assertIsNotNone(self.app.message_entry)
        self.assertIsNotNone(self.app.tree)

    def test_games_menu_starts_with_placeholder(self) -> None:
        labels = [label for _kind, label in self.app.games_menu.entries]
        self.assertIn("(no games yet)", labels)
        self.assertIn("Add game…", labels)

    def test_git_is_available(self) -> None:
        self.assertIsNotNone(core.which_git())


class SelectionTests(UITestCase):
    def test_selecting_a_non_repo_game(self) -> None:
        plain = self.root / "plain"
        plain.mkdir()
        self.add_game(plain, "Elden Ring")

        self.assertEqual(self.app.title_label._value, "Elden Ring")
        self.assertEqual(self.app.path_label._value, str(plain))
        self.assertEqual(self.app.val_state._value, "no repository")
        self.assertFalse(self.app.init_btn.hidden)   # offered, repo is missing
        self.assertTrue(self.app.remote_btn.hidden)  # pointless until then
        self.assertIn("Not a Git repository", self.app.changes_summary._value)
        self.assertIn("Elden Ring", self.app.message_entry.get())

    def test_selecting_a_repo_shows_mine_and_uploaded(self) -> None:
        repo = self.repo()
        (repo / "save00.dat").write_text("v1", encoding="utf-8")
        core.commit_all(repo, "first save")
        self.add_game(repo, "Elden Ring", "{game} @ {branch}")

        self.assertTrue(self.app.info.is_repo)
        combined = self.app.val_local._value + self.app.sub_local._value
        self.assertIn("first save", combined)

        # No remote yet, so the uploaded side stays empty.
        self.assertEqual(self.app.val_remote._value, "—")
        self.assertIn("no remote", self.app.val_state._value)
        self.assertEqual(self.app.init_btn.hidden, True)
        self.assertEqual(self.app.remote_btn.hidden, False)
        self.assertEqual(self.app.message_entry.get(),
                         f"Elden Ring @ {self.app.info.branch}")

    def test_menu_picker_selects_a_game(self) -> None:
        self.app.store.add("Game A", str(self.repo("a")))
        self.app.store.add("Game B", str(self.repo("b")))
        self.app._reload_game_list()
        self.assertEqual(self.app.games_list.items, ["Game A", "Game B"])

        self.app.games_list.selection = (1,)
        self.app._on_list_select()
        self.assertEqual(self.app.current.name, "Game B")

    def test_last_picked_game_is_remembered(self) -> None:
        self.app.store.add("Game A", str(self.repo("a")))
        self.app.store.add("Game B", str(self.repo("b")))
        self.app._select_game(self.app.store.games[1])

        reopened = gime.App()
        self.addCleanup(reopened.destroy)
        self.assertEqual(reopened.current.name, "Game B")

    def test_switching_game_mid_fetch_catches_up(self) -> None:
        """Selecting another game while git runs must not lose the sync."""
        origin = self.root / "origin.git"
        core.git(self.root, "init", "--bare", str(origin))
        repo_a, repo_b = self.repo("a"), self.repo("b")
        core.set_remote(repo_a, str(origin))
        core.set_remote(repo_b, str(origin))
        self.app.store.add("Game A", str(repo_a))
        self.app.store.add("Game B", str(repo_b))

        self.app._select_game(self.app.store.games[0])
        self.assertTrue(self.app.busy)          # fetch in flight

        self.app._select_game(self.app.store.games[1])
        self.assertEqual(self.app.current.name, "Game B")
        self.assertTrue(self.app._pending_fetch)

        self.settle()
        self.assertFalse(self.app._pending_fetch)
        self.assertFalse(self.app.busy)

    def test_remove_game_deletes_only_the_entry(self) -> None:
        repo = self.repo("kept")
        self.add_game(repo, "Kept")
        self.app.store.add("Doomed", str(self.root / "missing"))
        self.app._reload_game_list()

        self.app.current = self.app.store.games[1]
        self.app.remove_game()
        self.assertEqual([g.name for g in self.app.store.games], ["Kept"])
        self.assertTrue(repo.exists())


class MessageTests(UITestCase):
    def test_pattern_is_filled_in_on_selection(self) -> None:
        repo = self.repo()
        self.add_game(repo, "Hades", "{game} {count} {branch}")
        self.assertEqual(self.app.message_entry.get(),
                         f"Hades 0 {self.app.info.branch}")

    def test_edited_message_is_not_clobbered_by_refresh(self) -> None:
        repo = self.repo()
        self.add_game(repo, "Hades", "{game}")
        self.app.message_entry.delete(0, "end")
        self.app.message_entry.insert(0, "hand written")
        self.app._on_message_typed(None)

        self.app.refresh(fetch=False)
        self.assertEqual(self.app.message_entry.get(), "hand written")

        self.app.regenerate_message()
        self.assertEqual(self.app.message_entry.get(), "Hades")

    def test_regenerate_counts_changes(self) -> None:
        repo = self.repo()
        self.add_game(repo, "Hades", "{count} file(s)")
        (repo / "save.dat").write_text("x", encoding="utf-8")
        (repo / "save2.dat").write_text("x", encoding="utf-8")
        self.app.refresh(fetch=False)
        self.assertEqual(self.app.message_entry.get(), "2 file(s)")


class ActionTests(UITestCase):
    def test_init_repo_creates_git(self) -> None:
        plain = self.root / "fresh"
        plain.mkdir()
        self.add_game(plain, "Fresh")
        self.assertFalse(self.app.info.is_repo)

        self.run_action(self.app.init_repo)

        self.assertTrue((plain / ".git").exists())
        self.assertTrue(self.app.info.is_repo)
        self.assertIn("Initialized", self.log_text())

    def test_commit_stages_and_clears_changes(self) -> None:
        repo = self.repo()
        self.add_game(repo, "Elden Ring", "{game} backup")
        (repo / "save00.dat").write_text("v1", encoding="utf-8")
        self.app.refresh(fetch=False)
        self.assertEqual(len(self.app.info.changes), 1)

        self.run_action(self.app.commit)

        info = core.read_repo(repo)
        self.assertTrue(info.has_commits)
        self.assertEqual(info.local.subject, "Elden Ring backup")
        self.assertEqual(info.changes, [])
        self.assertEqual(self.app.tree.rows, [])
        self.assertIn("clean", self.app.changes_summary._value)

    def test_commit_with_nothing_staged(self) -> None:
        repo = self.repo()
        self.add_game(repo, "Elden Ring")
        self.run_action(self.app.commit)
        self.assertIn("Nothing to commit", self.log_text())

    def test_push_without_remote_reports_it(self) -> None:
        repo = self.repo()
        self.add_game(repo, "Elden Ring")
        (repo / "save.dat").write_text("v1", encoding="utf-8")
        self.app.refresh(fetch=False)

        self.run_action(self.app.push)

        self.assertIn("No remote configured", self.log_text())
        self.assertIn("Push failed.", self.log_text())

    def test_pull_without_remote_reports_it(self) -> None:
        repo = self.repo()
        self.add_game(repo, "Elden Ring")
        self.run_action(self.app.pull)
        self.assertIn("No remote configured", self.log_text())

    def test_commit_before_push_can_be_turned_off(self) -> None:
        self.assertTrue(self.app.store.auto_commit)
        self.app.auto_commit.set(False)
        self.app._save_auto_commit()
        self.assertFalse(gime.core.Store(gime.CONFIG_PATH).auto_commit)

    def test_push_pull_roundtrip_between_two_machines(self) -> None:
        origin = self.root / "origin.git"
        core.git(self.root, "init", "--bare", str(origin))

        writer = self.repo("writer")
        core.set_remote(writer, str(origin))
        writer_game = self.add_game(writer, "Writer", "commit {count}")
        (writer / "save.dat").write_text("v1", encoding="utf-8")
        self.app.refresh(fetch=False)

        # "Commit before push" is on by default, so this commits then pushes.
        self.run_action(self.app.push)
        self.assertIn("Push finished.", self.log_text())
        self.assertIn("in sync", self.app.val_state._value)

        # Another machine clones the same saves and pushes an update.
        reader = self.root / "reader"
        core.git(self.root, "clone", str(origin), str(reader))
        (reader / "save.dat").write_text("v2", encoding="utf-8")
        core.commit_all(reader, "second save")
        core.git(reader, "push")

        self.add_game(reader, "Reader")
        self.assertIn("in sync", self.app.val_state._value)

        # Back on the first machine the update must arrive via Pull.
        self.app._select_game(writer_game)
        self.settle()
        self.run_action(self.app.pull)

        self.assertIn("Pull finished.", self.log_text())
        self.assertEqual((writer / "save.dat").read_text(encoding="utf-8"),
                         "v2")
        self.assertIn("in sync", self.app.val_state._value)


class ThemeTests(UITestCase):
    def test_starts_light_by_default(self) -> None:
        self.assertEqual(self.app.store.theme, "light")
        self.assertEqual(self.app.C["name"], "light")
        self.assertFalse(self.app.dark_var.get())
        self.assertEqual(self.app.theme_btn.text, "Switch to dark mode")

    def test_menu_offers_dark_mode(self) -> None:
        self.assertIn(("checkbutton", "Dark mode"), self.app.view_menu.entries)
        self.assertIn(("cascade", "View"), self.app._menubar.entries)

    def test_toggling_from_the_menu(self) -> None:
        self.app.dark_var.set(True)
        self.app.toggle_theme()

        self.assertEqual(self.app.store.theme, "dark")
        self.assertEqual(self.app.C["name"], "dark")
        self.assertEqual(self.app.theme_btn.text, "Switch to light mode")
        self.assertEqual(self.app.style._theme, "clam")

        self.app.dark_var.set(False)
        self.app.toggle_theme()
        self.assertEqual(self.app.store.theme, "light")
        self.assertEqual(self.app.C["name"], "light")

    def test_status_bar_button_switches_theme(self) -> None:
        self.app._theme_button_clicked()
        self.assertEqual(self.app.store.theme, "dark")
        self.assertTrue(self.app.dark_var.get())
        self.app._theme_button_clicked()
        self.assertEqual(self.app.store.theme, "light")

    def test_theme_survives_a_restart(self) -> None:
        self.app.store.theme = "dark"
        self.app.store.save()

        reopened = gime.App()
        self.addCleanup(reopened.destroy)
        self.assertEqual(reopened.store.theme, "dark")
        self.assertEqual(reopened.C["name"], "dark")
        self.assertTrue(reopened.dark_var.get())

    def test_unknown_theme_falls_back_to_light(self) -> None:
        gime.CONFIG_PATH.write_text(
            '{"theme": "neon", "games": []}', encoding="utf-8")
        self.assertEqual(gime.core.Store(gime.CONFIG_PATH).theme, "light")

    def test_theme_change_keeps_rendering_the_repo(self) -> None:
        repo = self.repo()
        (repo / "save.dat").write_text("v1", encoding="utf-8")
        core.commit_all(repo, "first save")
        self.add_game(repo, "Elden Ring")

        self.app._theme_button_clicked()
        self.assertEqual(self.app.C["name"], "dark")
        self.assertTrue(self.app.info.is_repo)
        self.assertEqual(self.app.sub_local._value, "first save")


class StatusBarTests(UITestCase):
    def test_shows_git_version(self) -> None:
        self.assertIn("git version", self.app.status_git._value)

    def test_shows_game_count(self) -> None:
        self.assertEqual(self.app.status_games._value, "No games yet")
        self.app.store.add("Elden Ring", str(self.repo("a")))
        self.app.store.add("Hades", str(self.repo("b")))
        self.app._reload_game_list()
        self.assertEqual(self.app.status_games._value, "2 games")

    def test_shows_singular_for_one_game(self) -> None:
        self.app.store.add("Elden Ring", str(self.repo("a")))
        self.app._reload_game_list()
        self.assertEqual(self.app.status_games._value, "1 game")

    def test_icon_is_applied_to_the_window(self) -> None:
        self.assertTrue((gime.ICON_DIR / "gime.png").exists())
        self.assertTrue((gime.ICON_DIR / "gime.ico").exists())
        self.assertTrue(hasattr(self.app, "_gime_icon"))
        self.assertTrue(str(self.app._gime_icon.file).endswith("gime.png"))


class StateTextTests(unittest.TestCase):
    def info(self, **kwargs) -> core.RepoInfo:
        base = dict(path=".", exists=True, is_repo=True, has_commits=True,
                    branch="main", origin="git@example.com:x/y.git",
                    tracking="origin/main",
                    local=core.CommitInfo(hash="a" * 40, short="aaaaaaa",
                                          subject="mine",
                                          date="2026-10-06 14:00"),
                    remote=core.CommitInfo(hash="b" * 40, short="bbbbbbb",
                                           subject="uploaded",
                                           date="2026-10-06 13:00"))
        base.update(kwargs)
        return core.RepoInfo(**base)

    def test_in_sync(self) -> None:
        self.assertIn("in sync", gime.App._state_text(self.info()))

    def test_ahead(self) -> None:
        self.assertIn("mine is 3 ahead",
                      gime.App._state_text(self.info(ahead=3)))

    def test_behind(self) -> None:
        self.assertIn("uploaded is 2 ahead",
                      gime.App._state_text(self.info(behind=2)))

    def test_diverged(self) -> None:
        text = gime.App._state_text(self.info(ahead=1, behind=4))
        self.assertIn("diverged", text)
        self.assertIn("mine is 1 ahead", text)
        self.assertIn("uploaded is 4 ahead", text)

    def test_no_commits(self) -> None:
        self.assertEqual(gime.App._state_text(self.info(has_commits=False)),
                         "no commits yet")

    def test_upstream_not_fetched_yet_is_not_called_in_sync(self) -> None:
        text = gime.App._state_text(self.info(remote=None))
        self.assertNotIn("in sync", text)
        self.assertIn("not fetched", text)

    def test_no_remote(self) -> None:
        self.assertEqual(gime.App._state_text(self.info(origin="",
                                                        tracking="")),
                         "local only — no remote")

    def test_remote_but_no_upstream(self) -> None:
        self.assertIn("no upstream",
                      gime.App._state_text(self.info(tracking="")))

    def test_colors_are_palette_keys_not_literals(self) -> None:
        self.assertEqual(gime.App._state_color(self.info()), "success")
        self.assertEqual(gime.App._state_color(self.info(behind=2)), "danger")
        self.assertEqual(gime.App._state_color(self.info(ahead=2)), "warning")
        self.assertEqual(
            gime.App._state_color(core.RepoInfo(is_repo=False)), "warning")


class DialogTests(UITestCase):
    def test_add_dialog_builds_a_game(self) -> None:
        folder = self.root / "elden"
        folder.mkdir()

        dialog = gime.GameDialog(self.app, "Add game", None, "{game} {count}")
        dialog.name_var.set("Elden Ring")
        dialog.path_var.set(str(folder))
        dialog.pattern_var.set("{datetime} {game}")
        dialog._ok()

        self.assertEqual(dialog.result,
                         {"name": "Elden Ring", "path": str(folder),
                          "pattern": "{datetime} {game}"})

    def test_add_dialog_refuses_empty_name(self) -> None:
        dialog = gime.GameDialog(self.app, "Add game", None, "{game}")
        dialog.path_var.set(str(self.root))
        dialog.name_var.set("   ")
        dialog._ok()
        self.assertIsNone(dialog.result)
        self.assertIn("showwarning",
                      [name for name, _a, _k in STUB_TK.dialog_calls])

    def test_add_dialog_creates_missing_folder(self) -> None:
        target = self.root / "new-folder"
        dialog = gime.GameDialog(self.app, "Add game", None, "{game}")
        dialog.name_var.set("Brand New")
        dialog.path_var.set(str(target))
        dialog._ok()
        self.assertTrue(target.is_dir())
        self.assertIsNotNone(dialog.result)

    def test_token_button_inserts_placeholder(self) -> None:
        dialog = gime.GameDialog(self.app, "Add game", None, "{game}")
        dialog.pattern_entry.delete(0, "end")
        dialog._insert_token("{datetime}")
        self.assertEqual(dialog.pattern_entry.get(), "{datetime}")
        dialog.destroy()


if __name__ == "__main__":
    unittest.main(verbosity=2)
