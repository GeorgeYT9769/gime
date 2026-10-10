#!/usr/bin/env python3
"""Gime — a tiny Git-based backup tool for game save files.

Run with:  python gime.py
"""

from __future__ import annotations

import ctypes
import os
import queue
import subprocess
import sys
import threading
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, simpledialog, ttk

import gime_core as core
import gime_theme as theme

CONFIG_PATH = Path(__file__).resolve().with_name("gime.json")
ICON_DIR = Path(__file__).resolve().parent


def apply_icon(window) -> None:
    """Best-effort: give a window the Gime icon on every platform."""
    png = ICON_DIR / "gime.png"
    ico = ICON_DIR / "gime.ico"
    try:
        if png.exists():
            image = tk.PhotoImage(file=str(png))
            window.iconphoto(True, image)
            # Tk only keeps a reference from the Tcl side; keep it alive too.
            window._gime_icon = image
        if os.name == "nt" and ico.exists():
            window.iconbitmap(str(ico))
    except tk.TclError:
        pass


def apply_dark_titlebar(window, enabled: bool) -> None:
    """Match the Windows title bar to dark mode (Windows 10 20H1 / 11).

    Best effort: older builds use attribute 19 instead of 20, and anything
    unusual simply leaves the default light title bar.
    """
    if os.name != "nt":
        return
    try:
        window.update_idletasks()
        handle = int(str(window.wm_frame()), 16)
        if handle <= 0:
            return
        value = ctypes.c_int(1 if enabled else 0)
        dwmapi = ctypes.WinDLL("dwmapi", use_last_error=True)
        dwmapi.DwmSetWindowAttribute.restype = ctypes.c_long
        dwmapi.DwmSetWindowAttribute.argtypes = [
            ctypes.c_void_p, ctypes.c_uint, ctypes.c_void_p, ctypes.c_uint]
        for attribute in (20, 19):          # 19 = pre-20H1 builds
            if dwmapi.DwmSetWindowAttribute(handle, attribute,
                                            ctypes.byref(value),
                                            ctypes.sizeof(value)) == 0:
                return
    except Exception:                       # noqa: BLE001 - purely cosmetic
        pass


