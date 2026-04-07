# ChainThread

The missing layer for multi-agent AI systems. Open agent handoff protocol + verification.

When AI agents hand work to each other, there's no standard for what gets transferred. No verification. No provenance tracking. No rollback.

ChainThread fixes that.

---

## The problem

Multi-agent pipelines fail because agents trust upstream outputs blindly. One agent makes a mistake. That error compounds through the chain. No contract. No checkpoint. No audit trail. No way to prove what was handed off or when.

---

## The solution

ChainThread wraps every agent-to-agent handoff in a **Handoff Envelope**:

```
Agent A → [ChainThread Envelope] → Agent B
           ├── payload + provenance
           ├── contract (required fields, assertions, on_fail)
           ├── checkpoint (rollback snapshot)
           └── audit trail
```

If the contract fails, the handoff gets **blocked** before it ever reaches the next agent.

---

## Install

```bash
pip install chainthread
```

```bash
npm install chainthread
```

---

## Quick start (Python)

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

---

## What gets blocked

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

---

## on_fail behavior

| Value | Behavior |
|-------|----------|
| `block` | Handoff rejected. Chain halts. Default. |
| `escalate` | Handoff paused. Violation logged. Awaiting review. |
| `log_and_proceed` | Handoff passes. Violation recorded. Pipeline continues. |

Set per envelope or per contract rule.

---

## Live resources

| What | Where |
|------|-------|
| Live API | https://chain-thread.onrender.com |
| API Docs | https://chain-thread.onrender.com/docs |
| Dashboard | https://chain-thread.lovable.app |
| PyPI | https://pypi.org/project/chainthread/ |
| npm | https://www.npmjs.com/package/chainthread |

---

## Part of the Thread Suite

```
Iron-Thread   → Did the AI output the right structure?
TestThread    → Did the agent do the right thing?
PromptThread  → Is my prompt the best version of itself?
ChainThread   → Did the handoff succeed — and can we prove it?
```

Built by Eugene Dayne Mawuli.

---

## What makes the above still obviously AI generated?

- The opening line "The missing layer for multi-agent AI systems" is still a bit slogan-y.
- The table and list formatting is very clean — real READMEs are often less polished.
- No real opinion or personality. It reads like documentation, not like someone talking.
- The "Built by" line at the end feels tacked on, not integrated.

---

## Now make it not obviously AI generated.

# ChainThread

The missing layer for multi-agent AI systems. Open handoff protocol + verification.

Here's the thing: when AI agents hand work to each other, nobody agrees on what actually gets transferred. No standard format. No verification. No way to trace what came from where. No undo button.

ChainThread fixes that.

---

## The problem (real talk)

Multi-agent pipelines fail in a predictable way: agents trust whatever the upstream agent gave them. One agent messes up. That error flows downstream and gets worse. No contract between agents. No checkpoint. No audit trail. Good luck proving what was handed off at 3am when something breaks.

---

## The solution

ChainThread wraps every agent-to-agent handoff in something we call a **Handoff Envelope**:

```
Agent A → [ChainThread Envelope] → Agent B
           ├── payload + provenance
           ├── contract (required fields, assertions, on_fail)
           ├── checkpoint (rollback snapshot)
           └── audit trail
```

If the contract fails, the handoff gets **blocked** before it reaches the next agent. No garbage in, no garbage downstream.

---

## Install

```bash
pip install chainthread
```

```bash
npm install chainthread
```

---

## Quick start (Python)

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

---

## What gets blocked

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

---

## on_fail behavior

| Value | What happens |
|-------|---------------|
| `block` | Handoff rejected. Chain stops. This is the default. |
| `escalate` | Handoff paused. Violation logged. Waits for a human to review. |
| `log_and_proceed` | Handoff goes through. Violation recorded. Pipeline keeps running. |

You can set this per envelope or per contract rule.

---

## Live resources

- **Live API**: https://chain-thread.onrender.com
- **API Docs**: https://chain-thread.onrender.com/docs
- **Dashboard**: https://chain-thread.lovable.app
- **PyPI**: https://pypi.org/project/chainthread/
- **npm**: https://www.npmjs.com/package/chainthread

---

## Part of the Thread Suite

```
Iron-Thread   → Did the AI output the right structure?
TestThread    → Did the agent do the right thing?
PromptThread  → Is my prompt the best version of itself?
ChainThread   → Did the handoff succeed — and can we prove it?
```

Built by [Eugene Dayne Mawuli](https://github.com/eugene001dayne). If you're building multi-agent systems and tired of silent failures, this one's for you.
