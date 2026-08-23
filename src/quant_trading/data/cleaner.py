"""Validation and canonicalization of daily OHLCV data."""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
import pandas as pd

PRICE_COLUMNS = ("open", "high", "low", "close")
REQUIRED_COLUMNS = (*PRICE_COLUMNS, "volume")


class DataQualityError(ValueError):
    """Raised when observations violate hard market-data invariants."""


@dataclass(frozen=True)
class QualityReport:
    input_rows: int
    output_rows: int
    duplicate_rows_removed: int = 0
    missing_values_by_column: dict[str, int] = field(default_factory=dict)
    extreme_return_rows: int = 0
    zero_volume_rows: int = 0


def _normalise_columns(frame: pd.DataFrame) -> pd.DataFrame:
    result = frame.copy()
    result.columns = [str(column).strip().lower().replace(" ", "_") for column in result.columns]
    return result


def clean_ohlcv(
    frame: pd.DataFrame,
    *,
    ticker: str,
    max_abs_daily_return: float = 0.80,
    allow_zero_volume: bool = True,
) -> tuple[pd.DataFrame, QualityReport]:
    """Return a canonical daily frame after enforcing hard price invariants.

    Extreme returns are flagged rather than silently deleted: genuine splits should already
    be handled by adjusted data, but large moves can also be real and need human review.
    """
    if frame.empty:
        raise DataQualityError(f"No rows returned for {ticker}")
    cleaned = _normalise_columns(frame)
    missing_columns = sorted(set(REQUIRED_COLUMNS) - set(cleaned.columns))
    if missing_columns:
        raise DataQualityError(f"{ticker} missing required columns: {missing_columns}")

    cleaned.index = pd.to_datetime(cleaned.index, utc=True).tz_convert(None).normalize()
    cleaned.index.name = "date"
    cleaned = cleaned.sort_index()
    duplicate_count = int(cleaned.index.duplicated(keep="last").sum())
    cleaned = cleaned.loc[~cleaned.index.duplicated(keep="last"), list(REQUIRED_COLUMNS)]
    cleaned = cleaned.apply(pd.to_numeric, errors="coerce")

    missing = cleaned.isna().sum().astype(int).to_dict()
    if any(missing.values()):
        cleaned = cleaned.dropna(subset=list(REQUIRED_COLUMNS))
    if cleaned.empty:
        raise DataQualityError(f"All rows for {ticker} are incomplete")
    if (~np.isfinite(cleaned[list(REQUIRED_COLUMNS)].to_numpy())).any():
        raise DataQualityError(f"{ticker} contains non-finite values")
    if (cleaned[list(PRICE_COLUMNS)] <= 0).any(axis=None):
        raise DataQualityError(f"{ticker} contains zero or negative prices")
    if (cleaned["volume"] < 0).any():
        raise DataQualityError(f"{ticker} contains negative volume")
    if not allow_zero_volume and (cleaned["volume"] == 0).any():
        raise DataQualityError(f"{ticker} contains zero-volume observations")

    # Provider adjustment arithmetic can differ by a few floating-point ULPs (for example,
    # adjusted high can be 3e-15 below adjusted close). Preserve strict economic validation while
    # tolerating numerically equivalent prices.
    upper_reference = cleaned[["open", "close", "low"]].max(axis=1)
    lower_reference = cleaned[["open", "close", "high"]].min(axis=1)
    tolerance = 1e-10 * cleaned[["open", "high", "low", "close"]].abs().max(axis=1)
    invalid_bars = (
        (cleaned["high"] + tolerance < upper_reference)
        | (cleaned["low"] - tolerance > lower_reference)
    )
    if invalid_bars.any():
        dates = cleaned.index[invalid_bars].strftime("%Y-%m-%d").tolist()[:5]
        raise DataQualityError(f"{ticker} has impossible OHLC bars at {dates}")

    daily_returns = cleaned["close"].pct_change(fill_method=None)
    cleaned["possible_extreme_return"] = daily_returns.abs() > max_abs_daily_return
    cleaned["ticker"] = ticker.upper()
    report = QualityReport(
        input_rows=len(frame),
        output_rows=len(cleaned),
        duplicate_rows_removed=duplicate_count,
        missing_values_by_column=missing,
        extreme_return_rows=int(cleaned["possible_extreme_return"].sum()),
        zero_volume_rows=int((cleaned["volume"] == 0).sum()),
    )
    return cleaned, report


def to_panel(frames: dict[str, pd.DataFrame]) -> pd.DataFrame:
    """Combine cleaned ticker frames into a sorted ``(date, ticker)`` panel."""
    if not frames:
        raise DataQualityError("Cannot construct a panel from no securities")
    parts: list[pd.DataFrame] = []
    for ticker, frame in frames.items():
        part = frame.copy()
        part["ticker"] = ticker.upper()
        part = part.reset_index().set_index(["date", "ticker"])
        parts.append(part)
    panel = pd.concat(parts).sort_index()
    if panel.index.has_duplicates:
        raise DataQualityError("Panel contains duplicate (date, ticker) observations")
    return panel
