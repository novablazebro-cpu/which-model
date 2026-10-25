# Haiku vase test: axiom3d with and without the protocol, and no tool

Date: 2026-10-25. Tool version: commit `e32f38f` (branch `v2-work`).
Task: `meiping_vase`, a Ming plum vase as a lathe profile (red body, blue band at the foot, blue rim), 10 acceptance criteria at the time of the runs (11 after the fix below).
Model: the `haiku` agent alias (assumed Haiku 5.5), effort **high**, one run per arm, a 60-tool-call budget each.

## Arms

| arm | what Haiku had | prompt |
|---|---|---|
| protocol | axiom3d CLI, quiz, predictions before every edit, certified `finish` | `test_prompt("meiping_vase", bare=False, via="cli")` |
| bare | axiom3d CLI, same tools and guide, no quiz, no predictions | `test_prompt(..., bare=True)` |
| raw | Python 3 + numpy, write an OBJ by hand | `raw_prompt("meiping_vase", workdir)` |

All three arms got the same goal text, the same 10 criteria and the same conventions. None saw the photo.
One grader, `axiom3d.eval.vase`, graded all three: it slices each mesh by height (`measure_obj`) or measures the session's profile (`measure_spec`), then applies `grade_vessel`.

## Results

| | protocol | bare | raw | reference |
|---|---|---|---|---|
| criteria passed | **10/10** | **10/10** | **10/10** | 10/10 |
| certified / watertight | certified | n/a | watertight | — |
| tool calls (from the transcript) | 14 | 14 | 4 | — |
| tokens (harness) | 72k | 68k | 110k | — |
| wall time (harness) | 63 s | 56 s | 252 s | — |
| predictions right | 11/12 | — | — | — |
| discrepancies / undos | 1 / 0 | — | — | — |
| finish attempts | 2 | 1 | — | — |
| dry runs | 1 | 2 | — | — |
| mesh vertices | 10,130 | 10,226 | 61,154 | 10,226 |

Measured shapes (H = height):

| | height | max D / H | shoulder | mouth / H | foot / H | neck / mouth (mm) | foot / waist (mm) |
|---|---|---|---|---|---|---|---|
| protocol | 0.400 | 0.540 | 0.720 | 0.100 | 0.320 | 36 / 40 | 128 / 100 |
| bare | 0.400 | 0.540 | 0.720 | 0.100 | 0.320 | 38 / 40 | 128 / 104 |
| raw | 0.400 | 0.525 | 0.719 | 0.112 | 0.290 | 37 / 45 | 116 / 100 |
| reference | 0.400 | 0.535 | 0.725 | 0.105 | 0.330 | 36 / 42 | 132 / 120 |

Every run aimed at the middle of each acceptance range (0.40 m tall, 0.54 width, 0.72 shoulder). The two tool runs chose different profiles from each other and from the reference: 10 and 13 points.

## Rule compliance

The prompts forbade reading anything outside the run's own tool or folder. This was instructed, not enforced, so I audited every tool call in the three transcripts:
- protocol and bare: every call is an `axiom3d call ...` CLI command in the run's own workdir.
- raw: `mkdir`, two file writes (`make_vase.py`, `measure_vase.py`), one run. Everything stayed inside its folder.

## What this shows

1. **Success was saturated.** Haiku 5.5 at high effort built this vase with or without axiom3d. This task cannot rank the arms on correctness, the same finding as the v1 walking baseline.
2. **The tool's measured gain is cost.** The tool runs used about 37% fewer tokens and a quarter of the wall time. The raw run made only 4 calls, but two were whole programs: a 6 KB mesher (Catmull-Rom profile, arc-length resampling, an inward-normal offset for the wall) and a 5 KB checker.
3. **The protocol caught one real misunderstanding.** Haiku predicted that `paint_band` leaves out its end height. The tool measured that the end is included (`start <= h <= end`). The guide never said which, so the docs are at fault.
4. **The protocol cost almost nothing here.** 14 calls, the same as bare. Quiz passed on the first attempt; 11 of 12 predictions were right.
5. **The raw arm's self-check was honest.** Its own measurements matched the grader to within 1 mm, and its mesh is closed with outward normals.

## The hourglass: a vase the tool should not have certified

Looking at the vases in 3D, the protocol run's lower body pinches into a stem. The waist positions explain it:

| | waist height | inside the blue foot band? | pinch per side |
|---|---|---|---|
| reference | 0.100 H | at its edge | 6 mm |
| **protocol** | **0.175 H** | **no, 2 cm above it** | 14 mm |
| bare | 0.075 H | yes | 12 mm |
| raw | 0.125 H | yes | 8 mm |

