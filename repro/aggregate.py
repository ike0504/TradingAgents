"""Aggregate several trials of the same arm into mean +/- spread.

The repo's own scorer already reports, per rating, how many decisions were made
and what their mean alpha was. What it does not do is combine repeated runs: a
single run is a single sample from an LLM's output distribution, so the numbers
below are reported as mean and sample standard deviation over trials, which is
what the assignment asks for ("run 3-5 trials and report mean/variance").

One trial may be spread over several files when the sweep was split by ticker
(``--tag``), so files are grouped by trial number and combined before the
statistics are taken.
"""

from __future__ import annotations

import argparse
import json
import math
from pathlib import Path

from repro import config as cfg

# Direction each rating claims, mirroring tradingagents/backtest.py::_DIRECTION.
DIRECTION = {"Buy": 1, "Overweight": 1, "Hold": 0, "Underweight": -1, "Sell": -1}


def _mean(xs: list[float]) -> float:
    return sum(xs) / len(xs) if xs else float("nan")


def _std(xs: list[float]) -> float:
    if len(xs) < 2:
        return 0.0
    m = _mean(xs)
    return math.sqrt(sum((x - m) ** 2 for x in xs) / (len(xs) - 1))


def _fmt(m: float, s: float, pct: bool = True) -> str:
    if math.isnan(m):
        return "n/a"
    return f"{m:.2%} +/- {s:.2%}" if pct else f"{m:.2f} +/- {s:.2f}"


def load_runs(arm: str, results_dir: str | None = None) -> list[dict]:
    """Every saved run of one arm, excluding smoke tests."""
    d = Path(results_dir or cfg.RESULTS_DIR) / "sweeps"
    return [json.loads(p.read_text(encoding="utf-8"))
            for p in sorted(d.glob(f"{arm}_t*.json")) if "_smoke" not in p.name]


def _combine(runs: list[dict]) -> dict:
    """Merge the runs of one trial into a single per-trial scorecard."""
    ratings: dict[str, dict] = {}
    for r in runs:
        for rating, s in r["summary"]["by_rating"].items():
            b = ratings.setdefault(rating, {"n": 0, "hit": 0.0, "hit_n": 0, "alpha": 0.0})
            b["n"] += s["n"]
            b["alpha"] += s["mean_alpha"] * s["n"]
            if s["hit_rate"] is not None:
                b["hit"] += s["hit_rate"] * s["n"]
                b["hit_n"] += s["n"]
    out = {}
    for rating, b in ratings.items():
        out[rating] = {
            "n": b["n"],
            "mean_alpha": b["alpha"] / b["n"] if b["n"] else float("nan"),
            "hit_rate": b["hit"] / b["hit_n"] if b["hit_n"] else None,
        }
    return out


