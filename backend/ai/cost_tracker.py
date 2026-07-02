"""Token normalization and conservative model-cost estimates."""
import os

DEFAULT_PRICES = {
    "gpt-5.5": (5.00, 30.00),
    "gpt-5.4": (2.50, 15.00),
    "gpt-5.4-mini": (0.75, 4.50),
    "gpt-5": (5.00, 15.00),
    "gpt-5-mini": (0.30, 1.20),
    "gpt-4o-mini": (0.15, 0.60),
}


def normalize_usage(usage: dict | None) -> dict:
    usage = usage or {}
    input_tokens = int(usage.get("prompt_tokens") or usage.get("input_tokens") or 0)
    output_tokens = int(usage.get("completion_tokens") or usage.get("output_tokens") or 0)
    total_tokens = int(usage.get("total_tokens") or input_tokens + output_tokens)
    return {"input": input_tokens, "output": output_tokens, "total": total_tokens}


def estimate_cost(model: str, tokens: dict) -> float:
    override = os.environ.get("AI_COST_PER_1M")
    if override:
        input_price = output_price = float(override)
    else:
        prices = DEFAULT_PRICES.get(model)
        if prices is None:
            return 0.0
        input_price, output_price = prices
    cost = (tokens["input"] / 1_000_000) * input_price
    cost += (tokens["output"] / 1_000_000) * output_price
    return round(cost, 6)
