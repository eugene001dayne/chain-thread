"""
chainthread/envelope.py
Updated core validator — integrates DLQ, Lineage Graph, and Confidence Decay.

Drop-in replacement for your existing validate_envelope logic.
All three new systems are opt-in via the kwargs — your existing calls still work.
"""

import uuid
from datetime import datetime, timezone
from typing import Optional

from .dlq import DeadLetterQueue
from .lineage import LineageGraph
from .confidence_decay import apply_decay, check_minimum_confidence, get_decay_config


# ------------------------------------------------------------------ #
#  Default required contract fields                                   #
# ------------------------------------------------------------------ #

DEFAULT_REQUIRED_FIELDS = ["agent_id", "payload", "confidence", "timestamp"]


# ------------------------------------------------------------------ #
#  Envelope factory                                                    #
# ------------------------------------------------------------------ #

def create_envelope(
    agent_id: str,
    payload: dict,
    confidence: float,
    required_output_fields: Optional[list[str]] = None,
    trace_id: Optional[str] = None,
    **extra,
) -> dict:
    """
    Create a new envelope ready for validation.

    trace_id: if None, a new trace is started.
               Pass an existing trace_id to continue a chain.
    """
    return {
        "envelope_id": str(uuid.uuid4()),
        "trace_id": trace_id or str(uuid.uuid4()),
        "agent_id": agent_id,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "confidence": confidence,
        "payload": payload,
        "hop_count": 0,
        "decay_history": [],
        "required_output_fields": required_output_fields or [],
        **extra,
    }


# ------------------------------------------------------------------ #
#  Core validate function                                              #
# ------------------------------------------------------------------ #

def validate_envelope(
    envelope: dict,
    required_fields: Optional[list[str]] = None,
    type_checks: Optional[dict] = None,
    minimum_confidence: float = 0.0,
    agent_from: str = "unknown",
    agent_to: str = "unknown",
    # New systems (all optional — existing calls unaffected)
    dlq: Optional[DeadLetterQueue] = None,
    lineage: Optional[LineageGraph] = None,
    apply_confidence_decay: bool = False,
    parent_node_id: Optional[str] = None,
) -> dict:
    """
    Validate an envelope against a contract.

    Returns:
    {
        "contract_passed": bool,
        "status": "delivered" | "blocked",
        "violations": [...],
        "envelope": {...},          # mutated envelope (decay applied if requested)
        "dlq_id": str | None,       # set if envelope was captured by DLQ
        "node_id": str | None,      # lineage node id for this hop
    }

    New params:
        dlq                    — pass a DeadLetterQueue instance to auto-capture failures
        lineage                — pass a LineageGraph instance to record every hop
        apply_confidence_decay — set True to degrade confidence before validation
        parent_node_id         — lineage node_id of the upstream hop (for chaining)
    """
    if required_fields is None:
        required_fields = DEFAULT_REQUIRED_FIELDS

    violations = []

    # ── 1. Apply confidence decay BEFORE checking confidence floor ──
    if apply_confidence_decay:
        config = get_decay_config(envelope)
        envelope = apply_decay(envelope, config)

    # ── 2. Required field checks ──
    for field in required_fields:
        if field not in envelope or envelope[field] is None:
            violations.append(f"Required field '{field}' is missing.")

    # ── 3. Type checks ──
    if type_checks:
        for field, expected_type in type_checks.items():
            if field in envelope:
                actual = envelope[field]
                if not isinstance(actual, expected_type):
                    violations.append(
                        f"Field '{field}' expected {expected_type.__name__}, "
                        f"got {type(actual).__name__}."
                    )

    # ── 4. Confidence floor check ──
    if minimum_confidence > 0.0:
        ok, msg = check_minimum_confidence(envelope, minimum_confidence)
        if not ok:
            violations.append(msg)

    # ── 5. Build result ──
    passed = len(violations) == 0
    status = "delivered" if passed else "blocked"
    dlq_id = None
    node_id = None

    # ── 6. Dead Letter Queue capture on failure ──
    if not passed and dlq is not None:
        dlq_id = dlq.capture(
            envelope=envelope,
            violations=violations,
            source_agent=agent_from,
        )

    # ── 7. Lineage recording (always, pass or fail) ──
    if lineage is not None:
        node_id = lineage.record_hop(
            envelope=envelope,
            agent_from=agent_from,
            agent_to=agent_to,
            contract_status="passed" if passed else "blocked",
            parent_node_id=parent_node_id,
        )

    return {
        "contract_passed": passed,
        "status": status,
        "violations": violations,
        "envelope": envelope,
        "dlq_id": dlq_id,
        "node_id": node_id,
    }