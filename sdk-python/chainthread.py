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
    
    # --- Dead Letter Queue ---

    def list_dlq(self, status: str = None):
        path = "/dlq"
        if status:
            path += f"?status={status}"
        return self._get(path)

    def get_dlq_record(self, dlq_id: str):
        return self._get(f"/dlq/{dlq_id}")

    def patch_dlq(self, dlq_id: str, field_patches: dict):
        return self._post(f"/dlq/{dlq_id}/patch", {"field_patches": field_patches})

    def reinject_dlq(self, dlq_id: str):
        return self._post(f"/dlq/{dlq_id}/reinject", {})

    def drop_dlq(self, dlq_id: str, reason: str = ""):
        return self._post(f"/dlq/{dlq_id}/drop", {"reason": reason})

    # --- Lineage ---

    def get_lineage_trace(self, trace_id: str):
        return self._get(f"/lineage/trace/{trace_id}")

    def get_chain_lineage(self, chain_id: str):
        return self._get(f"/lineage/chain/{chain_id}")
    
    # --- Analytics ---

    def analytics_chains(self):
        return self._get("/analytics/chains")

    def analytics_agents(self):
        return self._get("/analytics/agents")

    def analytics_confidence(self):
        return self._get("/analytics/confidence")

    def analytics_violations(self):
        return self._get("/analytics/violations")

    # --- Bidirectional Contracts ---

    def respond_to_envelope(
        self,
        envelope_id: str,
        chain_id: str,
        responder_id: str,
        responder_role: str,
        response_payload: Dict[str, Any],
        response_contract: Dict = {}
    ):
        return self._post(f"/envelopes/{envelope_id}/respond", {
            "chain_id": chain_id,
            "responder_id": responder_id,
            "responder_role": responder_role,
            "response_payload": response_payload,
            "response_contract": response_contract
        })

    def get_envelope_responses(self, envelope_id: str):
        return self._get(f"/envelopes/{envelope_id}/responses")

# --- Webhooks ---

    def create_webhook(
        self,
        name: str,
        url: str,
        chain_id: str = None,
        on_block: bool = True,
        on_violation: bool = True,
        on_low_confidence: bool = False,
        confidence_threshold: float = 0.5,
        active: bool = True
    ):
        return self._post("/webhooks", {
            "name": name,
            "url": url,
            "chain_id": chain_id,
            "on_block": on_block,
            "on_violation": on_violation,
            "on_low_confidence": on_low_confidence,
            "confidence_threshold": confidence_threshold,
            "active": active
        })

    def list_webhooks(self):
        return self._get("/webhooks")

    def delete_webhook(self, webhook_id: str):
        with httpx.Client() as client:
            r = client.delete(f"{self.base_url}/webhooks/{webhook_id}")
            r.raise_for_status()
            return r.json()

    # --- HITL ---

    def list_hitl(self, status: str = None):
        path = "/hitl"
        if status:
            path += f"?status={status}"
        return self._get(path)

    def get_hitl_checkpoint(self, checkpoint_id: str):
        return self._get(f"/hitl/{checkpoint_id}")

    def decide_hitl(self, checkpoint_id: str, decision: str, reviewer_note: str = ""):
        return self._post(f"/hitl/{checkpoint_id}/decide", {
            "decision": decision,
            "reviewer_note": reviewer_note
        })

# --- Contract Registry ---

    def create_registry_contract(
        self,
        name: str,
        version: str,
        required_fields: List[str] = [],
        assertions: List[Dict] = [],
        on_fail: str = "block",
        description: str = None
    ):
        return self._post("/registry", {
            "name": name,
            "version": version,
            "description": description,
            "required_fields": required_fields,
            "assertions": assertions,
            "on_fail": on_fail
        })

    def list_registry_contracts(self):
        return self._get("/registry")

    def get_registry_contract_versions(self, name: str):
        return self._get(f"/registry/{name}")

    def get_registry_contract(self, name: str, version: str):
        return self._get(f"/registry/{name}/{version}")

    def deprecate_registry_contract(self, name: str, version: str):
        with httpx.Client() as client:
            r = client.delete(f"{self.base_url}/registry/{name}/{version}")
            r.raise_for_status()
            return r.json()

    def validate_against_registry(self, name: str, version: str, payload: Dict[str, Any]):
        return self._post(f"/registry/{name}/{version}/validate", payload)

    def diff_registry_contracts(self, name: str, version_a: str, version_b: str):
        return self._get(f"/registry/{name}/diff/{version_a}/{version_b}")

# --- PII ---

    def scan_pii(self, payload: Dict[str, Any], redact: bool = False):
        return self._post("/pii/scan", {
            "payload": payload,
            "redact": redact
        })

    def redact_payload(self, payload: Dict[str, Any]):
        return self._post("/pii/redact", payload)

    # --- Signing ---

    def sign_envelope(self, envelope_id: str, payload: Dict[str, Any], sender_id: str):
        return self._post("/sign", {
            "envelope_id": envelope_id,
            "payload": payload,
            "sender_id": sender_id
        })

    def verify_envelope(self, envelope_id: str, payload: Dict[str, Any], sender_id: str, signature: str):
        return self._post("/verify", {
            "envelope_id": envelope_id,
            "payload": payload,
            "sender_id": sender_id,
            "signature": signature
        })