# --------------------------------------------------------------------------- #
# Add / edit game dialog
# --------------------------------------------------------------------------- #
class GameDialog(tk.Toplevel):
    """Modal dialog collecting name, folder and commit message pattern."""

    def __init__(self, parent: tk.Misc, title: str, game: core.Game | None,
                 default_pattern: str, colors: dict | None = None):
        super().__init__(parent)
        self.C = colors or theme.LIGHT
        self.title(title)
        self.configure(bg=self.C["bg"])
        self.resizable(False, False)
        self.transient(parent)
        self.result: dict | None = None
        apply_icon(self)
        apply_dark_titlebar(self, self.C.get("name") == "dark")

        body = ttk.Frame(self, padding=16)
        body.pack(fill="both", expand=True)
        body.columnconfigure(1, weight=1)

        ttk.Label(body, text="Name").grid(row=0, column=0, sticky="w",
                                          pady=(4, 6))
        self.name_var = tk.StringVar(value=game.name if game else "")
        name_entry = ttk.Entry(body, textvariable=self.name_var, width=40)
        name_entry.grid(row=0, column=1, sticky="ew", pady=(4, 6))

        ttk.Label(body, text="Folder").grid(row=1, column=0, sticky="nw",
                                            pady=4)
        path_row = ttk.Frame(body)
        path_row.grid(row=1, column=1, sticky="ew", pady=4)
        path_row.columnconfigure(0, weight=1)
        self.path_var = tk.StringVar(value=game.path if game else "")
        ttk.Entry(path_row, textvariable=self.path_var).grid(
            row=0, column=0, sticky="ew")
        ttk.Button(path_row, text="Browse…", command=self._browse).grid(
            row=0, column=1, padx=(6, 0))

        ttk.Label(body, text="Commit message").grid(
            row=2, column=0, sticky="nw", pady=(16, 4))
        msg_col = ttk.Frame(body)
        msg_col.grid(row=2, column=1, sticky="ew", pady=(16, 4))
        msg_col.columnconfigure(0, weight=1)

        self.pattern_var = tk.StringVar(
            value=(game.pattern if game and game.pattern else default_pattern))
        self.pattern_entry = ttk.Entry(msg_col, textvariable=self.pattern_var)
        self.pattern_entry.grid(row=0, column=0, sticky="ew")

        tokens = tk.Menu(self, tearoff=False, **theme.menu_kwargs(self.C))
        for token, example in core.TOKEN_HELP:
            tokens.add_command(
                label=f"{token}   →  {example}",
                command=lambda t=token: self._insert_token(t),
            )

        def _post_tokens() -> None:
            x = token_btn.winfo_rootx()
            y = token_btn.winfo_rooty() + token_btn.winfo_height()
            try:
                tokens.tk_popup(x, y)
            finally:
                tokens.grab_release()

        token_btn = ttk.Button(msg_col, text="Tokens ▾", command=_post_tokens)
        token_btn.grid(row=0, column=1, padx=(6, 0))

        hint = ("Blank uses the app default. Placeholders are filled in when "
                "a game is selected.")
        ttk.Label(body, text=hint, style="Caption.TLabel",
                  wraplength=420).grid(row=3, column=0, columnspan=2,
                                       sticky="w", pady=(6, 16))

        buttons = ttk.Frame(body)
        buttons.grid(row=4, column=0, columnspan=2, sticky="e")
        ttk.Button(buttons, text="Cancel", command=self.destroy).pack(
            side="left", padx=(0, 8))
        ttk.Button(buttons, text="Save", style="Accent.TButton",
                   command=self._ok).pack(side="left")

        self.bind("<Return>", lambda _e: self._ok())
        self.bind("<Escape>", lambda _e: self.destroy())
        self.grab_set()
        self.after(50, name_entry.focus_set)

    def _insert_token(self, token: str) -> None:
        entry = self.pattern_entry
        entry.insert(tk.INSERT, token)
        entry.focus_set()

    def _browse(self) -> None:
        chosen = filedialog.askdirectory(parent=self, title="Choose game folder")
        if chosen:
            self.path_var.set(chosen)
            if not self.name_var.get().strip():
                self.name_var.set(Path(chosen).name)

    def _ok(self) -> None:
        name = self.name_var.get().strip()
        path = self.path_var.get().strip()
        if not name:
            messagebox.showwarning("Missing name", "Give this game a name.",
                                   parent=self)
            return
        if not path:
            messagebox.showwarning("Missing folder", "Pick the save folder.",
                                   parent=self)
            return
        if not Path(path).exists():
            if not messagebox.askyesno(
                    "Folder does not exist",
                    f"{path}\n\nCreate it?", parent=self):
                return
            try:
                Path(path).mkdir(parents=True, exist_ok=True)
            except OSError as exc:
                messagebox.showerror("Cannot create folder", str(exc), parent=self)
                return
        self.result = {
            "name": name,
            "path": str(Path(path)),
            "pattern": self.pattern_var.get().strip(),
        }
        self.destroy()


