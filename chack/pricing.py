from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Dict, Optional

import yaml


@dataclass
class ModelPricing:
    input: float
    cached_input: float
    output: float


@dataclass
class PricingTable:
    models: Dict[str, ModelPricing]


def load_pricing(path: str) -> PricingTable:
    with open(path, "r", encoding="utf-8") as handle:
        raw = yaml.safe_load(handle) or {}
    models_raw = raw.get("models", {}) or {}
    models: Dict[str, ModelPricing] = {}
    for name, values in models_raw.items():
        if not isinstance(values, dict):
            continue
        try:
            models[name] = ModelPricing(
                input=float(values.get("input", 0.0)),
                cached_input=float(values.get("cached_input", 0.0)),
                output=float(values.get("output", 0.0)),
            )
        except (TypeError, ValueError):
            continue
    return PricingTable(models=models)


def resolve_pricing_path() -> str:
    return os.environ.get("CHACK_PRICING", "./config/pricing.yaml")


def estimate_cost(
    pricing: PricingTable,
    model: str,
    prompt_tokens: int,
    completion_tokens: int,
    cached_prompt_tokens: int = 0,
) -> Optional[float]:
    if model not in pricing.models:
        return None
    rates = pricing.models[model]
    billable_prompt = max(prompt_tokens - cached_prompt_tokens, 0)
    total = (
        billable_prompt * rates.input
        + cached_prompt_tokens * rates.cached_input
        + completion_tokens * rates.output
    )
    return total / 1_000_000.0
