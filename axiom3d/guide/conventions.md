# Conventions

## World frame
- Right-handed, **Z up**, metres, degrees. The ground is z = 0.
- At heading 0 the mannequin **faces -Y** and its **left is +X**.
- Positive heading turns it left (counter-clockwise seen from above).
  At heading h: forward = (sin h, -cos h, 0), left = (cos h, sin h, 0).

## Track coordinates
Every position you give a command (`forward`, `left`) is a **track coordinate**.
They are measured from the task's start point along the task's start facing.
They do not rotate when the mannequin turns: after turning to heading 90 at a
start heading of 0, "the new forward" is the track's +left axis.

## Anatomy: positive = the anatomical motion
You never pick rotation axes. You set anatomical angles and the tool converts them.

| channel | positive angle moves |
|---|---|
| hip / shoulder flexion | the limb forward |
| knee flexion | the foot backward (the knee only bends this way) |
| elbow flexion | the hand forward and up (the elbow only bends this way) |
| ankle dorsiflexion | the toes up |
| hip / shoulder abduction | the limb away from the midline (each side) |
| hip / shoulder internal_rotation | the toes / forearm toward the midline |
| spine / neck flexion | the head forward |
| spine / neck lateral_bend, twist | toward the mannequin's left |

Knee and elbow flexion are never negative: a negative value is hyperextension.

## Why legs go backward
A hanging bone points along (0, 0, -1). Rotating it +t about world +X gives
y' = y·cos t - z·sin t = +sin t. So **a positive raw X rotation swings a hanging
leg toward +Y, which is BACKWARD** at heading 0. The hip and the knee need
opposite raw signs to move forward. The anatomical channels hide this, so use
them instead of guessing signs.
