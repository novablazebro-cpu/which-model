# Calculator

`calc(expr)` does exact math on the scene, so you never have to estimate a
number. It never changes the scene, and you can use it at any time, even
before the quiz.

## Statements
- `dist(left_ankle@24, pelvis@24)` evaluates and shows the result.
- `stride = dist(left_ankle@24, left_ankle@0)` saves a variable for this session.
- Separate several statements with `;`.
- Use a saved variable in a prediction with `$`: `left_ankle.forward@24 ~= $stride ± 0.02`.
- Variable names use lowercase letters, digits and `_`; at most 50 per session.

## Reading the scene
- `left_toe` is a point's world position [x, y, z] at the last frame. `left_toe@12` is the same at frame 12.
- `left_toe.z@12`, `left_toe.forward@12`, `left_toe.left@12`: one coordinate (forward and left are track coordinates).
- `left_hip.flexion@12`: a joint angle in degrees.
- `root.forward@12`, `root.left`, `root.height`, `root.heading`.

## Functions
| function | gives |
|---|---|
| `dist(a, b)` | distance between two points |
| `angle(a, b, c)` | angle at b, in degrees |
| `vec(a, b)` | the vector from a to b |
| `dot`, `cross`, `norm`, `unit` | vector math |
| `proj(v, axis)` | length of v along axis |
| `track(p)` | [forward, left, z] in track coordinates |
| `char(v, frame)` | [forward, left, up] of a vector in the mannequin's own frame at that frame |
| `world_from_track([f, l, z])` | a world position from track coordinates |
| `reach(h)` | how far a foot can sit in front of or behind its hip with the pelvis at height h |
| `knee_needed(h, horizontal)` | the knee bend needed for a flat foot that far from the hip |
| `sin`, `cos`, `tan` | take degrees |
| `asin`, `acos`, `atan2` | return degrees |
| `sqrt`, `abs`, `min`, `max`, `round`, `lerp`, `clamp` | as usual |

Constants: `thigh`, `shank`, `leg`, `ankle_height`, `pelvis_height`,
`hip_half_width`, `foot_length`, `fps`, `start`, `end`, `pi`, `FORWARD0`,
`LEFT0`, `UP`.

## Examples
- `reach(0.89)`: about 0.25, so a planted foot can sit up to 0.25 m from its hip.
- `knee_needed(0.92, 0)`: about 15 degrees of knee bend at mid-stance.
- `step = 0.36; mid = step / 2`, then plant at `forward=0.36` and predict `root.forward@24 ~= $mid ± 0.02`.
- `char(vec(pelvis@24, left_toe@24), 24).x`: how far the toe is in front of the pelvis at frame 24.
