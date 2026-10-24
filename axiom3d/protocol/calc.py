"""The scene calculator: exact math on the scene, so the model never has to invent a number.

A small language parsed with Python's `ast` and walked against a whitelist; nothing is ever
executed. `left_toe@12` reads a point at frame 12 (`@` means "at frame").
"""

from __future__ import annotations

import ast
import difflib
import math
import re
from dataclasses import dataclass

import numpy as np

from axiom3d.conventions import FORWARD0, LEFT0, UP, character_axes, track_to_world, world_to_track

MAX_SOURCE = 500
MAX_DEPTH = 40
MAX_EXPONENT = 10
MAX_MAGNITUDE = 1e6
MAX_VARIABLES = 50
_NAME = re.compile(r"[a-z_][a-z0-9_]*")
_ROOT_ATTRS = ("x", "y", "z", "height", "forward", "left", "heading")
_POINT_ATTRS = ("x", "y", "z", "height", "forward", "left")


class CalcError(ValueError):
    pass


@dataclass
class CalcResult:
    lines: list[str]
    assigned: dict[str, float | list[float]]


def _fmt(value) -> str:
    if isinstance(value, np.ndarray):
        return "[" + ", ".join(f"{v:.3f}" for v in value) + "]"
    return f"{value:.3f}"


