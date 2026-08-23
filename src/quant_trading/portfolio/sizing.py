"""Whole-share equal-weight sizing without leverage."""

from __future__ import annotations

import math


def target_shares(
    equity: float,
    price: float,
    positions: int,
    *,
    fractional_shares: bool = False,
) -> float:
    if equity < 0 or price <= 0 or positions <= 0:
        raise ValueError("Equity, price, and position count must be valid")
    raw = equity / positions / price
    return raw if fractional_shares else float(math.floor(raw))

