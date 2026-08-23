"""Cached present-day sector labels for research controls only.

These labels are not point-in-time classifications and must not be used to claim historical
sector membership accuracy. ETFs are grouped separately.
"""

from __future__ import annotations

import pandas as pd

SECTOR_MAP: dict[str, str] = {
    "AAPL":"Information Technology","ABBV":"Health Care","ABT":"Health Care","ACN":"Information Technology","ADBE":"Information Technology","AMD":"Information Technology","AMGN":"Health Care","AMZN":"Consumer Discretionary","AVGO":"Information Technology","AXP":"Financials",
    "BA":"Industrials","BAC":"Financials","BKNG":"Consumer Discretionary","BLK":"Financials","BMY":"Health Care","BRK-B":"Financials","CAT":"Industrials","CL":"Consumer Staples","CMCSA":"Communication Services","COP":"Energy",
    "COST":"Consumer Staples","CRM":"Information Technology","CSCO":"Information Technology","CVX":"Energy","DE":"Industrials","DHR":"Health Care","DIS":"Communication Services","GE":"Industrials","GILD":"Health Care","GOOG":"Communication Services",
    "GS":"Financials","HD":"Consumer Discretionary","HON":"Industrials","IBM":"Information Technology","INTC":"Information Technology","ISRG":"Health Care","JNJ":"Health Care","JPM":"Financials","KO":"Consumer Staples","LIN":"Materials",
    "LLY":"Health Care","LOW":"Consumer Discretionary","MA":"Financials","MCD":"Consumer Discretionary","MDLZ":"Consumer Staples","META":"Communication Services","MMM":"Industrials","MRK":"Health Care","MS":"Financials","MSFT":"Information Technology",
    "NEE":"Utilities","NFLX":"Communication Services","NKE":"Consumer Discretionary","NOW":"Information Technology","NVDA":"Information Technology","ORCL":"Information Technology","PEP":"Consumer Staples","PFE":"Health Care","PG":"Consumer Staples","PM":"Consumer Staples",
    "QCOM":"Information Technology","RTX":"Industrials","SBUX":"Consumer Discretionary","SCHW":"Financials","SPGI":"Financials","T":"Communication Services","TMO":"Health Care","TMUS":"Communication Services","TSLA":"Consumer Discretionary","TXN":"Information Technology",
    "UNH":"Health Care","UNP":"Industrials","UPS":"Industrials","V":"Financials","VZ":"Communication Services","WFC":"Financials","WMT":"Consumer Staples","XOM":"Energy","QQQ":"ETF","IWM":"ETF","SPY":"ETF",
}


def sector_series(index: pd.MultiIndex) -> pd.Series:
    tickers = index.get_level_values("ticker")
    values = pd.Series(tickers.map(SECTOR_MAP), index=index, name="sector")
    missing = sorted(set(tickers[values.isna()]))
    if missing:
        raise ValueError(f"Missing current sector labels for {missing}")
    return values

