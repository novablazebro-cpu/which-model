"""Tasks: a goal the model can read, and numeric criteria the tool grades."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Literal

import numpy as np

from axiom3d.anim.clip import Clip, Timeline
from axiom3d.anim.commands import apply_command
from axiom3d.conventions import TrackFrame, character_axes
from axiom3d.measure import foot_contact, foot_xy, root_travel, swing_windows


@dataclass(frozen=True)
class Criterion:
    id: str
    description: str
    fn: Callable  # (skel, clip, states) -> (passed: bool, measured: str)


@dataclass(frozen=True)
class Task:
    id: str
    title: str
    goal: str
    kind: Literal["step", "walk", "pose"]
    timeline: Timeline
    start_heading_deg: float
    setup: tuple[dict, ...]
    criteria: tuple[Criterion, ...]


def _step_length(side: str, low: float, high: float) -> Criterion:
    def fn(skel, clip, states):
        swings = swing_windows(states, side)
        if not swings:
            return False, f"{side} foot never left the ground (step length 0.00 m)"
        lift = states[swings[0][0] - states[0].frame - 1] if swings[0][0] > states[0].frame else states[0]
        forward, _, _ = character_axes(lift.heading_deg)
        length = float((foot_xy(states[-1], side) - foot_xy(lift, side)) @ forward[:2])
        return low <= length <= high, f"{side} step {length:+.2f} m along the facing at lift-off"

    return Criterion(f"{side}_step_length", f"{side} foot ends {low}-{high} m forward of where it lifted off", fn)


def _foot_still(side: str, tol: float = 0.02) -> Criterion:
    def fn(skel, clip, states):
        start = foot_xy(states[0], side)
        drift = max(float(np.linalg.norm(foot_xy(s, side) - start)) for s in states)
        return drift <= tol, f"{side} foot drifted {drift:.3f} m"

    return Criterion(f"{side}_foot_still", f"{side} foot stays put (drift <= {tol} m)", fn)


def _feet_down(which: tuple[str, ...]) -> Criterion:
    def fn(skel, clip, states):
        picks = {"start": states[0], "end": states[-1]}
        bad = [f"{w}:{side}" for w in which for side in ("left", "right") if not foot_contact(picks[w], side)]
        return not bad, "both feet down" if not bad else "off the ground: " + ", ".join(bad)

    label = " and ".join(which)
    return Criterion(f"both_feet_down_at_{'_and_'.join(which)}", f"both feet on the ground at the {label}", fn)


def _travel(low: float, high: float) -> Criterion:
    def fn(skel, clip, states):
        t = root_travel(clip, states)
        return low <= t <= high, f"root travelled {t:+.2f} m forward"

    return Criterion("travel", f"root travels {low}-{high} m forward", fn)


def _steps(minimum: int) -> Criterion:
    def fn(skel, clip, states):
        n = len(swing_windows(states, "left")) + len(swing_windows(states, "right"))
        return n >= minimum, f"{n} steps"

    return Criterion("steps", f"at least {minimum} steps", fn)


def _final_heading(target: float, tol: float) -> Criterion:
    def fn(skel, clip, states):
        h = states[-1].heading_deg
        return abs(h - target) <= tol, f"final heading {h:.1f} deg"

    return Criterion("final_heading", f"final heading {target} +/- {tol} deg", fn)


TASKS: dict[str, Task] = {
    t.id: t
    for t in (
        Task(
            "step_forward",
            "Step forward",
            "Step the LEFT foot forward 0.3-0.5 m and end standing on both feet. Frames 0..24 at 24 fps.",
            "step",
            Timeline(fps=24, start=0, end=24),
            0.0,
            (),
            (_step_length("left", 0.3, 0.5), _foot_still("right"), _feet_down(("end",))),
        ),
        Task(
            "walk_forward",
            "Walk forward",
            "Walk forward 1.0-1.6 m, starting and ending standing. Frames 0..48 at 24 fps.",
            "walk",
            Timeline(fps=24, start=0, end=48),
            0.0,
            (),
            (_travel(1.0, 1.6), _steps(3), _feet_down(("start", "end"))),
        ),
        Task(
            "turn_then_step",
            "Turn, then step",
            "Turn left to heading 90 (face world +X), then step the LEFT foot forward 0.3-0.5 m "
            "along the NEW facing. Frames 0..36 at 24 fps.",
            "step",
            Timeline(fps=24, start=0, end=36),
            0.0,
            (),
            (_final_heading(90.0, 5.0), _step_length("left", 0.3, 0.5), _feet_down(("end",))),
        ),
    )
}


def get_task(task_id: str) -> Task:
    if task_id not in TASKS:
        raise KeyError(f"unknown task {task_id!r}; tasks: {', '.join(TASKS)}")
    return TASKS[task_id]


def new_clip(task: Task, skel) -> Clip:
    clip = Clip(task.timeline, TrackFrame((0.0, 0.0), task.start_heading_deg))
    for cmd in task.setup:
        clip = apply_command(skel, clip, cmd)
    return clip
