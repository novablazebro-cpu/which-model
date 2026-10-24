"""The Workbench: every tool a model can call. MCP and CLI are thin wrappers over this."""

from __future__ import annotations

import functools
import hashlib
import json
import threading
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np

from axiom3d.anim.commands import CommandError, apply_command
from axiom3d.anim.evaluate import evaluate_clip
from axiom3d.checks.base import CheckContext, run_checks
from axiom3d.conventions import CONVENTIONS_TEXT
from axiom3d.perceive.diff import describe_diff
from axiom3d.perceive.render import render_filmstrip, render_footprints, render_sheet, to_png
from axiom3d.perceive.report import describe_frame, describe_timeline
from axiom3d.protocol.briefing import Question, grade_quiz
from axiom3d.protocol.calc import CalcError, run_calc
from axiom3d.protocol.gate import run_exam
from axiom3d.protocol.predict import PredictionError, evaluate_prediction, is_precise, parse_prediction
from axiom3d.rig.humanoid import build_mannequin
from axiom3d.session_store import current_id, load, new_session, rebuild, save
from axiom3d.tasks.library import get_task

VIEWS = ("report", "timeline", "sheet", "filmstrip", "footprints")
EXPECT_HELP = (
    "Every edit needs expect=[...]: at least one PRECISE prediction of what the edit will do; the tool measures "
    "it after applying the edit. Examples: 'left_ankle.forward ~= 0.36 ± 0.05', 'left_toe in_front_of pelvis', "
    "'left_knee.flexion in [20, 40]', 'slide(right_heel) < 0.02'. Precise = a tolerance or range of at most "
    "0.15 m / 20 deg, or a relation. See guide('predictions')."
)
WORKFLOW = (
    "WORKFLOW: 1) answer_quiz  2) observe  3) edit with set_root / set_pose / plant_foot / swing_foot, each with "
    "expect=[predictions]  4) check  5) finish(claims).\n"
    "Tip: plant_foot pins a foot to the ground and the tool solves the leg; swing_foot carries it in an arc "
    "between two plants. guide('walking') explains a gait, guide('predictions') the prediction syntax."
)


class AxiomError(Exception):
    pass


@dataclass
class ToolResult:
    text: str
    images: list[tuple[str, bytes]] = field(default_factory=list)


def _prediction_frame(cmd: dict) -> int:
    """Where an edit's predictions are measured by default: the keyed frame, a plant's last frame, mid-swing.
    A batch uses its last edit's frame."""
    if cmd["op"] == "batch":
        return _prediction_frame(cmd["edits"][-1])
    if cmd["op"] in ("set_root", "set_pose"):
        return int(float(cmd["frame"]))
    if cmd["op"] == "swing_foot":
        return (int(float(cmd["start"])) + int(float(cmd["end"]))) // 2
    return int(float(cmd["end"]))


def _same_scene(a, b) -> bool:
    return all(np.allclose(sa.points[k], sb.points[k], atol=1e-9) for sa, sb in zip(a, b) for k in sa.points)


def _describe(cmd: dict) -> str:
    if cmd["op"] == "batch":
        return f"batch({len(cmd['edits'])} edits: {', '.join(e['op'] for e in cmd['edits'])})"
    args = ", ".join(f"{k}={v}" for k, v in cmd.items() if k != "op")
    return f"{cmd['op']}({args})"


def _locked(method):
    """One tool call at a time per Workbench: MCP runs sync tools in worker threads."""

    @functools.wraps(method)
    def wrapper(self, *args, **kwargs):
        with self._lock:
            return method(self, *args, **kwargs)

    return wrapper


