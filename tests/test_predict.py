import pytest

from axiom3d.anim.commands import apply_command
from axiom3d.anim.evaluate import evaluate_clip
from axiom3d.protocol.predict import PredictionError, evaluate_prediction, is_precise, parse_prediction
from axiom3d.tasks.library import get_task, new_clip
from axiom3d.tasks.reference import reference_commands


@pytest.fixture(scope="module")
def step(skel):
    clip = new_clip(get_task("step_forward"), skel)
    for c in reference_commands("step_forward"):
        clip = apply_command(skel, clip, c)
    return clip, evaluate_clip(skel, clip)


def check(skel, step, text, default_frame=24):
    clip, states = step
    return evaluate_prediction(parse_prediction(text, skel), skel, clip, states, default_frame)


def test_variants_parse_identically(skel):
    texts = ["left_toe.forward ~= 0.36 ± 0.05", "LEFT_TOE.forward ~= 0.36 +- 0.05", "left_toe.forward~=0.36+/-0.05"]
    parsed = [parse_prediction(t, skel) for t in texts]
    assert all(p == parsed[0] for p in parsed[1:])
    assert parsed[1].text == texts[1]


def test_unicode_minus(skel):
    assert parse_prediction("left_hip.flexion in [−10, 10]", skel) == parse_prediction("left_hip.flexion in [-10, 10]", skel)


def test_precision_rules(skel):
    assert is_precise(parse_prediction("left_toe.x ~= 0.1 ± 0.1", skel))
    assert not is_precise(parse_prediction("left_toe.x < 1000", skel))
    assert not is_precise(parse_prediction("left_hip.flexion ~= 30 ± 45", skel))
    assert is_precise(parse_prediction("left_hip.flexion ~= 30 ± 15", skel))
    assert is_precise(parse_prediction("left_toe in_front_of pelvis", skel))
    assert is_precise(parse_prediction("slide(right_heel) < 0.02", skel))
    assert not is_precise(parse_prediction("slide(right_heel) < 0.5", skel))
    assert not is_precise(parse_prediction("root.forward in [0, 5]", skel))


def test_evaluate_against_step_reference(skel, step):
    assert check(skel, step, "left_toe.forward@24 ~= 0.56 ± 0.03").passed
    assert check(skel, step, "left_ankle.forward ~= 0.36 ± 0.01").passed  # default frame 24
    out = check(skel, step, "left_toe behind pelvis @24")
    assert not out.passed and "in front of" in out.measured
    assert check(skel, step, "left_toe in_front_of pelvis").passed
    assert check(skel, step, "root.forward@24 ~= 0.18 ± 0.01").passed
    assert check(skel, step, "root.heading ~= 0 ± 1").passed


def test_frame_ranges_and_metrics(skel, step):
    assert check(skel, step, "right_heel on_ground @all").passed
    assert not check(skel, step, "left_heel on_ground @0..24").passed
    assert check(skel, step, "slide(right_heel) < 0.02").passed
    assert check(skel, step, "max_height(left_ankle) ~= 0.148 ± 0.01").passed
    assert check(skel, step, "left_toe.z < right_toe.z @12").passed is False


def test_channel_subject(skel, step):
    assert check(skel, step, "right_knee.flexion in [0, 40] @0..24").passed


def test_unknown_name_suggests(skel):
    with pytest.raises(PredictionError, match="left_toe"):
        parse_prediction("left_tow.x < 1", skel)
    with pytest.raises(PredictionError, match="left_hip.flexion"):
        parse_prediction("left_hip.flex ~= 10 ± 5", skel)


def test_malformed_and_no_eval(skel):
    for bad in ["__import__('os').x < 1", "left_toe.x", "left_toe.x ~= 0.1", "", "left_toe.x in [1]", "left_toe.x < 1 @2 @3"]:
        with pytest.raises(PredictionError):
            parse_prediction(bad, skel)


def test_frame_outside_timeline(skel, step):
    with pytest.raises(PredictionError, match="0..24"):
        check(skel, step, "left_toe.z < 0.1 @99")


def test_self_comparisons_rejected(skel):
    # Review I3: tautologies used to count as precise predictions.
    for bad in ["pelvis.z >= pelvis.z", "left_hip.flexion <= left_hip.flexion", "left_toe in_front_of left_toe"]:
        with pytest.raises(PredictionError, match="itself"):
            parse_prediction(bad, skel)
