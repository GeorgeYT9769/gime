#!/usr/bin/env python3
"""Real-Tk verification for Gime. Needs a display (run it on the desktop).

    python verify_ui.py

It does three things the display-less unit tests cannot:

1. probes every tk/ttk option Gime passes against the real Tcl interpreter,
   so a misspelled or unsupported option is reported in one pass;
2. builds the real App, opens both dialogs and flips dark mode, reporting any
   TclError raised along the way;
3. saves ``shot_light.png`` / ``shot_dark.png`` / ``shot_dialog.png`` so the
   result can actually be looked at.
"""

from __future__ import annotations

import ctypes
import os
import subprocess
import sys
import tempfile
import time
from ctypes import wintypes
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
OUT = HERE

PROBLEMS: list[str] = []


def note_problem(msg: str) -> None:
    PROBLEMS.append(msg)
    print(f"  PROBLEM: {msg}")


# --------------------------------------------------------------------------- #
# A throwaway save folder with a real commit and a real remote
# --------------------------------------------------------------------------- #
def build_repo() -> tuple[Path, Path]:
    root = Path(tempfile.mkdtemp(prefix="gime-verify-"))
    work = root / "Elden Ring"
    work.mkdir()
    git_env = dict(os.environ,
                   GIT_AUTHOR_NAME="Verify", GIT_AUTHOR_EMAIL="v@example.com",
                   GIT_COMMITTER_NAME="Verify", GIT_COMMITTER_EMAIL="v@example.com")

    def git(*args, cwd=None):
        subprocess.run(["git", "-c", "core.quotepath=false", *args], cwd=cwd,
                       env=git_env, check=True, capture_output=True)

    (work / "save00.dat").write_text("v1", encoding="utf-8")
    (work / "save01.dat").write_text("v1", encoding="utf-8")
    git("init", "-q", "-b", "main", cwd=work)
    git("add", "-A", cwd=work)
    git("commit", "-qm", "2026-10-06 14:00:00: Elden Ring save (2 file(s))",
        cwd=work)

    remote = root / "remote.git"
    git("init", "-q", "--bare", str(remote))
    git("remote", "add", "origin", str(remote), cwd=work)
    git("push", "-q", "-u", "origin", "main", cwd=work)

    # one uncommitted edit, so the "Changed files" tree has a row
    (work / "save00.dat").write_text("v2 in progress", encoding="utf-8")
    return root, work


