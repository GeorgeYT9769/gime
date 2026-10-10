"""Gime core: game list persistence + Git helpers.

No GUI code lives here, so it can be imported and tested without a display.
"""

from __future__ import annotations

import json
import os
import platform
import re
import shutil
import subprocess
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

APP_NAME = "Gime"
DEFAULT_PATTERN = "{datetime}: {game} save ({count} file(s))"
UNIT_SEP = "\x1f"
COMMIT_FMT = f"%H{UNIT_SEP}%h{UNIT_SEP}%s{UNIT_SEP}%ci"

# Hides the flashing console window on Windows; ignored elsewhere.
_WIN_FLAGS = {"creationflags": 0x08000000} if os.name == "nt" else {}

# Tokens accepted in commit message patterns.
TOKEN_HELP = [
    ("{datetime}", "2026-10-06 14:32"),
    ("{datetime:%Y%m%d-%H%M%S}", "20261006-143205"),
    ("{date}", "2026-10-06"),
    ("{date:%d.%m.%Y}", "06.10.2026"),
    ("{time}", "14:32:05"),
    ("{game}", "Elden Ring"),
    ("{count}", "3"),
    ("{files}", "save00.dat, save01.dat (+1 more)"),
    ("{branch}", "main"),
    ("{host}", "DESKTOP-ABC"),
    ("{user}", "juraj"),
    ("{path}", "D:/Games/ELDEN RING"),
]


# --------------------------------------------------------------------------- #
# Errors / results
# --------------------------------------------------------------------------- #
class GitMissing(RuntimeError):
    """Raised when the git executable cannot be found."""


# --------------------------------------------------------------------------- #
# Data model
# --------------------------------------------------------------------------- #
@dataclass
class Game:
    id: str
    name: str
    path: str
    pattern: str = ""  # empty -> use the store-wide default

    @staticmethod
    def new(name: str, path: str, pattern: str = "") -> "Game":
        return Game(id=uuid.uuid4().hex, name=name, path=path, pattern=pattern)


class Store:
    """Remembers the picked games in a JSON file next to the script."""

    def __init__(self, path: Path | str, default_pattern: str = DEFAULT_PATTERN):
        self.path = Path(path)
        self.default_pattern = default_pattern
        self.games: list[Game] = []
        self.last_id: str = ""
        self.auto_commit: bool = True
        self.theme: str = "light"
        self.load()

    # -- persistence -------------------------------------------------------- #
    def load(self) -> None:
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
        except FileNotFoundError:
            return
        except (OSError, ValueError):
            # A broken config must never stop the app from starting.
            return

        self.default_pattern = str(data.get("default_pattern", self.default_pattern))
        self.auto_commit = bool(data.get("auto_commit", True))
        self.last_id = str(data.get("last_id", ""))
        theme = str(data.get("theme", "light")).lower()
        self.theme = theme if theme in ("light", "dark") else "light"

        for raw in data.get("games", []):
            if not isinstance(raw, dict):
                continue
            name = str(raw.get("name", "")).strip()
            path = str(raw.get("path", "")).strip()
            if not name or not path:
                continue
            self.games.append(
                Game(
                    id=str(raw.get("id") or uuid.uuid4().hex),
                    name=name,
                    path=path,
                    pattern=str(raw.get("pattern", "")),
                )
            )

        if self.last_id not in {g.id for g in self.games}:
            self.last_id = self.games[0].id if self.games else ""

    def save(self) -> None:
        payload = {
            "default_pattern": self.default_pattern,
            "auto_commit": self.auto_commit,
            "theme": self.theme,
            "last_id": self.last_id,
            "games": [
                {"id": g.id, "name": g.name, "path": g.path, "pattern": g.pattern}
                for g in self.games
            ],
        }
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_suffix(self.path.suffix + ".tmp")
        tmp.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
        tmp.replace(self.path)

    # -- accessors ---------------------------------------------------------- #
    def find(self, game_id: str) -> Game | None:
        for game in self.games:
            if game.id == game_id:
                return game
        return None

    def add(self, name: str, path: str, pattern: str = "") -> Game:
        game = Game.new(name.strip(), str(Path(path)), pattern.strip())
        self.games.append(game)
        if not self.last_id:
            self.last_id = game.id
        self.save()
        return game

    def update(self, game: Game, *, name: str, path: str, pattern: str) -> None:
        game.name = name.strip()
        game.path = str(Path(path))
        game.pattern = pattern.strip()
        self.save()

    def remove(self, game_id: str) -> None:
        self.games = [g for g in self.games if g.id != game_id]
        if self.last_id == game_id:
            self.last_id = self.games[0].id if self.games else ""
        self.save()


