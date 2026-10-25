import json

from axiom3d.api import Workbench
from axiom3d.eval.blocks import grade_home, grade_json
from axiom3d.tasks.library import CREEPER
from axiom3d.tasks.reference import reference_commands

REF = reference_commands("minecraft_creeper")


def test_home_grade_of_the_reference_passes_every_criterion(home):
    wb = Workbench(home, protocol=False)
    wb.start_session("minecraft_creeper")
    wb.batch(REF)
    row = grade_home(home)
    assert row["passed"] == len(CREEPER) == row["total"] == 12 and row["phase"] == "WORKING"
    assert row["batches"] == 1 and [b.name for b in row["model"].boxes][-1] == "head"


def test_json_grade_of_the_reference_passes_every_criterion(tmp_path):
    path = tmp_path / "creeper.json"
    path.write_text(json.dumps(REF))
    row = grade_json(path)
    assert row["passed"] == 12 and row["replay_error"] is None


def test_bad_files_give_error_rows_and_a_bad_command_grades_what_was_built(tmp_path):
    assert "no such file" in grade_json(tmp_path / "nope.json")["error"]
    broken = tmp_path / "broken.json"
    broken.write_text("[{]")
    assert "not valid JSON" in grade_json(broken)["error"]
    partial = tmp_path / "partial.json"
    partial.write_text(json.dumps(REF[:5] + [dict(REF[5], high=[4, 4, 18])] + REF[6:]))  # a flat head
    row = grade_json(partial)
    assert row["replay_error"].startswith("command #6") and len(row["model"].boxes) == 5
    assert row["passed"] < 12


def test_empty_home_is_an_error_row(tmp_path):
    assert "no session" in grade_home(tmp_path / "empty")["error"]
