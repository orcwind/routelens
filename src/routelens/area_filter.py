from __future__ import annotations

from .hideout_filter import is_hideout_area

__all__ = ["is_hideout_area", "filter_hideout_nodes"]


def filter_hideout_nodes(nodes: list) -> list:
    result = []
    for node in nodes:
        if hasattr(node, "name"):
            name = node.name
        else:
            name = str(node.get("area") or node.get("area_en") or node.get("name", ""))
        if is_hideout_area(name):
            continue
        result.append(node)
    return result
