"""
ChainThread CrewAI Adapter
Wraps CrewAI agent task outputs in verified ChainThread envelopes.

Usage:
    from adapters.crewai_adapter import chainthread_task

    @chainthread_task(
        chain_id="my-chain",
        sender_id="research-agent",
        sender_role="researcher",
        receiver_id="writer-agent",
        receiver_role="writer",
        contract={"required_fields": ["result"], "on_fail": "block"}
    )
    def my_task(input_data):
        # your task logic
        return {"result": "...", "confidence": 0.9}
"""

import httpx
from typing import Any, Dict, Optional
from functools import wraps


CHAINTHREAD_BASE = "https://chain-thread.onrender.com"


def chainthread_task(
    chain_id: str,
    sender_id: str,
    sender_role: str,
    receiver_id: str,
    receiver_role: str,
    contract: Optional[Dict] = None,
    on_fail: str = "block",
    base_url: str = CHAINTHREAD_BASE
):
    """
    Decorator that wraps a CrewAI task function output
    in a ChainThread handoff envelope automatically.

    The decorated function must return a dict.
    ChainThread validates the dict against the contract.
    """
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            result = func(*args, **kwargs)

            if not isinstance(result, dict):
                result = {"output": str(result)}

            effective_contract = contract or {
                "required_fields": list(result.keys()),
                "on_fail": on_fail
            }

            try:
                with httpx.Client(timeout=5) as client:
                    r = client.post(f"{base_url}/envelopes", json={
                        "chain_id": chain_id,
                        "sender_id": sender_id,
                        "sender_role": sender_role,
                        "receiver_id": receiver_id,
                        "receiver_role": receiver_role,
                        "payload": result,
                        "summary": f"{sender_role} completed task, handing off to {receiver_role}",
                        "contract": effective_contract,
                        "on_fail": on_fail
                    })
                    envelope = r.json()

                    if envelope.get("status") == "blocked":
                        if on_fail == "block":
                            raise ValueError(
                                f"ChainThread blocked handoff: {envelope.get('violations')}"
                            )
            except ValueError:
                raise
            except Exception:
                pass  # Never crash the crew pipeline

            return result
        return wrapper
    return decorator


class CrewChainThread:
    """
    Class-based adapter for CrewAI crews.
    Attach to a crew to automatically verify all agent handoffs.
    """

    def __init__(self, chain_id: str, base_url: str = CHAINTHREAD_BASE):
        self.chain_id = chain_id
        self.base_url = base_url

    def wrap_handoff(
        self,
        payload: dict,
        sender_id: str,
        sender_role: str,
        receiver_id: str,
        receiver_role: str,
        contract: Optional[Dict] = None
    ) -> dict:
        contract = contract or {"required_fields": list(payload.keys()), "on_fail": "block"}
        try:
            with httpx.Client(timeout=5) as client:
                r = client.post(f"{self.base_url}/envelopes", json={
                    "chain_id": self.chain_id,
                    "sender_id": sender_id,
                    "sender_role": sender_role,
                    "receiver_id": receiver_id,
                    "receiver_role": receiver_role,
                    "payload": payload,
                    "summary": f"{sender_role} → {receiver_role}",
                    "contract": contract,
                    "on_fail": contract.get("on_fail", "block")
                })
                return r.json()
        except Exception as e:
            return {"status": "error", "detail": str(e)}