# --------------------------------------------------------------------------- #
# Main window
# --------------------------------------------------------------------------- #
class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title(f"{core.APP_NAME} — game save backup")
        self.geometry("1060x780")
        self.minsize(940, 660)

        self.store = core.Store(CONFIG_PATH)
        self.current: core.Game | None = None
        self.info = core.RepoInfo()
        self.busy = False
        self.msg_dirty = False
        self._pending_fetch = False
        self._queue: queue.Queue = queue.Queue()
        self._action_buttons: list[ttk.Button] = []

        self.style = ttk.Style(self)
        self.C = theme.THEMES.get(self.store.theme, theme.LIGHT)
        self.dark_var = tk.BooleanVar(value=self.store.theme == "dark")
        self.git_version = core.git_version()
        apply_icon(self)

        self._build_menu()
        self._build_layout()
        self._apply_theme()
        self._reload_game_list()

        if core.which_git() is None:
            self.banner.grid(row=0, column=0, columnspan=2, sticky="ew")

        game = self.store.find(self.store.last_id)
        if game is not None:
            self._select_game(game, scroll=True)
        elif self.store.games:
            self._select_game(self.store.games[0], scroll=True)
        else:
            self.refresh()

        self.after(80, self._poll_queue)
        self.protocol("WM_DELETE_WINDOW", self._on_close)

    # -- menu --------------------------------------------------------------- #
    def _build_menu(self) -> None:
        menubar = tk.Menu(self, **theme.menu_kwargs(self.C))
        self.games_menu = tk.Menu(menubar, tearoff=False,
                                  **theme.menu_kwargs(self.C))
        menubar.add_cascade(label="Games", menu=self.games_menu)

        self.view_menu = tk.Menu(menubar, tearoff=False,
                                 **theme.menu_kwargs(self.C))
        self.view_menu.add_checkbutton(label="Dark mode",
                                       variable=self.dark_var,
                                       command=self.toggle_theme)
        menubar.add_cascade(label="View", menu=self.view_menu)

        menubar.add_command(label="Add game…", command=self.add_game)
        menubar.add_command(label="Refresh", command=self._refresh_clicked)
        menubar.add_separator()
        menubar.add_command(label="Quit", command=self._on_close)
        self._menubar = menubar
        self.config(menu=menubar)

    def _rebuild_games_menu(self) -> None:
        menu = self.games_menu
        menu.delete(0, "end")
        if not self.store.games:
            menu.add_command(label="(no games yet)", state="disabled")
        for game in self.store.games:
            menu.add_command(
                label=game.name,
                command=lambda g=game: self._select_game(g, scroll=True),
            )
        menu.add_separator()
        menu.add_command(label="Add game…", command=self.add_game)

    # -- layout ------------------------------------------------------------- #
    def _build_layout(self) -> None:
        self.columnconfigure(1, weight=1)
        self.rowconfigure(1, weight=1)

        self.banner = ttk.Label(
            self, style="Banner.TLabel",
            text="Git is not installed or not on PATH — install Git, then "
                 "restart Gime.")

        # Left: the game picker -------------------------------------------- #
        left = ttk.Frame(self, style="Sidebar.TFrame", padding=(14, 14, 8, 12))
        left.grid(row=1, column=0, sticky="nsew")
        left.rowconfigure(1, weight=1)

        ttk.Label(left, text="Games",
                  style="SidebarTitle.TLabel").grid(
            row=0, column=0, sticky="w", pady=(0, 8))
        self.games_list = tk.Listbox(left, width=26, height=20,
                                     **theme.listbox_kwargs(self.C))
        self.games_list.grid(row=1, column=0, sticky="nsew")
        self.games_list.bind("<<ListboxSelect>>", self._on_list_select)

        picker = ttk.Frame(left, style="Sidebar.TFrame")
        picker.grid(row=2, column=0, sticky="ew", pady=(8, 0))
        for col in range(3):
            picker.columnconfigure(col, weight=1)
        for col, (text, cmd) in enumerate((
                ("Add…", self.add_game),
                ("Edit…", self.edit_game),
                ("Remove", self.remove_game))):
            ttk.Button(picker, text=text, command=cmd).grid(
                row=0, column=col, sticky="ew",
                padx=(0 if col == 0 else 4, 0))

        # Right: everything else ------------------------------------------- #
        right = ttk.Frame(self, padding=(0, 14, 14, 0))
        right.grid(row=1, column=1, sticky="nsew")
        right.columnconfigure(0, weight=1)
        right.rowconfigure(2, weight=3)
        right.rowconfigure(5, weight=2)

        # Header
        header = ttk.Frame(right)
        header.grid(row=0, column=0, sticky="ew", pady=(0, 10))
        header.columnconfigure(0, weight=1)
        self.title_label = ttk.Label(header, text="No game selected",
                                     style="Title.TLabel")
        self.title_label.grid(row=0, column=0, sticky="w")
        self.path_label = ttk.Label(header, text="", style="Caption.TLabel")
        self.path_label.grid(row=1, column=0, sticky="w", pady=(3, 0))
        ttk.Button(header, text="Open folder", style="Link.TButton",
                   command=self._open_folder).grid(
            row=0, column=1, rowspan=2, sticky="ne", padx=(12, 0))

        # Versions
        versions = ttk.LabelFrame(right, text="Versions",
                                  padding=(12, 10, 12, 12))
        versions.grid(row=1, column=0, sticky="ew", pady=(0, 10))
        versions.columnconfigure(1, weight=1)

        self.val_local = ttk.Label(versions, text="—", style="Mono.TLabel")
        self.sub_local = ttk.Label(versions, text="",
                                   style="MonoCaption.TLabel")
        self.val_remote = ttk.Label(versions, text="—", style="Mono.TLabel")
        self.sub_remote = ttk.Label(versions, text="",
                                    style="MonoCaption.TLabel")
        self.val_state = ttk.Label(versions, text="—", style="Mono.TLabel")
        self.val_origin = ttk.Label(versions, text="—",
                                    style="MonoCaption.TLabel")

        for row, (caption, value) in enumerate((
                ("Mine (local)", self.val_local),
                ("Uploaded (remote)", self.val_remote),
                ("Status", self.val_state),
                ("Remote", self.val_origin))):
            ttk.Label(versions, text=caption, width=18,
                      style="CaptionPanel.TLabel").grid(
                row=row * 2, column=0, sticky="nw", pady=(0, 2))
            value.grid(row=row * 2, column=1, sticky="w", pady=(0, 2))
        self.sub_local.grid(row=1, column=1, sticky="w", pady=(0, 6))
        self.sub_remote.grid(row=3, column=1, sticky="w", pady=(0, 6))

        self.init_btn = ttk.Button(versions, text="Initialize Git…",
                                   style="Link.TButton", command=self.init_repo)
        self.init_btn.grid(row=8, column=1, sticky="w", pady=(10, 0))
        self.remote_btn = ttk.Button(versions, text="Set remote…",
                                     style="Link.TButton",
                                     command=self.set_remote)
        self.remote_btn.grid(row=8, column=1, sticky="e", pady=(10, 0))
        # Both are real actions, so they must grey out while git is running.
        self._action_buttons.extend([self.init_btn, self.remote_btn])

        # Changed files
        changes = ttk.LabelFrame(right, text="Changed files",
                                 padding=(8, 8, 8, 10))
        changes.grid(row=2, column=0, sticky="nsew", pady=(0, 10))
        changes.columnconfigure(0, weight=1)
        changes.rowconfigure(0, weight=1)

        self.tree = ttk.Treeview(changes, columns=("status", "file"),
                                 show="headings", height=6)
        self.tree.heading("status", text="Status")
        self.tree.column("status", width=110, anchor="w", stretch=False)
        self.tree.heading("file", text="File")
        self.tree.column("file", width=560, anchor="w")
        tree_scroll = ttk.Scrollbar(changes, orient="vertical",
                                    command=self.tree.yview)
        self.tree.configure(yscrollcommand=tree_scroll.set)
        self.tree.grid(row=0, column=0, sticky="nsew")
        tree_scroll.grid(row=0, column=1, sticky="ns")
        self.changes_summary = ttk.Label(changes, text="",
                                         style="CaptionPanel.TLabel")
        self.changes_summary.grid(row=1, column=0, columnspan=2, sticky="w",
                                  pady=(7, 0))

        # Commit message
        message = ttk.LabelFrame(right, text="Commit message",
                                 padding=(8, 8, 8, 10))
        message.grid(row=3, column=0, sticky="ew", pady=(0, 10))
        message.columnconfigure(0, weight=1)
        self.message_entry = ttk.Entry(message)
        self.message_entry.grid(row=0, column=0, sticky="ew")
        self.message_entry.bind("<KeyRelease>", self._on_message_typed)
        ttk.Button(message, text="Regenerate", style="Link.TButton",
                   command=self.regenerate_message).grid(
            row=0, column=1, padx=(8, 0))

        # Actions
        actions = ttk.Frame(right)
        actions.grid(row=4, column=0, sticky="ew", pady=(0, 10))
        self.auto_commit = tk.BooleanVar(value=self.store.auto_commit)
        ttk.Checkbutton(
            actions, text="Commit before push",
            variable=self.auto_commit,
            command=self._save_auto_commit).pack(side="left")
        # Packed from the right so the visual order is Refresh…Push.
        for text, cmd, style_name in (
                ("Push", self.push, "Accent.TButton"),
                ("Pull", self.pull, "TButton"),
                ("Commit", self.commit, "TButton"),
                ("Refresh", self._refresh_clicked, "TButton")):
            btn = ttk.Button(actions, text=text, style=style_name, command=cmd)
            btn.pack(side="right", padx=4)
            self._action_buttons.append(btn)

        # Log
        log_frame = ttk.LabelFrame(right, text="Output",
                                   padding=(8, 8, 8, 10))
        log_frame.grid(row=5, column=0, sticky="nsew")
        log_frame.columnconfigure(0, weight=1)
        log_frame.rowconfigure(0, weight=1)
        self.log = tk.Text(log_frame, height=8, wrap="none", state="disabled",
                           **theme.text_kwargs(self.C))
        self.log.grid(row=0, column=0, sticky="nsew")
        y_scroll = ttk.Scrollbar(log_frame, orient="vertical",
                                 command=self.log.yview)
        x_scroll = ttk.Scrollbar(log_frame, orient="horizontal",
                                 command=self.log.xview)
        self.log.configure(yscrollcommand=y_scroll.set,
                           xscrollcommand=x_scroll.set)
        y_scroll.grid(row=0, column=1, sticky="ns")
        x_scroll.grid(row=1, column=0, sticky="ew")

        # Status bar --------------------------------------------------------- #
        status = ttk.Frame(self, style="StatusBar.TFrame", padding=(12, 4))
        status.grid(row=2, column=0, columnspan=2, sticky="ew")
        self.status_games = ttk.Label(status, text="", style="Status.TLabel")
        self.status_games.pack(side="left")
        self.status_git = ttk.Label(status, text="", style="Status.TLabel")
        self.status_git.pack(side="left", padx=(18, 0))
        self.theme_btn = ttk.Button(status, text="Dark mode",
                                    style="StatusButton.TButton",
                                    command=self._theme_button_clicked)
        self.theme_btn.pack(side="right")

        ttk.Button(right, text="Clear output", style="Link.TButton",
                   command=self.clear_log).grid(row=6, column=0, sticky="e")

    # -- helpers ------------------------------------------------------------ #
    def _append_log(self, text: str, tag: str = "") -> None:
        self.log.configure(state="normal")
        if tag:
            self.log.insert("end", text + "\n", tag)
        else:
            self.log.insert("end", text + "\n")
        self.log.see("end")
        self.log.configure(state="disabled")

    def _log(self, text: str, tag: str = "") -> None:
        """Thread-safe log."""
        self._queue.put(("line", text, tag))

    def clear_log(self) -> None:
        self.log.configure(state="normal")
        self.log.delete("1.0", "end")
        self.log.configure(state="disabled")

    def _set_busy(self, busy: bool) -> None:
        state = "disabled" if busy else "normal"
        for btn in self._action_buttons:
            btn.configure(state=state)

    def _poll_queue(self) -> None:
        try:
            while True:
                item = self._queue.get_nowait()
                if item[0] == "line":
                    self._append_log(item[1], item[2])
                elif item[0] == "done":
                    self.busy = False
                    self._set_busy(False)
                    if self._pending_fetch:
                        # A game was switched away from mid-fetch; catch up
                        # on whatever is selected now.
                        self._pending_fetch = False
                        self.refresh(fetch=True)
                    else:
                        # Re-read what changed, but never auto-fetch here:
                        # that would kick off an endless fetch loop.
                        self.refresh(fetch=False)
        except queue.Empty:
            pass
        self.after(80, self._poll_queue)

    def _run(self, label: str, task, quiet: bool = False) -> None:
        if self.busy:
            if not quiet:
                self._log(">> Busy — wait for the current operation to finish.")
            return
        if core.which_git() is None:
            if not quiet:
                self._log("!! Git is not installed or not on PATH.", "err")
            return
        self.busy = True
        self._set_busy(True)
        if not quiet:
            self._log(f"$ {label}", "cmd")

        def worker() -> None:
            try:
                task()
            except core.GitMissing as exc:
                self._log(f"!! {exc}", "err")
            except Exception as exc:  # noqa: BLE001 - show, never crash
                self._log(f"!! {exc}", "err")
            finally:
                self._queue.put(("done",))

        threading.Thread(target=worker, daemon=True, name="gime-worker").start()

    def _open_folder(self) -> None:
        if not self.current:
            return
        path = Path(self.current.path)
        if not path.exists():
            messagebox.showwarning("Missing folder", str(path))
            return
        try:
            if os.name == "nt":
                os.startfile(path)  # type: ignore[attr-defined]
            elif sys.platform == "darwin":
                subprocess.Popen(["open", str(path)])
            else:
                subprocess.Popen(["xdg-open", str(path)])
        except OSError as exc:
            messagebox.showerror("Cannot open folder", str(exc))

    def _save_auto_commit(self) -> None:
        self.store.auto_commit = bool(self.auto_commit.get())
        self.store.save()

    # -- theme --------------------------------------------------------------- #
    def _apply_theme(self) -> None:
        """Recolour every widget for the current palette."""
        C = theme.THEMES.get(self.store.theme, theme.LIGHT)
        self.C = C
        theme.apply_style(self.style, C)

        self.configure(bg=C["bg"])
        self.games_list.configure(**theme.listbox_kwargs(C))
        self.log.configure(**theme.text_kwargs(C))
        self.log.tag_configure("cmd", foreground=C["log_cmd"])
        self.log.tag_configure("ok", foreground=C["log_ok"])
        self.log.tag_configure("err", foreground=C["log_err"])
        for menu in (self._menubar, self.games_menu, self.view_menu):
            menu.configure(**theme.menu_kwargs(C))
        apply_dark_titlebar(self, self.store.theme == "dark")
        self._update_status()

    def set_theme(self, name: str) -> None:
        if name not in theme.THEMES:
            name = "light"
        if self.store.theme == name:
            return
        self.store.theme = name
        self.dark_var.set(name == "dark")
        self.store.save()
        self._apply_theme()
        self.refresh(fetch=False)

    def toggle_theme(self) -> None:
        """Bound to the View ▾ Dark mode checkbutton."""
        self.set_theme("dark" if self.dark_var.get() else "light")

    def _theme_button_clicked(self) -> None:
        """Bound to the status-bar button."""
        self.set_theme("light" if self.store.theme == "dark" else "dark")

    def _update_status(self) -> None:
        count = len(self.store.games)
        self.status_games.configure(
            text="No games yet" if count == 0
            else ("1 game" if count == 1 else f"{count} games"))
        self.status_git.configure(
            text=self.git_version or "Git not found")
        dark = self.store.theme == "dark"
        self.theme_btn.configure(
            text="Switch to light mode" if dark else "Switch to dark mode")
        self.dark_var.set(dark)

    # -- game list ---------------------------------------------------------- #
    def _reload_game_list(self) -> None:
        self.games_list.delete(0, "end")
        for game in self.store.games:
            self.games_list.insert("end", game.name)
        self._rebuild_games_menu()
        if self.current:
            ids = [g.id for g in self.store.games]
            if self.current.id in ids:
                self.games_list.selection_set(ids.index(self.current.id))
        self._update_status()

    def _on_list_select(self, _event=None) -> None:
        selection = self.games_list.curselection()
        if not selection:
            return
        game = self.store.games[selection[0]]
        if self.current and game.id == self.current.id:
            return
        self._select_game(game)

    def _select_game(self, game: core.Game, scroll: bool = False) -> None:
        self.current = game
        self.store.last_id = game.id
        self.store.save()
        self._reload_game_list()
        if scroll:
            try:
                index = [g.id for g in self.store.games].index(game.id)
                self.games_list.see(index)
            except ValueError:
                pass
        self.title_label.configure(text=game.name)
        self.path_label.configure(text=game.path)
        self.msg_dirty = False
        self.refresh()

    def add_game(self) -> None:
        dialog = GameDialog(self, "Add game", None, self.store.default_pattern,
                            colors=self.C)
        self.wait_window(dialog)
        if not dialog.result:
            return
        game = self.store.add(**dialog.result)
        self._reload_game_list()
        self._select_game(game, scroll=True)

    def edit_game(self) -> None:
        if not self.current:
            messagebox.showinfo("No game", "Pick a game first.")
            return
        dialog = GameDialog(self, "Edit game", self.current,
                            self.store.default_pattern, colors=self.C)
        self.wait_window(dialog)
        if not dialog.result:
            return
        self.store.update(self.current, **dialog.result)
        self._reload_game_list()
        self.msg_dirty = False
        self.title_label.configure(text=self.current.name)
        self.path_label.configure(text=self.current.path)
        self.refresh()

    def remove_game(self) -> None:
        if not self.current:
            return
        if not messagebox.askyesno(
                "Remove game",
                f"Remove '{self.current.name}' from Gime?\n\n"
                "No files are deleted — only the entry in the list."):
            return
        removed_id = self.current.id
        self.store.remove(removed_id)
        self.current = None
        self._reload_game_list()
        if self.store.games:
            self._select_game(self.store.games[0], scroll=True)
        else:
            self.title_label.configure(text="No game selected")
            self.path_label.configure(text="")
            self.info = core.RepoInfo()
            self._render_info()

    # -- refreshing --------------------------------------------------------- #
    def _refresh_clicked(self) -> None:
        self.refresh(fetch=True, announce=True)

    def refresh(self, fetch: bool = True, announce: bool = False) -> None:
        """Re-read the selected repo locally, then quietly sync with remote."""
        if not self.current:
            self.info = core.RepoInfo()
            self._render_info()
            return
        self.info = core.read_repo(self.current.path)
        self._render_info()
        if not self.msg_dirty:
            self.regenerate_message()
        if fetch:
            self._fetch_async(announce)

    def _fetch_async(self, announce: bool = False) -> None:
        """Update the remote-tracking ref so 'Uploaded' is really uploaded."""
        if not self.current:
            return
        if self.busy:
            # Something is running; catch up on the current game afterwards.
            self._pending_fetch = True
            return
        info = self.info
        if not info.is_repo or not info.origin:
            return
        path = self.current.path
        name = self.current.name

        def task() -> None:
            code, text = core.fetch(path)
            if code != 0 and announce:
                self._log(text or "fetch failed", "err")
                self._log(">> Remote unreachable — showing the last known "
                          "uploaded version.", "err")

        self._run(f"git fetch --prune  ({name})", task, quiet=not announce)

    def regenerate_message(self) -> None:
        if not self.current:
            return
        message = core.build_commit_message(
            self.current, self.info, self.store.default_pattern,
            core.git_user(Path(self.current.path)
                          if self.info.exists else None))
        self.message_entry.delete(0, "end")
        self.message_entry.insert(0, message)
        self.msg_dirty = False

    def _on_message_typed(self, _event) -> None:
        self.msg_dirty = True

    def _commit_text(self) -> str:
        return self.message_entry.get().strip()

    def _render_info(self) -> None:
        info = self.info

        if info.error:
            self.val_local.configure(text="—", foreground=self.C["muted"])
            self.sub_local.configure(text=info.error,
                                     foreground=self.C["danger"])
            self.val_remote.configure(text="—", foreground=self.C["muted"])
            self.sub_remote.configure(text="", foreground=self.C["muted"])
            self.val_state.configure(text="—", foreground=self.C["danger"])
        elif not info.is_repo:
            self.val_local.configure(text="—", foreground=self.C["muted"])
            self.sub_local.configure(text="not a Git repository yet",
                                     foreground=self.C["warning"])
            self.val_remote.configure(text="—", foreground=self.C["muted"])
            self.sub_remote.configure(text="", foreground=self.C["muted"])
            self.val_state.configure(text="no repository",
                                     foreground=self.C["warning"])
        else:
            if info.local:
                self.val_local.configure(
                    text=f"{info.local.short}  {info.local.date}",
                    foreground=self.C["success"])
                self.sub_local.configure(text=info.local.subject,
                                         foreground=self.C["muted"])
            else:
                self.val_local.configure(text="(no commits yet)",
                                         foreground=self.C["warning"])
                self.sub_local.configure(text="",
                                         foreground=self.C["muted"])

            if info.remote:
                self.val_remote.configure(
                    text=f"{info.remote.short}  {info.remote.date}",
                    foreground=self.C["success"])
                self.sub_remote.configure(text=info.remote.subject,
                                          foreground=self.C["muted"])
            elif info.tracking:
                self.val_remote.configure(text=f"{info.tracking} (not fetched)",
                                          foreground=self.C["warning"])
                self.sub_remote.configure(text="",
                                          foreground=self.C["muted"])
            else:
                self.val_remote.configure(text="—",
                                          foreground=self.C["muted"])
                self.sub_remote.configure(text="",
                                          foreground=self.C["muted"])

            self.val_state.configure(
                text=self._state_text(info),
                foreground=self.C[self._state_color(info)])

        self.val_origin.configure(text=info.origin or "(none set)",
                                  foreground=self.C["muted"])

        # Only offer the repo buttons when they can actually do something.
        if info.error:
            self.init_btn.grid_remove()
            self.remote_btn.grid_remove()
        elif info.is_repo:
            self.init_btn.grid_remove()
            self.remote_btn.grid()
        else:
            self.init_btn.grid()
            self.remote_btn.grid_remove()

        # Changed files
        self.tree.delete(*self.tree.get_children())
        for change in info.changes:
            label = core.describe_status(change.code)
            shown = change.path
            if change.old_path:
                shown = f"{change.old_path}  →  {change.path}"
            self.tree.insert("", "end", values=(label, shown))
        if not info.is_repo:
            summary = "Not a Git repository — initialize it to start backing up."
        elif info.changes:
            summary = f"{len(info.changes)} change(s) waiting to be committed."
        else:
            summary = "Working tree is clean — everything is saved."
        self.changes_summary.configure(text=summary)

    @staticmethod
    def _state_text(info: core.RepoInfo) -> str:
        if not info.has_commits:
            return "no commits yet"
        if not info.tracking:
            if info.has_remote:
                return "no upstream — push once to link it"
            return "local only — no remote"
        if info.in_sync:
            # Without the fetched upstream commit we cannot actually compare.
            if info.remote:
                return f"in sync  ({info.tracking})"
            return f"{info.tracking} — not fetched yet"
        parts = []
        if info.ahead:
            parts.append(f"mine is {info.ahead} ahead")
        if info.behind:
            parts.append(f"uploaded is {info.behind} ahead")
        if info.ahead and info.behind:
            return f"diverged — {', '.join(parts)}"
        return f"{parts[0]}  ({info.tracking})" if parts else "unknown"

    @staticmethod
    def _state_color(info: core.RepoInfo) -> str:
        """Return a palette key, not a literal colour, so it works in both themes."""
        if not info.is_repo or info.error:
            return "warning"
        if info.in_sync and info.remote:
            return "success"
        if info.behind:
            return "danger"
        return "warning"

    # -- actions ------------------------------------------------------------ #
    def commit(self) -> None:
        if not self._require_repo():
            return
        path = self.current.path
        message = self._commit_text()
        if not message:
            messagebox.showinfo("Empty message",
                                "Write a commit message first.")
            return

        def task() -> None:
            info = core.read_repo(path)
            if not info.changes:
                self._log("Nothing to commit — working tree is clean.", "ok")
                return
            code, text = core.commit_all(path, message)
            if text:
                for line in text.splitlines():
                    self._log(line)
            if code == 0:
                self._log(f"Committed {len(info.changes)} change(s).", "ok")
            else:
                self._log("Commit failed.", "err")

        self._run(f'git commit -m "{message}"  ({self.current.name})', task)

    def pull(self) -> None:
        if not self._require_repo():
            return
        path = self.current.path
        name = self.current.name

        def task() -> None:
            fresh = core.read_repo(path)
            code, text = core.pull(path, fresh, self._log)
            if text:
                for line in text.splitlines():
                    self._log(line, "err")
            self._log("Pull finished." if code == 0 else "Pull failed.", "ok"
                      if code == 0 else "err")

        self._run(f"git pull --rebase --autostash  ({name})", task)

    def push(self) -> None:
        if not self._require_repo():
            return
        path = self.current.path
        name = self.current.name
        message = self._commit_text()
        auto = bool(self.auto_commit.get())

        def task() -> None:
            fresh = core.read_repo(path)
            if auto and fresh.changes:
                if not message:
                    self._log("!! 'Commit before push' is on, but the commit "
                              "message is empty.", "err")
                    return
                self._log("$ git add -A && git commit", "cmd")
                code, text = core.commit_all(path, message)
                if text:
                    for line in text.splitlines():
                        self._log(line)
                if code != 0:
                    self._log("Commit failed — push cancelled.", "err")
                    return
                fresh = core.read_repo(path)
            code, text = core.push(path, fresh, self._log)
            if text:
                for line in text.splitlines():
                    self._log(line, "err")
            self._log("Push finished." if code == 0 else "Push failed.", "ok"
                      if code == 0 else "err")

        self._run(f"git push  ({name})", task)

    def init_repo(self) -> None:
        if not self._require_game():
            return
        path = self.current.path
        if not Path(path).is_dir():
            messagebox.showerror("Missing folder",
                                 f"Folder not found:\n{path}")
            return
        if not messagebox.askyesno(
                "Initialize Git",
                f"Create a Git repository in\n{path}\n\n"
                "Existing files become tracked automatically."):
            return

        def task() -> None:
            code, text = core.init_repo(path)
            for line in (text or "Repository created.").splitlines():
                self._log(line)
            if code == 0:
                self._log("Initialized empty Git repository.", "ok")

        self._run(f"git init  ({self.current.name})", task)

    def set_remote(self) -> None:
        if not self._require_repo():
            return
        path = self.current.path
        current = self.info.origin or "https://github.com/user/repo.git"
        url = simpledialog.askstring(
            "Remote repository",
            "Remote URL for push / pull:",
            initialvalue=current, parent=self)
        if not url or not url.strip():
            return
        url = url.strip()

        def task() -> None:
            code, text = core.set_remote(path, url)
            if code == 0:
                self._log(f"origin → {url}", "ok")
            else:
                self._log(text or "Failed to set remote.", "err")

        self._run(f"git remote set-url origin {url}", task)

    def _require_game(self) -> bool:
        if not self.current:
            messagebox.showinfo("No game", "Pick or add a game first.")
            return False
        return True

    def _require_repo(self) -> bool:
        if not self._require_game():
            return False
        if not self.info.is_repo:
            messagebox.showinfo(
                "Not a Git repository",
                f"'{self.current.name}' is not a Git repository yet.\n\n"
                "Use 'Initialize Git…' first.")
            return False
        return True

    def _on_close(self) -> None:
        if self.busy and not messagebox.askyesno(
                "Operation running", "A Git operation is still running.\n"
                "Quit anyway?"):
            return
        self.store.save()
        self.destroy()


if __name__ == "__main__":
    App().mainloop()
