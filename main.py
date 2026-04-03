from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Optional, List, Any, Dict
from datetime import datetime, timezone
import httpx
import os
import uuid
import json
from dotenv import load_dotenv
import re

load_dotenv()

SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")

HEADERS = {
    "apikey": SUPABASE_KEY,
    "Authorization": f"Bearer {SUPABASE_KEY}",
    "Content-Type": "application/json",
    "Prefer": "return=representation"
}

def db():
    return httpx.Client(base_url=f"{SUPABASE_URL}/rest/v1", headers=HEADERS)

app = FastAPI(
    title="ChainThread",
    description="Open agent handoff protocol and verification infrastructure.",
    version="0.5.0"
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# --- Models ---

class ChainCreate(BaseModel):
    name: str
    description: Optional[str] = None
    tags: Optional[Dict[str, str]] = {}

class ProvenanceEntry(BaseModel):
    field: str
    source: str  # tool_call | model_generated | human_input | prior_envelope
    tool_name: Optional[str] = None
    confidence: Optional[float] = 1.0

class ContractAssertion(BaseModel):
    field: str
    type: str  # exists | type_check | range | regex
    value: Optional[Any] = None

class Contract(BaseModel):
    required_fields: Optional[List[str]] = []
    assertions: Optional[List[ContractAssertion]] = []
    on_fail: Optional[str] = "block"  # block | escalate | log_and_proceed

class EnvelopeCreate(BaseModel):
    chain_id: str
    sender_id: str
    sender_role: str
    receiver_id: str
    receiver_role: str
    payload: Dict[str, Any]
    summary: str
    provenance: Optional[List[ProvenanceEntry]] = []
    contract: Optional[Contract] = Contract()
    on_fail: Optional[str] = "block"

class CheckpointCreate(BaseModel):
    chain_id: str
    envelope_id: Optional[str] = None
    state_snapshot: Dict[str, Any]
    checkpoint_name: Optional[str] = None

# --- Contract Validation ---

def validate_contract(payload: Dict, contract: Contract):
    violations = []

    for field in contract.required_fields:
        if field not in payload:
            violations.append(f"Required field '{field}' is missing.")

    for assertion in contract.assertions:
        field = assertion.field
        if field not in payload:
            violations.append(f"Field '{field}' missing for assertion.")
            continue
        value = payload[field]

        if assertion.type == "exists":
            if value is None:
                violations.append(f"Field '{field}' must not be null.")

        elif assertion.type == "type_check":
            type_map = {"str": str, "int": int, "float": float, "bool": bool, "list": list, "dict": dict}
            expected = assertion.value
            if expected in type_map and not isinstance(value, type_map[expected]):
                violations.append(f"Field '{field}' must be {expected}, got {type(value).__name__}.")

        elif assertion.type == "range":
            try:
                min_val, max_val = assertion.value.get("min"), assertion.value.get("max")
                if min_val is not None and value < min_val:
                    violations.append(f"Field '{field}' value {value} is below minimum {min_val}.")
                if max_val is not None and value > max_val:
                    violations.append(f"Field '{field}' value {value} is above maximum {max_val}.")
            except Exception:
                violations.append(f"Field '{field}' range check failed.")

        elif assertion.type == "regex":
            import re
            pattern = assertion.value
            if not isinstance(value, str) or not re.match(pattern, value):
                violations.append(f"Field '{field}' does not match pattern '{pattern}'.")

    return violations

# --- Webhook Firing ---

def fire_webhooks(chain_id: str, event_type: str, payload: dict):
    """Fire all active webhooks for a chain matching the event type."""
    try:
        with db() as client:
            r = client.get(f"/webhooks?active=eq.true")
            if r.status_code != 200:
                return
            all_webhooks = r.json()

        matching = [
            w for w in all_webhooks
            if (w.get("chain_id") is None or w.get("chain_id") == chain_id)
        ]

        for webhook in matching:
            should_fire = False
            if event_type == "block" and webhook.get("on_block"):
                should_fire = True
            elif event_type == "violation" and webhook.get("on_violation"):
                should_fire = True
            elif event_type == "low_confidence" and webhook.get("on_low_confidence"):
                should_fire = True

            if should_fire:
                try:
                    with httpx.Client(timeout=5) as client:
                        client.post(webhook["url"], json={
                            "event": event_type,
                            "chain_id": chain_id,
                            "timestamp": datetime.now(timezone.utc).isoformat(),
                            "data": payload
                        })
                except Exception:
                    pass  # Never let webhook failure crash the pipeline
    except Exception:
        pass

# --- Routes ---

@app.get("/")
def root():
    return {
        "tool": "ChainThread",
        "version": "0.5.0",
        "status": "running",
        "description": "Open agent handoff protocol and verification infrastructure."
    }

@app.get("/health")
def health():
    try:
        with db() as client:
            r = client.get("/chains?limit=1")
        return {"status": "ok", "database": "connected"}
    except Exception as e:
        return {"status": "ok", "database": "error", "detail": str(e)}

# --- Chains ---

@app.post("/chains")
def create_chain(body: ChainCreate):
    chain_id = str(uuid.uuid4())
    now = datetime.now(timezone.utc).isoformat()
    record = {
        "id": str(uuid.uuid4()),
        "chain_id": chain_id,
        "name": body.name,
        "description": body.description,
        "tags": body.tags,
        "created_at": now,
        "updated_at": now
    }
    with db() as client:
        r = client.post("/chains", json=record)
    if r.status_code not in (200, 201):
        raise HTTPException(status_code=500, detail=r.text)
    return r.json()[0]

@app.get("/chains")
def list_chains():
    with db() as client:
        r = client.get("/chains?order=created_at.desc")
    if r.status_code != 200:
        raise HTTPException(status_code=500, detail=r.text)
    return r.json()

# --- Envelopes ---

@app.post("/envelopes")
def send_envelope(body: EnvelopeCreate):
    # Validate contract first
    violations = validate_contract(body.payload, body.contract)
    contract_passed = len(violations) == 0
    on_fail = body.contract.on_fail or body.on_fail or "block"

    if not contract_passed and on_fail == "block":
        return {
            "status": "blocked",
            "reason": "Contract validation failed",
            "violations": violations,
            "on_fail": "block"
        }

    now = datetime.now(timezone.utc).isoformat()
    envelope_id = str(uuid.uuid4())

    record = {
        "id": envelope_id,
        "chain_id": body.chain_id,
        "sender_id": body.sender_id,
        "sender_role": body.sender_role,
        "receiver_id": body.receiver_id,
        "receiver_role": body.receiver_role,
        "payload": body.payload,
        "summary": body.summary,
        "provenance": [p.dict() for p in body.provenance],
        "contract": body.contract.dict(),
        "on_fail": on_fail,
        "contract_passed": contract_passed,
        "violations": violations,
        "status": "delivered" if contract_passed else on_fail,
        "created_at": now
    }

    with db() as client:
        r = client.post("/envelopes", json=record)
        if r.status_code not in (200, 201):
            raise HTTPException(status_code=500, detail=r.text)

        # Log violations if any
        if not contract_passed:
            for v in violations:
                violation_record = {
                    "id": str(uuid.uuid4()),
                    "envelope_id": envelope_id,
                    "chain_id": body.chain_id,
                    "violation_type": "contract_failure",
                    "severity": "critical" if on_fail == "block" else "warning",
                    "message": v,
                    "on_fail": on_fail,
                    "detected_at": now
                }
                client.post("/contract_violations", json=violation_record)

            # Fire block/violation webhooks
            fire_webhooks(body.chain_id, "block", {
                "envelope_id": envelope_id,
                "violations": violations,
                "sender_role": body.sender_role,
                "receiver_role": body.receiver_role
            })

        # HITL checkpoint — pause if on_fail is escalate
        if not contract_passed and on_fail == "escalate":
            hitl_record = {
                "id": str(uuid.uuid4()),
                "envelope_id": envelope_id,
                "chain_id": body.chain_id,
                "reason": f"Contract failed: {', '.join(violations)}",
                "confidence": body.payload.get("confidence"),
                "status": "pending",
                "created_at": now
            }
            with db() as client2:
                client2.post("/hitl_checkpoints", json=hitl_record)
            fire_webhooks(body.chain_id, "violation", {
                "envelope_id": envelope_id,
                "hitl": True,
                "reason": hitl_record["reason"]
            })

    result = r.json()[0]
    result["violations"] = violations
    result["contract_passed"] = contract_passed
    return result

@app.get("/envelopes/{envelope_id}")
def get_envelope(envelope_id: str):
    with db() as client:
        r = client.get(f"/envelopes?id=eq.{envelope_id}")
    if r.status_code != 200 or not r.json():
        raise HTTPException(status_code=404, detail="Envelope not found")
    return r.json()[0]

@app.get("/chains/{chain_id}/envelopes")
def get_chain_envelopes(chain_id: str):
    with db() as client:
        r = client.get(f"/envelopes?chain_id=eq.{chain_id}&order=created_at.asc")
    if r.status_code != 200:
        raise HTTPException(status_code=500, detail=r.text)
    return {
        "chain_id": chain_id,
        "envelope_count": len(r.json()),
        "envelopes": r.json()
    }

@app.post("/envelopes/{envelope_id}/validate")
def validate_envelope(envelope_id: str):
    with db() as client:
        r = client.get(f"/envelopes?id=eq.{envelope_id}")
    if r.status_code != 200 or not r.json():
        raise HTTPException(status_code=404, detail="Envelope not found")
    envelope = r.json()[0]
    from pydantic import BaseModel
    contract_data = envelope.get("contract", {})
    contract = Contract(**contract_data)
    payload = envelope.get("payload", {})
    violations = validate_contract(payload, contract)
    return {
        "envelope_id": envelope_id,
        "passed": len(violations) == 0,
        "violations": violations
    }

# --- Violations ---

@app.get("/violations")
def get_violations():
    with db() as client:
        r = client.get("/contract_violations?order=detected_at.desc")
    if r.status_code != 200:
        raise HTTPException(status_code=500, detail=r.text)
    return r.json()

# --- Checkpoints ---

@app.post("/checkpoints")
def create_checkpoint(body: CheckpointCreate):
    now = datetime.now(timezone.utc).isoformat()
    record = {
        "id": str(uuid.uuid4()),
        "chain_id": body.chain_id,
        "envelope_id": body.envelope_id,
        "checkpoint_name": body.checkpoint_name,
        "state_snapshot": body.state_snapshot,
        "created_at": now
    }
    with db() as client:
        r = client.post("/checkpoints", json=record)
    if r.status_code not in (200, 201):
        raise HTTPException(status_code=500, detail=r.text)
    return r.json()[0]

@app.get("/checkpoints/{chain_id}")
def get_checkpoints(chain_id: str):
    with db() as client:
        r = client.get(f"/checkpoints?chain_id=eq.{chain_id}&order=created_at.asc")
    if r.status_code != 200:
        raise HTTPException(status_code=500, detail=r.text)
    return r.json()

# --- Dashboard ---

@app.get("/dashboard/stats")
def dashboard_stats():
    with db() as client:
        envelopes = client.get("/envelopes").json()
        violations = client.get("/contract_violations").json()
        chains = client.get("/chains").json()
        checkpoints = client.get("/checkpoints").json()
        dlq_records = client.get("/dead_letter_queue").json()
        lineage_nodes = client.get("/lineage_nodes").json()

    total = len(envelopes)
    passed = sum(1 for e in envelopes if e.get("contract_passed"))
    failed = total - passed
    blocked = sum(1 for e in envelopes if e.get("status") == "block")
    dlq_pending = sum(1 for d in dlq_records if d.get("status") == "pending")
    dlq_reinjected = sum(1 for d in dlq_records if d.get("status") == "reinjected")

    return {
        "total_chains": len(chains),
        "total_envelopes": total,
        "passed": passed,
        "failed": failed,
        "blocked": blocked,
        "total_violations": len(violations),
        "total_checkpoints": len(checkpoints),
        "pass_rate": round(100 * passed / total, 2) if total > 0 else 0,
        "dlq_total": len(dlq_records),
        "dlq_pending": dlq_pending,
        "dlq_reinjected": dlq_reinjected,
        "total_lineage_hops": len(lineage_nodes)
    }
    
# --- Dead Letter Queue ---

@app.get("/dlq")
def list_dlq(status: str = None):
    url = "/dead_letter_queue?order=captured_at.desc"
    if status:
        url += f"&status=eq.{status}"
    with db() as client:
        r = client.get(url)
    if r.status_code != 200:
        raise HTTPException(status_code=500, detail=r.text)
    return r.json()

@app.get("/dlq/{dlq_id}")
def get_dlq_record(dlq_id: str):
    with db() as client:
        r = client.get(f"/dead_letter_queue?dlq_id=eq.{dlq_id}")
    if r.status_code != 200 or not r.json():
        raise HTTPException(status_code=404, detail="DLQ record not found")
    return r.json()[0]

class DLQPatch(BaseModel):
    field_patches: Dict[str, Any]

@app.post("/dlq/{dlq_id}/patch")
def patch_dlq_record(dlq_id: str, body: DLQPatch):
    with db() as client:
        r = client.get(f"/dead_letter_queue?dlq_id=eq.{dlq_id}")
    if r.status_code != 200 or not r.json():
        raise HTTPException(status_code=404, detail="DLQ record not found")
    record = r.json()[0]
    if record["status"] == "reinjected":
        raise HTTPException(status_code=400, detail="Envelope already reinjected")

    # Apply patches to envelope snapshot
    envelope = record["envelope_snapshot"]
    for key, value in body.field_patches.items():
        envelope[key] = value

    patch_entry = {
        "patched_at": datetime.now(timezone.utc).isoformat(),
        "patches": body.field_patches
    }
    patch_history = record.get("patch_history", [])
    patch_history.append(patch_entry)

    with db() as client:
        r = client.patch(
            f"/dead_letter_queue?dlq_id=eq.{dlq_id}",
            json={
                "status": "patched",
                "envelope_snapshot": envelope,
                "patch_history": patch_history
            }
        )
    if r.status_code not in (200, 201, 204):
        raise HTTPException(status_code=500, detail=r.text)
    return {"dlq_id": dlq_id, "status": "patched", "patched_envelope": envelope}

@app.post("/dlq/{dlq_id}/reinject")
def reinject_dlq_record(dlq_id: str):
    with db() as client:
        r = client.get(f"/dead_letter_queue?dlq_id=eq.{dlq_id}")
    if r.status_code != 200 or not r.json():
        raise HTTPException(status_code=404, detail="DLQ record not found")
    record = r.json()[0]
    if record["status"] == "pending":
        raise HTTPException(status_code=400, detail="Patch the envelope before reinjecting")
    if record["status"] == "reinjected":
        raise HTTPException(status_code=400, detail="Already reinjected")

    now = datetime.now(timezone.utc).isoformat()
    with db() as client:
        r = client.patch(
            f"/dead_letter_queue?dlq_id=eq.{dlq_id}",
            json={"status": "reinjected", "reinjected_at": now}
        )
    if r.status_code not in (200, 201, 204):
        raise HTTPException(status_code=500, detail=r.text)
    return {
        "dlq_id": dlq_id,
        "status": "reinjected",
        "envelope": record["envelope_snapshot"]
    }

class DLQDrop(BaseModel):
    reason: Optional[str] = ""

@app.post("/dlq/{dlq_id}/drop")
def drop_dlq_record(dlq_id: str, body: DLQDrop):
    with db() as client:
        r = client.patch(
            f"/dead_letter_queue?dlq_id=eq.{dlq_id}",
            json={"status": "dropped", "drop_reason": body.reason}
        )
    if r.status_code not in (200, 201, 204):
        raise HTTPException(status_code=500, detail=r.text)
    return {"dlq_id": dlq_id, "status": "dropped"}

# --- Lineage ---

@app.post("/lineage")
def record_lineage_hop(
    trace_id: str,
    node_id: str,
    chain_id: str,
    agent_from: str,
    agent_to: str,
    contract_status: str,
    confidence: Optional[float] = None,
    hop_count: Optional[int] = 0,
    parent_node_id: Optional[str] = None,
    envelope_snapshot: Optional[Dict] = None
):
    now = datetime.now(timezone.utc).isoformat()
    record = {
        "id": str(uuid.uuid4()),
        "node_id": node_id,
        "trace_id": trace_id,
        "parent_node_id": parent_node_id,
        "chain_id": chain_id,
        "agent_from": agent_from,
        "agent_to": agent_to,
        "contract_status": contract_status,
        "confidence": confidence,
        "hop_count": hop_count,
        "envelope_snapshot": envelope_snapshot or {},
        "timestamp": now
    }
    with db() as client:
        r = client.post("/lineage_nodes", json=record)
    if r.status_code not in (200, 201):
        raise HTTPException(status_code=500, detail=r.text)
    return r.json()[0]

@app.get("/lineage/trace/{trace_id}")
def get_lineage_trace(trace_id: str):
    with db() as client:
        r = client.get(f"/lineage_nodes?trace_id=eq.{trace_id}&order=timestamp.asc")
    if r.status_code != 200:
        raise HTTPException(status_code=500, detail=r.text)
    nodes = r.json()
    return {
        "trace_id": trace_id,
        "total_hops": len(nodes),
        "passed": sum(1 for n in nodes if n["contract_status"] == "passed"),
        "blocked": sum(1 for n in nodes if n["contract_status"] == "blocked"),
        "nodes": nodes
    }

@app.get("/lineage/chain/{chain_id}")
def get_chain_lineage(chain_id: str):
    with db() as client:
        r = client.get(f"/lineage_nodes?chain_id=eq.{chain_id}&order=timestamp.asc")
    if r.status_code != 200:
        raise HTTPException(status_code=500, detail=r.text)
    return r.json()

    # --- Analytics ---

@app.get("/analytics/chains")
def analytics_chains():
    with db() as client:
        envelopes = client.get("/envelopes").json()
        chains = client.get("/chains").json()

    chain_map = {c["chain_id"]: c["name"] for c in chains}
    stats = {}

    for e in envelopes:
        cid = e["chain_id"]
        if cid not in stats:
            stats[cid] = {
                "chain_id": cid,
                "chain_name": chain_map.get(cid, "unknown"),
                "total": 0,
                "passed": 0,
                "blocked": 0,
                "violations": 0
            }
        stats[cid]["total"] += 1
        if e.get("contract_passed"):
            stats[cid]["passed"] += 1
        else:
            stats[cid]["blocked"] += 1
            stats[cid]["violations"] += len(e.get("violations") or [])

    result = list(stats.values())
    for r in result:
        r["pass_rate"] = round(100 * r["passed"] / r["total"], 2) if r["total"] > 0 else 0

    return sorted(result, key=lambda x: x["pass_rate"])


@app.get("/analytics/agents")
def analytics_agents():
    with db() as client:
        envelopes = client.get("/envelopes").json()

    stats = {}
    for e in envelopes:
        pair = f"{e['sender_role']} → {e['receiver_role']}"
        if pair not in stats:
            stats[pair] = {
                "pair": pair,
                "sender_role": e["sender_role"],
                "receiver_role": e["receiver_role"],
                "total": 0,
                "passed": 0,
                "blocked": 0
            }
        stats[pair]["total"] += 1
        if e.get("contract_passed"):
            stats[pair]["passed"] += 1
        else:
            stats[pair]["blocked"] += 1

    result = list(stats.values())
    for r in result:
        r["pass_rate"] = round(100 * r["passed"] / r["total"], 2) if r["total"] > 0 else 0
        r["failure_rate"] = round(100 * r["blocked"] / r["total"], 2) if r["total"] > 0 else 0

    return sorted(result, key=lambda x: x["failure_rate"], reverse=True)


@app.get("/analytics/confidence")
def analytics_confidence():
    with db() as client:
        nodes = client.get("/lineage_nodes?order=timestamp.asc").json()

    if not nodes:
        return {"message": "No lineage data yet", "data": []}

    by_chain = {}
    for n in nodes:
        cid = n.get("chain_id", "unknown")
        if cid not in by_chain:
            by_chain[cid] = []
        if n.get("confidence") is not None:
            by_chain[cid].append({
                "hop": n["hop_count"],
                "confidence": n["confidence"],
                "agent_from": n["agent_from"],
                "agent_to": n["agent_to"],
                "contract_status": n["contract_status"]
            })

    result = []
    for cid, hops in by_chain.items():
        if hops:
            avg_conf = round(sum(h["confidence"] for h in hops) / len(hops), 4)
            result.append({
                "chain_id": cid,
                "avg_confidence": avg_conf,
                "total_hops": len(hops),
                "hops": hops
            })

    return result


@app.get("/analytics/violations")
def analytics_violations():
    with db() as client:
        violations = client.get("/contract_violations").json()

    patterns = {}
    for v in violations:
        msg = v.get("message", "unknown")
        if msg not in patterns:
            patterns[msg] = {
                "violation": msg,
                "count": 0,
                "severity": v.get("severity", "unknown"),
                "chains_affected": set()
            }
        patterns[msg]["count"] += 1
        patterns[msg]["chains_affected"].add(v.get("chain_id", "unknown"))

    result = []
    for p in patterns.values():
        result.append({
            "violation": p["violation"],
            "count": p["count"],
            "severity": p["severity"],
            "chains_affected": len(p["chains_affected"])
        })

    return sorted(result, key=lambda x: x["count"], reverse=True)


# --- Bidirectional Contracts ---

class ResponseContract(BaseModel):
    required_fields: Optional[List[str]] = []
    assertions: Optional[List[ContractAssertion]] = []
    on_fail: Optional[str] = "block"

class EnvelopeResponse(BaseModel):
    chain_id: str
    responder_id: str
    responder_role: str
    response_payload: Dict[str, Any]
    response_contract: Optional[ResponseContract] = ResponseContract()

@app.post("/envelopes/{envelope_id}/respond")
def respond_to_envelope(envelope_id: str, body: EnvelopeResponse):
    # Validate response against response contract
    contract = Contract(
        required_fields=body.response_contract.required_fields,
        assertions=body.response_contract.assertions,
        on_fail=body.response_contract.on_fail
    )
    violations = validate_contract(body.response_payload, contract)
    contract_passed = len(violations) == 0
    on_fail = body.response_contract.on_fail or "block"

    if not contract_passed and on_fail == "block":
        return {
            "status": "blocked",
            "reason": "Response contract validation failed",
            "violations": violations,
            "envelope_id": envelope_id
        }

    now = datetime.now(timezone.utc).isoformat()
    record = {
        "id": str(uuid.uuid4()),
        "envelope_id": envelope_id,
        "chain_id": body.chain_id,
        "responder_id": body.responder_id,
        "responder_role": body.responder_role,
        "response_payload": body.response_payload,
        "response_contract": body.response_contract.dict(),
        "contract_passed": contract_passed,
        "violations": violations,
        "status": "accepted" if contract_passed else on_fail,
        "created_at": now
    }

    with db() as client:
        r = client.post("/envelope_responses", json=record)
        if r.status_code not in (200, 201):
            raise HTTPException(status_code=500, detail=r.text)

        if not contract_passed:
            for v in violations:
                violation_record = {
                    "id": str(uuid.uuid4()),
                    "envelope_id": envelope_id,
                    "chain_id": body.chain_id,
                    "violation_type": "response_contract_failure",
                    "severity": "critical" if on_fail == "block" else "warning",
                    "message": v,
                    "on_fail": on_fail,
                    "detected_at": now
                }
                client.post("/contract_violations", json=violation_record)

    result = r.json()[0]
    result["violations"] = violations
    result["contract_passed"] = contract_passed
    return result

@app.get("/envelopes/{envelope_id}/responses")
def get_envelope_responses(envelope_id: str):
    with db() as client:
        r = client.get(f"/envelope_responses?envelope_id=eq.{envelope_id}&order=created_at.asc")
    if r.status_code != 200:
        raise HTTPException(status_code=500, detail=r.text)
    return {
        "envelope_id": envelope_id,
        "total_responses": len(r.json()),
        "responses": r.json()
    }

# --- Webhooks ---

class WebhookCreate(BaseModel):
    name: str
    url: str
    chain_id: Optional[str] = None
    on_block: Optional[bool] = True
    on_violation: Optional[bool] = True
    on_low_confidence: Optional[bool] = False
    confidence_threshold: Optional[float] = 0.5
    active: Optional[bool] = True

@app.post("/webhooks")
def create_webhook(body: WebhookCreate):
    now = datetime.now(timezone.utc).isoformat()
    record = {
        "id": str(uuid.uuid4()),
        "name": body.name,
        "url": body.url,
        "chain_id": body.chain_id,
        "on_block": body.on_block,
        "on_violation": body.on_violation,
        "on_low_confidence": body.on_low_confidence,
        "confidence_threshold": body.confidence_threshold,
        "active": body.active,
        "created_at": now
    }
    with db() as client:
        r = client.post("/webhooks", json=record)
    if r.status_code not in (200, 201):
        raise HTTPException(status_code=500, detail=r.text)
    return r.json()[0]

@app.get("/webhooks")
def list_webhooks():
    with db() as client:
        r = client.get("/webhooks?order=created_at.desc")
    if r.status_code != 200:
        raise HTTPException(status_code=500, detail=r.text)
    return r.json()

@app.delete("/webhooks/{webhook_id}")
def delete_webhook(webhook_id: str):
    with db() as client:
        r = client.patch(
            f"/webhooks?id=eq.{webhook_id}",
            json={"active": False}
        )
    if r.status_code not in (200, 201, 204):
        raise HTTPException(status_code=500, detail=r.text)
    return {"webhook_id": webhook_id, "status": "deactivated"}

# --- HITL Checkpoints ---

class HITLDecision(BaseModel):
    decision: str  # approve | reject
    reviewer_note: Optional[str] = ""

@app.get("/hitl")
def list_hitl_checkpoints(status: str = None):
    url = "/hitl_checkpoints?order=created_at.desc"
    if status:
        url += f"&status=eq.{status}"
    with db() as client:
        r = client.get(url)
    if r.status_code != 200:
        raise HTTPException(status_code=500, detail=r.text)
    return r.json()

@app.get("/hitl/{checkpoint_id}")
def get_hitl_checkpoint(checkpoint_id: str):
    with db() as client:
        r = client.get(f"/hitl_checkpoints?id=eq.{checkpoint_id}")
    if r.status_code != 200 or not r.json():
        raise HTTPException(status_code=404, detail="HITL checkpoint not found")
    return r.json()[0]

@app.post("/hitl/{checkpoint_id}/decide")
def decide_hitl_checkpoint(checkpoint_id: str, body: HITLDecision):
    if body.decision not in ("approve", "reject"):
        raise HTTPException(status_code=400, detail="Decision must be 'approve' or 'reject'")

    now = datetime.now(timezone.utc).isoformat()
    with db() as client:
        r = client.patch(
            f"/hitl_checkpoints?id=eq.{checkpoint_id}",
            json={
                "status": body.decision + "d",
                "reviewer_note": body.reviewer_note,
                "decided_at": now
            }
        )
    if r.status_code not in (200, 201, 204):
        raise HTTPException(status_code=500, detail=r.text)
    return {
        "checkpoint_id": checkpoint_id,
        "decision": body.decision,
        "status": body.decision + "d",
        "reviewer_note": body.reviewer_note,
        "decided_at": now
    }