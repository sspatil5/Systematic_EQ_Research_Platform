from pathlib import Path

import pandas as pd

from quant_trading.data.loader import MarketDataLoader


def sample_download(**_: object) -> pd.DataFrame:
    return pd.DataFrame(
        {
            "Open": [10.0, 11.0],
            "High": [11.0, 12.0],
            "Low": [9.0, 10.0],
            "Close": [10.5, 11.5],
            "Volume": [100, 200],
        },
        index=pd.to_datetime(["2024-01-02", "2024-01-03"]),
    )


def test_loader_downloads_then_uses_cache(tmp_path: Path) -> None:
    calls = 0

    def counted_download(**kwargs: object) -> pd.DataFrame:
        nonlocal calls
        calls += 1
        return sample_download(**kwargs)

    loader = MarketDataLoader(tmp_path, downloader=counted_download)
    first = loader.load(["AAA"], start="2024-01-01", end="2024-02-01")
    second = loader.load(["AAA"], start="2024-01-01", end="2024-02-01")
    assert calls == 1
    assert first.cache_hits == ()
    assert second.cache_hits == ("AAA",)
    pd.testing.assert_frame_equal(first.panel, second.panel)


def test_loader_deduplicates_symbols(tmp_path: Path) -> None:
    loader = MarketDataLoader(tmp_path, downloader=sample_download)
    result = loader.load(["aaa", "AAA"], start="2024-01-01", end="2024-02-01")
    assert result.panel.index.get_level_values("ticker").unique().tolist() == ["AAA"]

