import pandas as pd
import pytest

from quant_trading.data.cleaner import DataQualityError, clean_ohlcv, to_panel


def bars() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "Open": [100.0, 101.0, 102.0],
            "High": [102.0, 103.0, 104.0],
            "Low": [99.0, 100.0, 101.0],
            "Close": [101.0, 102.0, 103.0],
            "Volume": [1000, 1100, 1200],
        },
        index=pd.to_datetime(["2024-01-02", "2024-01-03", "2024-01-04"]),
    )


def test_cleaner_normalises_schema_and_reports_duplicates() -> None:
    frame = pd.concat([bars(), bars().iloc[[1]]])
    cleaned, report = clean_ohlcv(frame, ticker="abc")
    assert list(cleaned.columns) == [
        "open", "high", "low", "close", "volume", "possible_extreme_return", "ticker"
    ]
    assert report.duplicate_rows_removed == 1
    assert cleaned["ticker"].eq("ABC").all()
    assert cleaned.index.is_monotonic_increasing


def test_cleaner_rejects_impossible_prices() -> None:
    frame = bars()
    frame.loc[frame.index[0], "High"] = 98.0
    with pytest.raises(DataQualityError, match="impossible OHLC"):
        clean_ohlcv(frame, ticker="ABC")


def test_cleaner_tolerates_floating_point_adjustment_noise() -> None:
    frame = bars()
    frame.loc[frame.index[0], "High"] = frame.loc[frame.index[0], "Close"] - 1e-14
    cleaned, _ = clean_ohlcv(frame, ticker="ABC")
    assert len(cleaned) == len(frame)


def test_cleaner_flags_adjustment_or_data_anomaly_without_dropping_it() -> None:
    frame = bars()
    frame.loc[frame.index[-1], ["Open", "High", "Low", "Close"]] = [200, 205, 195, 202]
    cleaned, report = clean_ohlcv(frame, ticker="ABC", max_abs_daily_return=0.5)
    assert report.extreme_return_rows == 1
    assert bool(cleaned.iloc[-1]["possible_extreme_return"])


def test_panel_has_canonical_multiindex() -> None:
    first, _ = clean_ohlcv(bars(), ticker="AAA")
    second, _ = clean_ohlcv(bars() * 2, ticker="BBB")
    panel = to_panel({"AAA": first, "BBB": second})
    assert panel.index.names == ["date", "ticker"]
    assert len(panel) == 6
    assert panel.index.is_monotonic_increasing
