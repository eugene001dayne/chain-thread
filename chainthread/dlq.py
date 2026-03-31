"""
chainthread/dlq.py
Dead Letter Queue — captures blocked envelopes with full violation context.
Supports inspect, patch, and re-inject without restarting the pipeline.
"""

import json
import uuid
from datetime import datetime, timezone
from typing import Optional


class DeadLetterQueue:
    def __init__(self):
        # In production, swap this list for a Supabase table or Redis list.
        self._store: list[dict] = []

    # ------------------------------------------------------------------ #
    #  Core write                                                          #
    # ------------------------------------------------------------------ #

    def capture(self, envelope: dict, violations: list[str], source_agent: str = "unknown") -> str:
        """
        Store a blocked envelope.  Returns the dlq_id so the caller can
        reference it in logs / API responses.
        """
        dlq_id = str(uuid.uuid4())
        record = {
            "dlq_id": dlq_id,
            "captured_at": datetime.now(timezone.utc).isoformat(),
            "source_agent": source_agent,
            "violations": violations,
            "envelope": envelope,          # full original envelope preserved
            "status": "pending",           # pending | patched | reinjected | dropped
            "patch_history": [],
        }
        self._store.append(record)
        return dlq_id

    # ------------------------------------------------------------------ #
    #  Inspection                                                          #
    # ------------------------------------------------------------------ #

    def list_pending(self) -> list[dict]:
        """Return all envelopes still waiting for a decision."""
        return [r for r in self._store if r["status"] == "pending"]

    def get(self, dlq_id: str) -> Optional[dict]:
        """Fetch a single DLQ record by ID."""
        for r in self._store:
            if r["dlq_id"] == dlq_id:
                return r
        return None

    def summary(self) -> dict:
        """Quick health snapshot — useful for dashboards / logging."""
        statuses = {}
        for r in self._store:
            statuses[r["status"]] = statuses.get(r["status"], 0) + 1
        return {
            "total": len(self._store),
            "by_status": statuses,
        }

    # ------------------------------------------------------------------ #
    #  Patch + re-inject                                                   #
    # ------------------------------------------------------------------ #

    def patch(self, dlq_id: str, field_patches: dict) -> dict:
        """
        Apply field-level patches to a blocked envelope so it can be retried.

        field_patches = {"confidence": 0.85, "payload": {"answer": "corrected"}}

        Returns the patched envelope (not yet re-injected).
        """
        record = self.get(dlq_id)
        if record is None:
            raise KeyError(f"DLQ record not found: {dlq_id}")
        if record["status"] == "reinjected":
            raise ValueError(f"Envelope {dlq_id} already reinjected.")

        # Deep-merge patches into the envelope copy
        patched = json.loads(json.dumps(record["envelope"]))  # cheap deep copy
        for key, value in field_patches.items():
            patched[key] = value

        record["patch_history"].append({
            "patched_at": datetime.now(timezone.utc).isoformat(),
            "patches": field_patches,
        })
        record["envelope"] = patched
        record["status"] = "patched"
        return patched

    def reinject(self, dlq_id: str) -> dict:
        """
        Mark envelope as reinjected and return it so the caller can pass it
        back into validate_envelope() / the pipeline.

        Raises if the envelope hasn't been patched since capture.
        """
        record = self.get(dlq_id)
        if record is None:
            raise KeyError(f"DLQ record not found: {dlq_id}")
        if record["status"] == "pending":
            raise ValueError(
                "Patch the envelope before reinjecting. "
                "Call dlq.patch(dlq_id, {...}) first."
            )
        if record["status"] == "reinjected":
            raise ValueError(f"Envelope {dlq_id} already reinjected.")

        record["status"] = "reinjected"
        record["reinjected_at"] = datetime.now(timezone.utc).isoformat()
        return record["envelope"]

    def drop(self, dlq_id: str, reason: str = "") -> None:
        """Permanently discard an envelope (e.g. genuinely bad data)."""
        record = self.get(dlq_id)
        if record is None:
            raise KeyError(f"DLQ record not found: {dlq_id}")
        record["status"] = "dropped"
        record["drop_reason"] = reason

    # ------------------------------------------------------------------ #
    #  Persistence helpers (swap for Supabase in production)              #
    # ------------------------------------------------------------------ #

    def export_json(self) -> str:
        """Dump entire queue to JSON string — for saving to disk or DB."""
        return json.dumps(self._store, indent=2)

    def load_json(self, raw: str) -> None:
        """Restore queue from a JSON string."""
        self._store = json.loads(raw)