# axiom3d v2: AI toolkit + reliability

## Context
v1 is built: 172 tests, reviewed, pushed on `claude/vigilant-goodall-y4x0bf`. The v1 design lives in `docs/superpowers/specs/2026-10-24-axiom3d-design.md`.

The user wants axiom3d to become "the best in the world, a Blender for AI". For v2 they chose:
- **Workspace:** the sandbox only (no notebook or project folder for now).
- **Calculator:** a safe scene calculator.
- **Focus:** AI toolkit + reliability first.
- **Testing:** connect axiom3d to Claude over MCP and test it with Haiku.

They don't have Blender, and they mostly work from a phone.

**Approving this plan approves the v2 design.** It is then committed as `docs/superpowers/specs/2026-10-24-axiom3d-v2-design.md`, turned into a TDD task plan (writing-plans), and built on the same branch.

**Principles carried from v1, with research behind them:**
- **Delegate the math to a runtime.** PAL beat a much larger model by 15 points; geometric-query tools eliminated hallucinated angles (AgentsCAD).
- **Use a real simulator, not imagined outcomes.** LLM "world models" hallucinate (R-WOM). axiom3d's sandbox runs the real evaluation.
- **Report numbers, not images.** VLMs hallucinate image differences (BlenderGym), so every edit reports a numeric diff.
- **"Best" must be measured.** v2 includes a live Haiku baseline, before and after.

## What v2 adds

### 1. Scene calculator: tool `calc(expr)`
- **Syntax:** one or more statements separated by `;` or newlines. Assignments `stride = dist(left_ankle@24, left_ankle@0)` persist in the session (`SessionState.variables`) and can be reused in predictions as `$stride`.
- **Values:** numbers and 3-vectors (`[x, y, z]`).
- **Scene references:**
  - points: `left_toe@12`, which defaults to the last frame
  - channels: `left_hip.flexion@12`
  - root: `root.heading@12`
  - frame conversions: `track(v)` gives [forward, left, up] in the track frame; `char(v, @f)` gives the character frame; `world_from_track([f, l, u])`
- **Functions:**
  - geometry: `dist`, `angle(a, b, c)` (degrees, at b), `vec(a, b)`, `dot`, `cross`, `norm`, `unit`, `proj`
  - general math: `lerp`, `clamp`; `sin`/`cos`/`tan` take degrees; `asin`/`acos`/`atan2` return degrees; `sqrt`, `abs`, `min`, `max`, `round`; `.x/.y/.z`
- **Constants:** `thigh`, `shank`, `leg`, `ankle_height`, `pelvis_height`, `hip_half_width`, `fps`, `FORWARD0`, `LEFT0`, `UP`.
- **Domain helpers.** These are the hand-done reach math from v1, now available to the model:
  - `reach(pelvis_h)`: max horizontal foot offset from the hip
  - `knee_needed(pelvis_h, horizontal)`: knee flexion for a flat foot
- **Safety:** Python `ast` parse plus a whitelist walker: Module, Expr, Assign (one Name), BinOp, UnaryOp, Call (whitelisted names), Name, Constant, List, Attribute, and MatMult used as the `@frame` operator. No `eval`/`exec`. Limits: 500 characters, exponent ≤ 10, |value| ≤ 1e6, 50 variables. Errors become `AxiomError`s with suggestions.
- **Prediction language:** `$var` is accepted wherever a number goes (`axiom3d/protocol/predict.py`).

### 2. Sandbox: `dry_run` + tool `batch(edits, expect, dry_run)`
- **dry_run:** every edit tool (`set_root`, `set_pose`, `plant_foot`, `swing_foot`) gains `dry_run: bool = False`. A dry run computes everything on a copy (predictions graded, checks, numeric diff, optional sheet image) and commits nothing. The result begins `DRY RUN: nothing changed`.
- **batch:** `batch(edits=[{op...}, ...], expect, dry_run)` applies several edits atomically under one set of predictions. A plant + swing + plant step becomes one call, which means fewer turns for cheap models.
- **Ledger rules, so the "test" stays meaningful:**
  - Dry runs also need one precise, edit-relevant prediction, and they count toward calibration.
  - A failed dry-run prediction doesn't block anything, because nothing was applied.
  - Committing an edit identical to a previous dry run (same command hash) doesn't re-count its predictions (marked "seen in sandbox").
  - New ledger fields: `dry_runs`, `batches`.

