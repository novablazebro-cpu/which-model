# axiom3d — a 3D workbench built for AI models (v1: walk-cycle slice)

## Context

The repo `which-model` holds nothing worth keeping: a stub README, a `.gitignore`, and `.antigravity/` chat and phone-sync state. The user wants it cleared and rebuilt as **axiom3d**: a 3D tool designed for AI models rather than humans, aimed at the mistakes cheap or fast models make.

Research findings that drive the design (sources were given in chat):
- **Models invent angles and coordinates.** Agents without measurement tools hallucinate rotations (AgentsCAD).
- **Models get rotation direction, order and handedness wrong** (DORI benchmark; Huang et al. 2023 on rigged models).
- **Models' vision is unreliable.** VLMs hallucinate differences between renders (BlenderGym).
- **Physics goes wrong.** Floating or disconnected parts are common (3DCodeBench).
- **Placing things with raw coordinates goes badly**; relative placement works (Cutscene Agent).
- **Agents declare success early**, and prompt rules are weaker than gates the system enforces.
- **Self-grading fails and outside verifiers work** (Huang et al., ICLR 2024).

**Design principles that follow:**
1. **The tool computes; the model decides.** The model works with anatomy-level controls (hip flexion, foot plants) and the tool works out the rotation math, so the model never has to.
2. **The model predicts; the tool grades.** This is the user's "test" idea, with the grading moved out of the model's hands.
3. **Text measurements first, images second.**
4. **Finishing is gated:** the tool never certifies work that fails its checks.

**User decisions:** own Python core (no Blender dependency; export glTF so Blender opens results), walk cycle first, name `axiom3d`, delete `.antigravity/` and gitignore it.

**Approving this plan approves the design spec.** After approval it is committed verbatim as `docs/superpowers/specs/2026-10-24-axiom3d-design.md`. The superpowers writing-plans skill then turns the milestones below into a TDD task list, and execution follows.

## Limits to be honest about
- An MCP server **cannot force a model to keep working.** It can only refuse to certify. Hard enforcement belongs in the host or harness (the eval harness re-prompts; a Claude Code Stop hook is possible later).
- Whether the protocol helps cheap models more than it costs them in turns is **a hypothesis**. The eval A/B (protocol on vs off) exists to test it.
- Gait reference ranges are standard clinical approximations. The software renderer is diagnostic, not pretty.
- I can't rename the GitHub repo. The user does it under GitHub → Settings → Rename (`which-model` → `axiom3d`). Old URLs redirect.

## Repo reset (Milestone 0)
- `git rm -r .antigravity/`, then add `.antigravity/`, `.axiom3d/`, `.pytest_cache/`, `*.egg-info/`, `dist/` and `build/` to `.gitignore`. Keep the existing entries.
- Replace `README.md` with the axiom3d overview, the conventions, MCP setup snippets (Claude Code, Antigravity, Gemini CLI), and a quickstart.
- `pyproject.toml` (hatchling, Python ≥3.11). Dependencies: `numpy`, `Pillow`, `mcp>=2.3,<3`. Dev dependency: `pytest`. Console script `axiom3d`. Managed with `uv`.
- Work on branch `claude/vigilant-goodall-y4x0bf` and push after each milestone. No PR unless asked. `main` keeps the old files until the branch is merged.

## Conventions (the "axioms": one source of truth in `conventions.py`)
- Right-handed, **Z up**, metres, character **faces −Y**, character's **left = +X** (Blender's convention, so `.L` bones sit at +X).
- glTF export wraps the scene in a −90° X rotation: (x, y, z) → (x, z, −y). Up becomes +Y and forward becomes +Z, as the glTF spec requires.

### Anatomy sign table
Positive angle = the anatomical motion. Derived with the right-hand rule and pinned by tests.

| Joint DOF | Axis | Positive moves distal end |
|---|---|---|
| hip / shoulder flexion | −X | forward (−Y) |
| knee flexion | +X | backward (+Y) |
| elbow flexion | −X | forward / up |
| ankle dorsiflexion | −X | toes up |
| hip / shoulder abduction (L / R) | −Y / +Y | away from midline |
| hip internal rotation (L / R) | −Z / +Z | toes toward midline |
| spine / neck flexion | +X | forward |
| lateral bend left, twist left, root heading | +Y, +Z, +Z | toward the left |

3-DOF joints compose as `R = Rx·Ry·Rz` with signed angles. Internally poses are stored as quaternions; anatomical angles are decomposed from them for reports and limit checks.

