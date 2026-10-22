"""Evaluation metrics from the TradingAgents paper, Appendix 8.2.

Reproduced verbatim from arXiv:2412.20138v7 so the numbers we produce are
comparable to the paper's Table 1:

    CR  = (V_end - V_start) / V_start * 100%
    AR  = ((V_end / V_start) ** (1 / N) - 1) * 100%      N = years in simulation
    SR  = (mean(R) - R_f) / std(R)
    MDD = max((Peak_t - Trough_t) / Peak_t) * 100%

The paper does not state which return series R is for the Sharpe ratio (its
formula says "average portfolio return"), nor the risk-free rate used. We take
the daily simple returns of the equity curve and annualise with sqrt(252), and
take R_f = 0 by default -- both reported explicitly so the choice is auditable.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

TRADING_DAYS_PER_YEAR = 252


def cumulative_return(equity: pd.Series) -> float:
    """CR% -- total return over the simulation, in percent."""
    equity = pd.Series(equity).dropna()
    if len(equity) < 2 or equity.iloc[0] == 0:
        return float("nan")
    return (equity.iloc[-1] - equity.iloc[0]) / equity.iloc[0] * 100.0


def annualised_return(equity: pd.Series, years: float | None = None) -> float:
    """ARR% -- CR normalised by the length of the simulation, in percent.

    ``years`` defaults to the number of trading days observed / 252, matching the
    paper's N = "number of years in the simulation".
    """
    equity = pd.Series(equity).dropna()
    if len(equity) < 2 or equity.iloc[0] <= 0:
        return float("nan")
    if years is None:
        years = (len(equity) - 1) / TRADING_DAYS_PER_YEAR
    if years <= 0:
        return float("nan")
    return ((equity.iloc[-1] / equity.iloc[0]) ** (1.0 / years) - 1.0) * 100.0


def sharpe_ratio(equity: pd.Series, risk_free_rate: float = 0.0) -> float:
    """SR -- annualised Sharpe ratio of the equity curve's daily returns.

    Risk-free rate is quoted as an annual decimal (0.0 by default) and converted
    to a daily rate by /252.
    """
    equity = pd.Series(equity).dropna()
    if len(equity) < 3:
        return float("nan")
    rets = equity.pct_change().dropna()
    if len(rets) < 2:
        return float("nan")
    sigma = rets.std(ddof=1)
    if sigma == 0 or np.isnan(sigma):
        return float("nan")
    daily_rf = risk_free_rate / TRADING_DAYS_PER_YEAR
    excess = rets - daily_rf
    return float(excess.mean() / sigma * np.sqrt(TRADING_DAYS_PER_YEAR))


def max_drawdown(equity: pd.Series) -> float:
    """MDD% -- largest peak-to-trough decline of the equity curve, in percent."""
    equity = pd.Series(equity).dropna()
    if len(equity) < 2:
        return float("nan")
    peak = equity.cummax()
    dd = (peak - equity) / peak
    return float(dd.max() * 100.0)


def evaluate(equity: pd.Series, risk_free_rate: float = 0.0) -> dict[str, float]:
    """All four paper metrics for one equity curve."""
    equity = pd.Series(equity).dropna()
    return {
        "CR%": cumulative_return(equity),
        "ARR%": annualised_return(equity),
        "SR": sharpe_ratio(equity, risk_free_rate),
        "MDD%": max_drawdown(equity),
    }
