"""The exit exam: the tool, not the model, decides whether work is finished."""

from __future__ import annotations

from dataclasses import dataclass, field

from axiom3d.checks.base import CheckContext, CheckResult, run_checks
from axiom3d.protocol.predict import Outcome, PredictionError, evaluate_prediction, is_precise, parse_prediction

MIN_CLAIMS = 2


@dataclass
class ExamResult:
    passed: bool
    task_success: bool
    errors: list[CheckResult]
    warnings: list[CheckResult]
    criteria: list[tuple[str, bool, str]]
    claims: list[tuple[str, Outcome | None, str]]  # (text, outcome, parse error)
    problems: list[str] = field(default_factory=list)


def run_exam(skel, clip, states, task, claims: list[str], protocol: bool, variables: dict | None = None) -> ExamResult:
    results = run_checks(CheckContext(skel, clip, states, task.kind))
    errors = [r for r in results if r.severity == "error"]
    warnings = [r for r in results if r.severity == "warning"]
    criteria = [(c.id, *c.fn(skel, clip, states)) for c in task.criteria]
    task_success = not errors and all(ok for _, ok, _ in criteria)

    graded, precise = [], 0
    for text in claims:
        try:
            p = parse_prediction(text, skel, variables)
            graded.append((text, evaluate_prediction(p, skel, clip, states, states[-1].frame), ""))
            precise += is_precise(p)
        except PredictionError as e:
            graded.append((text, None, str(e)))

    problems = []
    if protocol:
        if len(claims) < MIN_CLAIMS:
            problems.append(f"submit at least {MIN_CLAIMS} claims about the final result (you gave {len(claims)})")
        if claims and not precise:
            problems.append("at least one claim must be precise (a tolerance/range of <= 0.15 m or 20 deg, or a relation)")
        problems += [f"claim not true: {t} -> {o.measured}" for t, o, _ in graded if o is not None and not o.passed]
        problems += [f"claim unreadable: {t} -> {err}" for t, o, err in graded if o is None]
    passed = task_success and not problems
    return ExamResult(passed, task_success, errors, warnings, criteria, graded, problems)