# --------------------------------------------------------------------------- #
# Git plumbing
# --------------------------------------------------------------------------- #
def _git_env() -> dict[str, str]:
    env = os.environ.copy()
    # Never block forever waiting for a password in a terminal we do not have.
    env["GIT_TERMINAL_PROMPT"] = "0"
    return env


def _cmd(*args: str) -> list[str]:
    return ["git", "-c", "core.quotepath=false", "-c", "color.ui=false", *args]


def _clean(text: str | None) -> str:
    return (text or "").strip()


def git(repo: Path | str, *args: str, input: str | None = None,
        timeout: int = 180, check: bool = False) -> tuple[int, str, str]:
    """Run a git command. Returns (returncode, stdout, stderr), unstripped."""
    cmd = _cmd(*args)
    try:
        proc = subprocess.run(
            cmd,
            cwd=str(repo) if repo is not None else None,
            input=input,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            env=_git_env(),
            timeout=timeout,
            **_WIN_FLAGS,
        )
    except FileNotFoundError as exc:
        raise GitMissing("git was not found on this system's PATH") from exc
    except subprocess.TimeoutExpired as exc:
        raise RuntimeError(f"git {' '.join(args)} timed out") from exc

    if check and proc.returncode != 0:
        raise RuntimeError(_clean(proc.stderr) or _clean(proc.stdout) or "git failed")
    return proc.returncode, proc.stdout, proc.stderr


def git_streaming(repo: Path | str, args: list[str], on_line, timeout: int = 900) -> int:
    """Run git, forwarding every output line to ``on_line`` as it arrives."""
    cmd = _cmd(*args)
    try:
        proc = subprocess.Popen(
            cmd,
            cwd=str(repo),
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            encoding="utf-8",
            errors="replace",
            bufsize=1,
            env=_git_env(),
            **_WIN_FLAGS,
        )
    except FileNotFoundError as exc:
        raise GitMissing("git was not found on this system's PATH") from exc

    assert proc.stdout is not None
    try:
        for line in proc.stdout:
            on_line(line.rstrip("\n"))
        return proc.wait(timeout=timeout)
    except subprocess.TimeoutExpired:
        proc.kill()
        raise RuntimeError(f"git {' '.join(args[:2])} timed out") from None
    finally:
        if proc.stdout:
            proc.stdout.close()


def which_git() -> str | None:
    return shutil.which("git")


def git_version() -> str:
    """e.g. ``git version 2.53.0``, or ``""`` when git is unavailable."""
    if which_git() is None:
        return ""
    try:
        code, out, _ = git(None, "--version")
    except (GitMissing, RuntimeError, OSError, subprocess.SubprocessError):
        return ""
    return _clean(out) if code == 0 else ""


# --------------------------------------------------------------------------- #
# Repo inspection
# --------------------------------------------------------------------------- #
@dataclass
class CommitInfo:
    hash: str = ""
    short: str = ""
    subject: str = ""
    date: str = ""


@dataclass
class Change:
    code: str  # raw two-letter porcelain status
    path: str
    old_path: str = ""


@dataclass
class RepoInfo:
    path: str = ""
    exists: bool = False
    is_repo: bool = False
    has_commits: bool = False
    branch: str = ""
    origin: str = ""
    tracking: str = ""
    ahead: int = 0
    behind: int = 0
    local: CommitInfo | None = None
    remote: CommitInfo | None = None
    changes: list[Change] = field(default_factory=list)
    error: str = ""

    @property
    def has_remote(self) -> bool:
        return bool(self.origin)

    @property
    def in_sync(self) -> bool:
        return bool(self.tracking) and self.ahead == 0 and self.behind == 0