class Workbench:
    """All tools. `shared_current=False` (the MCP server) only ever touches sessions it started itself;
    the CLI, one process per call, uses the shared home/current pointer instead."""

    def __init__(self, home: Path, protocol: bool = True, label: str | None = None, shared_current: bool = True):
        self.home = Path(home)
        self.protocol = protocol
        self.label = label
        self.shared_current = shared_current
        self.session_id: str | None = None
        self.skel = build_mannequin()
        self._lock = threading.RLock()

    # ---- helpers ---------------------------------------------------------------------------
    def _load(self, session: str | None):
        sid = session or self.session_id or (current_id(self.home) if self.shared_current else None)
        if not sid:
            raise AxiomError("no session yet; call start_session first")
        try:
            return load(sid, self.home)
        except (FileNotFoundError, ValueError) as e:
            raise AxiomError(str(e)) from None

    def _counts(self, st, clip, states) -> tuple[int, int]:
        results = run_checks(CheckContext(self.skel, clip, states, get_task(st.task_id).kind))
        return (sum(r.severity == "error" for r in results), sum(r.severity == "warning" for r in results))

    def _finish_text(self, st, lines: list[str], clip=None, states=None) -> str:
        if not st.protocol:
            return "\n".join(lines)
        if clip is None:
            clip, states = rebuild(st, self.skel)
        errors, warnings = self._counts(st, clip, states)
        verdict = "CERTIFIED" if st.ledger["certified"] else "NOT COMPLETE"
        lines.append(f"STATUS: phase={st.phase} · errors={errors} · warnings={warnings} · {verdict}")
        return "\n".join(lines)

    # ---- session -----------------------------------------------------------------------------
    @_locked
    def start_session(self, task: str) -> ToolResult:
        try:
            spec = get_task(task)
        except KeyError as e:
            raise AxiomError(e.args[0]) from None
        st = new_session(task, self.protocol, self.label, self.home, self.skel)
        save(st, self.home)
        self.session_id = st.id
        lines = [
            f"SESSION {st.id}  task: {spec.title}",
            f"GOAL: {spec.goal}",
            "ACCEPTANCE (graded by the tool):",
            *[f"- {c.description}" for c in spec.criteria],
            "CONVENTIONS:",
            CONVENTIONS_TEXT,
        ]
        if st.protocol:
            lines += [WORKFLOW, 'BRIEFING QUIZ: answer with answer_quiz({"q1": "...", ..., "q5": "..."}):']
            for q in st.quiz:
                choices = f"  [choices: {', '.join(q['choices'])}]" if q["choices"] else ""
                lines.append(f"{q['id']}: {q['text']}{choices}")
        return ToolResult(self._finish_text(st, lines))

    @_locked
    def answer_quiz(self, answers: dict, session: str | None = None) -> ToolResult:
        st = self._load(session)
        if not st.protocol:
            raise AxiomError("No quiz in bare mode.")
        if st.phase != "BRIEFING":
            raise AxiomError("The quiz is already passed." if st.phase == "WORKING" else "Session is finished; start a new one.")
        if not isinstance(answers, dict):
            raise AxiomError('answers must be an object like {"q1": "-Y", "q2": "+X", ...}')
        questions = [Question(**{**q, "choices": tuple(q["choices"]) if q["choices"] else None}) for q in st.quiz]
        result = grade_quiz(questions, {str(k): str(v) for k, v in answers.items()})
        st.ledger["quiz_attempts"] += 1
        lines = [f"{qid}: {feedback}" for qid, _, feedback in result.results]
        if result.passed:
            st.phase = "WORKING"
            st.ledger["quiz_passed"] = True
            lines.append("PASSED. Editing is unlocked. Every edit needs expect=[...] predictions.")
        else:
            lines.append("Not yet: read the explanations, fix the wrong answers and call answer_quiz again.")
        save(st, self.home)
        return ToolResult(self._finish_text(st, lines))

    @_locked
    def guide(self, topic: str) -> ToolResult:
        from axiom3d.guide import read_topic

        try:
            return ToolResult(read_topic(topic))
        except KeyError as e:
            raise AxiomError(e.args[0]) from None

    @_locked
    def calc(self, expr: str, session: str | None = None) -> ToolResult:
        """Exact math on the scene. Allowed in every phase; never changes the scene."""
        st = self._load(session)
        clip, states = rebuild(st, self.skel)
        try:
            result = run_calc(expr, self.skel, clip, states, st.variables)
        except CalcError as e:
            raise AxiomError(f"{e}. See guide('calculator').") from None
        st.variables.update(result.assigned)
        save(st, self.home)
        lines = result.lines + (["Use these in predictions as $name, e.g. ~= $" + next(iter(result.assigned)) + " ± 0.02."]
                                if result.assigned else [])
        return ToolResult(self._finish_text(st, lines, clip, states))

    # ---- seeing --------------------------------------------------------------------------------
    def _frames(self, clip, frames) -> list[int]:
        tl = clip.timeline
        if frames is None:
            return [tl.end]
        if isinstance(frames, (int, float, str)):
            frames = [frames]
        out = []
        for f in frames:
            try:
                x = float(f)
            except (TypeError, ValueError):
                raise AxiomError(f"frames must be whole numbers in {tl.start}..{tl.end}, got {f!r}") from None
            if x != int(x) or not tl.start <= x <= tl.end:
                raise AxiomError(f"frames must be whole numbers in {tl.start}..{tl.end}, got {f!r}")
            out.append(int(x))
        return out

    @_locked
    def observe(self, frames=None, views=None, session: str | None = None) -> ToolResult:
        st = self._load(session)
        clip, states = rebuild(st, self.skel)
        views = list(views) if views else ["report", "timeline"]
        bad = [v for v in views if v not in VIEWS]
        if bad:
            raise AxiomError(f"unknown view {bad[0]!r}; views: {', '.join(VIEWS)}")
        picked = self._frames(clip, frames)
        first = states[0].frame
        lines, images = [], []
        for view in views:
            if view == "report":
                lines += [describe_frame(self.skel, clip, states[f - first], hints=st.protocol) for f in picked]
            elif view == "timeline":
                lines.append("TIMELINE (heights are the lowest heel/toe point):\n" + describe_timeline(self.skel, clip, states))
            elif view == "sheet":
                images += [(f"sheet@{f}", to_png(render_sheet(self.skel, states[f - first]))) for f in picked]
            elif view == "filmstrip":
                strip = picked if frames is not None and len(picked) > 1 else \
                    sorted({int(round(x)) for x in np.linspace(states[0].frame, states[-1].frame, 8)})
                images.append(("filmstrip", to_png(render_filmstrip(self.skel, [states[f - first] for f in strip], size=200))))
            else:
                images.append(("footprints", to_png(render_footprints(self.skel, clip, states))))
        if images:
            lines.append("IMAGES: " + ", ".join(label for label, _ in images) + " (blue = LEFT, orange = RIGHT)")
        return ToolResult(self._finish_text(st, lines, clip, states), images)

    @_locked
    def check(self, session: str | None = None) -> ToolResult:
        st = self._load(session)
        clip, states = rebuild(st, self.skel)
        task = get_task(st.task_id)
        results = run_checks(CheckContext(self.skel, clip, states, task.kind))
        lines = ["CHECKS:" if results else "CHECKS: none failed"]
        for r in results:
            lines.append(f"[{r.severity.upper()}] {r.id}: {r.message}")
            if st.protocol and r.hint:
                lines.append(f"   hint: {r.hint}")
        lines.append("ACCEPTANCE:")
        for c in task.criteria:
            ok, measured = c.fn(self.skel, clip, states)
            lines.append(f"  {'PASS' if ok else 'FAIL'}  {c.id}: {measured}")
        return ToolResult(self._finish_text(st, lines, clip, states))

    # ---- editing -------------------------------------------------------------------------------
    def _edit(self, cmd: dict, expect, session: str | None, dry_run: bool = False) -> ToolResult:
        st = self._load(session)
        if st.phase == "DONE":
            raise AxiomError("Session is finished; start a new one.")
        if st.protocol and st.phase == "BRIEFING":
            raise AxiomError("Pass the briefing quiz first: call answer_quiz.")
        if st.protocol and st.pending_discrepancy and not dry_run:
            raise AxiomError(
                "Your last edit broke a prediction. Before editing again, call undo() to revert it, or "
                "accept_discrepancy(reason) to keep it and say why your prediction was wrong."
            )
        predictions = []
        if st.protocol:
            texts = [expect] if isinstance(expect, str) else list(expect or [])
            try:
                predictions = [parse_prediction(t, self.skel, st.variables) for t in texts]
            except PredictionError as e:
                st.ledger["rejected_edits"] += 1
                save(st, self.home)
                raise AxiomError(f"{e}\n{EXPECT_HELP}") from None
            if not predictions or not any(is_precise(p) for p in predictions):
                st.ledger["rejected_edits"] += 1
                save(st, self.home)
                why = "No expect given." if not predictions else "None of your predictions is precise."
                raise AxiomError(f"{why} {EXPECT_HELP}")
        before, states_before = rebuild(st, self.skel)
        try:
            clip = apply_command(self.skel, before, cmd)
        except CommandError as e:
            raise AxiomError(str(e)) from None
        states = evaluate_clip(self.skel, clip)
        frame = _prediction_frame(cmd)
        graded = []
        try:
            for p in predictions:
                new = evaluate_prediction(p, self.skel, clip, states, frame)
                old = evaluate_prediction(p, self.skel, before, states_before, frame)
                graded.append((p, new, new.measured != old.measured))
        except PredictionError as e:
            raise AxiomError(f"{e}\n{EXPECT_HELP}") from None
        if st.protocol and not _same_scene(states_before, states) and not any(
                changed and is_precise(p) for p, _, changed in graded):
            st.ledger["rejected_edits"] += 1
            save(st, self.home)
            raise AxiomError(
                "None of your precise predictions measures something this edit changes, so it can't show you "
                "understood the edit. Predict its effect, e.g. the moved point or angle at the edited frame "
                f"(@{frame}) or at another frame it affects. {EXPECT_HELP}"
            )

        key = hashlib.sha256(json.dumps(cmd, sort_keys=True, default=str).encode()).hexdigest()
        seen = key in st.sandbox_seen and not dry_run
        if dry_run:
            st.ledger["dry_runs"] = st.ledger.get("dry_runs", 0) + 1
            st.sandbox_seen = (st.sandbox_seen + [key])[-50:]
            lines = ["DRY RUN: nothing changed. To apply, repeat the call with dry_run=false."]
        else:
            st.commands.append(cmd)
            st.ledger["edits"] += 1
            if cmd["op"] == "batch":
                st.ledger["batches"] = st.ledger.get("batches", 0) + 1
            lines = [f"APPLIED: {_describe(cmd)}"]
        if graded:
            # A true prediction about something the edit didn't touch carries no information; it isn't counted.
            # Neither is one already graded on this exact edit in the sandbox.
            counted = [] if seen else [(p, o) for p, o, changed in graded if changed or not o.passed]
            st.ledger["predictions_total"] += len(counted)
            st.ledger["predictions_correct"] += sum(o.passed for _, o in counted)
            lines.append("PREDICTIONS (measured by the tool):")
            for p, o, changed in graded:
                if seen:
                    status = f"{'PASS' if o.passed else 'FAIL'} (seen in sandbox; not counted)"
                elif changed or not o.passed:
                    status = "PASS" if o.passed else "FAIL"
                else:
                    status = "UNCHANGED (true but not affected by this edit; not counted)"
                lines.append(f"  {status}  {p.text}   (measured: {o.measured})")
            failed = [p.text for p, o, _ in graded if not o.passed]
            if failed and dry_run:
                lines.append("Your prediction failed in the sandbox. Nothing was applied, so nothing is blocked.")
            elif failed:
                st.ledger["discrepancies"] += 1
                st.pending_discrepancy = {"command": len(st.commands) - 1, "failed": failed}
                lines.append(
                    "DISCREPANCY: the scene disagrees with your mental model. Before the next edit, call undo() "
                    "or accept_discrepancy(reason)."
                )
        notes = states[frame - states[0].frame].notes
        if notes:
            lines.append("NOTES: " + " | ".join(notes))
        lines += describe_diff(self.skel, get_task(st.task_id).kind, (before, states_before), (clip, states), frame)
        save(st, self.home)
        if dry_run:  # the status line describes the real, unchanged scene
            return ToolResult(self._finish_text(st, lines, before, states_before))
        return ToolResult(self._finish_text(st, lines, clip, states))

    @_locked
    def set_root(self, frame, forward=None, left=None, height=None, heading=None, expect=None,
                 dry_run: bool = False, session: str | None = None) -> ToolResult:
        cmd = {"op": "set_root", "frame": frame}
        cmd.update({k: v for k, v in (("forward", forward), ("left", left), ("height", height), ("heading", heading))
                    if v is not None})
        return self._edit(cmd, expect, session, dry_run)

    @_locked
    def set_pose(self, frame, angles: dict, expect=None, dry_run: bool = False, session: str | None = None) -> ToolResult:
        return self._edit({"op": "set_pose", "frame": frame, "angles": angles}, expect, session, dry_run)

    @_locked
    def plant_foot(self, side, start, end, forward=None, left=None, expect=None, dry_run: bool = False,
                   session: str | None = None) -> ToolResult:
        cmd = {"op": "plant_foot", "side": side, "start": start, "end": end}
        cmd.update({k: v for k, v in (("forward", forward), ("left", left)) if v is not None})
        return self._edit(cmd, expect, session, dry_run)

    @_locked
    def swing_foot(self, side, start, end, apex=0.08, expect=None, dry_run: bool = False,
                   session: str | None = None) -> ToolResult:
        return self._edit({"op": "swing_foot", "side": side, "start": start, "end": end, "apex": apex},
                          expect, session, dry_run)

    @_locked
    def batch(self, edits, expect=None, dry_run: bool = False, session: str | None = None) -> ToolResult:
        """Several edits applied together under one set of predictions; one undo reverts them all."""
        if not isinstance(edits, list) or not edits:
            raise AxiomError("batch needs a list of 1..40 edits, e.g. [{\"op\": \"plant_foot\", ...}, ...]")
        return self._edit({"op": "batch", "edits": edits}, expect, session, dry_run)

    # ---- recovery ------------------------------------------------------------------------------
    @_locked
    def undo(self, session: str | None = None) -> ToolResult:
        st = self._load(session)
        if st.phase == "DONE":
            raise AxiomError("Session is finished; start a new one.")
        if not st.commands:
            raise AxiomError("Nothing to undo.")
        cmd = st.commands.pop()
        st.pending_discrepancy = None
        st.ledger["undos"] += 1
        save(st, self.home)
        return ToolResult(self._finish_text(st, [f"UNDONE: {_describe(cmd)}"]))

    @_locked
    def accept_discrepancy(self, reason: str, session: str | None = None) -> ToolResult:
        st = self._load(session)
        if not st.pending_discrepancy:
            raise AxiomError("No failed prediction to accept.")
        if not isinstance(reason, str) or len(reason.strip()) < 3:
            raise AxiomError("Give a reason: why was your prediction wrong, and why is the edit still right?")
        failed = st.pending_discrepancy["failed"]
        st.pending_discrepancy = None
        st.ledger["accepted_discrepancies"] += 1
        save(st, self.home)
        return ToolResult(self._finish_text(st, [f"ACCEPTED (failed: {'; '.join(failed)}). Reason recorded: {reason.strip()}"]))

    # ---- ending --------------------------------------------------------------------------------
    @_locked
    def finish(self, claims=None, session: str | None = None) -> ToolResult:
        st = self._load(session)
        if st.phase == "DONE":
            raise AxiomError("Session is finished; start a new one.")
        if st.protocol and st.phase == "BRIEFING":
            raise AxiomError("Pass the briefing quiz first: call answer_quiz.")
        if st.protocol and st.pending_discrepancy:
            raise AxiomError("Resolve the failed prediction first: undo() or accept_discrepancy(reason).")
        claims = [claims] if isinstance(claims, str) else list(claims or [])
        clip, states = rebuild(st, self.skel)
        exam = run_exam(self.skel, clip, states, get_task(st.task_id), claims, st.protocol, st.variables)
        st.ledger["exam_attempts"] += 1
        st.ledger["task_success"] = exam.task_success
        if not st.protocol:
            st.phase = "DONE"
            save(st, self.home)
            return ToolResult("Session closed.")
        lines = ["EXAM:"]
        for r in exam.errors:
            lines.append(f"  [ERROR] {r.id}: {r.message}")
            lines.append(f"     hint: {r.hint}")
        lines += [f"  [WARNING] {r.id}: {r.message}" for r in exam.warnings]
        lines += [f"  {'PASS' if ok else 'FAIL'}  {cid}: {measured}" for cid, ok, measured in exam.criteria]
        for text, outcome, err in exam.claims:
            status = "UNREADABLE" if outcome is None else ("TRUE" if outcome.passed else "FALSE")
            lines.append(f"  claim {status}: {text}   ({err or outcome.measured})")
        lines += [f"  problem: {p}" for p in exam.problems]
        if exam.passed:
            st.phase = "DONE"
            st.ledger["certified"] = True
            lines.append("CERTIFIED: the tool measured every requirement and every claim as true.")
        else:
            st.ledger["certified"] = False
            lines.append("NOT CERTIFIED: fix the items above and call finish again. The task is not done.")
        save(st, self.home)
        return ToolResult(self._finish_text(st, lines, clip, states))

    @_locked
    def export(self, session: str | None = None) -> ToolResult:
        from axiom3d.export.gltf import export_glb

        st = self._load(session)
        clip, states = rebuild(st, self.skel)
        path = export_glb(self.skel, clip, states, self.home / "exports" / f"{st.id}.glb")
        return ToolResult(self._finish_text(st, [f"EXPORTED: {path} (glTF 2.0 binary; Y-up, opens in Blender)"], clip, states))

