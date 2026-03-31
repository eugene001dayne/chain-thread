"""
demo.py
Run this to see all three new ChainThread systems working together.

    python demo.py

Simulates a 3-agent pipeline:
    Agent A  →  Agent B  →  Agent C
         (pass)       (fail — low confidence → DLQ → patch → reinject → pass)
"""

import sys
import os
sys.path.insert(0, os.path.dirname(__file__))

from chainthread.dlq import DeadLetterQueue
from chainthread.lineage import LineageGraph
from chainthread.confidence_decay import DecayConfig, project_decay, set_decay_config
from chainthread.envelope import create_envelope, validate_envelope


# ─────────────────────────────────────────────────────────────────── #
#  Setup shared infrastructure                                         #
# ─────────────────────────────────────────────────────────────────── #

dlq = DeadLetterQueue()
lineage = LineageGraph()

# Custom decay: 12% linear loss per hop, floor at 0.20
decay_cfg = DecayConfig(decay_rate=0.12, decay_model="linear", min_floor=0.20)


# ─────────────────────────────────────────────────────────────────── #
#  Hop 1: Agent A  →  Agent B  (passes)                               #
# ─────────────────────────────────────────────────────────────────── #

print("\n" + "═" * 60)
print("HOP 1: Agent A → Agent B")
print("═" * 60)

envelope = create_envelope(
    agent_id="agent-a",
    payload={"query": "What is the ESG risk score for Acme Corp?"},
    confidence=0.91,
)
set_decay_config(envelope, decay_cfg)

result_1 = validate_envelope(
    envelope=envelope,
    required_fields=["agent_id", "payload", "confidence", "timestamp"],
    type_checks={"confidence": float},
    minimum_confidence=0.50,
    agent_from="agent-a",
    agent_to="agent-b",
    dlq=dlq,
    lineage=lineage,
    apply_confidence_decay=True,   # decay applied before threshold check
    parent_node_id=None,           # first hop, no parent
)

node_id_1 = result_1["node_id"]

print(f"contract_passed : {result_1['contract_passed']}")
print(f"status          : {result_1['status']}")
print(f"confidence      : {result_1['envelope']['confidence']}  (after 1 hop decay)")
print(f"hop_count       : {result_1['envelope']['hop_count']}")
print(f"lineage node_id : {node_id_1}")
print(f"violations      : {result_1['violations']}")


# ─────────────────────────────────────────────────────────────────── #
#  Hop 2: Agent B  →  Agent C  (fails — confidence too low)           #
# ─────────────────────────────────────────────────────────────────── #

print("\n" + "═" * 60)
print("HOP 2: Agent B → Agent C  (confidence floor = 0.80 → FAIL)")
print("═" * 60)

# Agent B has done some processing and passes the envelope on
envelope_b = result_1["envelope"].copy()
envelope_b["agent_id"] = "agent-b"
envelope_b["payload"]["answer"] = "ESG score: 72 / 100"

result_2 = validate_envelope(
    envelope=envelope_b,
    required_fields=["agent_id", "payload", "confidence", "timestamp"],
    minimum_confidence=0.80,       # Agent C has a strict floor
    agent_from="agent-b",
    agent_to="agent-c",
    dlq=dlq,
    lineage=lineage,
    apply_confidence_decay=True,
    parent_node_id=node_id_1,      # chain from hop 1
)

node_id_2 = result_2["node_id"]
dlq_id = result_2["dlq_id"]

print(f"contract_passed : {result_2['contract_passed']}")
print(f"status          : {result_2['status']}")
print(f"confidence      : {result_2['envelope']['confidence']}  (after 2 hop decays total)")
print(f"violations      : {result_2['violations']}")
print(f"dlq_id          : {dlq_id}  ← captured in Dead Letter Queue")


# ─────────────────────────────────────────────────────────────────── #
#  DLQ: inspect, patch, reinject                                       #
# ─────────────────────────────────────────────────────────────────── #

print("\n" + "═" * 60)
print("DLQ: inspect → patch → reinject")
print("═" * 60)

print(f"\nDLQ summary: {dlq.summary()}")
pending = dlq.list_pending()
print(f"Pending records: {len(pending)}")
print(f"Violations on first pending: {pending[0]['violations']}")

# Human reviews and patches: override confidence back to acceptable level
patched_envelope = dlq.patch(dlq_id, {"confidence": 0.85})
print(f"\nAfter patch — confidence: {patched_envelope['confidence']}")

# Reinject back into the pipeline
reinjected = dlq.reinject(dlq_id)
print(f"Reinjected envelope confidence: {reinjected['confidence']}")
print(f"DLQ summary after reinject: {dlq.summary()}")

# Re-validate the patched envelope (no additional decay — it was patched, not hopped)
result_3 = validate_envelope(
    envelope=reinjected,
    required_fields=["agent_id", "payload", "confidence", "timestamp"],
    minimum_confidence=0.80,
    agent_from="agent-b",   # same agent, second attempt
    agent_to="agent-c",
    dlq=dlq,
    lineage=lineage,
    apply_confidence_decay=False,  # don't decay again — human approved this value
    parent_node_id=node_id_2,
)

print(f"\nRe-validation after patch:")
print(f"contract_passed : {result_3['contract_passed']}")
print(f"status          : {result_3['status']}")


# ─────────────────────────────────────────────────────────────────── #
#  Lineage: print the full trace tree                                  #
# ─────────────────────────────────────────────────────────────────── #

print("\n" + "═" * 60)
print("LINEAGE TREE")
print("═" * 60)

trace_id = reinjected["trace_id"]
print(lineage.print_tree(trace_id))
print(f"\nLineage summary: {lineage.summary()}")


# ─────────────────────────────────────────────────────────────────── #
#  Confidence decay projection                                         #
# ─────────────────────────────────────────────────────────────────── #

print("\n" + "═" * 60)
print("CONFIDENCE DECAY PROJECTION  (starting 0.91, 8 hops, 12% linear)")
print("═" * 60)

projection = project_decay(0.91, 8, decay_cfg)
for i, conf in enumerate(projection):
    bar = "█" * int(conf * 30)
    print(f"  hop {i}: {conf:.4f}  {bar}")

print("\nDone. All three systems operational.\n")