"""The ledger: what a model did in a session, and how often its predictions were right."""

from __future__ import annotations


def new_ledger(label: str | None, task: str, protocol: bool) -> dict:
    return {
        "label": label,
        "task": task,
        "protocol": protocol,
        "quiz_attempts": 0,
        "quiz_passed": False,
        "edits": 0,
        "rejected_edits": 0,
        "predictions_total": 0,
        "predictions_correct": 0,
        "discrepancies": 0,
        "undos": 0,
        "accepted_discrepancies": 0,
        "exam_attempts": 0,
        "certified": None,
        "task_success": None,
    }


def calibration(ledger: dict) -> float | None:
    """Share of predictions the tool measured as correct; None before any prediction."""
    total = ledger.get("predictions_total", 0)
    return None if total == 0 else ledger["predictions_correct"] / total
