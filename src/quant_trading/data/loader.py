"""Cached yfinance market-data loader with injectable download function."""

from __future__ import annotations

from collections.abc import Callable, Iterable
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Any

import pandas as pd

from quant_trading.data.cleaner import QualityReport, clean_ohlcv, to_panel

DownloadFunction = Callable[..., pd.DataFrame]


@dataclass(frozen=True)
class LoadResult:
    panel: pd.DataFrame
    quality_reports: dict[str, QualityReport]
    cache_hits: tuple[str, ...]


class MarketDataLoader:
    """Load adjusted daily bars and persist one Parquet file per request/ticker."""

    def __init__(
        self,
        cache_dir: str | Path = "data/cache",
        *,
        downloader: DownloadFunction | None = None,
    ) -> None:
        self.cache_dir = Path(cache_dir)
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self._downloader = downloader

    @property
    def downloader(self) -> DownloadFunction:
        if self._downloader is None:
            import yfinance as yf

            self._downloader = yf.download
        return self._downloader

    @staticmethod
    def _date_token(value: str | date | None) -> str:
        return "latest" if value is None else pd.Timestamp(value).strftime("%Y%m%d")

    def _cache_path(self, ticker: str, start: str | date, end: str | date | None) -> Path:
        safe_ticker = ticker.upper().replace("/", "-")
        return self.cache_dir / (
            f"{safe_ticker}_{self._date_token(start)}_{self._date_token(end)}_adjusted.parquet"
        )

    @staticmethod
    def _flatten_download(frame: pd.DataFrame, ticker: str) -> pd.DataFrame:
        if not isinstance(frame.columns, pd.MultiIndex):
            return frame
        tickers = set(frame.columns.get_level_values(-1))
        if ticker in tickers:
            return frame.xs(ticker, axis=1, level=-1, drop_level=True)
        if len(tickers) == 1:
            return frame.droplevel(-1, axis=1)
        raise ValueError(f"Downloaded frame does not contain {ticker}")

    def load(
        self,
        tickers: Iterable[str],
        *,
        start: str | date,
        end: str | date | None = None,
        refresh: bool = False,
        max_abs_daily_return: float = 0.80,
        allow_zero_volume: bool = True,
    ) -> LoadResult:
        symbols = tuple(dict.fromkeys(symbol.upper() for symbol in tickers))
        if not symbols:
            raise ValueError("At least one ticker is required")
        frames: dict[str, pd.DataFrame] = {}
        reports: dict[str, QualityReport] = {}
        cache_hits: list[str] = []

        for ticker in symbols:
            cache_path = self._cache_path(ticker, start, end)
            if cache_path.exists() and not refresh:
                raw = pd.read_parquet(cache_path)
                cache_hits.append(ticker)
            else:
                kwargs: dict[str, Any] = {
                    "tickers": ticker,
                    "start": str(start),
                    "auto_adjust": True,
                    "actions": False,
                    "progress": False,
                    "threads": False,
                }
                if end is not None:
                    kwargs["end"] = str(end)
                raw = self._flatten_download(self.downloader(**kwargs), ticker)
                raw.to_parquet(cache_path)
            frames[ticker], reports[ticker] = clean_ohlcv(
                raw,
                ticker=ticker,
                max_abs_daily_return=max_abs_daily_return,
                allow_zero_volume=allow_zero_volume,
            )
        return LoadResult(to_panel(frames), reports, tuple(cache_hits))