# --------------------------------------------------------------------------- #
# Option prober
# --------------------------------------------------------------------------- #
def probe_options() -> None:
    import tkinter as tk
    from tkinter import ttk

    import gime_theme as theme

    print("probing widget options against real Tcl …")
    root = tk.Tk()
    root.withdraw()
    var = tk.StringVar()
    boolvar = tk.BooleanVar()

    cases = [
        ("tk.Listbox()", lambda **kw: tk.Listbox(root, **kw),
         {"width": 26, "height": 20, **theme.listbox_kwargs(theme.LIGHT)}),
        ("tk.Listbox.configure", None, theme.listbox_kwargs(theme.LIGHT)),
        ("tk.Listbox()", lambda **kw: tk.Listbox(root, **kw),
         {"width": 26, "height": 20, **theme.listbox_kwargs(theme.DARK)}),
        ("tk.Text()", lambda **kw: tk.Text(root, **kw),
         {"height": 8, "wrap": "none", "state": "disabled",
          **theme.text_kwargs(theme.LIGHT)}),
        ("tk.Text.configure", None, theme.text_kwargs(theme.LIGHT)),
        ("tk.Menu()", lambda **kw: tk.Menu(root, **kw),
         {"tearoff": False, **theme.menu_kwargs(theme.LIGHT)}),
        ("tk.Menu.configure", None, theme.menu_kwargs(theme.LIGHT)),
        ("tk.Menu()", lambda **kw: tk.Menu(root, **kw),
         {"tearoff": False, **theme.menu_kwargs(theme.DARK)}),
        ("ttk.Frame", lambda **kw: ttk.Frame(root, **kw),
         {"padding": (14, 14, 8, 12), "style": "Sidebar.TFrame"}),
        ("ttk.Label", lambda **kw: ttk.Label(root, **kw),
         {"text": "Versions", "style": "Title.TLabel", "width": 18,
          "wraplength": 420}),
        ("ttk.LabelFrame", lambda **kw: ttk.LabelFrame(root, **kw),
         {"text": "Changed files", "padding": (8, 8, 8, 10)}),
        ("ttk.Button", lambda **kw: ttk.Button(root, **kw),
         {"text": "Push", "style": "Accent.TButton", "command": lambda: None}),
        ("ttk.Checkbutton", lambda **kw: ttk.Checkbutton(root, **kw),
         {"text": "Commit before push", "variable": boolvar}),
        ("ttk.Entry", lambda **kw: ttk.Entry(root, **kw),
         {"textvariable": var}),
        ("ttk.Treeview", lambda **kw: ttk.Treeview(root, **kw),
         {"columns": ("status", "file"), "show": "headings", "height": 6}),
        ("ttk.Scrollbar", lambda **kw: ttk.Scrollbar(root, **kw),
         {"orient": "vertical", "command": lambda *a: None}),
    ]

    made: dict[str, object] = {}
    for label, factory, kwargs in cases:
        if factory is not None:
            try:
                made[label] = factory(**kwargs)
                print(f"  ok   {label}")
                continue
            except tk.TclError as exc:
                note_problem(f"{label}: {exc}")
                continue
        # configure-only case: reuse a widget of the right kind
        host = made.get("tk.Listbox()" if "Listbox" in label else
                        "tk.Text()" if "Text" in label else
                        "tk.Menu()", None)
        if host is None:
            continue
        try:
            host.configure(**kwargs)
            print(f"  ok   {label}")
        except tk.TclError as exc:
            note_problem(f"{label}: {exc}")

    # Styles: probe the whole palette through apply_style for both themes.
    style = ttk.Style(root)
    for name, C in theme.THEMES.items():
        try:
            theme.apply_style(style, C)
            print(f"  ok   apply_style({name})")
        except tk.TclError as exc:
            note_problem(f"apply_style({name}): {exc}")
    theme.apply_style(style, theme.LIGHT)
    root.destroy()


# --------------------------------------------------------------------------- #
# Screenshot
# --------------------------------------------------------------------------- #
class BITMAPINFOHEADER(ctypes.Structure):
    _fields_ = [
        ("biSize", wintypes.DWORD), ("biWidth", ctypes.c_long),
        ("biHeight", ctypes.c_long), ("biPlanes", wintypes.WORD),
        ("biBitCount", wintypes.WORD), ("biCompression", wintypes.DWORD),
        ("biSizeImage", wintypes.DWORD), ("biXPelsPerMeter", ctypes.c_long),
        ("biYPelsPerMeter", ctypes.c_long), ("biClrUsed", wintypes.DWORD),
        ("biClrImportant", wintypes.DWORD),
    ]


class BITMAPINFO(ctypes.Structure):
    _fields_ = [("bmiHeader", BITMAPINFOHEADER), ("bmiColors", wintypes.DWORD * 1)]


