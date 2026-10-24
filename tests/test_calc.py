import time

import numpy as np
import pytest

from axiom3d.anim.commands import apply_command
from axiom3d.anim.evaluate import evaluate_clip
from axiom3d.protocol.calc import CalcError, run_calc
from axiom3d.tasks.library import get_task, new_clip
from axiom3d.tasks.reference import reference_commands


@pytest.fixture(scope="module")
def step(skel):
    clip = new_clip(get_task("step_forward"), skel)
    for c in reference_commands("step_forward"):
        clip = apply_command(skel, clip, c)
    return clip, evaluate_clip(skel, clip)


def calc(skel, step, source, variables=None):
    return run_calc(source, skel, step[0], step[1], variables or {})


def test_scene_values(skel, step):
    r = calc(skel, step, "stride = dist(left_ankle@24, left_ankle@0); h = left_hip.flexion@0")
    assert abs(r.assigned["stride"] - 0.36) < 1e-6
    assert r.lines[0] == "stride = 0.360"
    assert set(r.assigned) == {"stride", "h"}


def test_points_default_to_last_frame(skel, step):
    r = calc(skel, step, "left_ankle.z; root.forward; root.heading@12")
    assert r.lines == ["= 0.068", "= 0.180", "= 0.000"]


def test_track_char_and_world(skel, step):
    r = calc(skel, step, "t = track(left_ankle@24); c = char(vec(pelvis@24, left_toe@24), 24); w = world_from_track([0.36, 0.0875, 0])")
    assert np.allclose(r.assigned["t"], [0.36, 0.0875, 0.06825], atol=1e-4)
    assert r.assigned["c"][0] > 0.2
    assert np.allclose(r.assigned["w"], [0.0875, -0.36, 0.0], atol=1e-9)


def test_vector_math_and_functions(skel, step):
    r = calc(skel, step, "v = [3, 4, 0]; n = norm(v); a = angle([1,0,0], [0,0,0], [0,1,0]); s = sin(30); q = atan2(1, 1); u = unit(v).x")
    assert r.assigned["n"] == 5 and abs(r.assigned["a"] - 90) < 1e-9
    assert abs(r.assigned["s"] - 0.5) < 1e-12 and abs(r.assigned["q"] - 45) < 1e-9 and abs(r.assigned["u"] - 0.6) < 1e-12


def test_reach_matches_ik(skel, step):
    r = calc(skel, step, "r = reach(0.89); k = knee_needed(0.92, 0)")
    assert abs(r.assigned["r"] - 0.2512) < 1e-3 and abs(r.assigned["k"] - 15) < 1
    with pytest.raises(CalcError, match="unreachable"):
        calc(skel, step, "knee_needed(0.92, 0.5)")


def test_variables_carry(skel, step):
    assert calc(skel, step, "s * 2", {"s": 0.5}).lines == ["= 1.000"]


def test_frame_out_of_range(skel, step):
    with pytest.raises(CalcError, match="0..24"):
        calc(skel, step, "left_toe@99")


def test_unknown_name_suggests(skel, step):
    with pytest.raises(CalcError, match="left_toe"):
        calc(skel, step, "left_tow.z")


@pytest.mark.parametrize("bad", [
    "__import__('os')", "left_toe.__class__", "(lambda: 1)()", "[x for x in [1]]", "9**9**9",
    "-(" * 100 + "1" + ")" * 100, "a" * 10001, "open('f')", "x = 1; x.y = 2", "pelvis = 3",
    "1e7 * 1e7", "[1, 2] @ 3", "'text'", "Sin = 1", "a = b = 1",
])
def test_hostile_input_rejected(skel, step, bad):
    t0 = time.perf_counter()
    with pytest.raises(CalcError):
        calc(skel, step, bad)
    assert time.perf_counter() - t0 < 1.0


def test_variable_limit(skel, step):
    many = {f"v{i}": 1.0 for i in range(50)}
    with pytest.raises(CalcError, match="50"):
        calc(skel, step, "extra = 1", many)
