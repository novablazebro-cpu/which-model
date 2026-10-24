"""Scripted agents for testing the protocol: one that computes honestly, one that makes the classic errors.

They stand in for real models. The quiz answers are read from the session file,
which simulates a model that learned from the quiz feedback.
"""

from __future__ import annotations

from pathlib import Path

from axiom3d.anim.commands import apply_command
from axiom3d.anim.evaluate import evaluate_clip
from axiom3d.api import AxiomError, Workbench
from axiom3d.measure import track_coords
from axiom3d.rig.humanoid import build_mannequin
from axiom3d.session_store import current_id, load
from axiom3d.tasks.library import get_task, new_clip
from axiom3d.tasks.reference import reference_commands

AUTO = "AUTO"  # answer_quiz placeholder: fill in the session's own answers
Step = tuple[str, dict]


def _honest_expect(skel, clip, cmd: dict) -> list[str]:
    """Predictions computed by actually simulating the edit, as a careful model would."""
    states = evaluate_clip(skel, clip)
    first = states[0].frame
    if cmd["op"] == "set_root":
        f = int(cmd["frame"])
        s = states[f - first]
        fwd, left = track_coords(clip, s.root_position[:2])
        return [f"root.forward@{f} ~= {fwd:.3f} ± 0.01", f"root.left@{f} ~= {left:.3f} ± 0.01",
                f"root.height@{f} ~= {s.root_position[2]:.3f} ± 0.01", f"root.heading@{f} ~= {s.heading_deg:.1f} ± 1"]
    if cmd["op"] == "set_pose":
        f = int(cmd["frame"])
        return [f"{ch}@{f} ~= {states[f - first].angles[ch]:.1f} ± 1" for ch in cmd["angles"]]
    side = cmd["side"]
    f = (int(cmd["start"]) + int(cmd["end"])) // 2 if cmd["op"] == "swing_foot" else int(cmd["end"])
    ankle = states[f - first].points[f"{side}_ankle"]
    fwd, _ = track_coords(clip, ankle[:2])
    return [f"{side}_ankle.forward@{f} ~= {fwd:.3f} ± 0.02", f"{side}_ankle.z@{f} ~= {ankle[2]:.3f} ± 0.01"]


def correct_script(task_id: str) -> list[Step]:
    return _honest_script(task_id, reference_commands(task_id))


def mirrored_script(task_id: str) -> list[Step]:
    """Computes honestly but has left and right swapped: the left foot is planted at -X."""
    cmds = []
    for cmd in reference_commands(task_id):
        cmd = dict(cmd)
        if cmd["op"] == "plant_foot":
            cmd["left"] = 0.0875 if cmd["side"] == "right" else -0.0875
        if cmd["op"] == "set_root" and "height" in cmd:
            cmd["height"] -= 0.02
        cmds.append(cmd)
    return _honest_script(task_id, cmds)


def _honest_script(task_id: str, commands: list[dict]) -> list[Step]:
    skel = build_mannequin()
    clip = new_clip(get_task(task_id), skel)
    steps: list[Step] = [("start_session", {"task": task_id}), ("answer_quiz", {"answers": AUTO})]
    for cmd in commands:
        clip = apply_command(skel, clip, cmd)
        args = {k: v for k, v in cmd.items() if k != "op"}
        steps.append((cmd["op"], {**args, "expect": _honest_expect(skel, clip, cmd)}))
    last = evaluate_clip(skel, clip)[-1]
    fwd, _ = track_coords(clip, last.root_position[:2])
    claims = [f"root.forward@{last.frame} ~= {fwd:.3f} ± 0.02", f"left_heel on_ground @{last.frame}",
              f"right_heel on_ground @{last.frame}"]
    steps.append(("finish", {"claims": claims}))
    return steps


def _naive_swing(frame: int, side: str) -> Step:
    # The classic sign error: "negative flexion moves the leg forward".
    return ("set_pose", {"frame": frame, "angles": {f"{side}_hip.flexion": -25, f"{side}_knee.flexion": 40},
                         "expect": [f"{side}_toe in_front_of pelvis"]})


def _naive_rest(frame: int) -> Step:
    zero = {f"{s}_{j}.flexion": 0 for s in ("left", "right") for j in ("hip", "knee")}
    return ("set_pose", {"frame": frame, "angles": zero, "expect": [f"left_hip.flexion@{frame} ~= 0 ± 1"]})


def _accept() -> Step:
    return ("accept_discrepancy", {"reason": "looks fine to me"})


def naive_script(task_id: str) -> list[Step]:
    start: list[Step] = [("start_session", {"task": task_id}), ("answer_quiz", {"answers": AUTO})]
    if task_id == "step_forward":
        return start + [
            ("set_root", {"frame": 0, "forward": 0, "expect": ["root.forward@0 ~= 0 ± 0.02"]}),
            ("set_root", {"frame": 24, "forward": 0.18, "expect": ["root.forward@24 ~= 0.18 ± 0.02"]}),
            _naive_rest(0),
            ("set_pose", {"frame": 12, "angles": {"left_hip.flexion": -30, "left_knee.flexion": 40},
                          "expect": ["left_toe in_front_of pelvis"]}),
            _accept(),
            _naive_rest(24),
            ("finish", {"claims": ["left_toe.forward@24 ~= 0.36 ± 0.05", "slide(right_heel) < 0.02"]}),
        ]
    if task_id == "walk_forward":
        return start + [
            ("set_root", {"frame": 0, "forward": 0, "expect": ["root.forward@0 ~= 0 ± 0.02"]}),
            ("set_root", {"frame": 48, "forward": 1.2, "expect": ["root.forward@48 ~= 1.2 ± 0.02"]}),
            _naive_rest(0), _naive_swing(12, "left"), _accept(), _naive_rest(24),
            _naive_swing(36, "right"), _accept(), _naive_rest(48),
            ("finish", {"claims": ["root.forward@48 ~= 1.2 ± 0.05", "slide(left_heel) < 0.02"]}),
        ]
    return start + [
        # Turns the wrong way (thinks positive heading is a right turn) and walks along the old facing.
        ("set_root", {"frame": 0, "heading": 0, "expect": ["root.heading@0 ~= 0 ± 1"]}),
        ("set_root", {"frame": 12, "heading": -90, "expect": ["root.heading@12 ~= -90 ± 5"]}),
        ("set_root", {"frame": 36, "forward": 0.3, "expect": ["root.forward@36 ~= 0.3 ± 0.02"]}),
        _naive_rest(0), _naive_swing(24, "left"), _accept(), _naive_rest(36),
        ("finish", {"claims": ["root.heading@36 ~= 90 ± 5", "left_heel on_ground @36"]}),
    ]


def run_script(script: list[Step], home: Path, protocol: bool, label: str | None) -> tuple[str, list[str]]:
    """Run a script through the Workbench. Tool errors are recorded, not raised, as a model would see them."""
    wb = Workbench(home, protocol=protocol, label=label)
    transcript: list[str] = []
    for tool, kwargs in script:
        if tool == "answer_quiz":
            if not protocol:
                continue
            quiz = load(current_id(home), home).quiz
            kwargs = {"answers": {q["id"]: q["answer"] for q in quiz}}
        try:
            transcript.append(f"{tool}: {getattr(wb, tool)(**kwargs).text}")
        except AxiomError as e:
            transcript.append(f"{tool}: ERROR {e}")
    return current_id(home), transcript
