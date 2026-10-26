"""Put our reconstructed equity curve next to the paper's Table 1.

Table 1 is in CR% / ARR% / SR / MDD%. The released code refuses to produce an
equity curve, so ``portfolio_sim`` rebuilds one from the rating stream. This
module does the bookkeeping around that: group cells by (arm, trial), simulate
each run, average repeated trials, and lay the result beside three references --

  * the paper's own TradingAgents row,
  * the paper's own Buy & Hold row,
  * *our* Buy & Hold over the same prices.

The last one is the control that makes the comparison legible. CR% for a
strategy depends on the price series only through that series, so if our B&H
matches the paper's B&H then any gap in the TradingAgents row is attributable to
the agent; if our B&H does not match, the gap is in the data before the agent
ever sees it. That split is the whole point of running the deterministic row.
"""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
import yfinance as yf

from repro import config as cfg
from repro import portfolio_sim as ps
from repro.metrics import evaluate
from repro.baselines import buy_and_hold


def load_runs(results_dir: str | None = None) -> list[dict]:
    """Every scored sweep run, as (arm, trial, tickers, log_path)."""
    base = Path(results_dir or cfg.RESULTS_DIR) / "sweeps"
    runs = []
    for f in sorted(base.glob("*.json")):
        d = json.loads(f.read_text(encoding="utf-8"))
        log = d.get("log_path")
        if not log or not Path(log).exists():
            continue
        runs.append({
            "arm": d.get("arm"),
            "trial": d.get("trial"),
            "run_id": d.get("run_id"),
            "log_path": log,
            "summary": d.get("summary") or {},
        })
    return runs


def prices(ticker: str, start: str, end: str) -> pd.Series:
    df = yf.Ticker(ticker).history(start=start, end=end, interval="1d",
                                   auto_adjust=False)
    df.index = pd.to_datetime(df.index).tz_localize(None)
    return df["Close"]


def simulate_run(run: dict, tickers: list[str] | None = None) -> dict:
    """Portfolio metrics for one run, per ticker."""
    entries = ps.load_entries(run["log_path"])
    out = {}
    for tk in (tickers or cfg.TICKERS):
        ratings = ps.ratings_frame(entries, tk)
        if ratings.empty:
            continue
        sim = ps.simulate(tk, ratings, cfg.WINDOW_START, cfg.WINDOW_END)
        out[tk] = {
            "metrics": sim["metrics"],
            "n_decisions": sim["n_decisions"],
            "rating_counts": sim["rating_counts"],
        }
    return out


def mean_std(rows: list[dict], key: str) -> tuple[float | None, float | None]:
    """Mean and sample std of ``metrics[key]`` across repeated trial dicts."""
    vals = [r["metrics"][key] for r in rows if key in r.get("metrics", {})]
    if not vals:
        return None, None
    s = pd.Series(vals, dtype=float)
    return float(s.mean()), (float(s.std(ddof=1)) if len(s) > 1 else 0.0)


def build(results_dir: str | None = None) -> dict:
    """Assemble the full comparison, grouped arm -> ticker."""
    runs = load_runs(results_dir)
    grouped: dict[str, list[dict]] = {}
    for r in runs:
        if r["arm"]:
            grouped.setdefault(r["arm"], []).append(r)

    out = {
        "window": {"start": cfg.WINDOW_START, "end": cfg.WINDOW_END},
        "arms": {},
        "reference": {},
    }

    # Deterministic reference rows, computed on our own prices.
    for tk in cfg.TICKERS:
        close = prices(tk, cfg.WINDOW_START, cfg.WINDOW_END)
        if close.empty:
            continue
        out["reference"][tk] = {
            "our_B&H": evaluate(buy_and_hold(close)),
            "paper_B&H": ps.PAPER_TABLE1["B&H"].get(tk),
            "paper_TradingAgents": ps.PAPER_TABLE1["TradingAgents"].get(tk),
        }

    for arm, arm_runs in sorted(grouped.items()):
        per_ticker: dict[str, list[dict]] = {}
        for r in arm_runs:
            for tk, row in simulate_run(r).items():
                per_ticker.setdefault(tk, []).append(row)
        out["arms"][arm] = {
            "n_runs": len(arm_runs),
            "tickers": {
                tk: {
                    "n_runs": len(rows),
                    "n_decisions": rows[0]["n_decisions"],
                    "rating_counts": rows[0]["rating_counts"],
                    "metrics": {
                        m: {"mean": mean_std(rows, m)[0], "std": mean_std(rows, m)[1]}
                        for m in ("CR%", "ARR%", "SR", "MDD%")
                    },
                }
                for tk, rows in per_ticker.items()
            },
        }
    return out


_METRICS = ("CR%", "ARR%", "SR", "MDD%")


def render(res: dict) -> str:
    lines = []
    lines.append(f"window {res['window']['start']} .. {res['window']['end']}")
    lines.append("")
    hdr = f"{'ticker':7s} {'row':22s} " + " ".join(f"{m:>9s}" for m in _METRICS)
    lines.append(hdr)
    lines.append("-" * len(hdr))

    for tk in cfg.TICKERS:
        ref = res["reference"].get(tk)
        if not ref:
            continue
        rows = [
            ("paper: TradingAgents", ref["paper_TradingAgents"]),
            ("paper: B&H", ref["paper_B&H"]),
            ("ours: B&H (same px)", ref["our_B&H"]),
        ]
        for arm in sorted(res["arms"]):
            t = res["arms"][arm]["tickers"].get(tk)
            if not t:
                continue
            rows.append((f"ours: {arm}", {m: t["metrics"][m]["mean"] for m in _METRICS}))
        for label, m in rows:
            if m is None:
                continue
            cells = " ".join(f"{m[k]:9.2f}" if k in m and m[k] is not None
                             else f"{'--':>9s}" for k in _METRICS)
            lines.append(f"{tk:7s} {label:22s} {cells}")
        lines.append("")
    return "\n".join(lines)


if __name__ == "__main__":
    import argparse
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--out", default=None)
    a = p.parse_args()
    res = build()
    print(render(res))
    if a.out:
        Path(a.out).write_text(json.dumps(res, indent=2), encoding="utf-8")
        print("\nwrote", a.out)
