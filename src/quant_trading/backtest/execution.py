"""Signal-to-execution timestamp mapping."""

from __future__ import annotations

from dataclasses import dataclass

import pandas as pd


@dataclass(frozen=True)
class ExecutionInstruction:
    signal_date: pd.Timestamp
    order_date: pd.Timestamp
    execution_date: pd.Timestamp
    price_column: str


def execution_instruction(
    dates: pd.DatetimeIndex, signal_date: pd.Timestamp, mode: str
) -> ExecutionInstruction | None:
    location = dates.get_indexer([signal_date])[0]
    if location < 0:
        raise ValueError("Signal date is not a market session")
    offsets = {"next_open": (1, "open"), "next_close": (1, "close"), "second_open": (2, "open")}
    if mode not in offsets:
        raise ValueError(f"Unknown execution mode {mode!r}")
    offset, column = offsets[mode]
    if location + offset >= len(dates):
        return None
    execution_date = dates[location + offset]
    return ExecutionInstruction(signal_date, execution_date, execution_date, column)

