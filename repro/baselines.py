"""The paper's five baseline strategies (arXiv:2412.20138v7, Appendix 8.1).

The paper describes but does not release these baselines; the descriptions in
Appendix 8.1 are one-line summaries, so each implementation below is the
standard textbook form of the named indicator, documented inline. Any deviation
between our baseline numbers and the paper's is expected to come from this gap
(no released code, no parameter details) and is reported as such, not hidden.

All strategies trade the same daily bars as the agent sees: they decide a
position of {+1 long, 0 flat, -1 short} for the *next* trading day using data up
to and including the current day (no look-ahead), are marked to market on the
close, and are charged no transaction costs -- the paper's Appendix 8.2 contains
no transaction-cost term either.
"""

from __future__ import annotations

import numpy as np
import pandas as pd


def _equity(position: pd.Series, close: pd.Series) -> pd.Series:
    """Equity curve of a position series marked to market on the close.

    ``position`` is the exposure decided using data through day t-1, applied to
    day t's return, so the first day's decided position earns no return (it is
    only knowable after the close). Long/short/flat = +1/-1/0, always one unit.
    """
    position = position.reindex(close.index).fillna(0.0)
    daily_ret = close.pct_change().fillna(0.0)
    strategy_ret = position.shift(1).fillna(0.0) * daily_ret
    return (1.0 + strategy_ret).cumprod()


def buy_and_hold(close: pd.Series) -> pd.Series:
    """Buy and hold: long from the first close to the last."""
    position = pd.Series(1.0, index=close.index)
    return _equity(position, close)


def macd(close: pd.Series, fast: int = 12, slow: int = 26, signal: int = 9) -> pd.Series:
    """MACD: long when the MACD line crosses above its signal line, else flat."""
    ema_fast = close.ewm(span=fast, adjust=False).mean()
    ema_slow = close.ewm(span=slow, adjust=False).mean()
    macd_line = ema_fast - ema_slow
    signal_line = macd_line.ewm(span=signal, adjust=False).mean()
    position = (macd_line > signal_line).astype(float)
    return _equity(position, close)


def kdj_rsi(close: pd.Series, high: pd.Series, low: pd.Series,
            n: int = 9, m1: int = 3, m2: int = 3, rsi_len: int = 14) -> pd.Series:
    """KDJ + RSI: long when K crosses above D while RSI is under 70, else flat.

    KDJ with the standard 9/3/3 parameters; RSI(14). The combination rule
    (both must agree bullish) is the usual reading of "KDJ&RSI" as a joint
    filter; the paper gives no parameters or combination rule.
    """
    low_n = low.rolling(n, min_periods=1).min()
    high_n = high.rolling(n, min_periods=1).max()
    denom = (high_n - low_n).replace(0.0, np.nan)
    rsv = (close - low_n) / denom * 100.0
    rsv = rsv.fillna(50.0)
    k = rsv.ewm(alpha=1.0 / m1, adjust=False).mean()
    d = k.ewm(alpha=1.0 / m2, adjust=False).mean()

    delta = close.diff()
    gain = delta.clip(lower=0.0).rolling(rsi_len, min_periods=1).mean()
    loss = (-delta.clip(upper=0.0)).rolling(rsi_len, min_periods=1).mean()
    rs = gain / loss.replace(0.0, np.nan)
    rsi = (100.0 - 100.0 / (1.0 + rs)).fillna(50.0)

    k_prev, d_prev = k.shift(1), d.shift(1)
    cross_up = (k > d) & (k_prev <= d_prev)
    position = pd.Series(0.0, index=close.index)
    # hold the long while K stays above D and RSI has not gone above 70
    for i in range(1, len(close)):
        if cross_up.iloc[i] and rsi.iloc[i] < 70.0:
            position.iloc[i] = 1.0
        elif position.iloc[i - 1] == 1.0:
            position.iloc[i] = 1.0 if (k.iloc[i] > d.iloc[i] and rsi.iloc[i] < 70.0) else 0.0
    return _equity(position, close)


def zmr(close: pd.Series, window: int = 20) -> pd.Series:
    """Zero-mean reversion: short above the rolling mean, long below it.

    "ZMR" is not a standard acronym; the paper's one-line description reads as a
    rolling-mean reversion rule. We use the common 20-day window.
    """
    ma = close.rolling(window, min_periods=1).mean()
    position = pd.Series(np.where(close < ma, 1.0, np.where(close > ma, -1.0, 0.0)),
                         index=close.index)
    return _equity(position, close)


def sma(close: pd.Series, short: int = 20, long: int = 50) -> pd.Series:
    """SMA crossover: long when the short moving average is above the long one."""
    ma_s = close.rolling(short, min_periods=1).mean()
    ma_l = close.rolling(long, min_periods=1).mean()
    position = (ma_s > ma_l).astype(float)
    return _equity(position, close)


BASELINES = {
    "B&H": buy_and_hold,
    "MACD": macd,
    "KDJ&RSI": kdj_rsi,
    "ZMR": zmr,
    "SMA": sma,
}
