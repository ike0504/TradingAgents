"""Exact significance tests for the two arms.

scipy is not installed in the study environment, and the counts here are small
enough that exact tests are both feasible and preferable: no normal
approximation is needed for a 2x2 table whose smallest cell is 0.

Everything is computed from the scored cells, so the tests are re-derived
whenever more cells land.
"""

from __future__ import annotations

import math
from collections import defaultdict

import repro.cells as cells_mod


# ---------------------------------------------------------------------------
# exact tests
# ---------------------------------------------------------------------------
def _log_choose(n: int, k: int) -> float:
    return (math.lgamma(n + 1) - math.lgamma(k + 1) - math.lgamma(n - k + 1))


def fisher_exact(a: int, b: int, c: int, d: int) -> float:
    """Two-sided Fisher exact p for [[a, b], [c, d]].

    Sums the hypergeometric mass of every table at least as extreme as the
    observed one, i.e. every table with probability <= the observed one.
    """
    n = a + b + c + d
    r1, r2 = a + b, c + d
    c1 = a + c
    denom = _log_choose(n, c1)

    def pr(x: int) -> float:
        # x = top-left cell; the rest of the table follows from the margins
        return math.exp(_log_choose(r1, x) + _log_choose(r2, c1 - x) - denom)

    lo, hi = max(0, c1 - r2), min(r1, c1)
    if hi < lo:
        return 1.0
    p_obs = pr(a)
    tol = 1e-12
    return sum(pr(x) for x in range(lo, hi + 1) if pr(x) <= p_obs * (1 + tol))


def chi2_sf_df2(x: float) -> float:
    """Upper tail of chi-square with 2 degrees of freedom.

    chi2(2) is exponential with mean 2, so the tail has a closed form and no
    incomplete gamma is needed.
    """
    return math.exp(-x / 2.0) if x > 0 else 1.0


# ---------------------------------------------------------------------------
# the comparisons this study needs
# ---------------------------------------------------------------------------
def cross_trial_stability(rows: list[dict]) -> dict:
    """Do repeated runs of the same cell agree with each other?

    The (ticker, date) cell is the unit: the market data is identical across
    trials, and temperature is 0, so any disagreement is the pipeline's, not
    the market's or the sampler's.
    """
    by_cell: dict[tuple, list[str]] = defaultdict(list)
    for r in rows:
        by_cell[(r["arm"], r["ticker"], r["date"])].append(r["rating"])
    out: dict[str, dict] = {}
    for arm in sorted({r["arm"] for r in rows}):
        unanimous = 0
        total = 0
        for (a, _tk, _d), ratings in by_cell.items():
            if a != arm:
                continue
            if len(ratings) < 2:
                continue
            total += 1
            if len(set(ratings)) == 1:
                unanimous += 1
        out[arm] = {"n_cells": total,
                    "n_unanimous": unanimous,
                    "agree_frac": (unanimous / total) if total else None}
    return out


def rating_collapse(rows: list[dict]) -> dict:
    """Overweight vs anything else, baseline vs no_debate."""
    def split(arm: str) -> tuple[int, int]:
        sub = [r for r in rows if r["arm"] == arm]
        ow = sum(1 for r in sub if r["rating"] == "Overweight")
        return ow, len(sub) - ow

    b_ow, b_other = split("baseline")
    n_ow, n_other = split("no_debate")
    return {
        "baseline": {"overweight": b_ow, "other": b_other},
        "no_debate": {"overweight": n_ow, "other": n_other},
        # rows = arm, cols = [overweight, other]
        "p_fisher": fisher_exact(b_ow, b_other, n_ow, n_other),
    }


def pooled_hit_rate(rows: list[dict]) -> dict:
    """Hit rate pooled over cells, which is what a cell is actually worth."""
    def split(arm: str) -> tuple[int, int]:
        sub = [r for r in rows if r["arm"] == arm and r.get("hit") in (0, 1)]
        hits = sum(1 for r in sub if r["hit"] == 1)
        return hits, len(sub) - hits

    b_hit, b_miss = split("baseline")
    n_hit, n_miss = split("no_debate")
    return {
        "baseline": {"hits": b_hit, "misses": b_miss,
                     "rate": b_hit / (b_hit + b_miss) if (b_hit + b_miss) else None},
        "no_debate": {"hits": n_hit, "misses": n_miss,
                      "rate": n_hit / (n_hit + n_miss) if (n_hit + n_miss) else None},
        "p_fisher": fisher_exact(b_hit, b_miss, n_hit, n_miss),
    }


