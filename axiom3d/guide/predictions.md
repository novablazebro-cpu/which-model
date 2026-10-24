# Predictions

Every edit takes `expect=[...]`: what you predict the edit will do. The tool
applies the edit, measures, and shows PASS or FAIL with the measured value.
At least one prediction per edit must be **precise**. If one fails, call `undo()`
or `accept_discrepancy(reason)` before the next edit.

## Subjects
- `<point>.x|y|z|height`: world coordinates. Points include pelvis, head_top,
  left_hip, left_knee, left_ankle, left_heel, left_toe, left_shoulder,
  left_elbow, left_wrist, left_hand, and the right_ versions.
- `<point>.forward|left`: **track** coordinates (from the start point, along the start facing).
- `root.x|y|z|height|forward|left|heading`
- a channel such as `left_hip.flexion` or `right_knee.flexion` (degrees)
- `slide(<point>)`, `min_height(<point>)`, `max_height(<point>)`: measured over a frame range

## Forms
- `subject < 0.3`, `>`, `<=`, `>=`
- `subject ~= 0.36 ± 0.05` (you can also write `+-` or `+/-`)
- `subject in [10, 40]`
- `subject < other_subject`, e.g. `left_toe.z < right_toe.z`
- `left_toe in_front_of pelvis`, plus `behind`, `left_of`, `right_of`, `above`, `below` (in the mannequin's own frame)
- `left_heel on_ground`

## Frames
Add `@12`, `@0..24` or `@all` after the subject or at the end.
Without one, an edit's predictions use the edited frame (the end frame for
plant_foot and swing_foot), and metrics use the whole timeline.

## Precise means
- `~=` with a tolerance of at most 0.15 m (20 deg for angles and heading)
- `in [a, b]` with a width of at most 0.15 m (20 deg)
- any relation (`in_front_of`, `on_ground`, ...) or a subject-vs-subject comparison
- `slide(...) < v` with v of at most 0.05

## Examples
- `left_ankle.forward ~= 0.36 ± 0.03`
- `left_toe in_front_of pelvis @24`
- `right_heel on_ground @all`
- `slide(right_heel) < 0.02`
- `left_knee.flexion in [20, 50] @12`
- `max_height(left_ankle) ~= 0.15 ± 0.02`
- `root.forward@48 ~= 1.05 ± 0.05`
- `root.heading ~= 90 ± 5 @36`