def describe_status(code: str) -> str:
    """Turn a porcelain status code into a human word."""
    if code == "??":
        return "untracked"
    if code == "!!":
        return "ignored"
    x, y = code[0], code[1] if len(code) > 1 else " "
    if "U" in code or (x == "A" and y == "A"):
        return "conflict"
    if "R" in code:
        return "renamed"
    if "C" in code:
        return "copied"
    if "D" in code:
        return "deleted"
    if "A" in code:
        return "added"
    if "T" in code:
        return "type change"
    if "M" in code:
        return "modified"
    return _clean(code) or "changed"


def parse_status_z(raw: str) -> list[Change]:
    """Parse ``git status --porcelain=v1 -z`` output."""
    changes: list[Change] = []
    entries = raw.split("\0")
    i = 0
    while i < len(entries):
        entry = entries[i]
        if not entry:
            i += 1
            continue
        # Format: "XY <path>" — X/Y may be a space, so do not strip.
        code = entry[:2]
        path = entry[3:] if len(entry) > 3 else entry
        old = ""
        if ("R" in code or "C" in code) and i + 1 < len(entries):
            i += 1
            old = entries[i]
        changes.append(Change(code=code, path=path, old_path=old))
        i += 1
    return changes


def _read_commit(path: Path, rev: str) -> CommitInfo | None:
    code, out, _ = git(path, "log", "-1", f"--format={COMMIT_FMT}", rev)
    if code != 0:
        return None
    parts = out.rstrip("\n").split(UNIT_SEP)
    parts += [""] * (4 - len(parts))
    return CommitInfo(
        hash=parts[0],
        short=parts[1],
        subject=parts[2],
        date=parts[3][:16],
    )


def read_repo(path: Path | str) -> RepoInfo:
    """Detect ``.git`` and collect everything the UI needs to show."""
    path = Path(path)
    info = RepoInfo(path=str(path))

    if not path.exists():
        info.error = f"Folder not found: {path}"
        return info
    if not path.is_dir():
        info.error = f"Not a folder: {path}"
        return info

    info.exists = True
    # Handles both a .git directory and a .git file (worktrees/submodules).
    if not (path / ".git").exists():
        return info
    info.is_repo = True

    # Branch name (works on an unborn branch; falls back for detached HEAD).
    code, out, _ = git(path, "symbolic-ref", "--short", "-q", "HEAD")
    if code != 0:
        code2, out2, _ = git(path, "rev-parse", "--abbrev-ref", "HEAD")
        out = out2 if code2 == 0 else ""
    info.branch = _clean(out)

    code, out, _ = git(path, "rev-parse", "--verify", "--quiet", "HEAD")
    info.has_commits = code == 0
    if info.has_commits:
        info.local = _read_commit(path, "HEAD")

    code, out, _ = git(path, "remote", "get-url", "origin")
    if code == 0:
        info.origin = _clean(out)

    code, out, _ = git(path, "rev-parse", "--abbrev-ref",
                       "--symbolic-full-name", "@{u}")
    if code == 0:
        info.tracking = _clean(out)
        if info.has_commits:
            code2, out2, _ = git(path, "rev-list", "--left-right", "--count",
                                 f"HEAD...{info.tracking}")
            if code2 == 0:
                bits = _clean(out2).split()
                if len(bits) == 2:
                    info.ahead, info.behind = int(bits[0]), int(bits[1])
            info.remote = _read_commit(path, info.tracking)

    code, out, _ = git(path, "status", "--porcelain=v1", "-z")
    if code == 0:
        info.changes = parse_status_z(out)
    return info


def git_user(path: Path | str | None = None) -> str:
    try:
        code, out, _ = git(path or Path.cwd(), "config", "--get", "user.name")
    except (GitMissing, RuntimeError, OSError, subprocess.SubprocessError):
        return ""
    return _clean(out) if code == 0 else ""


# --------------------------------------------------------------------------- #
# Commit message patterns
# --------------------------------------------------------------------------- #
_TOKEN_RE = re.compile(r"\{(\w+)(?::([^{}]*))?\}")


