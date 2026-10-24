import json

import pytest

from axiom3d.cli import main
from axiom3d.eval.agents import correct_script, naive_script, run_script
from axiom3d.eval.report import collect, render_report
from axiom3d.session_store import load
from axiom3d.tasks.library import TASKS


@pytest.mark.parametrize("tid", list(TASKS))
def test_correct_agent_certified(home, tid):
    sid, transcript = run_script(correct_script(tid), home, protocol=True, label="correct")
    st = load(sid, home)
    assert st.phase == "DONE" and st.ledger["certified"] is True, transcript[-3:]
    assert st.ledger["predictions_correct"] == st.ledger["predictions_total"] > 0


def test_naive_caught_with_protocol(home):
    sid, transcript = run_script(naive_script("step_forward"), home, protocol=True, label="naive")
    st = load(sid, home)
    assert st.ledger["discrepancies"] >= 1 and st.ledger["certified"] is False and st.phase == "WORKING"
    exam = transcript[-1]
    for check_id in ("anatomy.joint_limits", "gait.step_direction", "gait.foot_slide"):
        assert check_id in exam, check_id


def test_naive_walk_fails_exam(home):
    sid, transcript = run_script(naive_script("walk_forward"), home, protocol=True, label="naive")
    assert load(sid, home).ledger["certified"] is False
    gait_errors = {w.split(":")[0].split()[-1] for w in transcript[-1].splitlines() if "[ERROR] gait." in w}
    assert len(gait_errors) >= 2, transcript[-1]


def test_naive_turn_fails_exam(home):
    sid, _ = run_script(naive_script("turn_then_step"), home, protocol=True, label="naive")
    assert load(sid, home).ledger["certified"] is False


def test_bare_mode_naive_done_but_unsuccessful(home):
    sid, _ = run_script(naive_script("step_forward"), home, protocol=False, label="naive")
    st = load(sid, home)
    assert st.phase == "DONE" and st.ledger["task_success"] is False and st.ledger["certified"] is None


def test_report_rates(home, capsys):
    run_script(correct_script("step_forward"), home, protocol=True, label="correct")
    run_script(naive_script("step_forward"), home, protocol=True, label="naive")
    run_script(naive_script("step_forward"), home, protocol=False, label="naive")
    rows = collect(home)
    assert len(rows) == 3
    text = render_report(rows)
    assert "naive" in text and "correct" in text and "success" in text
    assert "1/1" in text and "0/1" in text
    assert main(["eval", "report", "--home", str(home)]) == 0
    assert "calibration" in capsys.readouterr().out


def test_report_skips_unreadable_files(home):
    run_script(correct_script("step_forward"), home, protocol=True, label="correct")
    (home / "sessions" / "junk.json").write_text("{bad")
    assert len(collect(home)) == 1
    assert json.loads(json.dumps(collect(home)))  # rows are plain data