class _Calc:
    def __init__(self, skel, clip, states, variables: dict):
        self.skel, self.clip, self.states = skel, clip, states
        self.first, self.last = states[0].frame, states[-1].frame
        self.vars = {k: (np.asarray(v, dtype=float) if isinstance(v, list) else float(v)) for k, v in variables.items()}
        d = skel.dims
        self.consts = {
            "thigh": d["thigh"], "shank": d["shank"], "leg": d["thigh"] + d["shank"], "ankle_height": d["ankle_height"],
            "pelvis_height": d["pelvis_height"], "hip_half_width": d["hip_half_width"], "foot_length": d["foot_length"],
            "fps": float(clip.timeline.fps), "start": float(self.first), "end": float(self.last), "pi": math.pi,
            "FORWARD0": FORWARD0.copy(), "LEFT0": LEFT0.copy(), "UP": UP.copy(),
        }
        self.points = set(skel.point_names())
        self.funcs = {
            "dist": self._dist, "angle": self._angle, "vec": lambda a, b: self._vec(b) - self._vec(a),
            "dot": lambda a, b: float(self._vec(a) @ self._vec(b)),
            "cross": lambda a, b: np.cross(self._vec(a), self._vec(b)),
            "norm": lambda v: float(np.linalg.norm(self._vec(v))), "unit": self._unit,
            "proj": lambda v, axis: float(self._vec(v) @ self._unit(axis)),
            "lerp": lambda a, b, t: a + self._num(t) * (b - a),
            "clamp": lambda x, lo, hi: min(max(self._num(x), self._num(lo)), self._num(hi)),
            "sin": lambda d_: math.sin(math.radians(self._num(d_))), "cos": lambda d_: math.cos(math.radians(self._num(d_))),
            "tan": lambda d_: math.tan(math.radians(self._num(d_))),
            "asin": lambda x: math.degrees(math.asin(self._unit_range(x))),
            "acos": lambda x: math.degrees(math.acos(self._unit_range(x))),
            "atan2": lambda y, x: math.degrees(math.atan2(self._num(y), self._num(x))),
            "sqrt": self._sqrt, "abs": lambda x: np.abs(x) if isinstance(x, np.ndarray) else abs(self._num(x)),
            "min": lambda *xs: min(self._num(x) for x in xs), "max": lambda *xs: max(self._num(x) for x in xs),
            "round": lambda x, n=0: round(self._num(x), int(self._num(n))),
            "track": self._track, "char": self._char, "world_from_track": self._world_from_track,
            "reach": self._reach, "knee_needed": self._knee_needed,
        }
        self.reserved = set(self.consts) | set(self.funcs) | self.points | {"root"}

    # ---- value helpers -------------------------------------------------------------------
    def _num(self, x) -> float:
        if isinstance(x, np.ndarray):
            raise CalcError("expected a number, got a vector")
        return float(x)

    def _vec(self, v) -> np.ndarray:
        if not isinstance(v, np.ndarray):
            raise CalcError("expected a point or vector, got a number")
        return v

    def _unit(self, v) -> np.ndarray:
        v = self._vec(v)
        n = np.linalg.norm(v)
        if n < 1e-12:
            raise CalcError("unit() of a zero vector")
        return v / n

    def _unit_range(self, x) -> float:
        x = self._num(x)
        if not -1.0 <= x <= 1.0:
            raise CalcError(f"asin/acos need a value in -1..1, got {x:.3f}")
        return x

    def _sqrt(self, x) -> float:
        x = self._num(x)
        if x < 0:
            raise CalcError(f"sqrt of a negative number ({x:.3f})")
        return math.sqrt(x)

    def _dist(self, a, b) -> float:
        return float(np.linalg.norm(self._vec(a) - self._vec(b)))

    def _angle(self, a, b, c) -> float:
        ba, bc = self._vec(a) - self._vec(b), self._vec(c) - self._vec(b)
        na, nc = np.linalg.norm(ba), np.linalg.norm(bc)
        if na < 1e-12 or nc < 1e-12:
            raise CalcError("angle() needs three distinct points")
        return math.degrees(math.acos(float(np.clip(ba @ bc / (na * nc), -1.0, 1.0))))

    def _track(self, p) -> np.ndarray:
        p = self._vec(p)
        f, l = world_to_track(self.clip.track, p[:2])
        return np.array([f, l, p[2]])

    def _world_from_track(self, t) -> np.ndarray:
        t = self._vec(t)
        x, y = track_to_world(self.clip.track, t[0], t[1])
        return np.array([x, y, t[2]])

    def _char(self, v, frame) -> np.ndarray:
        state = self._state(frame)
        f, l, u = character_axes(state.heading_deg)
        v = self._vec(v)
        return np.array([v @ f, v @ l, v @ u])

    def _reach(self, h) -> float:
        leg = self.consts["leg"]
        drop = self._num(h) - self.consts["ankle_height"]
        return math.sqrt(max(0.0, leg * leg - drop * drop))

    def _knee_needed(self, h, horizontal) -> float:
        a, b = self.consts["thigh"], self.consts["shank"]
        length = math.hypot(self._num(horizontal), self._num(h) - self.consts["ankle_height"])
        if length > a + b:
            raise CalcError(f"unreachable: short by {length - a - b:.3f} m")
        cos_k = (a * a + b * b - length * length) / (2 * a * b)
        return 180.0 - math.degrees(math.acos(max(-1.0, min(1.0, cos_k))))

    def _state(self, frame):
        f = self._num(frame)
        if f != int(f) or not self.first <= f <= self.last:
            raise CalcError(f"frame must be a whole number in {self.first}..{self.last}, got {frame}")
        return self.states[int(f) - self.first]

    def _check(self, value):
        arr = np.atleast_1d(np.asarray(value, dtype=float))
        if not np.all(np.isfinite(arr)) or np.any(np.abs(arr) > MAX_MAGNITUDE):
            raise CalcError(f"value out of range (|x| must be <= {MAX_MAGNITUDE:g})")
        return value

    # ---- scene references --------------------------------------------------------------------
    def _ref(self, node, frame):
        """Value of a scene reference at `frame`, or None if `node` is not a scene reference."""
        if isinstance(node, ast.Name) and node.id in self.points and node.id not in self.vars:
            return self._state(frame).points[node.id].copy()
        if isinstance(node, ast.Attribute) and isinstance(node.value, ast.Name):
            base, attr = node.value.id, node.attr
            state = self._state(frame)
            if base == "root":
                if attr not in _ROOT_ATTRS:
                    raise CalcError(f"root has {', '.join(_ROOT_ATTRS)}; got root.{attr}")
                return self._component(state.root_position, attr, state)
            channel = f"{base}.{attr}"
            if channel in state.angles:
                return float(state.angles[channel])
            if base in self.points and base not in self.vars:
                if attr not in _POINT_ATTRS:
                    raise CalcError(f"points have {', '.join(_POINT_ATTRS)}; got {base}.{attr}")
                return self._component(state.points[base], attr, state)
        return None

    def _component(self, p, attr: str, state) -> float:
        if attr == "heading":
            return float(state.heading_deg)
        if attr in ("forward", "left"):
            f, l = world_to_track(self.clip.track, p[:2])
            return f if attr == "forward" else l
        return float(p[2] if attr == "height" else p["xyz".index(attr)])

    def _suggest(self, name: str) -> str:
        pool = sorted(self.vars) + sorted(self.consts) + sorted(self.funcs) + sorted(self.points) + self.skel.channels()
        close = difflib.get_close_matches(name, pool, n=8, cutoff=0.5)
        return f"; closest: {', '.join(close)}" if close else ""

    # ---- evaluation ----------------------------------------------------------------------------
    def eval(self, node, depth: int = 0):
        if depth > MAX_DEPTH:
            raise CalcError(f"expression nested too deeply (max {MAX_DEPTH})")
        return self._check(self._eval(node, depth + 1))

    def _eval(self, node, depth: int):
        if isinstance(node, ast.Constant):
            if isinstance(node.value, bool) or not isinstance(node.value, (int, float)):
                raise CalcError("only numbers are allowed as literals")
            return float(node.value)
        if isinstance(node, ast.List):
            if len(node.elts) != 3:
                raise CalcError("vectors have exactly 3 numbers: [x, y, z]")
            return np.array([self._num(self.eval(e, depth)) for e in node.elts])
        if isinstance(node, (ast.Name, ast.Attribute)):
            ref = self._ref(node, self.last)
            if ref is not None:
                return ref
            if isinstance(node, ast.Name):
                if node.id in self.vars:
                    return self.vars[node.id]
                if node.id in self.consts:
                    return self.consts[node.id]
                raise CalcError(f"unknown name {node.id!r}{self._suggest(node.id)}")
            if node.attr in ("x", "y", "z"):
                return float(self._vec(self.eval(node.value, depth))["xyz".index(node.attr)])
            label = f"{node.value.id}.{node.attr}" if isinstance(node.value, ast.Name) else node.attr
            raise CalcError(f"unknown attribute {label!r}{self._suggest(label)}")
        if isinstance(node, ast.UnaryOp) and isinstance(node.op, (ast.USub, ast.UAdd)):
            v = self.eval(node.operand, depth)
            return -v if isinstance(node.op, ast.USub) else v
        if isinstance(node, ast.BinOp):
            if isinstance(node.op, ast.MatMult):
                frame = self.eval(node.right, depth)
                ref = self._ref(node.left, frame)
                if ref is None:
                    raise CalcError("@ means 'at frame' and needs a point, channel or root value on its left")
                return ref
            return self._binop(node.op, self.eval(node.left, depth), self.eval(node.right, depth))
        if isinstance(node, ast.Call):
            if not isinstance(node.func, ast.Name) or node.func.id not in self.funcs:
                name = node.func.id if isinstance(node.func, ast.Name) else "?"
                raise CalcError(f"unknown function {name!r}; functions: {', '.join(sorted(self.funcs))}")
            if node.keywords:
                raise CalcError("functions take positional arguments only")
            args = [self.eval(a, depth) for a in node.args]
            try:
                return self.funcs[node.func.id](*args)
            except TypeError:
                raise CalcError(f"wrong number of arguments for {node.func.id}()") from None
        raise CalcError(f"{type(node).__name__} is not allowed here")

    def _binop(self, op, a, b):
        vec_a, vec_b = isinstance(a, np.ndarray), isinstance(b, np.ndarray)
        if isinstance(op, ast.Add) or isinstance(op, ast.Sub):
            if vec_a != vec_b:
                raise CalcError("can't add a number and a vector")
            return a + b if isinstance(op, ast.Add) else a - b
        if isinstance(op, ast.Mult):
            if vec_a and vec_b:
                raise CalcError("use dot() or cross() to multiply two vectors")
            return a * b
        if isinstance(op, ast.Div):
            if vec_b:
                raise CalcError("can't divide by a vector")
            if b == 0:
                raise CalcError("division by zero")
            return a / b
        if isinstance(op, (ast.Pow, ast.Mod)):
            a, b = self._num(a), self._num(b)
            if isinstance(op, ast.Mod):
                if b == 0:
                    raise CalcError("modulo by zero")
                return a % b
            if abs(b) > MAX_EXPONENT:
                raise CalcError(f"exponent too large (max {MAX_EXPONENT})")
            if a == 0 and b < 0:
                raise CalcError("division by zero")
            return float(a ** b)
        raise CalcError(f"operator {type(op).__name__} is not allowed")


