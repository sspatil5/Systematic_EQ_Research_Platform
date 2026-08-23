"""Explicit one-way execution-cost assumptions."""


def transaction_cost(notional: float, cost_bps: float) -> float:
    if cost_bps < 0:
        raise ValueError("Cost bps cannot be negative")
    return abs(notional) * cost_bps / 10_000.0

