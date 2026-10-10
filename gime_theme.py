"""Colour palettes and ttk styling for Gime (light + dark mode)."""

from __future__ import annotations

import sys

# --------------------------------------------------------------------------- #
# Fonts
# --------------------------------------------------------------------------- #
if sys.platform == "win32":
    FONT_SANS = "Segoe UI"
    FONT_MONO = ("Consolas", 10)
    FONT_MONO_SMALL = ("Consolas", 9)
elif sys.platform == "darwin":
    FONT_SANS = "SF Pro Text"
    FONT_MONO = ("Menlo", 11)
    FONT_MONO_SMALL = ("Menlo", 10)
else:
    FONT_SANS = "DejaVu Sans"
    FONT_MONO = ("DejaVu Sans Mono", 10)
    FONT_MONO_SMALL = ("DejaVu Sans Mono", 9)

TITLE_FONT = (FONT_SANS, 15, "bold")
SECTION_FONT = (FONT_SANS, 10, "bold")
UI_FONT = (FONT_SANS, 10)
UI_BOLD = (FONT_SANS, 10, "bold")
SMALL_FONT = (FONT_SANS, 9)


# --------------------------------------------------------------------------- #
# Palettes
# --------------------------------------------------------------------------- #
LIGHT = {
    "name": "light",
    "bg": "#f3f4f6",
    "panel": "#ffffff",
    "panel_alt": "#f8fafc",
    "sidebar": "#eceef2",
    "border": "#d9dde3",
    "text": "#1f2328",
    "muted": "#6b7280",
    "accent": "#4f46e5",
    "accent_hover": "#4338ca",
    "on_accent": "#ffffff",
    "success": "#15803d",
    "warning": "#b45309",
    "danger": "#b91c1c",
    "btn": "#ffffff",
    "btn_hover": "#eef0f3",
    "entry": "#ffffff",
    "list": "#ffffff",
    "list_alt": "#f6f7f9",
    "select": "#4f46e5",
    "select_text": "#ffffff",
    "tree_head": "#eef0f3",
    "tree_head_text": "#374151",
    "log": "#f7f8fa",
    "log_text": "#24292f",
    "log_cmd": "#0550ae",
    "log_ok": "#1a7f37",
    "log_err": "#cf222e",
    "menu": "#ffffff",
    "menu_text": "#1f2328",
    "menu_hover": "#eef0f3",
    "menu_disabled": "#9ca3af",
    "status_bar": "#eceef2",
}

DARK = {
    "name": "dark",
    "bg": "#16181d",
    "panel": "#1f2229",
    "panel_alt": "#252932",
    "sidebar": "#191c22",
    "border": "#31363f",
    "text": "#e7e9ec",
    "muted": "#9aa2ad",
    "accent": "#6366f1",
    "accent_hover": "#818cf8",
    "on_accent": "#ffffff",
    "success": "#4ade80",
    "warning": "#fbbf24",
    "danger": "#f87171",
    "btn": "#2a2f38",
    "btn_hover": "#343a45",
    "entry": "#15181d",
    "list": "#1f2229",
    "list_alt": "#23272f",
    "select": "#4f46e5",
    "select_text": "#ffffff",
    "tree_head": "#252932",
    "tree_head_text": "#b9c0ca",
    "log": "#14161a",
    "log_text": "#d4d4d4",
    "log_cmd": "#9cdcfe",
    "log_ok": "#89d185",
    "log_err": "#f48771",
    "menu": "#1f2229",
    "menu_text": "#e7e9ec",
    "menu_hover": "#31363f",
    "menu_disabled": "#6b7280",
    "status_bar": "#191c22",
}

THEMES = {"light": LIGHT, "dark": DARK}


