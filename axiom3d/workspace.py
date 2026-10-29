"""A dedicated folder for the AI's models, kept apart from every git repository you care about."""

from __future__ import annotations

import json
import re
import subprocess
from dataclasses import dataclass
from pathlib import Path

MARKER = ".axiom3d-workspace"
DEFAULT_HOME = "~/.axiom3d-ai"
DEFAULT_DEV = "~/axiom3d-ai-dev"
_NAME = re.compile(r"[a-z0-9][a-z0-9-]{0,39}")

# git runs this before every push and feeds it one line per ref: "<local ref> <local sha> <remote ref> <remote sha>".
PRE_PUSH_HOOK = """#!/bin/sh
# Installed by `axiom3d workspace dev`. AI work goes on ai/* branches and reaches main through a pull request.
while read local_ref local_sha remote_ref remote_sha; do
  case "$remote_ref" in
    refs/heads/main|refs/heads/master)
      echo "axiom3d: refusing to push to ${remote_ref#refs/heads/}. Push your ai/* branch and open a pull request." >&2
      exit 1 ;;
  esac
done
exit 0
"""


class WorkspaceError(Exception):
    """A refusal, worded for the person at the terminal."""


@dataclass(frozen=True)
class WorkspaceInfo:
    home: Path

    @property
    def claude_command(self) -> str:
        return f"claude mcp add axiom3d -- axiom3d serve --home {self.home}"

    @property
    def mcp_json(self) -> str:
        server = {"command": "axiom3d", "args": ["serve", "--home", str(self.home)]}
        return json.dumps({"mcpServers": {"axiom3d": server}}, indent=2)


def repo_root(path: Path) -> Path | None:
    """The nearest folder at or above `path` that holds a `.git` (a folder, or a file in linked worktrees)."""
    path = Path(path).expanduser().resolve()
    for folder in (path, *path.parents):
        if (folder / ".git").exists():
            return folder
    return None


def in_git_repo(path: Path) -> bool:
    return repo_root(path) is not None


def home_warning(home: Path) -> str | None:
    """The warning for a state folder that sits inside a git repository, or None when it is somewhere safe."""
    root = repo_root(home)
    if root is None:
        return None
    return (f"WARNING: --home {Path(home).expanduser().resolve()} is inside the git repository {root}. "
            "Sessions, images and exports are written there and can end up in commits. "
            "Make a safe folder with `axiom3d workspace init` and pass it as --home.")


def init_workspace(home: Path) -> WorkspaceInfo:
    home = Path(home).expanduser().resolve()
    root = repo_root(home)
    if root is not None:
        raise WorkspaceError(f"{home} is inside the git repository {root}. Pick a folder outside every git "
                             f"repository, e.g. {DEFAULT_HOME}.")
    if home.exists():
        if not home.is_dir():
            raise WorkspaceError(f"{home} is not a folder.")
        if not (home / MARKER).exists() and any(home.iterdir()):
            raise WorkspaceError(f"{home} is not empty and was not made by `axiom3d workspace init`, so it is "
                                 "not safe to use. Pick a new or empty folder.")
    home.mkdir(parents=True, exist_ok=True)
    (home / MARKER).write_text("made by `axiom3d workspace init`; the AI's models live in this folder\n")
    return WorkspaceInfo(home)


@dataclass(frozen=True)
class DevInfo:
    path: Path
    branch: str


def _git(*args: str, cwd: Path | None = None) -> subprocess.CompletedProcess:
    return subprocess.run(["git", *args], cwd=cwd, capture_output=True, text=True)


def _default_source() -> str:
    top = _git("rev-parse", "--show-toplevel")
    if top.returncode != 0:
        raise WorkspaceError("You are not inside a git repository, so there is nothing to clone. "
                             "Pass --source <url or path>.")
    origin = _git("remote", "get-url", "origin", cwd=Path(top.stdout.strip()))
    return origin.stdout.strip() if origin.returncode == 0 else top.stdout.strip()


def dev_workspace(name: str, source: str | None = None, dest: Path | None = None) -> DevInfo:
    """A separate clone on branch ai/<name>, whose pre-push hook refuses main and master."""
    if not _NAME.fullmatch(name):
        raise WorkspaceError(f"Bad name {name!r}: use 1-40 lowercase letters, digits and dashes, "
                             "starting with a letter or digit (it becomes the branch ai/<name>).")
    dest = Path(dest if dest is not None else f"{DEFAULT_DEV}/{name}").expanduser().resolve()
    root = repo_root(dest)
    if root is not None:
        raise WorkspaceError(f"{dest} is inside the git repository {root}. Pick a folder outside every git repository.")
    if dest.exists() and (not dest.is_dir() or any(dest.iterdir())):
        raise WorkspaceError(f"{dest} is not empty. Pick a new or empty folder.")
    source = source or _default_source()
    cloned = _git("clone", "-q", source, str(dest))
    if cloned.returncode != 0:
        raise WorkspaceError(f"git clone of {source} failed: {cloned.stderr.strip()}")
    branch = f"ai/{name}"
    made = _git("checkout", "-q", "-b", branch, cwd=dest)
    if made.returncode != 0:
        raise WorkspaceError(f"could not create branch {branch}: {made.stderr.strip()}")
    hooks = dest / ".git" / "hooks"
    hooks.mkdir(exist_ok=True)
    (hooks / "pre-push").write_text(PRE_PUSH_HOOK)
    (hooks / "pre-push").chmod(0o755)
    # A global core.hooksPath would make git ignore .git/hooks, so pin this clone to its own.
    _git("config", "--local", "core.hooksPath", str(hooks), cwd=dest)
    return DevInfo(dest, branch)