def screenshot(widget, path: Path) -> bool:
    """PrintWindow into a top-down 32-bit DIB, saved as PNG."""
    if os.name != "nt":
        return False
    user32, gdi32 = ctypes.windll.user32, ctypes.windll.gdi32
    user32.GetWindowRect.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.RECT)]
    user32.GetWindowRect.restype = wintypes.BOOL
    user32.GetDC.argtypes = [wintypes.HWND]
    user32.GetDC.restype = wintypes.HDC
    user32.ReleaseDC.argtypes = [wintypes.HWND, wintypes.HDC]
    user32.PrintWindow.argtypes = [wintypes.HWND, wintypes.HDC, ctypes.c_uint]
    user32.PrintWindow.restype = wintypes.BOOL
    gdi32.CreateCompatibleDC.argtypes = [wintypes.HDC]
    gdi32.CreateCompatibleDC.restype = wintypes.HDC
    gdi32.CreateCompatibleBitmap.argtypes = [wintypes.HDC, ctypes.c_int,
                                             ctypes.c_int]
    gdi32.CreateCompatibleBitmap.restype = ctypes.c_void_p
    gdi32.SelectObject.argtypes = [wintypes.HDC, ctypes.c_void_p]
    gdi32.SelectObject.restype = ctypes.c_void_p
    gdi32.GetDIBits.argtypes = [wintypes.HDC, ctypes.c_void_p, ctypes.c_uint,
                                ctypes.c_uint, ctypes.c_void_p,
                                ctypes.c_void_p, ctypes.c_uint]
    gdi32.GetDIBits.restype = ctypes.c_int
    gdi32.DeleteObject.argtypes = [ctypes.c_void_p]
    gdi32.DeleteDC.argtypes = [wintypes.HDC]

    try:
        hwnd = int(str(widget.wm_frame()), 16)
        rect = wintypes.RECT()
        if not user32.GetWindowRect(hwnd, ctypes.byref(rect)):
            return False
        w = rect.right - rect.left
        h = rect.bottom - rect.top
        if w <= 0 or h <= 0:
            return False

        hdc = user32.GetDC(0)
        memdc = gdi32.CreateCompatibleDC(hdc)
        bmp = gdi32.CreateCompatibleBitmap(hdc, w, h)
        gdi32.SelectObject(memdc, bmp)
        ok = user32.PrintWindow(hwnd, memdc, 2)  # PW_RENDERFULLCONTENT
        if not ok:
            return False

        info = BITMAPINFO()
        info.bmiHeader.biSize = ctypes.sizeof(BITMAPINFOHEADER)
        info.bmiHeader.biWidth = w
        info.bmiHeader.biHeight = -h          # top-down
        info.bmiHeader.biPlanes = 1
        info.bmiHeader.biBitCount = 32
        info.bmiHeader.biCompression = 0      # BI_RGB
        buf = ctypes.create_string_buffer(w * h * 4)
        gdi32.GetDIBits(memdc, bmp, 0, h, buf, ctypes.byref(info), 0)
        gdi32.DeleteObject(bmp)
        gdi32.DeleteDC(memdc)
        user32.ReleaseDC(0, hdc)

        raw = bytearray(buf.raw)
        for i in range(0, len(raw), 4):       # BGRA -> RGBA
            raw[i], raw[i + 2] = raw[i + 2], raw[i]
            raw[i + 3] = 255
        import make_icon
        make_icon.write_png(path, raw, w, h)
        print(f"  shot {path.name}  {w}x{h}")
        return True
    except Exception as exc:                  # noqa: BLE001 - best effort
        note_problem(f"screenshot {path.name}: {exc}")
        return False


# --------------------------------------------------------------------------- #
def pump(app, timeout: float = 8.0, quiet: float = 0.7) -> None:
    """Run Tk until no background action has changed state for a moment."""
    started = time.time()
    last_change = time.time()
    state = (app.busy, app._pending_fetch)
    while time.time() - started < timeout:
        app.update()
        new = (app.busy, app._pending_fetch)
        if new != state:
            state, last_change = new, time.time()
        if not any(state) and time.time() - last_change > quiet:
            break
        time.sleep(0.03)


def check(label: str, ok: bool, detail: str = "") -> None:
    print(f"  {'ok  ' if ok else 'FAIL'} {label}{'  ' + detail if detail else ''}")
    if not ok:
        note_problem(label + (" " + detail if detail else ""))


