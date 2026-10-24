"""Sessions are a task plus an ordered command log; replaying the log rebuilds the scene."""

from __future__ import annotations

import dataclasses
import json
import os
import re
import secrets
import threading
from dataclasses import dataclass, field
from pathlib import Path

from axiom3d.anim.commands import CommandError, apply_command
from axiom3d.anim.evaluate import evaluate_clip
from axiom3d.protocol.briefing import make_quiz, make_vessel_quiz
from axiom3d.protocol.ledger import new_ledger
from axiom3d.tasks.library import get_task, new_clip

_ID = re.compile(r"[a-z_]+-[0-9a-f]+")
VERSION = 2


class ReplayError(ValueError):
    """A stored command no longer applies (e.g. a session saved by an older version)."""


@dataclass
class SessionState:
    id: str
    task_id: str
    protocol: bool
    phase: str  # "BRIEFING" | "WORKING" | "DONE"
    seed: int
    commands: list[dict] = field(default_factory=list)
    quiz: list[dict] = field(default_factory=list)
    pending_discrepancy: dict | None = None
    ledger: dict = field(default_factory=dict)
    variables: dict = field(default_factory=dict)
    sandbox_seen: list[str] = field(default_factory=list)
    version: int = VERSION


def _path(home: Path, session_id: str) -> Path:
    return Path(home) / "sessions" / f"{session_id}.json"


def new_session(task_id: str, protocol: bool, label: str | None, home: Path, skel,
                session_id: str | None = None) -> SessionState:
    task = get_task(task_id)
    session_id = session_id or f"{task_id}-{secrets.token_hex(4)}"
    seed = int(session_id.rsplit("-", 1)[1], 16)
    quiz = []
    if protocol:
        questions = make_vessel_quiz(seed) if task.kind == "vessel" else make_quiz(skel, new_clip(task, skel), seed)
        quiz = json.loads(json.dumps([dataclasses.asdict(q) for q in questions]))
    return SessionState(
        id=session_id, task_id=task_id, protocol=protocol,
        phase="BRIEFING" if protocol else "WORKING", seed=seed, quiz=quiz,
        ledger=new_ledger(label, task_id, protocol),
    )


def save(state: SessionState, home: Path) -> None:
    path = _path(home, state.id)
    path.parent.mkdir(parents=True, exist_ok=True)
    _atomic_write(path, json.dumps(dataclasses.asdict(state), indent=1))
    _atomic_write(Path(home) / "current", state.id)


def _atomic_write(path: Path, text: str) -> None:
    """Readers never see a half-written file: write a sibling temp file, then rename over the target."""
    tmp = path.with_name(f".{path.name}.{os.getpid()}.{threading.get_ident()}.tmp")
    tmp.write_text(text)
    os.replace(tmp, path)


def load(session_id: str, home: Path) -> SessionState:
    if not isinstance(session_id, str) or not _ID.fullmatch(session_id) or not _path(home, session_id).exists():
        raise FileNotFoundError(f"unknown session {session_id!r}; call start_session to begin one")
    try:
        data = json.loads(_path(home, session_id).read_text())
        return SessionState(**_migrate(data))
    except (json.JSONDecodeError, UnicodeDecodeError, TypeError, KeyError, AttributeError) as e:
        raise ValueError(f"unreadable session {session_id!r} ({type(e).__name__}); call start_session to begin a new one") from None


def _migrate(data: dict) -> dict:
    """Bring a session file from any older version up to VERSION; unknown keys are dropped."""
    known = {f.name for f in dataclasses.fields(SessionState)}
    data = {k: v for k, v in data.items() if k in known}
    data.setdefault("variables", {})
    data.setdefault("sandbox_seen", [])
    for key, value in new_ledger(data["ledger"].get("label"), data["task_id"], data["protocol"]).items():
        data["ledger"].setdefault(key, value)
    data["version"] = VERSION
    return data


def current_id(home: Path) -> str | None:
    path = Path(home) / "current"
    return path.read_text().strip() if path.exists() else None


def rebuild(state: SessionState, skel):
    clip = new_clip(get_task(state.task_id), skel)
    for i, cmd in enumerate(state.commands):
        try:
            clip = apply_command(skel, clip, cmd)
        except CommandError as e:
            raise ReplayError(f"stored command #{i + 1} no longer applies ({e})") from None
    return clip, evaluate_clip(skel, clip)
