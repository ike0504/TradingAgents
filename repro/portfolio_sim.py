"""Turn the agent's rating stream into the paper's own metrics.

The released code deliberately does not do this -- ``tradingagents/backtest.py``
scores each (ticker, date) cell independently against a benchmark and refuses to
simulate a portfolio ("must not grow one"). The paper's Table 1, however, is in
CR% / ARR% / SR / MDD%, which need an equity curve. To compare our run against
Table 1 we therefore have to reconstruct one, and every choice that goes into
it is stated here so the comparison is auditable rather than implied:

* Rating -> exposure. The five-tier scale is mapped symmetrically onto
  +/-1 and +/-0.5. The paper never publishes this mapping; it only shows
  long/short arrows in its transaction-history figures.
* A decision holds from the first close after its analysis date until the next
  decision's date. The released code measures a 5-trading-day outcome; the
  paper's Figure 6 implies continuous positions. We use "until the next
  decision", which is the same thing when decisions are 5 days apart.
* No transaction costs, matching the paper's Appendix 8.2, whose formulas
  contain no cost term.
"""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
import yfinance as yf

from repro import config as cfg
from repro.metrics import evaluate

# Rating -> signed exposure. REVIEW is the repo's "no readable decision"
# sentinel and is not a position, so it is treated as flat.
EXPOSURE = {
    "Buy": 1.0,
    "Overweight": 0.5,
    "Hold": 0.0,
    "Underweight": -0.5,
    "Sell": -1.0,
    "REVIEW": 0.0,
}

# The paper's Table 1, transcribed from arXiv:2412.20138v7, for side-by-side
# comparison. Columns: CR%, ARR%, SR, MDD%.
PAPER_TABLE1 = {
    "TradingAgents": {
        "AAPL": {"CR%": 26.62, "ARR%": 30.5, "SR": 8.21, "MDD%": 0.91},
        "GOOGL": {"CR%": 24.36, "ARR%": 27.58, "SR": 6.39, "MDD%": 1.69},
        "AMZN": {"CR%": 23.21, "ARR%": 24.90, "SR": 5.60, "MDD%": 2.11},
    },
    "B&H": {
        "AAPL": {"CR%": -5.23, "ARR%": -5.09, "SR": -1.29, "MDD%": 11.90},
        "GOOGL": {"CR%": 7.78, "ARR%": 8.09, "SR": 1.35, "MDD%": 13.04},
        "AMZN": {"CR%": 17.1, "ARR%": 17.6, "SR": 3.53, "MDD%": 3.80},
    },
}


def load_entries(log_path: str | Path) -> list[dict]:
    """Read the memory log produced by a run into dicts."""
    from tradingagents.memory import TradingMemoryLog
    return TradingMemoryLog({"memory_log_path": str(log_path)}).load_entries()


def ratings_frame(entries: list[dict], ticker: str) -> pd.DataFrame:
    """Settled (date, rating) pairs for one ticker, sorted by date."""
    rows = [(e["date"], e["rating"]) for e in entries
            if e["ticker"] == ticker and not e["pending"]]
    df = pd.DataFrame(rows, columns=["date", "rating"]).drop_duplicates("date")
    df["date"] = pd.to_datetime(df["date"])
    return df.sort_values("date").reset_index(drop=True)


def simulate(ticker: str, ratings: pd.DataFrame, start: str, end: str) -> dict:
    """Equity curve and paper metrics for one ticker's rating stream."""
    px = yf.Ticker(ticker).history(start=start, end=end, interval="1d", auto_adjust=False)
    px.index = pd.to_datetime(px.index).tz_localize(None)
    close = px["Close"]
    if close.empty:
        raise ValueError(f"no prices for {ticker} in {start}..{end}")

    # Step-hold: each decision's exposure runs from the first close after its
    # date until the next decision takes over.
    exposure = pd.Series(0.0, index=close.index)
    dates = list(ratings["date"])
    for i, (_, row) in enumerate(ratings.iterrows()):
        nxt = dates[i + 1] if i + 1 < len(dates) else close.index[-1] + pd.Timedelta(days=1)
        mask = (close.index > row["date"]) & (close.index <= nxt)
        if mask.any():
            exposure.loc[mask] = EXPOSURE.get(row["rating"], 0.0)

    daily_ret = close.pct_change().fillna(0.0)
    strategy_ret = exposure.shift(1).fillna(0.0) * daily_ret
    equity = (1.0 + strategy_ret).cumprod()

    metrics = evaluate(equity)
    return {
        "ticker": ticker,
        "n_decisions": len(ratings),
        "rating_counts": ratings["rating"].value_counts().to_dict(),
        "mean_abs_exposure": float(exposure.abs().mean()),
        "metrics": metrics,
        "equity": equity,
    }


def run_all(log_path: str | Path, tickers=None, start=cfg.WINDOW_START,
            end=cfg.WINDOW_END) -> dict:
    """Simulate every ticker in one run's log and put it next to Table 1."""
    entries = load_entries(log_path)
    out = {"log_path": str(log_path), "window": {"start": start, "end": end}, "tickers": {}}
    for ticker in (tickers or cfg.TICKERS):
        ratings = ratings_frame(entries, ticker)
        if ratings.empty:
            out["tickers"][ticker] = {"error": "no settled decisions"}
            continue
        sim = simulate(ticker, ratings, start, end)
        row = {k: sim[k] for k in ("n_decisions", "rating_counts", "mean_abs_exposure")}
        row["ours"] = sim["metrics"]
        row["paper_TradingAgents"] = PAPER_TABLE1["TradingAgents"].get(ticker)
        row["paper_B&H"] = PAPER_TABLE1["B&H"].get(ticker)
        out["tickers"][ticker] = row
    return out


if __name__ == "__main__":
    import argparse
    p = argparse.ArgumentParser()
    p.add_argument("log_path")
    p.add_argument("--out", default=None)
    p.add_argument("--tickers", nargs="*", default=None)
    a = p.parse_args()
    res = run_all(a.log_path, a.tickers)
    text = json.dumps(res, indent=2, default=str)
    if a.out:
        Path(a.out).write_text(text, encoding="utf-8")
        print("wrote", a.out)
    print(text)
