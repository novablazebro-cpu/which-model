# Haiku baseline on axiom3d v1

Six live runs of Claude Haiku driving axiom3d v1 through its CLI: 3 tasks × protocol on/off, one run per
cell. Each run had a fresh state directory, a budget of 60 tool calls, and an instruction to use only the
CLI and never read files. That rule was given, not enforced: the repo contains the reference solutions,
and session files store quiz answers. Nothing in the transcripts suggests a run broke it.

## Results

| task | protocol | outcome | tool calls | edits | predictions right | discrepancies | rejected edits | undos |
|---|---|---|---|---|---|---|---|---|
| step_forward | on | CERTIFIED | 16 | 6 | 13/13 | 0 | 1 | 0 |
| step_forward | off | task passed | 37 | 17 | – | – | – | 7 |
| walk_forward | on | CERTIFIED | 38 | 23 | 32/32 | 0 | 5 | 0 |
| walk_forward | off | task passed | 38 | 26 | – | – | – | 0 |
| turn_then_step | on | CERTIFIED | 23 | 10 | 21/25 | 3 | 1 | 3 |
| turn_then_step | off | task passed | 20 | 9 | – | – | – | 0 |

"Task passed" means the tool measured every check and acceptance criterion as passing. In bare mode there is
no certification, so the model only learned that through `check`.

## What this shows

- **Haiku solved every v1 task, with and without the protocol.** On these tasks the quiz and the prediction
  gate made no measurable difference to success.
- **What carried Haiku was the tool doing the math.** Plants and swings are solved by IK, and `check` names
  what's wrong. Every bare run leaned on `check` and fixed what it reported.
- **The protocol didn't cost much.** Tool calls were similar or lower with it (16 vs 37, 38 vs 38, 23 vs 20),
  and prediction accuracy was high (66/70 overall).
- **The v1 tasks are too easy to separate the arms.** Separating them needs harder tasks, plus a baseline
  with Blender-style raw rotations and no IK. That comparison would show what the tool layer itself is worth.

## Where Haiku struggled (from its own reports)

- **Quiz call shape:** the start text showed `answer_quiz({"q1": ...})`, but the call needs `{"answers": {...}}`. Two runs tripped on it.
- **Claims in prose:** `finish` rejected plain-English claims; only prediction syntax works.
- **The relevance gate:** predictions that were already true before the edit got rejected, so the model
  had to re-predict at a frame the edit changes (5 rejected edits on the walk).
- **Fixing a misplaced plant** took 7 undos, because a plant can't be replaced in place.
- **Reach and flat-foot limits:** a stance foot far behind the pelvis needs more than 30° of ankle bend and
  sinks its toes. Real feet lift the heel; v1 feet stay flat.
- **Turning on planted feet:** the heel sweeps about 0.09 m during a pivot, and Haiku noticed this itself.
  v2 makes planted feet hold their heading.

## Caveats

One run per cell, one model, three tasks. This shows a direction, not a statistical result.
