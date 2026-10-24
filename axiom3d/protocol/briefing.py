"""The entry quiz: the model proves it knows the frame before it may edit.

Every answer is computed from the rig and geometry, never typed in, so the quiz
can't drift from what the tool actually does. Seeds vary the numbers.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from axiom3d.anim.evaluate import evaluate_frame
from axiom3d.conventions import character_axes
from axiom3d.rig.skeleton import forward_kinematics

# (channel, angle, point whose motion the question asks about)
Q4_OPTIONS = (
    ("left_hip.flexion", 30.0, "left_toe"),
    ("left_knee.flexion", 45.0, "left_ankle"),
    ("left_elbow.flexion", 60.0, "left_hand"),
    ("left_hip.abduction", 20.0, "left_ankle"),
    ("right_hip.abduction", 20.0, "right_ankle"),
)
AXES = {"+X": (1, 0, 0), "-X": (-1, 0, 0), "+Y": (0, 1, 0), "-Y": (0, -1, 0)}


@dataclass(frozen=True)
class Question:
    id: str
    text: str
    kind: str  # "choice" | "number"
    choices: tuple[str, ...] | None
    answer: str
    tolerance: float | None
    explanation: str


@dataclass
class QuizResult:
    passed: bool
    results: list[tuple[str, bool, str]]


def _nearest_axis(v) -> str:
    return max(AXES, key=lambda k: float(np.dot(AXES[k], v)))


def _direction(skel, root, heading, channel: str, angle: float, point: str) -> str:
    joint, dof = channel.split(".")
    _, before = forward_kinematics(skel, root, heading, {})
    _, after = forward_kinematics(skel, root, heading, {joint: skel.angles_to_quat(joint, {dof: angle})})
    forward, left, _ = character_axes(heading)
    d = after[point] - before[point]
    fw, lf = float(d @ forward), float(d @ left)
    if abs(fw) >= abs(lf):
        return "front" if fw > 0 else "back"
    return "left" if lf > 0 else "right"


def make_quiz(skel, clip, seed: int) -> list[Question]:
    rng = np.random.default_rng(seed)
    start = evaluate_frame(skel, clip, clip.timeline.start)
    h = start.heading_deg
    forward, left, _ = character_axes(h)
    pelvis = start.points["pelvis"]

    face = _nearest_axis(forward)
    side = _nearest_axis(left)
    q1 = Question("q1", f"At frame {start.frame} (heading {h:g} deg), which world axis does the mannequin face?",
                  "choice", tuple(AXES), face, None,
                  f"Forward at heading h is (sin h, -cos h, 0); at heading {h:g} that is {face}. At heading 0 it is -Y.")
    q2 = Question("q2", "Which world axis points to the mannequin's LEFT?", "choice", tuple(AXES), side, None,
                  f"Left is forward turned +90 deg about Z: (cos h, sin h, 0) = {side} here.")

    f_off = float(rng.uniform(0.1, 0.5)) * (1 if rng.random() < 0.5 else -1)
    l_off = float(rng.uniform(-0.5, 0.5))
    pt = pelvis[:2] + f_off * forward[:2] + l_off * left[:2]
    where = "in_front" if f_off > 0 else "behind"
    q3 = Question(
        "q3",
        f"A point is at world ({pt[0]:.2f}, {pt[1]:.2f}, 0.00). The pelvis is at world "
        f"({pelvis[0]:.2f}, {pelvis[1]:.2f}, {pelvis[2]:.2f}). Is the point in_front or behind the pelvis?",
        "choice", ("in_front", "behind"), where, None,
        f"(point - pelvis) . forward = {f_off:+.2f} m, using forward = {face}. Positive means in front.",
    )

    channel, angle, point = Q4_OPTIONS[int(rng.integers(len(Q4_OPTIONS)))]
    move = _direction(skel, start.root_position, h, channel, angle, point)
    q4 = Question(
        "q4",
        f"Starting from rest, you set {channel} to +{angle:g}. Which way does {point} move, "
        "relative to the mannequin: front, back, left or right?",
        "choice", ("front", "back", "left", "right"), move, None,
        "Positive anatomical angle = the anatomical motion: hip, shoulder and elbow flexion move the limb "
        "forward; knee flexion moves the foot backward; abduction moves the limb away from the midline.",
    )

    theta = int(rng.choice(np.arange(15, 61, 5)))
    y = float(np.sin(np.radians(theta)))
    q5 = Question(
        "q5",
        f"A bone of length 1 points straight down, from (0, 0, 0) to (0, 0, -1). Rotate it +{theta} degrees about "
        "the world +X axis (right-hand rule). What is the y coordinate of its tip? Answer with 2 decimals.",
        "number", None, f"{y:.4f}", 0.02,
        f"y' = y*cos(t) - z*sin(t) = -(-1)*sin({theta}) = {y:.2f}. The tip moves toward +Y, which is BACKWARD "
        "at heading 0: a positive raw X rotation swings a hanging leg backward.",
    )
    return [q1, q2, q3, q4, q5]


_SYNONYMS = {
    "front": "front", "forward": "front", "forwards": "front", "in front": "front",
    "back": "back", "backward": "back", "backwards": "back", "behind": "back",
    "left": "left", "right": "right",
    "in_front": "in_front", "in front": "in_front", "infront": "in_front", "front_of": "in_front",
}


def _norm_choice(question: Question, raw: str) -> str:
    a = str(raw).strip().replace("−", "-").lower()
    if question.choices and question.choices[0] in AXES:
        a = a.replace(" ", "")
        if a in ("x", "y"):
            a = "+" + a
        return a.upper()
    if question.id == "q3":
        return {"front": "in_front", "in front": "in_front", "in_front": "in_front", "infront": "in_front",
                "behind": "behind", "back": "behind"}.get(a, a)
    return _SYNONYMS.get(a, a)


def grade_quiz(questions: list[Question], answers: dict[str, str]) -> QuizResult:
    results = []
    for q in questions:
        raw = answers.get(q.id)
        if raw is None:
            results.append((q.id, False, f"no answer. {q.explanation}"))
            continue
        if q.kind == "number":
            try:
                ok = abs(float(str(raw).replace("−", "-")) - float(q.answer)) <= q.tolerance
            except ValueError:
                ok = False
        else:
            ok = _norm_choice(q, raw) == q.answer
        results.append((q.id, ok, "correct" if ok else f"wrong. {q.explanation}"))
    return QuizResult(all(r[1] for r in results), results)
