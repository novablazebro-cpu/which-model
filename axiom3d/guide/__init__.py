"""Guide topics served by the guide tool."""

from __future__ import annotations

from importlib import resources

TOPICS = ("conventions", "walking", "vessels", "predictions", "calculator", "tools")


def read_topic(name: str) -> str:
    if name not in TOPICS:
        raise KeyError(f"unknown topic {name!r}; topics: {', '.join(TOPICS)}")
    return resources.files(__package__).joinpath(f"{name}.md").read_text(encoding="utf-8")