### 3. A numeric diff in every edit result
- A `CHANGED:` block shows the top changes between before and after:
  - root track position and heading
  - feet, hands and head positions in track coordinates, at the edited frame and the worst frame
  - every channel that moved more than 0.5°
- A check delta: errors fixed and errors introduced.
- Implemented in a new `axiom3d/perceive/diff.py`, reusing `measure.track_coords` and `checks.base.run_checks`.

### 4. A viewer for humans (no Blender needed)
- `export(format="html")` writes one self-contained page:
  - three.js pinned at `three@0.160.0` from cdn.jsdelivr, using `GLTFLoader` and `OrbitControls`
  - the existing GLB embedded as base64
  - play/pause, a frame scrubber and a frame counter, a ground grid, blue = left / orange = right
  - phone-friendly
- New `axiom3d/export/viewer.py`, reusing `export_glb`.
- After the build I publish the reference walk's viewer as a private claude.ai Artifact, so you can watch it on your phone.

### 5. Reliability
- **Feet hold their heading while planted** (review I5). A plant stores `foot_yaw`: the heading at the plant's start, or an optional `facing=` argument to `plant_foot`.
  - The IK aims the knee over the toes (pole = foot yaw).
  - The ankle keeps the foot flat at `foot_yaw`.
  - Hip internal rotation absorbs the body turn, and its ±40° limit makes big pivots fail, which teaches step-turns.
  - Swings interpolate yaw between their plants.
  - `gait.foot_slide` measures heel, toe and ankle.
  - The `turn_then_step` reference becomes a two-step 45° + 45° step-turn.
  - This touches `rig/ik.py`, `anim/clip.py`, `anim/commands.py`, `anim/evaluate.py`, `checks/gait.py` and `tasks/reference.py`.
- **Fuzzing:** add `hypothesis` (dev dependency only) in a new `tests/test_fuzz.py`. Every tool gets random and malformed arguments and must return a result or an `AxiomError`, never another exception. The session file must still load afterwards.
- **Safety net:** the MCP `_reply` and the CLI `_call` turn any unexpected exception into `INTERNAL ERROR (please report): …` (CLI exit code 2). The model never sees a crash or traceback.
- **Session format version:** `SessionState.version = 2`.
  - `load()` migrates v1 files: it adds `variables` and the new ledger keys.
  - A command that no longer replays becomes an `AxiomError` that suggests undo or a new session.
- **Input bounds:** forward/left within ±50 m, angles within ±720°. This closes the 1e308 RuntimeError.
- **Deferred minors from the review:**
  - quiz retries re-seed the failed questions, and the explanations show the method, not the number (M5)
  - the eval report gets aligned columns and shows each session's phase (M6)
  - the sheet footer is no longer clipped (M7)
  - the session-id regex uses `fullmatch` (M8)
- **Speed:** an LRU cache of evaluated states keyed by command-log hash in `session_store.rebuild`, because the sandbox evaluates often.

### 6. Haiku test kit: test it yourself through Claude
- **HTTP transport:** `axiom3d serve --transport http --host 127.0.0.1 --port 8765` uses `MCPServer.run("streamable-http", host=…, port=…)`. Each MCP connection gets its own axiom3d session (a per-connection map; confirm how mcp 2.x Context identifies a connection). One HTTP server never mixes sessions, so the review's I2 bug can't come back.
- **`docs/TESTING_WITH_CLAUDE.md`:**
  - Claude Code: `claude mcp add axiom3d -- axiom3d serve --home ~/.axiom3d --label haiku`, then `claude --model haiku`
  - Claude Desktop: a stdio JSON config snippet
  - phone or claude.ai: needs the HTTP server reachable over public HTTPS (a host or a tunnel); marked as user setup, with honest caveats
  - reading results with `axiom3d eval report`
