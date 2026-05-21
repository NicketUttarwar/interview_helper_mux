from __future__ import annotations

from typing import Any


def nonlinear_edl_order(segment_ids: list[str], edges: list[tuple[str, str, float]]) -> list[str]:
    """
    Preset D: simple topological order on a directed graph (networkx).
    ``edges`` are (from_id, to_id, cost); lower cost = preferred edge.
    """
    try:
        import networkx as nx
    except ImportError as e:
        raise ImportError("Install deps for preset D: pip install -r requirements.txt") from e

    g = nx.DiGraph()
    g.add_nodes_from(segment_ids)
    for u, v, _cost in edges:
        if u in segment_ids and v in segment_ids:
            g.add_edge(u, v)
    if not nx.is_directed_acyclic_graph(g):
        return list(segment_ids)
    return list(nx.topological_sort(g))
