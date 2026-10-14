"""Registry of the Token Factory models Leakproof uses, with prices and default roles."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ModelSpec:
    id: str
    short: str
    context: int
    usd_in_per_m: float
    usd_out_per_m: float
    roles: tuple[str, ...]

    def cost(self, prompt_tokens: int, completion_tokens: int) -> float:
        return (
            prompt_tokens * self.usd_in_per_m + completion_tokens * self.usd_out_per_m
        ) / 1_000_000


# Prices are the Token Factory catalog list prices checked 2026-10-13 (USD per 1M tokens).
MODELS: dict[str, ModelSpec] = {
    m.short: m
    for m in (
        ModelSpec(
            "nvidia/Nemotron-3-Ultra-550b-a55b", "ultra", 1_000_000, 1.00, 3.00, ("planner",)
        ),
        ModelSpec("nvidia/Nemotron-3_5-Lightning", "lightning", 1_000_000, 0.06, 0.24, ("worker",)),
        ModelSpec(
            "nvidia/nemotron-3-super-120b-a12b", "super", 256_000, 0.30, 0.90, ("alt_planner",)
        ),
        ModelSpec(
            "nvidia/NVIDIA-Nemotron-3-Nano-30B-A3B", "nano", 262_000, 0.06, 0.24, ("triage",)
        ),
    )
}
_BY_ID = {m.id: m for m in MODELS.values()}


def get(name: str) -> ModelSpec:
    """Look a model up by short name ("ultra") or full Token Factory id."""
    if name in MODELS:
        return MODELS[name]
    if name in _BY_ID:
        return _BY_ID[name]
    raise KeyError(f"unknown model {name!r}; known: {sorted(MODELS)}")


def by_role(role: str) -> ModelSpec:
    for spec in MODELS.values():
        if role in spec.roles:
            return spec
    raise KeyError(f"no model has role {role!r}")