# --------------------------------------------------------------------------- #
# ttk styles
# --------------------------------------------------------------------------- #
def apply_style(style, C: dict) -> None:
    """Configure every ttk element we use for the given palette."""
    style.theme_use("clam")

    # Defaults for everything else ------------------------------------------------
    style.configure(
        ".",
        background=C["bg"],
        foreground=C["text"],
        fieldbackground=C["entry"],
        bordercolor=C["border"],
        lightcolor=C["border"],
        darkcolor=C["border"],
        arrowcolor=C["text"],
        insertcolor=C["text"],
        font=UI_FONT,
    )
    style.map(
        ".",
        foreground=[("disabled", C["muted"])],
        background=[("disabled", C["bg"])],
    )

    # Frames -------------------------------------------------------------------
    style.configure("TFrame", background=C["bg"])
    style.configure("Panel.TFrame", background=C["panel"])
    style.configure("Sidebar.TFrame", background=C["sidebar"])
    style.configure("StatusBar.TFrame", background=C["status_bar"])
    style.configure("Flat.TFrame", background=C["panel_alt"])

    # Labels -------------------------------------------------------------------
    style.configure("TLabel", background=C["bg"], foreground=C["text"],
                    font=UI_FONT)
    style.configure("Panel.TLabel", background=C["panel"], foreground=C["text"])
    style.configure("Sidebar.TLabel", background=C["sidebar"],
                    foreground=C["text"])
    style.configure("Title.TLabel", background=C["bg"], foreground=C["text"],
                    font=TITLE_FONT)
    style.configure("SidebarTitle.TLabel", background=C["sidebar"],
                    foreground=C["text"], font=(FONT_SANS, 11, "bold"))
    style.configure("Caption.TLabel", background=C["bg"], foreground=C["muted"],
                    font=SMALL_FONT)
    style.configure("CaptionPanel.TLabel", background=C["panel"],
                    foreground=C["muted"], font=SMALL_FONT)
    style.configure("CaptionSidebar.TLabel", background=C["sidebar"],
                    foreground=C["muted"], font=SMALL_FONT)
    style.configure("Mono.TLabel", background=C["panel"], foreground=C["text"],
                    font=FONT_MONO)
    style.configure("MonoCaption.TLabel", background=C["panel"],
                    foreground=C["muted"], font=FONT_MONO_SMALL)
    style.configure("Value.TLabel", background=C["panel"], foreground=C["text"],
                    font=FONT_MONO)
    style.configure("Heading.TLabel", background=C["panel"],
                    foreground=C["text"], font=SECTION_FONT)
    style.configure("Banner.TLabel", background=C["panel_alt"],
                    foreground=C["danger"], font=UI_BOLD, padding=(10, 6))
    style.configure("Status.TLabel", background=C["status_bar"],
                    foreground=C["muted"], font=SMALL_FONT, padding=(8, 3))

    # Label frames -------------------------------------------------------------
    style.configure("TLabelframe", background=C["panel"], foreground=C["text"],
                    bordercolor=C["border"], relief="solid", borderwidth=1)
    style.configure("TLabelframe.Label", background=C["panel"],
                    foreground=C["text"], font=SECTION_FONT, padding=(2, 0))

    # Buttons ------------------------------------------------------------------
    style.configure(
        "TButton",
        background=C["btn"],
        foreground=C["text"],
        bordercolor=C["border"],
        focusthickness=1,
        focuscolor=C["accent"],
        padding=(14, 7),
        font=UI_FONT,
    )
    style.map(
        "TButton",
        background=[("active", C["btn_hover"]), ("disabled", C["panel_alt"])],
        foreground=[("disabled", C["muted"])],
        bordercolor=[("active", C["muted"]), ("disabled", C["border"])],
    )

    # The primary action: Push, Save, etc.
    style.configure(
        "Accent.TButton",
        background=C["accent"],
        foreground=C["on_accent"],
        bordercolor=C["accent"],
        padding=(16, 7),
        font=UI_BOLD,
    )
    style.map(
        "Accent.TButton",
        background=[("active", C["accent_hover"]),
                    ("disabled", C["panel_alt"])],
        foreground=[("disabled", C["muted"]), ("active", C["on_accent"])],
        bordercolor=[("disabled", C["border"])],
    )

    # Quiet button used for small inline actions
    style.configure(
        "Link.TButton",
        background=C["panel"],
        foreground=C["muted"],
        bordercolor=C["border"],
        padding=(10, 5),
        font=SMALL_FONT,
    )
    style.map(
        "Link.TButton",
        background=[("active", C["btn_hover"]), ("disabled", C["panel"])],
        foreground=[("disabled", C["muted"]), ("active", C["text"])],
    )

    # Checkbutton / entry -----------------------------------------------------
    style.configure("TCheckbutton", background=C["panel"],
                    foreground=C["text"], focuscolor=C["panel"],
                    padding=(0, 0), font=UI_FONT)
    style.map("TCheckbutton",
              background=[("active", C["panel"])],
              foreground=[("disabled", C["muted"])])

    style.configure(
        "TEntry",
        fieldbackground=C["entry"],
        foreground=C["text"],
        insertcolor=C["text"],
        bordercolor=C["border"],
        lightcolor=C["border"],
        darkcolor=C["border"],
        padding=(7, 6),
    )
    style.map("TEntry",
              fieldbackground=[("readonly", C["entry"])],
              foreground=[("disabled", C["muted"])])

    # Treeview ----------------------------------------------------------------
    style.configure(
        "Treeview",
        background=C["list"],
        foreground=C["text"],
        fieldbackground=C["list"],
        bordercolor=C["border"],
        rowheight=26,
        padding=(6, 3),
        font=UI_FONT,
    )
    style.map("Treeview",
              background=[("selected", C["select"])],
              foreground=[("selected", C["select_text"])])
    style.configure(
        "Treeview.Heading",
        background=C["tree_head"],
        foreground=C["tree_head_text"],
        relief="flat",
        padding=(8, 7),
        font=(FONT_SANS, 9, "bold"),
    )
    style.map("Treeview.Heading",
              background=[("active", C["tree_head"])],
              foreground=[("active", C["tree_head_text"])])

    # Scrollbars --------------------------------------------------------------
    for name in ("TScrollbar", "Vertical.TScrollbar", "Horizontal.TScrollbar"):
        style.configure(name,
                        background=C["btn"],
                        troughcolor=C["bg"],
                        bordercolor=C["border"],
                        arrowcolor=C["muted"],
                        lightcolor=C["border"],
                        darkcolor=C["border"])
        style.map(name,
                  background=[("active", C["btn_hover"])],
                  arrowcolor=[("disabled", C["muted"])])

    # Status bar ---------------------------------------------------------------
    style.configure("StatusButton.TButton",
                    background=C["status_bar"],
                    foreground=C["muted"],
                    borderwidth=0,
                    padding=(10, 3),
                    font=SMALL_FONT)
    style.map("StatusButton.TButton",
              background=[("active", C["btn_hover"])],
              foreground=[("active", C["text"]),
                          ("disabled", C["muted"])])


# --------------------------------------------------------------------------- #
# tk-native widget helpers
# --------------------------------------------------------------------------- #
def menu_kwargs(C: dict) -> dict:
    return {
        "background": C["menu"],
        "foreground": C["menu_text"],
        "activebackground": C["select"],
        "activeforeground": C["select_text"],
        "disabledforeground": C["menu_disabled"],
        "borderwidth": 0,
        "font": UI_FONT,
    }


def text_kwargs(C: dict) -> dict:
    return {
        "background": C["log"],
        "foreground": C["log_text"],
        "insertbackground": C["log_text"],
        "selectbackground": C["select"],
        "selectforeground": C["select_text"],
        "font": FONT_MONO_SMALL,
        "relief": "solid",
        "borderwidth": 1,
        "highlightthickness": 0,
        "padx": 8,
        "pady": 6,
    }


def listbox_kwargs(C: dict) -> dict:
    return {
        "background": C["list"],
        "foreground": C["text"],
        "selectbackground": C["select"],
        "selectforeground": C["select_text"],
        "relief": "solid",
        "borderwidth": 1,
        "highlightthickness": 0,
        "activestyle": "none",
        "font": UI_FONT,
        "exportselection": False,
    }
