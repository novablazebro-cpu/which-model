"""Text perception: every number comes with a meaning the tool computed, not the model."""

from __future__ import annotations

from axiom3d.conventions import CONTACT_EPS, CONVENTIONS_TEXT
from axiom3d.measure import foot_contact, relation, support_label, track_coords


def _limit_text(dof, value: float) -> str:
    if value >= 0 and dof.max_deg > 0:
        side = f"{100 * value / dof.max_deg:.0f}% of range on that side"
    elif value < 0 and dof.min_deg < 0:
        side = f"{100 * value / dof.min_deg:.0f}% of range on that side"
    else:
        side = "no range on that side"
    flag = "  !! OUTSIDE LIMIT" if value < dof.min_deg - 0.5 or value > dof.max_deg + 0.5 else ""
    return f"(limit {dof.min_deg:g}..{dof.max_deg:g}, {side}){flag}"


def _point_line(clip, state, name: str) -> str:
    p = state.points[name]
    f, l = track_coords(clip, p[:2])
    line = f"{name:<14} world({p[0]:+.2f},{p[1]:+.2f},{p[2]:+.2f}) track(fwd {f:+.2f}, left {l:+.2f})"
    if name != "pelvis":
        rel = relation(state, name, "pelvis")
        fb = "IN FRONT of" if rel["forward"] >= 0 else "BEHIND"
        lr = "LEFT" if rel["left"] >= 0 else "RIGHT"
        line += f"  {fb} pelvis by {abs(rel['forward']):.2f} m, {lr} by {abs(rel['left']):.2f} m"
    if p[2] <= CONTACT_EPS:
        line += ", ON ground"
    return line


def describe_frame(skel, clip, state, hints: bool = True) -> str:
    fps = clip.timeline.fps
    r = state.root_position
    f, l = track_coords(clip, r[:2])
    out = [
        f"frame {state.frame} (t={state.frame / fps:.2f} s)",
        CONVENTIONS_TEXT,
        f"root: world({r[0]:+.2f},{r[1]:+.2f},{r[2]:+.2f}) track(fwd {f:+.2f}, left {l:+.2f}) heading {state.heading_deg:+.1f} deg",
        "POINTS (relative to the pelvis, in the mannequin's own frame):",
    ]
    out += [_point_line(clip, state, name) for name in skel.point_names()]
    out.append("ANGLES (anatomical, degrees):")
    for channel in skel.channels():
        v = state.angles[channel]
        out.append(f"{channel:<28} {v:+6.1f}°  {_limit_text(skel.dof(channel), v)}")
    legs = []
    for side in ("left", "right"):
        ik = state.ik[side]
        status = "" if ik is None else (" (IK ok)" if ik.reached else f" (IK SHORT by {ik.shortfall_m:.3f} m)")
        contact = "foot down" if foot_contact(state, side) else "foot up"
        legs.append(f"{side}={state.leg_modes[side]}{status}, {contact}")
    out.append("LEGS: " + "; ".join(legs))
    if state.notes:
        out.append("NOTES: " + " | ".join(state.notes))
    if hints and any(ik is not None and not ik.reached for ik in state.ik.values()):
        out.append("hint: a leg can't reach its target; lower the root height or plant the foot nearer the hip.")
    return "\n".join(out)


def describe_timeline(skel, clip, states, stride: int = 2) -> str:
    rows = ["frame root_fwd   L_h    R_h  L_contact R_contact support"]
    picks = [s for i, s in enumerate(states) if i % max(1, stride) == 0]
    if picks[-1] is not states[-1]:
        picks.append(states[-1])
    for s in picks:
        fwd = track_coords(clip, s.root_position[:2])[0]
        lh = min(s.points["left_heel"][2], s.points["left_toe"][2])
        rh = min(s.points["right_heel"][2], s.points["right_toe"][2])
        lc = "Y" if foot_contact(s, "left") else "-"
        rc = "Y" if foot_contact(s, "right") else "-"
        rows.append(f"{s.frame:>5} {fwd:+8.3f} {lh:6.3f} {rh:6.3f} {lc:>10} {rc:>9} {support_label(s):>7}")
    return "\n".join(rows)
