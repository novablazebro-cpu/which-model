# axiom3d

**A 3D workbench built for AI models, not humans.** Blender is designed around a
human's eyes and hands. axiom3d is designed around the ways AI models fail at 3D,
and it is aimed squarely at the cheap and fast ones.

v1 is a working slice: a humanoid mannequin, walking and stepping tasks, exposed
as an MCP server (13 tools) and a CLI.

## Why

Research on models doing 3D work keeps finding the same failures:

- **They invent angles.** Agents without measurement tools hallucinate rotation
  angles and report them as correct (AgentsCAD, 2026).
- **They get rotation direction and order wrong.** Even the best multimodal
  models score about 54% on coarse orientation questions and 33% on
  fine-grained ones (DORI benchmark).
- **Their vision is unreliable.** VLMs "hallucinate non-existent visual
  differences" between renders (BlenderGym, CVPR 2025).
- **Physics slips.** Floating and disconnected parts are common even when the
  code runs (3DCodeBench).
- **Raw coordinates go badly.** Relative, semantic placement works better (Cutscene Agent).
- **They stop early, and grading themselves doesn't help.** Self-correction
  without outside feedback doesn't improve reasoning; external verifiers do
  (Huang et al., ICLR 2024).

### The walking-leg bug, explained

A hanging leg points along (0, 0, -1). Rotate it +θ about X and its tip goes to
y = +sin θ, which is **backward** for a character facing -Y. A model that assumes
"positive = forward" gets a backward leg every time. The knee needs the opposite
sign, and a bone's roll can flip its local axes too. **The model didn't skip the
math; it was missing information.** So axiom3d does that math itself.

## Design

1. **The tool computes; the model decides.** Anatomical controls replace raw
   rotations: `left_hip.flexion = +30` always moves the leg forward.
   `plant_foot` pins a foot and the tool solves the leg with IK every frame.
2. **The model predicts; the tool grades.** Every edit must carry a precise
   prediction (`left_toe in_front_of pelvis`, `left_ankle.forward ~= 0.36 ± 0.05`).
   The tool measures and shows PASS or FAIL. A failed prediction blocks further
   edits until the model calls `undo` or `accept_discrepancy(reason)`.
3. **Text first, images second.** Every number comes with a meaning the tool
   computed: `left_toe ... IN FRONT of pelvis by 0.31 m, ON ground`. Images are
   extra: front, side, top and perspective views, filmstrips and footprint maps,
   with LEFT parts in blue and RIGHT parts in orange.
4. **Finishing is gated.** A session starts with a quiz whose answers the tool
   computes. `finish(claims)` certifies only when every check, every acceptance
   criterion and every claim measures true.

## Conventions