def pattern_values(game: Game, info: RepoInfo, user: str = "") -> dict:
    now = datetime.now()
    files = [c.path for c in info.changes]
    if len(files) > 3:
        shown = ", ".join(files[:3]) + f" (+{len(files) - 3} more)"
    else:
        shown = ", ".join(files)
    return {
        "datetime": now,
        "date": now,
        "time": now,
        "game": game.name,
        "count": len(files),
        "files": shown,
        "branch": info.branch or "?",
        "host": platform.node(),
        "user": user,
        "path": game.path,
    }


def render_pattern(pattern: str, values: dict) -> str:
    """Substitute ``{tokens}``; unknown tokens are left untouched."""

    def substitute(match: re.Match[str]) -> str:
        name, spec = match.group(1), match.group(2)
        if name not in values:
            return match.group(0)
        value = values[name]
        if spec and isinstance(value, datetime):
            return value.strftime(spec)
        if spec:
            try:
                return format(value, spec)
            except (ValueError, TypeError):
                return str(value)
        return str(value)

    return _TOKEN_RE.sub(substitute, pattern or "")


def build_commit_message(game: Game, info: RepoInfo, default_pattern: str,
                         user: str = "") -> str:
    pattern = game.pattern or default_pattern or DEFAULT_PATTERN
    return render_pattern(pattern, pattern_values(game, info, user))


# --------------------------------------------------------------------------- #
# Actions
# --------------------------------------------------------------------------- #
def init_repo(path: Path | str) -> tuple[int, str]:
    code, out, err = git(path, "init")
    return code, _clean(out) or _clean(err)


def fetch(path: Path | str, timeout: int = 60) -> tuple[int, str]:
    """Refresh remote-tracking refs so "Uploaded" reflects the real remote.

    Keeps everything else in the working tree untouched.
    """
    code, out, err = git(path, "fetch", "--prune", "origin", timeout=timeout)
    return code, _clean(err) or _clean(out)


def set_remote(path: Path | str, url: str) -> tuple[int, str]:
    url = url.strip()
    code, out, _ = git(path, "remote", "get-url", "origin")
    if code == 0:
        code, out, err = git(path, "remote", "set-url", "origin", url)
    else:
        code, out, err = git(path, "remote", "add", "origin", url)
    return code, _clean(err) or _clean(out)


def commit_all(path: Path | str, message: str) -> tuple[int, str]:
    """Stage everything and commit. Returns (returncode, human text)."""
    code, _, err = git(path, "add", "-A")
    if code != 0:
        return code, _clean(err) or "git add failed"
    code, out, err = git(path, "commit", "-F", "-", input=message)
    text = _clean(out) or _clean(err)
    return code, text


def rebase_in_progress(path: Path | str) -> bool:
    for name in ("rebase-merge", "rebase-apply"):
        try:
            code, out, _ = git(path, "rev-parse", "--git-path", name)
        except (GitMissing, RuntimeError, OSError):
            return False
        if code != 0:
            continue
        target = Path(_clean(out))
        if not target.is_absolute():
            target = Path(path) / target
        if target.exists():
            return True
    return False


def pull(path: Path | str, info: RepoInfo, on_line=None) -> tuple[int, str]:
    """Pull with rebase + autostash so uncommitted save files survive."""
    emit = on_line or (lambda _line: None)
    args = ["pull", "--rebase", "--autostash"]
    if not info.tracking:
        if not info.origin:
            return 1, "No remote configured — use 'Set remote' first."
        args += ["origin", info.branch or "HEAD"]
    code = git_streaming(path, args, emit)

    if code != 0 and rebase_in_progress(path):
        # Conflicts on save files: go back to the pre-pull state instead of
        # leaving the user stranded in the middle of a rebase.
        git(path, "rebase", "--abort")
        emit(">> Conflict while rebasing — aborted, nothing was changed.")
        emit(">> Resolve the conflict by hand, then pull again.")
    return code, ""


def push(path: Path | str, info: RepoInfo, on_line=None) -> tuple[int, str]:
    if not info.has_commits:
        return 1, "There are no commits yet — commit first."
    if not info.origin:
        return 1, "No remote configured — use 'Set remote' first."

    emit = on_line or (lambda _line: None)
    args = ["push"]
    if not info.tracking:
        # First push: record the upstream so later pulls/pushes know where to go.
        args += ["-u", "origin", info.branch or "HEAD"]
    code = git_streaming(path, args, emit)
    return code, ""
