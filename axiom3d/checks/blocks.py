"""Block checks: models that cannot stand or do not hold together, and why."""

from __future__ import annotations

from axiom3d.checks.base import CheckContext, CheckResult
from axiom3d.model.blocks import measure_blocks


def blocks_checks(ctx: CheckContext) -> list[CheckResult]:
    model = ctx.clip.blocks
    if model is None or not model.boxes:
        return [CheckResult("blocks.empty", "error", [], "the model has no boxes yet",
                            hint="call add_box(name, low=[x, y, z], high=[x, y, z]): corners in whole pixels")]
    m = measure_blocks(model)
    out = []
    for name in m.below_ground:
        box = model.get(name)
        out.append(CheckResult(
            "blocks.below_ground", "error", [], f"{name} reaches z = {box.low[2]}, below the ground (z = 0)",
            {"box": name, "low_z": box.low[2]}, "the model stands on z = 0: nothing may go below it."))
    for name in m.floating:
        box = model.get(name)
        out.append(CheckResult(
            "blocks.floating", "error", [],
            f"{name} (z {box.low[2]}..{box.high[2]}) floats: it touches nothing that reaches the ground",
            {"box": name},
            "a box rests on another when its low z equals the other's high z and they share some x and y. "
            "Touching along an edge counts; touching at a single corner does not."))
    for a, b, volume in m.overlaps:
        out.append(CheckResult(
            "blocks.overlap", "warning", [], f"{a} and {b} overlap by {volume} px³: they share space",
            {"boxes": [a, b], "volume": volume},
            "boxes should meet at their faces, not pass into each other: a's high corner equals b's low corner "
            "on the axis where they meet."))
    return out