Right-handed, **Z up**, metres, degrees. At heading 0 the mannequin **faces -Y**
and its **left is +X** (Blender's convention). Positive heading turns it left.
Positions in commands are **track coordinates** (`forward`, `left`), measured
from the task's start point along its start facing.

| channel | positive angle moves |
|---|---|
| hip / shoulder flexion | the limb forward |
| knee flexion | the foot backward (the only way a knee bends) |
| elbow flexion | the hand forward and up |
| ankle dorsiflexion | the toes up |
| abduction | the limb away from the midline (each side) |
| internal_rotation | the toes / forearm toward the midline |
| spine / neck lateral_bend, twist | toward the left |

## Install

```bash
uv tool install git+https://github.com/novablazebro-cpu/which-model
# or, without installing:
uvx --from git+https://github.com/novablazebro-cpu/which-model axiom3d tasks
```

(The repository is being renamed to `axiom3d`; GitHub redirects the old URL.)

## Connect a model (MCP)

Use a fixed `--home` so sessions don't land in whatever directory the client starts in.

**Claude Code**
```bash
claude mcp add axiom3d -- axiom3d serve --home ~/.axiom3d
```

**Gemini CLI / Antigravity / other MCP clients**: add this to the client's MCP server config:
```json
{
  "mcpServers": {
    "axiom3d": { "command": "axiom3d", "args": ["serve", "--home", "~/.axiom3d"] }
  }
}
```

Bare mode for A/B baselines: add `--protocol off`. It disables the quiz,
predictions, hints and certification. Add `--label <model-name>` to tag the ledgers.

## CLI quickstart

Every tool can also be called directly:

```bash
axiom3d tasks
axiom3d call start_session --json '{"task": "step_forward"}'
axiom3d call answer_quiz --json '{"answers": {"q1": "-Y", "q2": "+X", "q3": "behind", "q4": "front", "q5": "0.50"}}'
axiom3d call plant_foot --json '{"side": "right", "start": 0, "end": 24, "expect": ["right_heel on_ground @all"]}'
axiom3d call set_root --json '{"frame": 24, "forward": 0.18, "height": 0.885, "expect": ["root.forward@24 ~= 0.18 ± 0.01"]}'
axiom3d call observe --json '{"views": ["report", "sheet"]}'
axiom3d call check
axiom3d call finish --json '{"claims": ["left_ankle.forward@24 ~= 0.36 ± 0.02", "slide(right_heel) < 0.02"]}'
axiom3d call export        # .glb file; Blender opens it
```

Quiz answers are seeded per session, so read your own quiz. `guide` has four
topics: `conventions`, `walking`, `predictions` and `tools`.

This short sequence is deliberately incomplete. `finish` answers **NOT CERTIFIED**
because the unplanted left foot sinks 4 cm into the ground once the pelvis
lowers, and `check` says so. A full solution for each task is in
[`axiom3d/tasks/reference.py`](axiom3d/tasks/reference.py).

## The tools

| tool | what it does |
|---|---|
| `start_session(task)` | goal, acceptance criteria, conventions, quiz |
| `answer_quiz(answers)` | unlocks editing when every answer is right |
| `guide(topic)` | teaching material |
| `observe(frames, views)` | report, timeline, sheet, filmstrip, footprints |
| `check()` | every failed check, with a hint |
| `set_root`, `set_pose`, `plant_foot`, `swing_foot` | edits; each takes `expect=[...]` |
| `undo()`, `accept_discrepancy(reason)` | recovery after a failed prediction |
| `finish(claims)` | the exit exam; certifies or explains what's missing |
| `export()` | glTF 2.0 `.glb` (validated with the Khronos validator) |

Checks:
- **Geometry:** ground penetration, floating.
- **Anatomy:** joint limits, IK reach.
- **Gait:** support, foot slide, moonwalk, step direction (backswing), alternation,
  arm counter-swing, loop continuity, root progression.

## Evaluate

Every session writes a ledger: quiz attempts, predictions made versus correct
(the **calibration score**), discrepancies, rejected edits and the exam outcome.

```bash
axiom3d eval report --home ~/.axiom3d
```

The bundled scripted agents (`axiom3d.eval.agents`) prove that the checks and gates work:

```
correct      protocol=on  success 3/3  mean calibration 1.00
naive        protocol=off success 0/3  mean calibration -
naive        protocol=on  success 0/3  mean calibration 0.78
```

The naive agent makes the classic errors: negative hip flexion to "step forward",
keyed feet instead of plants, and accepting a failed prediction instead of fixing it.
In bare mode it closes its session believing it is done. With the protocol on,
the tool refuses to certify and says exactly why.

## Honest limits

- **An MCP server can't force a model to keep working.** It can only refuse to
  certify unfinished work. Hard enforcement has to live in the host or harness.
- **Whether the protocol helps a real cheap model more than it costs in turns is
  a hypothesis.** The A/B mode exists to measure it; it hasn't been measured yet.
- **v1 has a simplified body:** rigid segments, flat-foot plants (no heel-strike
  or toe-off), one rig and three tasks. The renderer is diagnostic, not pretty.
- Gait reference angles are textbook approximations.

## Development

```bash
uv sync
uv run pytest
```

Design spec: [`docs/superpowers/specs/2026-10-24-axiom3d-design.md`](docs/superpowers/specs/2026-10-24-axiom3d-design.md).
Implementation plan: [`docs/superpowers/plans/2026-10-24-axiom3d-v1.md`](docs/superpowers/plans/2026-10-24-axiom3d-v1.md).
