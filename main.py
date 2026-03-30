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
    version="0.1.0"
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

# --- Routes ---

@app.get("/")
def root():
    return {
        "tool": "ChainThread",
        "version": "0.1.0",
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

    total = len(envelopes)
    passed = sum(1 for e in envelopes if e.get("contract_passed"))
    failed = total - passed
    blocked = sum(1 for e in envelopes if e.get("status") == "block")

    return {
        "total_chains": len(chains),
        "total_envelopes": total,
        "passed": passed,
        "failed": failed,
        "blocked": blocked,
        "total_violations": len(violations),
        "total_checkpoints": len(checkpoints),
        "pass_rate": round(100 * passed / total, 2) if total > 0 else 0
    }