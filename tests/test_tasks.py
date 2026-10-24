import pytest

from axiom3d.anim.commands import apply_command
from axiom3d.anim.evaluate import evaluate_clip
from axiom3d.tasks.library import TASKS, get_task, new_clip
from axiom3d.tasks.reference import reference_commands


def solve(skel, tid, cmds):
    task = get_task(tid)
    clip = new_clip(task, skel)
    for c in cmds:
        clip = apply_command(skel, clip, c)
    return task, clip, evaluate_clip(skel, clip)


@pytest.mark.parametrize("tid", list(TASKS))
def test_reference_meets_criteria(skel, tid):
    task, clip, states = solve(skel, tid, reference_commands(tid))
    for crit in task.criteria:
        ok, measured = crit.fn(skel, clip, states)
        assert ok, (tid, crit.id, measured)


def test_doing_nothing_fails_criteria(skel):
    task, clip, states = solve(skel, "step_forward", [])
    results = {c.id: c.fn(skel, clip, states)[0] for c in task.criteria}
    assert results["left_step_length"] is False


def test_get_task_unknown_lists_ids():
    with pytest.raises(KeyError, match="walk_forward"):
        get_task("moonwalk")


def test_task_shapes():
    assert get_task("walk_forward").timeline.end == 48
    assert get_task("turn_then_step").timeline.end == 36
    assert all(t.goal and t.criteria for t in TASKS.values())