## Architecture: package `axiom3d/`
Each file has one job. Interfaces live in `api.py`.

- `conventions.py`: axes, units, character-frame helpers, glTF axis conversion.
- `math3d.py`: quaternions, axis-angle, slerp, Tait–Bryan compose/decompose, 4×4 transforms (numpy).
- `rig/skeleton.py`: `Joint(name, parent, rest_offset, dofs[axis, sign, min, max])`, and forward kinematics returning world transforms plus landmarks.
- `rig/humanoid.py`: `build_mannequin(height=1.75)`, using Winter's anthropometric ratios (thigh 0.245H, shank 0.246H, hip height 0.530H, and so on). 14 joints: root, spine, neck, head, and L/R shoulder, elbow, hip, knee, ankle. Rigid capsule or box segments attached to bones (no skinning in v1). Landmarks: head_top, pelvis, L/R hip, knee, ankle, heel, toe, shoulder, elbow, wrist, hand.
- `rig/ik.py`: analytic two-bone leg IK with the knee aimed forward along the character's facing, and an explicit "unreachable" result.
- `anim/clip.py`: timeline (fps and frame range from the task, optional loop) plus four kinds of command:
  - root keys: position, or "forward N m", and heading
  - pose keys: anatomical angles
  - `plant(side, frames, at)`
  - `swing(side, frames, apex)`: an arc between two plants
  Plants and swings are **constraints solved live at each frame**, never baked, so editing the root never leaves stale leg data. Keys use quaternion slerp; position uses cubic Hermite interpolation.
- `perceive/report.py`: the main perception channel, as text.
  - Conventions header and root pose.
  - Landmark world coordinates, each with a **tool-computed meaning**, e.g. `left_toe (0.10,-0.31,0.00): 0.31 m IN FRONT of pelvis, ON ground`.
  - Anatomical angles with % of joint limit, contacts, and active check warnings.
  - `timeline` mode: per-frame foot heights, foot sliding and support phases.
- `perceive/render.py`: numpy z-buffer rasterizer with flat Lambert shading, labelled with Pillow.
  - A 2×2 sheet of front, side, top and perspective views.
  - Ground grid at 0.5 m and a labelled axis gizmo.
  - **Left side blue, right side orange**, so laterality is visible.
  - A side-view filmstrip of N frames and a top-down footprint map.
  - Returned as MCP images.
- `checks/` (`base.py`, `geometry.py`, `anatomy.py`, `gait.py`): each check returns `CheckResult(id, severity, frames, message, evidence{numbers}, hint)`. The hint is the teacher, e.g. "+X raw rotation swings a downward bone toward +Y = backward".
  - Geometry: ground penetration, floating.
  - Anatomy: joint limits, knee/elbow hyperextension, IK unreachable.
  - Gait:
    - foot slide during contact
    - step direction vs facing (catches backward legs)
    - moonwalk (root moves forward while feet push the wrong way)
    - at least one foot down at every frame of a walk
    - L/R support phases alternate
    - arms counter-swing (warning)
    - loop continuity
    - root keeps progressing forward
- `protocol/`: the test. The session moves through `BRIEFING → WORKING → EXAM → DONE`.
  - `briefing.py`: an entry quiz with about 5 questions, seeded per session. The tool knows every answer, and some use randomised live coordinates so they can't be memorised. Examples: which way it faces, which axis is left, is the heel in front of or behind the pelvis, the sign of hip flexion, where +X raw rotation moves a downward bone. Editing tools stay locked until the quiz passes. Wrong answers come back with an explanation.
  - `predict.py`: a safe parser (no `eval`) for a small grammar:
    - `subject op value`, with ops `< > <= >= ~= v ± tol` and `in [a,b]`, and an optional frame selector `@f`, `@a..b` or `@all`
    - relations: `in_front_of`, `behind`, `left_of`, `right_of`, `above`, `below`, `on_ground`
    - metrics: `slide()`, `min_height()`, `max_height()`

    Every editing call **must carry at least one precise prediction**: a tolerance or range of ≤0.15 m or ≤20°, or a relation. Vacuous ones like `x < 1000` are rejected.
  - Discrepancy gate: if a prediction fails, the change stays applied, but further edits are blocked until the model calls `undo` or `accept_discrepancy(reason)`.
  - `gate.py`: `finish(claims)` runs all checks (errors block), the task's acceptance criteria, and grades the model's final claims. Any failure returns the session to WORKING with the report.
  - `ledger.py`: quiz attempts, predictions made and how many were correct (the **calibration score**), discrepancies, exam attempts. Stored as JSON in `.axiom3d/sessions/`. This is the seed of a "which model can actually do 3D" leaderboard.
  - `--protocol off` (bare mode) turns off the quiz, prediction requirements, hints and gating, for A/B testing.
