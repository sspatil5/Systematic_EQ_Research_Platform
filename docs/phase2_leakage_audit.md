# Phase 2 leakage audit

Information cutoff: a feature labeled session `t` may use values through the close of `t`. It may
not be executed before `t+1`. Targets are research labels and intentionally use future closes.

| Family | Data used | Latest feature timestamp | Audit result |
|---|---|---:|---|
| Trailing returns | Per-ticker adjusted closes at `t` and `t-L` | `t` | `pct_change(L)` is grouped by ticker and backward-looking. |
| Moving averages | Last `L` per-ticker adjusted closes, including `t` | `t` | `rolling(L)` is trailing; no centered windows. |
| 12-1 momentum | Per-ticker closes at `t-21` and `t-252` | `t-21` | Both shifts are positive/backward. |
| Return z-scores | Current and trailing 1-day returns | `t` | Rolling statistics are per ticker; no full-sample normalization. |
| Volatility | Last `L` per-ticker 1-day returns | `t` | Trailing sample standard deviation; ratios preserve undefined denominators as `NaN`. |
| Volume/liquidity | Per-ticker close/volume and trailing windows | `t` | No forward fill or future volume. |
| Market relative | Same-date SPY return and trailing asset/SPY histories | `t` | Join is by date. Missing SPY dates remain missing. |
| Beta | Trailing paired asset/SPY returns | `t` | Reported beta includes `t`; no future observations. |
| Residual return | Return at `t`, SPY return at `t`, beta through `t-1` | `t` | Beta is explicitly lagged one row to avoid explaining a return with an estimate containing itself. |
| Cross-sectional transforms | Non-missing securities on one date | `t` | `groupby(date)` prevents statistics from spanning time. |
| Forward targets | Per-ticker closes at `t` and `t+h` | `t+h` | Negative shift is confined to the target module; target names are rejected as feature inputs. |
| Target ranks/excess returns | Same-date forward labels across securities / SPY | `t+h` | Labels only; never included in feature metadata or transformations. |

## Mutation audit

The permanent regression test builds two panels identical through cutoff `T` and radically changes
all closes after `T`. Every feature through `T` must remain byte-for-byte equivalent, while forward
targets near `T` are expected to differ. The test passes.

## Remaining timing limitations

- Per-ticker row shifts represent observed rows, not an exchange-master calendar. If one ticker is
  missing a session, its `h`-row feature or target can span more than `h` market sessions.
- A close-to-close target does not exactly match the future open-execution return that the backtest
  will eventually realize. It is a prediction label, not an executable P&L series.
- Phase 1 uses a present-day universe and yfinance adjusted data, so survivorship, selection,
  delisting, provider-adjustment, and point-in-time membership limitations remain.

