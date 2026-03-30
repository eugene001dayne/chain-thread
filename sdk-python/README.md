# ChainThread Python SDK

Open agent handoff protocol and verification infrastructure.

## Install
```bash
pip install chainthread
```

## Quick Start
```python
from chainthread import ChainThread

ct = ChainThread()

# Create a chain
chain = ct.create_chain(
    name="my-agent-pipeline",
    description="Research to writer handoff"
)

# Send a handoff envelope
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
        "assertions": [{"field": "confidence", "type": "range", "value": {"min": 0.0, "max": 1.0}}],
        "on_fail": "block"
    }
)

print(envelope["contract_passed"])
print(ct.stats())
```

## Links
- GitHub: https://github.com/eugene001dayne/chain-thread
- Live API: https://chain-thread.onrender.com