The task text says the waist sits "just above the foot", but none of the 10 criteria measured where the waist is, only that the foot is 5 mm wider than it. The protocol run never called `observe`; every gate it passed was numeric. So the tool certified a vase that looks wrong. The mesh is not at fault: all four vases are identical and correct seen from below.

**Fix (commit `822f6f1`):** the tool measures `vessel.waist_height` (report, calc, predictions), and the meiping task gains an 11th criterion: the waist sits in the lowest 15% of the height. Graded on 11 criteria, the first protocol vase scores 10/11 and could not be certified; the reference, bare and raw vases still pass. The workflow text now says to look at the sheet before `finish`.

**Re-run on the fixed tool** (same prompt, new folder, one run):

| | criteria | certified | tool calls | tokens | time | predictions | finish attempts | waist |
|---|---|---|---|---|---|---|---|---|
| protocol, after the fix | **11/11** | yes | 14 | 71k | 60 s | 10/10 | 1 | 0.100 H, inside the band (0-0.07 m) |

It read the hourglass warning in the guide, called `observe(views=['sheet'])` and opened the image (the only file read, which the rules allow), then finished on the first attempt. Its pinch is 15 mm per side, but it sits inside the blue band and reads as a foot flare.

The 15% limit was set after seeing these five vases: it passes the four that look right and fails the one that does not. One good re-run is evidence that the fix works, not proof.

## The bottoms: three tool defects and two design habits

Seen close up, every bottom looked worse than every top. Measured causes:

| cause | whose | evidence | fix (commit `54ca0aa`) |
|---|---|---|---|
| base disk and wall shared one ring of vertices, so normals pointed 83.7° down: viewers and Blender (via the GLB) shaded the base edge as a dark smear | tool | normals measured on the protocol re-run's mesh | `display_mesh` splits vertices at the base edge, lip, inner floor and band edges; export and the sheet use it |
| colours blended across one sample (~4 mm) at every band edge | tool | per-vertex colours on one shared ring | same: one colour per triangle |
| the curve's end slope extrapolated the next segment: a 31.45° skirt where the points asked for 20.56° (every foot flare exaggerated by about half) | tool | `radius_at` tangent, old code vs new | the ends take their own segment's slope |
| pinches 2-3x deeper than the reference (12-15 mm per side) | Haiku | all three Haiku feet | not fixed: a style reference, see below |
| lower bodies bulging 6-10 mm outside a straight taper (the no-tool vase too) | Haiku | all three Haiku vases | not fixed: a style reference, see below |

The sheet image Haiku looks at is flat-shaded at 384 px with the foot about 40 px tall, and shows no reference, so the re-run "looked" and could not see either habit.

Adding criteria one by one (waist height, then pinch depth, then bulge) is whack-a-mole. The general fix is a style reference: a measured meiping profile the tool compares against, reporting where the shape departs from it, plus a close-up view of the foot and lip.

## Friction found in the tool (fixed after this run)

| # | what happened | evidence | fix |
|---|---|---|---|
| F1 | `guide('tools')` lists only the walking tools and describes a quiz; the bare run expected a quiz that never came | bare's hand-back | tools guide covers vessels and says the quiz is protocol-only |
| F2 | bare-mode `finish` prints only "Session closed.", so the run cannot tell if it passed | bare's hand-back | bare `finish` reports the acceptance result |
| F3 | band ends were undocumented; Haiku guessed "exclusive" | protocol's discrepancy | docs say both ends are included and the later band wins |
| F4 | first `finish` sent claims as one prose string (one wasted call; also seen in v1) | protocol's first `finish` | start text shows a claims example |

All four are fixed in commit `822f6f1`, with a test each in `tests/test_vessel_task.py`.

## Limits

- One run per arm, plus one re-run of the protocol arm. Another run could differ.
- The criteria check proportions and colour zones, not beauty, and not the dragon.
- The `haiku` alias is assumed to be Haiku 5.5.
- Token and time counts come from the harness and include each run reading its own tool output.
- The raw arm could not render images (no matplotlib), so it never looked at its vase; the tool runs could have (the bare run called `observe` with the sheet but did not open the PNG).

## What a discriminating test needs

This vase is too easy to separate the arms on success. Candidates, roughly from cheapest to most telling:
- the same task at low effort or with a 15-call budget;
- painted detail that needs coordinates on the surface (the dragon, a wave pattern), not height bands;
- a multi-part object (lid, handles, spout) where parts must meet without gaps;
- an animation task where v1 showed the real mistakes (backward knees, foot sliding).

## Reproduce

```bash
# prompts
uv run python -c 'from axiom3d.eval.prompts import test_prompt, raw_prompt; print(raw_prompt("meiping_vase", "/tmp/raw"))'
# grade
uv run python -c 'from axiom3d.eval.vase import grade_home, grade_obj; print(grade_obj("/tmp/raw/vase.obj")["passed"])'
```
