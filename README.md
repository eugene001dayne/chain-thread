# ChainThread

> The missing infrastructure for multi-agent AI systems. Open agent handoff protocol and verification infrastructure. The missing layer for multi-agent AI systems.

[![PyPI](https://img.shields.io/pypi/v/chainthread)](https://pypi.org/project/chainthread/)
[![npm](https://img.shields.io/npm/v/chainthread)](https://www.npmjs.com/package/chainthread)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

When AI agents hand work to each other, there is currently no standard
for what gets transferred, no verification layer, no provenance tracking,
and no rollback. **ChainThread fixes this.**

## The Problem

Multi-agent pipelines fail because agents trust upstream outputs blindly.
One agent's error compounds through the chain. There is no contract.
No checkpoint. No audit trail. No way to prove what was handed off and when.

## The Solution

ChainThread wraps every agent-to-agent handoff in a **Handoff Envelope**:
```
Agent A → [ChainThread Envelope] → Agent B
           ├── payload + provenance
           ├── contract (required fields, assertions, on_fail)
           ├── checkpoint (rollback snapshot)
           └── audit trail
```

If the contract fails — the handoff is **blocked** before it reaches the next agent.

## Install
```bash
pip install chainthread
```
```bash
npm install chainthread
```

## Quick Start (Python)
```python
from chainthread import ChainThread

ct = ChainThread()

# Create a chain
chain = ct.create_chain(name="research-to-writer")

# Send a verified handoff
envelope = ct.send_envelope(
    chain_id=chain["chain_id"],
    sender_id="research-agent",
    sender_role="researcher",
    receiver_id="writer-agent",
    receiver_role="writer",
    payload={"summary": "AI is transforming software.", "confidence": 0.95},
    summary="Research complete, handing off to writer",
    provenance=[{"field": "summary", "source": "model_generated", "confidence": 0.95}],
    contract={
        "required_fields": ["summary", "confidence"],
        "assertions": [{"field": "confidence", "type": "range", "value": {"min": 0.7, "max": 1.0}}],
        "on_fail": "block"
    }
)

print(envelope["contract_passed"])  # True
print(envelope["status"])           # delivered
```

## What Gets Blocked
```python
# Missing required field — blocked automatically
envelope = ct.send_envelope(
    ...
    payload={"summary": "AI is great."},  # confidence missing
    contract={"required_fields": ["summary", "confidence"], "on_fail": "block"}
)

# Response:
# {"status": "blocked", "violations": ["Required field 'confidence' is missing."]}
```

## on_fail Behavior

| Value | Behavior |
|-------|----------|
| `block` | Handoff rejected. Chain halts. Default. |
| `escalate` | Handoff paused. Violation logged. Awaiting review. |
| `log_and_proceed` | Handoff passes. Violation recorded. Pipeline continues. |

Set per envelope or per contract rule.

## Live Resources

| What | Where |
|------|-------|
| Live API | https://chain-thread.onrender.com |
| API Docs | https://chain-thread.onrender.com/docs |
| Dashboard | https://chain-thread.lovable.app |
| PyPI | https://pypi.org/project/chainthread/ |
| npm | https://www.npmjs.com/package/chainthread |

## Part of the Thread Suite
```
Iron-Thread   → Did the AI output the right structure?
TestThread    → Did the agent do the right thing?
PromptThread  → Is my prompt the best version of itself?
ChainThread   → Did the handoff succeed — and can we prove it?
```

Built by Eugene Dayne Mawuli.