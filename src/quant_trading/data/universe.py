"""Explicit, reproducible development universes.

This is a present-day liquid universe, not a point-in-time historical universe. Backtests
using it are subject to survivorship and selection bias and must be labelled accordingly.
"""

DEVELOPMENT_UNIVERSE: tuple[str, ...] = (
    "AAPL", "ABBV", "ABT", "ACN", "ADBE", "AMD", "AMGN", "AMZN", "AVGO", "AXP",
    "BA", "BAC", "BKNG", "BLK", "BMY", "BRK-B", "CAT", "CL", "CMCSA", "COP",
    "COST", "CRM", "CSCO", "CVX", "DE", "DHR", "DIS", "GE", "GILD", "GOOG",
    "GS", "HD", "HON", "IBM", "INTC", "ISRG", "JNJ", "JPM", "KO", "LIN",
    "LLY", "LOW", "MA", "MCD", "MDLZ", "META", "MMM", "MRK", "MS", "MSFT",
    "NEE", "NFLX", "NKE", "NOW", "NVDA", "ORCL", "PEP", "PFE", "PG", "PM",
    "QCOM", "RTX", "SBUX", "SCHW", "SPGI", "T", "TMO", "TMUS", "TSLA", "TXN",
    "UNH", "UNP", "UPS", "V", "VZ", "WFC", "WMT", "XOM", "QQQ", "IWM", "SPY",
)


def get_universe(name: str = "development") -> list[str]:
    """Return a copy of a named universe so callers cannot mutate the definition."""
    if name != "development":
        raise ValueError(f"Unknown universe {name!r}; available: development")
    return list(DEVELOPMENT_UNIVERSE)

