# axiom3d

A 3D workbench built for AI models, not humans.

Cheap and fast models fail at 3D in predictable ways: they invent rotation
angles, get signs and handedness backwards, misread renders, and declare a
task finished while the scene says otherwise. axiom3d is built around those
failures:

1. **The tool computes, the model decides.** The model says "hip flexion +30°"
   or "plant the left foot 0.3 m forward"; axiom3d does the rotation math.
2. **The model predicts, the tool grades.** Every edit carries a prediction
   the tool checks against the measured result.
3. **Text measurements first, images second.**
4. **Finishing is gated.** axiom3d never certifies work that fails its checks.

Status: under construction. The design spec lives in
[`docs/superpowers/specs/2026-10-24-axiom3d-design.md`](docs/superpowers/specs/2026-10-24-axiom3d-design.md).