def paired_trials(rows: list[dict]) -> dict:
    """Per-trial hit rates, paired by trial index.

    Trials are the resampling unit: within a trial the market data is fixed, so
    the trial-to-trial spread is the pipeline's own variability.
    """
    def rates(arm: str) -> dict[int, float]:
        per: dict[int, list[int]] = defaultdict(list)
        for r in rows:
            if r["arm"] == arm and r.get("hit") in (0, 1):
                per[r["trial"]].append(r["hit"])
        return {t: (sum(v) / len(v)) for t, v in sorted(per.items()) if v}

    b, n = rates("baseline"), rates("no_debate")
    common = sorted(set(b) & set(n))
    diffs = [b[t] - n[t] for t in common]
    sd = (sum((x - sum(diffs) / len(diffs)) ** 2 for x in diffs) / (len(diffs) - 1)) ** 0.5 \
        if len(diffs) > 1 else 0.0
    return {
        "baseline": b, "no_debate": n,
        "diffs": diffs,
        "mean_diff": sum(diffs) / len(diffs) if diffs else None,
        "sd_diff": sd,
        "n_positive": sum(1 for x in diffs if x > 0),
        "n_trials": len(diffs),
    }


def all_tests() -> dict:
    rows = cells_mod.read_cells(arms=["baseline", "no_debate"])
    return {
        "stability": cross_trial_stability(rows),
        "collapse": rating_collapse(rows),
        "hits": pooled_hit_rate(rows),
        "paired": paired_trials(rows),
        "n_cells": len(rows),
    }


def render(d: dict) -> str:
    st, co, hi, pa = d["stability"], d["collapse"], d["hits"], d["paired"]
    L = []
    A = L.append

    A("stability of a cell across repeated runs (temperature = 0)")
    for arm in ("baseline", "no_debate"):
        s = st.get(arm) or {}
        f = s.get("agree_frac")
        A(f"  {arm:10s} {s.get('n_unanimous')}/{s.get('n_cells')} cells "
          f"gave the same rating in every run"
          + (f"  ({f*100:.0f}%)" if f is not None else ""))
    A("")

    A("rating distribution, Overweight vs anything else")
    A(f"  baseline   Overweight {co['baseline']['overweight']:2d} / other "
      f"{co['baseline']['other']:2d}")
    A(f"  no_debate  Overweight {co['no_debate']['overweight']:2d} / other "
      f"{co['no_debate']['other']:2d}")
    A(f"  Fisher exact two-sided p = {co['p_fisher']:.2e}")
    A("")

    A("hit rate pooled over cells")
    for arm in ("baseline", "no_debate"):
        h = hi[arm]
        A(f"  {arm:10s} {h['hits']:2d} / {h['hits'] + h['misses']:2d}  "
          f"= {h['rate'] * 100:.1f}%")
    A(f"  Fisher exact two-sided p = {hi['p_fisher']:.4f}")
    A("")

    A("hit rate paired by trial")
    for t in sorted(set(pa["baseline"]) | set(pa["no_debate"])):
        b = pa["baseline"].get(t)
        n = pa["no_debate"].get(t)
        bs = f"{b * 100:5.1f}%" if b is not None else "    -"
        ns = f"{n * 100:5.1f}%" if n is not None else "    -"
        A(f"  trial {t}  baseline {bs}   no_debate {ns}")
    if pa["mean_diff"] is not None:
        A(f"  difference {pa['mean_diff'] * 100:+.1f} pp +/- "
          f"{pa['sd_diff'] * 100:.1f} pp over {pa['n_trials']} trials, "
          f"{pa['n_positive']}/{pa['n_trials']} in the same direction")
    return "\n".join(L)


def main() -> int:
    d = all_tests()
    print(render(d))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
