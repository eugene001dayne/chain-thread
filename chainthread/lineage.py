"""
chainthread/lineage.py
Lineage Graph — every envelope hop is recorded as a node in a directed graph.
Gives you full provenance: who sent what, when, and what changed.
"""

import uuid
from datetime import datetime, timezone
from typing import Optional


class LineageGraph:
    """
    Lightweight in-memory directed acyclic graph of envelope hops.

    Each node = one agent handoff.
    Edges = parent → child (the envelope that produced the next one).

    In production, persist nodes to a Supabase table:
        CREATE TABLE lineage_nodes (
            id TEXT PRIMARY KEY,
            trace_id TEXT NOT NULL,
            parent_id TEXT,
            agent_from TEXT,
            agent_to TEXT,
            timestamp TIMESTAMPTZ,
            envelope_snapshot JSONB,
            contract_status TEXT
        );
    """

    def __init__(self):
        self._nodes: dict[str, dict] = {}   # node_id → node
        self._edges: list[tuple[str, str]] = []  # (parent_id, child_id)

    # ------------------------------------------------------------------ #
    #  Create                                                              #
    # ------------------------------------------------------------------ #

    def record_hop(
        self,
        envelope: dict,
        agent_from: str,
        agent_to: str,
        contract_status: str = "passed",   # "passed" | "blocked"
        parent_node_id: Optional[str] = None,
    ) -> str:
        """
        Record one envelope handoff.  Returns the new node_id.

        Pass parent_node_id = the node_id returned by the previous hop
        to chain the lineage correctly.

        The trace_id is threaded automatically:
        - If the envelope already has a trace_id, it's kept.
        - If not (first hop), a new one is minted.
        """
        # Ensure trace_id exists on the envelope
        trace_id = envelope.get("trace_id") or str(uuid.uuid4())
        envelope["trace_id"] = trace_id

        node_id = str(uuid.uuid4())
        node = {
            "node_id": node_id,
            "trace_id": trace_id,
            "parent_node_id": parent_node_id,
            "agent_from": agent_from,
            "agent_to": agent_to,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "contract_status": contract_status,
            "confidence": envelope.get("confidence"),
            "hop_count": envelope.get("hop_count", 0),
            "envelope_snapshot": {
                k: v for k, v in envelope.items()
                if k not in ("payload",)    # strip large payload blobs
            },
        }
        self._nodes[node_id] = node

        if parent_node_id:
            self._edges.append((parent_node_id, node_id))

        return node_id

    # ------------------------------------------------------------------ #
    #  Query                                                               #
    # ------------------------------------------------------------------ #

    def get_trace(self, trace_id: str) -> list[dict]:
        """
        Return all nodes for a given trace_id, sorted chronologically.
        This is the full journey of one envelope chain.
        """
        nodes = [n for n in self._nodes.values() if n["trace_id"] == trace_id]
        return sorted(nodes, key=lambda n: n["timestamp"])

    def get_path(self, node_id: str) -> list[dict]:
        """
        Walk backwards from node_id to the root, returning the ancestry chain.
        Useful for debugging exactly how an envelope reached a failure state.
        """
        path = []
        current_id = node_id
        visited = set()

        while current_id:
            if current_id in visited:
                break  # cycle guard
            visited.add(current_id)
            node = self._nodes.get(current_id)
            if not node:
                break
            path.append(node)
            current_id = node.get("parent_node_id")

        return list(reversed(path))

    def get_children(self, node_id: str) -> list[dict]:
        """Return all direct children of a node."""
        child_ids = [child for parent, child in self._edges if parent == node_id]
        return [self._nodes[cid] for cid in child_ids if cid in self._nodes]

    def get_node(self, node_id: str) -> Optional[dict]:
        return self._nodes.get(node_id)

    # ------------------------------------------------------------------ #
    #  Replay                                                              #
    # ------------------------------------------------------------------ #

    def replay(self, trace_id: str) -> list[dict]:
        """
        Return the full sequence of envelope snapshots for a trace.
        Can be fed back into validate_envelope() to reproduce the run.
        """
        return [
            n["envelope_snapshot"]
            for n in self.get_trace(trace_id)
        ]

    # ------------------------------------------------------------------ #
    #  Visualise (text tree — pipe into your logs)                        #
    # ------------------------------------------------------------------ #

    def print_tree(self, trace_id: str) -> str:
        nodes = self.get_trace(trace_id)
        if not nodes:
            return f"No lineage found for trace_id: {trace_id}"

        lines = [f"Lineage trace: {trace_id}"]
        for i, node in enumerate(nodes):
            prefix = "  " * i + ("└─ " if i > 0 else "◉  ")
            status_icon = "✓" if node["contract_status"] == "passed" else "✗"
            lines.append(
                f"{prefix}[{status_icon}] {node['agent_from']} → {node['agent_to']}"
                f"  |  confidence: {node['confidence']}  "
                f"|  hop: {node['hop_count']}  "
                f"|  {node['timestamp'][:19]}"
            )
        return "\n".join(lines)

    # ------------------------------------------------------------------ #
    #  Stats                                                               #
    # ------------------------------------------------------------------ #

    def summary(self) -> dict:
        total = len(self._nodes)
        passed = sum(1 for n in self._nodes.values() if n["contract_status"] == "passed")
        blocked = total - passed
        unique_traces = len({n["trace_id"] for n in self._nodes.values()})
        return {
            "total_hops": total,
            "passed": passed,
            "blocked": blocked,
            "unique_traces": unique_traces,
        }