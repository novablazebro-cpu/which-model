"""Command line: run the MCP server, or call any tool directly with JSON arguments."""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

from axiom3d.api import AxiomError, Workbench
from axiom3d.session_store import current_id
from axiom3d.tasks.library import TASKS

TOOLS = ("start_session", "answer_quiz", "guide", "observe", "check", "calc", "set_root", "set_pose", "plant_foot",
         "swing_foot", "batch", "undo", "accept_discrepancy", "finish", "export")
NO_SESSION = ("start_session", "guide")


def _home(value: str | None) -> Path:
    # Expand "~" ourselves: MCP clients launch servers without a shell.
    return Path(value or os.environ.get("AXIOM3D_HOME") or ".axiom3d").expanduser()


def _call(args) -> int:
    if args.tool not in TOOLS:
        print(f"ERROR: unknown tool {args.tool!r}; tools: {', '.join(TOOLS)}")
        return 1
    try:
        kwargs = json.loads(args.json) if args.json else {}
    except json.JSONDecodeError as e:
        print(f"ERROR: --json is not valid JSON ({e})")
        return 1
    if not isinstance(kwargs, dict):
        print("ERROR: --json must be an object, e.g. '{\"task\": \"step_forward\"}'")
        return 1
    if args.session and args.tool not in NO_SESSION:
        kwargs["session"] = args.session
    home = _home(args.home)
    wb = Workbench(home, protocol=args.protocol != "off", label=args.label)
    try:
        result = getattr(wb, args.tool)(**kwargs)
    except AxiomError as e:
        print(f"ERROR: {e}")
        return 1
    except TypeError as e:
        print(f"ERROR: bad arguments for {args.tool}: {e}")
        return 1
    except Exception as e:  # safety net: never show a traceback
        print(f"INTERNAL ERROR (please report): {type(e).__name__}: {e}")
        return 2
    print(result.text)
    if result.images:
        out = home / "images"
        out.mkdir(parents=True, exist_ok=True)
        sid = current_id(home) or "session"
        for n, (label, png) in enumerate(result.images):
            path = out / f"{sid}-{args.tool}-{n}-{label.replace('@', '_')}.png"
            path.write_bytes(png)
            print(f"image: {path}")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="axiom3d", description="A 3D workbench built for AI models.")
    sub = parser.add_subparsers(dest="command", required=True)

    serve = sub.add_parser("serve", help="run the MCP server over stdio")
    call = sub.add_parser("call", help="call one tool with JSON arguments")
    call.add_argument("tool")
    call.add_argument("--json", default=None, help="tool arguments as a JSON object")
    call.add_argument("--session", default=None)
    for p in (serve, call):
        p.add_argument("--home", default=None, help="state directory (default $AXIOM3D_HOME or ./.axiom3d)")
        p.add_argument("--protocol", choices=("on", "off"), default="on", help="off = bare mode (A/B baseline)")
        p.add_argument("--label", default=None, help="model label recorded in the ledger")
    sub.add_parser("tasks", help="list tasks")
    ev = sub.add_parser("eval", help="evaluation utilities")
    ev.add_argument("what", choices=("report",))
    ev.add_argument("--home", default=None)

    args = parser.parse_args(argv)
    if args.command == "serve":
        from axiom3d.mcp_server import build_server

        build_server(_home(args.home), protocol=args.protocol != "off", label=args.label).run("stdio")
        return 0
    if args.command == "call":
        return _call(args)
    if args.command == "eval":
        from axiom3d.eval.report import collect, render_report

        print(render_report(collect(_home(args.home))))
        return 0
    for task in TASKS.values():
        print(f"{task.id:16} {task.goal}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
