"""Eval report: per-session ledgers, and success rates per model label and protocol mode."""

from __future__ import annotations

import json
from collections import defaultdict
from pathlib import Path

from axiom3d.protocol.ledger import calibration


def collect(home: Path) -> list[dict]:
    rows = []
    for path in sorted((Path(home) / "sessions").glob("*.json")):
        try:
            data = json.loads(path.read_text())
            rows.append({"session": data["id"], "phase": data["phase"], **data["ledger"]})
        except (json.JSONDecodeError, KeyError, TypeError):
            continue
    return rows


def _fmt(value) -> str:
    return "-" if value is None else ("yes" if value is True else "no" if value is False else str(value))


def render_report(rows: list[dict]) -> str:
    lines = [f"{'label':12} {'task':15} {'protocol':8} {'certified':9} {'success':7} {'calibration':11} "
             f"{'predictions':11} {'discrep':7} {'rejected':8} {'edits':5}"]
    for r in rows:
        cal = calibration(r)
        lines.append(
            f"{_fmt(r['label']):12} {r['task']:15} {'on' if r['protocol'] else 'off':8} {_fmt(r['certified']):9} "
            f"{_fmt(r['task_success']):7} {'-' if cal is None else f'{cal:.2f}':11} "
            f"{r['predictions_correct']}/{r['predictions_total']:<9} {r['discrepancies']:<7} {r['rejected_edits']:<8} {r['edits']:<5}"
        )
    groups: dict[tuple, list[dict]] = defaultdict(list)
    for r in rows:
        groups[(_fmt(r["label"]), "on" if r["protocol"] else "off")].append(r)
    lines.append("")
    lines.append("SUMMARY (task success = every check and criterion passes, measured by the tool):")
    for (label, mode), group in sorted(groups.items()):
        ok = sum(r["task_success"] is True for r in group)
        cals = [c for c in (calibration(r) for r in group) if c is not None]
        mean_cal = f"{sum(cals) / len(cals):.2f}" if cals else "-"
        lines.append(f"  {label:12} protocol={mode:3} success {ok}/{len(group)}  mean calibration {mean_cal}")
    return "\n".join(lines)
