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

from axiom3d.anim.commands import apply_command
from axiom3d.anim.evaluate import evaluate_clip
from axiom3d.protocol.briefing import make_quiz
from axiom3d.protocol.ledger import new_ledger
from axiom3d.tasks.library import get_task, new_clip

_ID = re.compile(r"^[a-z_]+-[0-9a-f]+$")


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


def _path(home: Path, session_id: str) -> Path:
    return Path(home) / "sessions" / f"{session_id}.json"


def new_session(task_id: str, protocol: bool, label: str | None, home: Path, skel,
                session_id: str | None = None) -> SessionState:
    task = get_task(task_id)
    session_id = session_id or f"{task_id}-{secrets.token_hex(4)}"
    seed = int(session_id.rsplit("-", 1)[1], 16)
    quiz = []
    if protocol:
        questions = make_quiz(skel, new_clip(task, skel), seed)
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
    if not isinstance(session_id, str) or not _ID.match(session_id) or not _path(home, session_id).exists():
        raise FileNotFoundError(f"unknown session {session_id!r}; call start_session to begin one")
    try:
        return SessionState(**json.loads(_path(home, session_id).read_text()))
    except (json.JSONDecodeError, TypeError) as e:
        raise ValueError(f"unreadable session {session_id!r} ({e}); call start_session to begin a new one") from None


def current_id(home: Path) -> str | None:
    path = Path(home) / "current"
    return path.read_text().strip() if path.exists() else None


def rebuild(state: SessionState, skel):
    clip = new_clip(get_task(state.task_id), skel)
    for cmd in state.commands:
        clip = apply_command(skel, clip, cmd)
    return clip, evaluate_clip(skel, clip)