def main() -> int:
    import gime
    import gime_core as core
    import gime_theme as theme

    probe_options()

    print("building the real App …")
    root_dir, work = build_repo()
    gime.CONFIG_PATH = root_dir / "gime.json"
    store = core.Store(gime.CONFIG_PATH)
    store.add("Elden Ring", str(work))
    store.save()

    try:
        app = gime.App()
    except Exception as exc:                      # noqa: BLE001
        import traceback
        traceback.print_exc()
        note_problem(f"App(): {exc}")
        return 1

    pump(app)
    info = app.info
    check("game selected", app.current is not None,
          app.current.name if app.current else "")
    check("repo detected", info.is_repo, str(info.origin))
    check("local version shown", info.local is not None,
          info.local.short if info.local else "-")
    check("remote version shown", info.remote is not None,
          info.remote.short if info.remote else "-")
    state = app._state_text(info)
    check("state readable", ("in sync" in state) or ("ahead" in state)
          or ("local only" in state) or ("not fetched" in state), state)
    rows = [app.tree.item(i, "values") for i in app.tree.get_children("")]
    check("changed file listed", len(rows) == 1,
          f"{len(rows)} row(s): {rows}")
    check("commit message filled", bool(app.message_entry.get()),
          repr(app.message_entry.get()))
    check("Initialize Git hidden (repo exists)",
          app.init_btn.winfo_manager() != "grid",
          f"manager={app.init_btn.winfo_manager()!r}")
    check("Set remote shown (repo exists)",
          app.remote_btn.winfo_manager() == "grid",
          f"manager={app.remote_btn.winfo_manager()!r}")
    check("status bar git version", bool(app.status_git.cget("text")),
          app.status_git.cget("text"))
    check("status bar count", app.status_games.cget("text") == "1 game",
          app.status_games.cget("text"))
    check("icon set", bool(getattr(app, "_gime_icon", None)))
    check("title", app.title().startswith("Gime"), app.title())

    shot_light = OUT / "shot_light.png"
    app.lift()
    app.update()
    time.sleep(0.4)
    screenshot(app, shot_light)

    print("flipping to dark mode …")
    try:
        app._theme_button_clicked()
        pump(app, timeout=3)
        check("dark palette active", app.C["name"] == "dark", app.C["name"])
        check("dark persisted",
              core.Store(gime.CONFIG_PATH).theme == "dark")
        app.lift()
        app.update()
        time.sleep(0.4)
        screenshot(app, OUT / "shot_dark.png")
    except Exception as exc:                      # noqa: BLE001
        import traceback
        traceback.print_exc()
        note_problem(f"dark mode: {exc}")

    print("opening the Add game dialog …")
    try:
        dialog = gime.GameDialog(app, "Add game", None,
                                 app.store.default_pattern, colors=app.C)
        for _ in range(10):
            dialog.update()
            time.sleep(0.03)
        time.sleep(0.3)
        screenshot(dialog, OUT / "shot_dialog.png")
        dialog.destroy()
        app.update()
        check("game dialog built", True)
    except Exception as exc:                      # noqa: BLE001
        import traceback
        traceback.print_exc()
        note_problem(f"GameDialog: {exc}")

    # The pattern/token path still works after the restyle.
    try:
        dialog = gime.GameDialog(app, "Edit game", app.current,
                                 app.store.default_pattern, colors=app.C)
        dialog._insert_token("{datetime:%Y%m%d-%H%M%S}")
        check("token inserted", "{datetime:%Y%m%d-%H%M%S}"
              in dialog.pattern_var.get(), repr(dialog.pattern_var.get()))
        dialog.destroy()
        app.update()
    except Exception as exc:                      # noqa: BLE001
        note_problem(f"token insert: {exc}")

    app.destroy()

    print()
    if PROBLEMS:
        print(f"{len(PROBLEMS)} problem(s):")
        for p in PROBLEMS:
            print(f"  - {p}")
        code = 1
    else:
        print("all checks passed")
        code = 0
    sys.stdout.flush()
    os._exit(code)


if __name__ == "__main__":
    main()
