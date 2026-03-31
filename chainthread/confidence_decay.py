"""
chainthread/confidence_decay.py
Confidence Decay — degrades envelope confidence automatically with each hop.
Forces downstream agents to declare a minimum_confidence floor.
If confidence falls below the floor, the handoff is blocked before it arrives.
"""

from dataclasses import dataclass
from typing import Optional


# ------------------------------------------------------------------ #
#  Configuration                                                       #
# ------------------------------------------------------------------ #

@dataclass
class DecayConfig:
    """
    decay_rate: how much confidence is lost per hop (0.0 – 1.0).
                Default 0.05 = 5% loss per hop.
    decay_model: "linear"      → subtract decay_rate each hop
                 "exponential" → multiply by (1 - decay_rate) each hop
    min_floor:   hard lower bound — confidence never goes below this.
    """
    decay_rate: float = 0.05
    decay_model: str = "linear"   # "linear" | "exponential"
    min_floor: float = 0.10


# ------------------------------------------------------------------ #
#  Core functions                                                      #
# ------------------------------------------------------------------ #

def apply_decay(envelope: dict, config: Optional[DecayConfig] = None) -> dict:
    """
    Mutates envelope in-place:
    - Increments hop_count
    - Degrades confidence according to the decay model
    - Records the decay history

    Returns the mutated envelope (for chaining).

    Usage:
        envelope = apply_decay(envelope)
        # or with custom config:
        envelope = apply_decay(envelope, DecayConfig(decay_rate=0.08, decay_model="exponential"))
    """
    if config is None:
        config = DecayConfig()

    original_confidence = envelope.get("confidence", 1.0)
    hop = envelope.get("hop_count", 0)

    # Compute new confidence
    if config.decay_model == "exponential":
        new_confidence = original_confidence * (1 - config.decay_rate)
    else:  # linear
        new_confidence = original_confidence - config.decay_rate

    # Apply floor
    new_confidence = max(round(new_confidence, 4), config.min_floor)

    # Write back
    envelope["confidence"] = new_confidence
    envelope["hop_count"] = hop + 1

    # Append to decay ledger (never overwrite — append-only audit trail)
    if "decay_history" not in envelope:
        envelope["decay_history"] = []

    envelope["decay_history"].append({
        "hop": hop + 1,
        "confidence_before": original_confidence,
        "confidence_after": new_confidence,
        "decay_rate": config.decay_rate,
        "model": config.decay_model,
    })

    return envelope


def check_minimum_confidence(envelope: dict, minimum: float) -> tuple[bool, Optional[str]]:
    """
    Check if the envelope meets the downstream agent's minimum confidence floor.

    Returns (ok: bool, violation_message: str | None).

    Usage in your validator:
        ok, msg = check_minimum_confidence(envelope, minimum=0.65)
        if not ok:
            violations.append(msg)
    """
    current = envelope.get("confidence", 1.0)
    if current < minimum:
        msg = (
            f"Confidence too low for this handoff: "
            f"got {current:.4f}, required >= {minimum:.4f}. "
            f"Hop count: {envelope.get('hop_count', 0)}."
        )
        return False, msg
    return True, None


def project_decay(
    starting_confidence: float,
    num_hops: int,
    config: Optional[DecayConfig] = None,
) -> list[float]:
    """
    Preview what confidence will look like over N hops.
    Useful for planning pipeline depth.

    Returns a list of [hop_0_confidence, hop_1_confidence, ..., hop_N_confidence]

    Example:
        >>> project_decay(0.91, 5)
        [0.91, 0.86, 0.81, 0.76, 0.71, 0.66]
    """
    if config is None:
        config = DecayConfig()

    values = [starting_confidence]
    current = starting_confidence

    for _ in range(num_hops):
        if config.decay_model == "exponential":
            current = current * (1 - config.decay_rate)
        else:
            current = current - config.decay_rate
        current = max(round(current, 4), config.min_floor)
        values.append(current)

    return values


# ------------------------------------------------------------------ #
#  Convenience: attach decay config to an envelope                    #
# ------------------------------------------------------------------ #

def set_decay_config(envelope: dict, config: DecayConfig) -> dict:
    """
    Embed the decay config into the envelope so every hop
    uses consistent settings regardless of which agent processes it.
    """
    envelope["decay_config"] = {
        "decay_rate": config.decay_rate,
        "decay_model": config.decay_model,
        "min_floor": config.min_floor,
    }
    return envelope


def get_decay_config(envelope: dict) -> DecayConfig:
    """
    Read decay config from the envelope (falls back to defaults if absent).
    """
    raw = envelope.get("decay_config", {})
    return DecayConfig(
        decay_rate=raw.get("decay_rate", 0.05),
        decay_model=raw.get("decay_model", "linear"),
        min_floor=raw.get("min_floor", 0.10),
    )