- **`axiom3d prompt <task> [--bare]`** prints a ready-to-paste test prompt: the task plus "keep working until finish says CERTIFIED", with no hints beyond the tools.
- **Live baseline, run by me:** a Haiku subagent drives the same tools through the CLI. Same Workbench, different transport. It runs 3 tasks × protocol on/off on **v1 first**, as the baseline, and again on **v2 at the end**, then I report the two eval tables side by side. Small n, so it's a signal, not proof.

## Tool surface after v2: 15
The 13 from v1 plus `calc` and `batch`. `dry_run` is a parameter, not a new tool. `export` gains `format`; `plant_foot` gains `facing`. The guide gains topic `calculator` and sandbox notes in `tools`.

## Files
- **New:** `axiom3d/protocol/calc.py`, `axiom3d/perceive/diff.py`, `axiom3d/export/viewer.py`, `docs/TESTING_WITH_CLAUDE.md`, `axiom3d/guide/calculator.md`, `tests/test_calc.py`, `tests/test_sandbox.py`, `tests/test_diff.py`, `tests/test_viewer.py`, `tests/test_fuzz.py`
- **Modified:** `axiom3d/api.py` (calc, batch, dry_run, diff, version), `axiom3d/mcp_server.py` (2 tools, HTTP, per-connection sessions), `axiom3d/cli.py` (`--transport`, `prompt`), `axiom3d/session_store.py` (variables, version, migration, cache), `axiom3d/protocol/predict.py` (`$var`), plus the foot-yaw files listed in section 5, `README.md`, and `pyproject.toml` (hypothesis as a dev dependency)

## Milestones (each test-first, then commit and push)
- **V0:** live Haiku baseline on v1 (6 runs), with the results saved in `docs/eval/`
- **V1:** scene calculator, plus `$var` in predictions
- **V2:** numeric diff
- **V3:** sandbox (`dry_run` + `batch`) and its ledger rules
- **V4:** foot yaw on plants, step-turn reference, heel/toe slide
- **V5:** reliability (fuzzing, safety net, versioning and migration, bounds, minors, cache)
- **V6:** HTML viewer, and publishing the reference walk as an Artifact
- **V7:** Haiku test kit (HTTP transport, per-connection sessions, docs, `prompt` command)
- **V8:** live Haiku run on v2, comparison report, README; then a whole-branch review by a fresh reviewer

## Verification
- `uv run pytest` passes in full, including the new tests:
  - calculator: correct values, `@frame` handling, every unsafe input (`__import__`, attribute escape, huge exponent) rejected
  - sandbox: a dry run changes nothing on disk, batches are atomic, ledger counting follows the rules
  - diff: content checks
  - viewer: the HTML contains the GLB and pinned script tags
  - fuzz: about 500 examples per tool
  - migration: a saved v1 session still loads
  - foot yaw: a planted foot's toe doesn't move during a turn; a 90° pivot in place fails with a step-turn hint
- All three references stay clean and certify; the Khronos validator still reports 0 errors.
- End-to-end MCP over stdio and over HTTP (two concurrent connections stay isolated).
- I open the viewer in headless Chromium (Playwright is pre-installed), check the animation plays and the frame counter advances, and take a screenshot.
- The Haiku before/after eval tables are committed in `docs/eval/`, then the final whole-branch review.

## Honest limits
- **Haiku runs are small-n.** They show direction, not statistical proof.
- **The CLI path isn't the MCP path.** The tools are the same, but the transport differs. Your own Claude + MCP run closes that gap.
- **Phone access needs hosting** the HTTP server somewhere public. That's yours to set up; I document it.
- **Step-turns make `turn_then_step` harder** for models. That's intended realism, not a regression.

## Roadmap after v2 (not in this plan)
- **v3:** a keep-working runner that re-prompts until certified, with API keys, and a public leaderboard ("which-model").
- **v4:** beyond walking: props, reaching and grabbing, balance (center of mass over the support), more tasks.
- **v5:** a locked-down Python kernel (SpatialClaw-style); the notebook and project folder if wanted.