def run_calc(source: str, skel, clip, states, variables: dict) -> CalcResult:
    if not isinstance(source, str) or not source.strip():
        raise CalcError("give an expression, e.g. dist(left_ankle@24, pelvis@24)")
    if len(source) > MAX_SOURCE:
        raise CalcError(f"expression too long (max {MAX_SOURCE} characters)")
    try:
        tree = ast.parse(source, mode="exec")
    except (SyntaxError, ValueError, RecursionError, MemoryError) as e:
        raise CalcError(f"can't parse: {getattr(e, 'msg', e)}") from None
    calc = _Calc(skel, clip, states, variables)
    lines, assigned = [], {}
    for stmt in tree.body:
        if isinstance(stmt, ast.Expr):
            lines.append(f"= {_fmt(calc.eval(stmt.value))}")
        elif isinstance(stmt, ast.Assign):
            if len(stmt.targets) != 1 or not isinstance(stmt.targets[0], ast.Name):
                raise CalcError("assign one name at a time: name = expression")
            name = stmt.targets[0].id
            if not _NAME.fullmatch(name):
                raise CalcError(f"variable names are lowercase letters, digits and _: got {name!r}")
            if name in calc.reserved:
                raise CalcError(f"{name!r} is a built-in name; pick another")
            if name not in calc.vars and len(set(calc.vars) | {name}) > MAX_VARIABLES:
                raise CalcError(f"too many variables (max {MAX_VARIABLES})")
            value = calc.eval(stmt.value)
            calc.vars[name] = value
            assigned[name] = [float(v) for v in value] if isinstance(value, np.ndarray) else float(value)
            lines.append(f"{name} = {_fmt(value)}")
        else:
            raise CalcError(f"{type(stmt).__name__} is not allowed; use expressions and name = expression")
    return CalcResult(lines, assigned)
