"""
ChainThread LangChain Adapter
Wraps LangChain agent handoffs in verified ChainThread envelopes.

Usage:
    from adapters.langchain_adapter import ChainThreadCallback
    from langchain.agents import AgentExecutor

    callback = ChainThreadCallback(
        chain_id="my-chain",
        sender_id="research-agent",
        sender_role="researcher",
        receiver_id="writer-agent",
        receiver_role="writer",
        contract={
            "required_fields": ["output"],
            "on_fail": "block"
        }
    )

    agent = AgentExecutor(agent=..., tools=..., callbacks=[callback])
"""

import httpx
import json
from typing import Any, Dict, Optional
from datetime import datetime, timezone


CHAINTHREAD_BASE = "https://chain-thread.onrender.com"


class ChainThreadCallback:
    """
    LangChain callback handler that wraps every agent
    action output in a ChainThread handoff envelope.
    """

    def __init__(
        self,
        chain_id: str,
        sender_id: str,
        sender_role: str,
        receiver_id: str,
        receiver_role: str,
        contract: Optional[Dict] = None,
        on_fail: str = "block",
        base_url: str = CHAINTHREAD_BASE
    ):
        self.chain_id = chain_id
        self.sender_id = sender_id
        self.sender_role = sender_role
        self.receiver_id = receiver_id
        self.receiver_role = receiver_role
        self.contract = contract or {"required_fields": ["output"], "on_fail": on_fail}
        self.base_url = base_url

    def on_agent_finish(self, finish, **kwargs):
        """Called when LangChain agent finishes — sends handoff envelope."""
        payload = {
            "output": finish.return_values.get("output", ""),
            "log": finish.log[:500] if finish.log else ""
        }
        self._send_envelope(payload, summary="LangChain agent completed task")

    def on_tool_end(self, output: str, **kwargs):
        """Called when a tool finishes — optionally wrap tool outputs."""
        pass

    def _send_envelope(self, payload: dict, summary: str):
        try:
            with httpx.Client(timeout=5) as client:
                client.post(f"{self.base_url}/envelopes", json={
                    "chain_id": self.chain_id,
                    "sender_id": self.sender_id,
                    "sender_role": self.sender_role,
                    "receiver_id": self.receiver_id,
                    "receiver_role": self.receiver_role,
                    "payload": payload,
                    "summary": summary,
                    "contract": self.contract,
                    "on_fail": self.contract.get("on_fail", "block")
                })
        except Exception:
            pass  # Never let ChainThread crash the agent pipeline


def chainthread_handoff(
    chain_id: str,
    sender_id: str,
    sender_role: str,
    receiver_id: str,
    receiver_role: str,
    payload: dict,
    summary: str,
    contract: Optional[Dict] = None,
    base_url: str = CHAINTHREAD_BASE
) -> dict:
    """
    Standalone function for manual LangChain handoffs.
    Call this directly when you want to wrap a specific output.

    Returns the ChainThread envelope response.
    """
    contract = contract or {"required_fields": list(payload.keys()), "on_fail": "block"}
    try:
        with httpx.Client(timeout=5) as client:
            r = client.post(f"{base_url}/envelopes", json={
                "chain_id": chain_id,
                "sender_id": sender_id,
                "sender_role": sender_role,
                "receiver_id": receiver_id,
                "receiver_role": receiver_role,
                "payload": payload,
                "summary": summary,
                "contract": contract,
                "on_fail": contract.get("on_fail", "block")
            })
            return r.json()
    except Exception as e:
        return {"status": "error", "detail": str(e)}