import httpx
from typing import Optional, List, Dict, Any


class ChainThread:
    """
    Python SDK for ChainThread — open agent handoff protocol
    and verification infrastructure.
    """

    def __init__(self, base_url: str = "https://chain-thread.onrender.com"):
        self.base_url = base_url.rstrip("/")

    def _get(self, path: str):
        with httpx.Client() as client:
            r = client.get(f"{self.base_url}{path}")
            r.raise_for_status()
            return r.json()

    def _post(self, path: str, data: dict):
        with httpx.Client() as client:
            r = client.post(f"{self.base_url}{path}", json=data)
            r.raise_for_status()
            return r.json()

    # --- Chains ---

    def create_chain(self, name: str, description: str = None, tags: dict = {}):
        return self._post("/chains", {
            "name": name,
            "description": description,
            "tags": tags
        })

    def list_chains(self):
        return self._get("/chains")

    # --- Envelopes ---

    def send_envelope(
        self,
        chain_id: str,
        sender_id: str,
        sender_role: str,
        receiver_id: str,
        receiver_role: str,
        payload: Dict[str, Any],
        summary: str,
        provenance: List[Dict] = [],
        contract: Dict = {},
        on_fail: str = "block"
    ):
        return self._post("/envelopes", {
            "chain_id": chain_id,
            "sender_id": sender_id,
            "sender_role": sender_role,
            "receiver_id": receiver_id,
            "receiver_role": receiver_role,
            "payload": payload,
            "summary": summary,
            "provenance": provenance,
            "contract": contract,
            "on_fail": on_fail
        })

    def get_envelope(self, envelope_id: str):
        return self._get(f"/envelopes/{envelope_id}")

    def get_chain_envelopes(self, chain_id: str):
        return self._get(f"/chains/{chain_id}/envelopes")

    def validate_envelope(self, envelope_id: str):
        return self._post(f"/envelopes/{envelope_id}/validate", {})

    # --- Violations ---

    def get_violations(self):
        return self._get("/violations")

    # --- Checkpoints ---

    def create_checkpoint(
        self,
        chain_id: str,
        state_snapshot: Dict[str, Any],
        envelope_id: str = None,
        checkpoint_name: str = None
    ):
        return self._post("/checkpoints", {
            "chain_id": chain_id,
            "envelope_id": envelope_id,
            "state_snapshot": state_snapshot,
            "checkpoint_name": checkpoint_name
        })

    def get_checkpoints(self, chain_id: str):
        return self._get(f"/checkpoints/{chain_id}")

    # --- Dashboard ---

    def stats(self):
        return self._get("/dashboard/stats")

    def health(self):
        return self._get("/health")