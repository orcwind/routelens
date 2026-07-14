from __future__ import annotations

HIDEOUT_KEYWORDS = ("hideout", "藏身处", "藏身處")


def is_hideout_area(area: str) -> bool:
    if not area:
        return False
    lowered = area.lower()
    return any(keyword in lowered for keyword in HIDEOUT_KEYWORDS)