- `tasks/`: `step_forward`, `walk_cycle` (1.2–1.6 m in 2 s at 24 fps, looping, no sliding), and `turn_then_step` (tests world frame vs character frame). Goals and numeric acceptance criteria are visible to the model.
- `session_store.py`: state = task + mode + an ordered command log. Replaying the log rebuilds the scene (deterministic), and `undo` pops the last command. This is how the CLI keeps state between calls.
- `api.py`: pure functions over a Session, one per tool. `mcp_server.py` and `cli.py` are thin wrappers around it.
- `export/gltf.py`: a hand-written glTF 2.0 `.glb` writer. Joint node hierarchy, rigid segment meshes, animation baked per frame (rotation quaternions plus root translation, LINEAR).
- `guide/` (markdown served by a tool): conventions, walk-cycle phases with reference angles (hip about +30°/−10°, knee peak about 60° in swing, ankle ±10–20°), and the prediction syntax.

### MCP tools
13 tools. Kept small because tool-selection errors grow with tool count.
- **Setup:** `start_session(task)`, `answer_quiz(answers)`, `guide(topic)`
- **Seeing:** `observe(frames, views, images)`, `check(frames)`
- **Editing** (each takes `expect`): `set_root`, `set_pose`, `plant_foot`, `swing_foot`
- **Recovery:** `undo`, `accept_discrepancy(reason)`
- **Ending:** `finish(claims)`, `export(format)`

Server: `from mcp.server.mcpserver import MCPServer, Image` (in mcp 2.x FastMCP was renamed), `@server.tool()`, `server.run("stdio")`.

CLI: `axiom3d serve`, `axiom3d call <tool> --session ID --json '{...}'`, `axiom3d eval report`.

## Milestones (each: tests first, then commit, then push)
- **M0** Repo reset, project skeleton, spec doc committed.
- **M1** Conventions, math3d, skeleton, mannequin, forward kinematics, anatomy frames. Sign-table tests.
- **M2** IK, clip, constraint solving (plants and swings), interpolation.
- **M3** Report and renderer (sheet, filmstrip, footprints).
- **M4** Checks.
- **M5** Protocol: store, quiz, predictions, discrepancy gate, finish gate, ledger, bare mode.
- **M6** Tasks, api, MCP server, CLI, guide docs.
- **M7** glTF export.
- **M8** Eval: scripted agents, ledger report, A/B, then README polish.

## Verification
- `uv run pytest`, covering:
  - quaternion and decomposition round-trips
  - **sign tests:** hip flexion +30° moves the toe toward −Y; knee flexion moves the ankle toward +Y; L/R abduction mirror; elbow and knee bend opposite ways
  - IK reaches targets and reports unreachable ones
  - each check fires on a deliberately planted bug and stays quiet on a clean walk
  - the prediction parser accepts valid input and rejects malformed or vacuous predictions
  - protocol: editing locked before the quiz; an edit without `expect` rejected; a failed prediction blocks the next edit; `finish` blocked by errors
  - session replay is deterministic
- **Scripted agents (core proof):**
  - `NaiveAgent` makes the classic errors: negative flexion stepping backward, mirrored signs, a sliding root. It must be caught by step_direction, foot_slide and moonwalk, and fail the exam.
  - `CorrectAgent` must pass all 3 tasks and reach DONE.
- **End-to-end MCP:** spawn `axiom3d serve` over stdio with `mcp.client.stdio` in a test, then drive `step_forward` all the way to DONE.
- **glTF:** run the Khronos validator (`npx gltf-validator`) with zero errors, and re-parse the file to check the axis mapping. Optional: import into headless `bpy` (on PyPI, about 400MB) to confirm the character faces −Y after import.
- **Visual check:** render the walk sheet, filmstrip and footprint PNGs and inspect them.
- **Optional live trial (only with the user's OK):** a Haiku subagent drives the CLI on the 3 tasks with the protocol on and off. With n this small it's a smoke signal, not proof.
