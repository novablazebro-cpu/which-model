"""Check results and the registry. Each hint is the teacher: what went wrong and why."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable, Literal

SEVERITY_ORDER = ("error", "warning", "info")


@dataclass
class CheckResult:
    id: str
    severity: Literal["error", "warning", "info"]
    frames: list[int]
    message: str
    evidence: dict[str, float] = field(default_factory=dict)
    hint: str = ""


@dataclass
class CheckContext:
    skel: object
    clip: object
    states: list
    kind: Literal["step", "walk", "pose", "vessel"]


REGISTRY: dict[str, Callable[[CheckContext], list[CheckResult]]] = {}


def register(check_id: str):
    def wrap(fn):
        REGISTRY[check_id] = fn
        return fn

    return wrap


def frames_text(frames: list[int]) -> str:
    """Compact frame list: 3-7, 12, 20-24."""
    if not frames:
        return ""
    parts, start, prev = [], frames[0], frames[0]
    for f in frames[1:] + [None]:
        if f is not None and f == prev + 1:
            prev = f
            continue
        parts.append(f"{start}" if start == prev else f"{start}-{prev}")
        if f is not None:
            start = prev = f
    return ", ".join(parts)


def run_checks(ctx: CheckContext) -> list[CheckResult]:
    if ctx.kind == "vessel":
        from axiom3d.checks.vessel import vessel_checks

        results = vessel_checks(ctx)
        return sorted(results, key=lambda r: (SEVERITY_ORDER.index(r.severity), r.id))
    # Importing registers the checks.
    from axiom3d.checks import anatomy, gait, geometry  # noqa: F401

    results = [r for fn in REGISTRY.values() for r in fn(ctx)]
    return sorted(results, key=lambda r: (SEVERITY_ORDER.index(r.severity), r.id))
