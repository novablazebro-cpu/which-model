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
from axiom3d.workspace import DEFAULT_DEV, DEFAULT_HOME, WorkspaceError, dev_workspace, home_warning, init_workspace

TOOLS = ("start_session", "answer_quiz", "guide", "observe", "check", "calc", "set_root", "set_pose", "plant_foot",
         "swing_foot", "shape_profile", "paint_band", "add_box", "remove_box", "paint_face", "batch", "undo",
         "accept_discrepancy", "finish", "export")
NO_SESSION = ("start_session", "guide")


def _home(value: str | None) -> Path:
    # Expand "~" ourselves: MCP clients launch servers without a shell.
    home = Path(value or os.environ.get("AXIOM3D_HOME") or ".axiom3d").expanduser()
    warning = home_warning(home)
    if warning:
        print(warning, file=sys.stderr)  # stderr: stdout carries the MCP protocol and the text models read
    return home


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
        sid = (args.session if args.tool not in NO_SESSION else None) or current_id(home) or "session"
        for n, (label, png) in enumerate(result.images):
            path = out / f"{sid}-{args.tool}-{n}-{label.replace('@', '_')}.png"
            path.write_bytes(png)
            print(f"image: {path}")
    return 0


def _workspace(args) -> int:
    if args.workspace_command == "dev":
        try:
            dev = dev_workspace(args.name, args.source, args.dest)
        except WorkspaceError as e:
            print(f"ERROR: {e}")
            return 1
        print(f"Dev clone ready: {dev.path}\nBranch: {dev.branch} (pushing to main or master is refused here)\n")
        print(f"Start the AI in that folder:\n  cd {dev.path}")
        print("When it is done:\n  git push -u origin " + dev.branch + "   then open a pull request on GitHub")
        return 0
    try:
        info = init_workspace(Path(args.home or os.environ.get("AXIOM3D_HOME") or DEFAULT_HOME))
    except WorkspaceError as e:
        print(f"ERROR: {e}")
        return 1
    print(f"Workspace ready: {info.home}\n")
    print("Connect Claude Code:\n  " + info.claude_command + "\n")
    print("Or add this to another MCP client's config:\n" + info.mcp_json)
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
    ws = sub.add_parser("workspace", help="set up a safe place for an AI to work")
    ws_sub = ws.add_subparsers(dest="workspace_command", required=True)
    ws_init = ws_sub.add_parser("init", help=f"make the dedicated models folder (default {DEFAULT_HOME})")
    ws_init.add_argument("--home", default=None)
    ws_dev = ws_sub.add_parser("dev", help="a separate clone on an ai/<name> branch that cannot push to main")
    ws_dev.add_argument("name", help="becomes the branch ai/<name>")
    ws_dev.add_argument("--source", default=None, help="repository to clone (default: origin of the repo you are in)")
    ws_dev.add_argument("--dest", default=None, help=f"where to put the clone (default {DEFAULT_DEV}/<name>)")

    args = parser.parse_args(argv)
    if args.command == "workspace":
        return _workspace(args)
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
