# Haiku creeper test: axiom3d blocks mode with and without the protocol, and no tool

Date: 2026-10-25. Tool version: commit `cae3187` (branch `v2-work`).
Task: `minecraft_creeper`, a Minecraft creeper from boxes in game pixels with its face on the front, 12 criteria.
Model: the `haiku` agent alias (assumed Haiku 5.5), effort **high**, one run per arm, a 60-tool-call budget each.
Design: `docs/superpowers/specs/2026-10-25-axiom3d-blocks-design.md`.

## Arms

| arm | what Haiku had | prompt |
|---|---|---|
| protocol | axiom3d CLI: quiz, predictions before every edit, certified `finish`, sheet images | `test_prompt("minecraft_creeper", bare=False, via="cli")` |
| bare | the same tools, guide and sheet images; no quiz, no predictions | `test_prompt(..., bare=True)` |
| raw | Python only; writes `creeper.json`, a list of `add_box`/`paint_face` commands | `raw_prompt("minecraft_creeper", workdir)` |

Every arm got the same goal text, the same 12 criteria, and the same conventions text that `start_session` prints. The raw arm did not get the guide's pixel-order table, renders, checks or the quiz: those are the tool. One grader, `axiom3d.eval.blocks`, graded all three, replaying the JSON for the raw arm.

## Results

| | protocol | bare | raw | reference |
|---|---|---|---|---|
| criteria passed | **12/12** (certified) | **12/12** | **12/12** (replay clean) | 12/12 |
| tool calls (from the transcript) | 16 | 12 | 2 | — |
| tokens (harness) | 74k | 66k | 65k | — |
| wall time (harness) | 77 s | 46 s | 45 s | — |
| predictions right | 27/28 | — | — | — |
| rejected edits / discrepancies | 1 / 1 | — | — | — |
| looked at a picture | yes (opened the sheet) | no | had none | — |

All three runs built the same model: legs at x −4..0 / 0..4 and y −4..0 (front) / 0..4 (back), body −4,−2,6 → 4,2,18, head −4,−4,18 → 4,4,26, and the face on the front, the right way up.

## Rule compliance

Every tool call in the three transcripts was audited. The protocol and bare runs used only `axiom3d call` commands in their own folders. The protocol run made one file read: the sheet PNG the tool printed, which the rules allow. The raw run made two shell calls inside its folder: one that wrote and ran `make_creeper.py`, and one that fixed a bug in its own checker.

## What this shows

1. **Success was saturated again.** Every run scored 12/12. The traps blocks mode was built to catch (a face on the back, mirrored or upside down, legs in a row, a turned body) caught nobody: Haiku 5.5 at high effort did not fall into them.
2. **The tool brought no saving here.** Unlike the vase, the no-tool run was as quick and as cheap as the tool runs: writing a dozen boxes as JSON is easy, and there was no mesh to write by hand.
3. **The protocol cost about 30 s and caught no real error.**
   - One edit was rejected: its predictions read `size_x = 4` instead of `box.<name>.size_x ~= 4 ± 0.5`.
   - One discrepancy was a misreading of its own face grid; the paint was right.
4. **A criterion gap of mine.** All three runs put the legs half under the body (y −4..4). The game's creeper, as I remember its model code (about 80% sure), has them further out at y −6..−2 and 2..6, with a gap beneath the body. My task text says the legs are "in front of the body and behind it". The `stance` criterion only checks in front of and behind the body's *centre*, so it passed all three. This is the same class of gap as the vase's waist height. I have not changed the criterion after the fact; it needs the user's call, and ideally a check of the real model.

## Limits

- One run per arm.
- The real creeper's leg layout is from memory.
- The face is symmetric left to right, so a mirrored face cannot fail. The quiz's mirror question tested that instead, and the protocol run answered it right.
- The `haiku` alias is assumed to be Haiku 5.5. Token and time counts come from the harness.

## What a discriminating test needs

Two tasks now saturate at high effort. The next test should be one where Haiku is likely to fail without feedback:
- a model whose face is **not** symmetric (a mob with a side marking, or a sign with text), so mirroring shows;
- painted detail on several faces at once (a full skin), where the pixel order of the side and top faces matters;
- many parts in non-obvious positions (a pig, a chicken, a villager with arms), where floating and overlapping parts become likely;
- the same tasks at low effort or with a 15-call budget.