def aggregate(arm: str, results_dir: str | None = None) -> dict:
    runs = load_runs(arm, results_dir)
    if not runs:
        raise FileNotFoundError(f"no saved trials for arm {arm!r}")

    by_trial: dict[int, list[dict]] = {}
    for r in runs:
        by_trial.setdefault(r["trial"], []).append(r)
    trial_ids = sorted(by_trial)

    per_trial = []
    for tid in trial_ids:
        group = by_trial[tid]
        combined = _combine(group)
        # Directional calls only: Hold claims no direction, so it cannot be
        # scored right or wrong.
        scored = [(rating, s) for rating, s in combined.items() if DIRECTION.get(rating)]
        hits = sum(s["hit_rate"] * s["n"] for rating, s in scored if s["hit_rate"] is not None)
        denom = sum(s["n"] for rating, s in scored if s["hit_rate"] is not None)
        alpha_num = sum(s["mean_alpha"] * s["n"] for rating, s in scored)
        alpha_den = sum(s["n"] for _, s in scored)
        per_trial.append({
            "trial": tid,
            "files": [r["run_id"] for r in group],
            "cells_run": sum(r["cells_run"] for r in group),
            "failures": sum(len(r["failures"]) for r in group),
            "elapsed_min": round(sum(r["elapsed_sec"] for r in group) / 60, 1),
            "n_directional": alpha_den,
            "hit_rate": hits / denom if denom else float("nan"),
            "mean_alpha": alpha_num / alpha_den if alpha_den else float("nan"),
            "by_rating": combined,
        })

    ratings = sorted({rating for t in per_trial for rating in t["by_rating"]})
    return {
        "arm": arm,
        "trials": len(per_trial),
        "modification": cfg.ARMS[arm],
        "llm": runs[0]["llm"],
        "window": runs[0]["window"],
        "per_trial": per_trial,
        "overall_hit_rate": {
            "mean": _mean([t["hit_rate"] for t in per_trial]),
            "std": _std([t["hit_rate"] for t in per_trial]),
            "per_trial": [t["hit_rate"] for t in per_trial],
        },
        "mean_alpha": {
            "mean": _mean([t["mean_alpha"] for t in per_trial]),
            "std": _std([t["mean_alpha"] for t in per_trial]),
            "per_trial": [t["mean_alpha"] for t in per_trial],
        },
        "by_rating": {
            rating: {
                "n": {"mean": _mean([t["by_rating"].get(rating, {}).get("n", 0)
                                     for t in per_trial]),
                      "std": _std([t["by_rating"].get(rating, {}).get("n", 0)
                                   for t in per_trial])},
                "mean_alpha": {
                    "mean": _mean([t["by_rating"][rating]["mean_alpha"]
                                   for t in per_trial if rating in t["by_rating"]]),
                    "std": _std([t["by_rating"][rating]["mean_alpha"]
                                 for t in per_trial if rating in t["by_rating"]]),
                },
                "hit_rate": {
                    "mean": _mean([t["by_rating"][rating]["hit_rate"]
                                   for t in per_trial
                                   if rating in t["by_rating"]
                                   and t["by_rating"][rating]["hit_rate"] is not None]),
                    "std": _std([t["by_rating"][rating]["hit_rate"]
                                 for t in per_trial
                                 if rating in t["by_rating"]
                                 and t["by_rating"][rating]["hit_rate"] is not None]),
                },
            }
            for rating in ratings
        },
    }


def render(a: dict) -> str:
    w = a["window"]
    lines = [
        f"arm={a['arm']}   modification={a['modification']}",
        f"llm={a['llm']['provider']}/{a['llm']['quick']} (deep={a['llm']['deep']}) "
        f"temp={a['llm']['temperature']} max_tokens={a['llm']['max_tokens']}",
        f"window={w['start']}..{w['end']} every {w['every_n_days']}d   trials={a['trials']}",
        "",
        f"{'trial':<7}{'cells':>7}{'fail':>6}{'min':>8}{'hit rate':>12}{'mean alpha':>14}",
    ]
    for t in a["per_trial"]:
        lines.append(f"{t['trial']:<7}{t['cells_run']:>7}{t['failures']:>6}"
                     f"{t['elapsed_min']:>8.1f}{t['hit_rate']:>11.1%}"
                     f"{t['mean_alpha']:>+13.2%}")
    lines += [
        "",
        f"OVERALL  hit rate   {_fmt(a['overall_hit_rate']['mean'], a['overall_hit_rate']['std'])}"
        f"   per trial {[round(x, 3) for x in a['overall_hit_rate']['per_trial']]}",
        f"OVERALL  mean alpha {_fmt(a['mean_alpha']['mean'], a['mean_alpha']['std'])}"
        f"   per trial {[round(x, 4) for x in a['mean_alpha']['per_trial']]}",
        "",
        f"{'rating':<12}{'n':>7}{'hit rate':>18}{'mean alpha':>18}",
    ]
    for rating, s in sorted(a["by_rating"].items(), key=lambda kv: -kv[1]["n"]["mean"]):
        hr = _fmt(s["hit_rate"]["mean"], s["hit_rate"]["std"])
        lines.append(f"{rating:<12}{s['n']['mean']:>7.1f}{hr:>18}"
                     f"{_fmt(s['mean_alpha']['mean'], s['mean_alpha']['std']):>18}")
    return "\n".join(lines)


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--arm", action="append", choices=sorted(cfg.ARMS), required=True)
    p.add_argument("--out", default=None)
    a = p.parse_args()
    out = {arm: aggregate(arm) for arm in a.arm}
    text = json.dumps(out, indent=2)
    if a.out:
        Path(a.out).write_text(text, encoding="utf-8")
        print("wrote", a.out)
    for arm, agg in out.items():
        print("\n" + render(agg) + "\n")
