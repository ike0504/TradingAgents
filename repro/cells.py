"""Read every scored cell back out of the run logs, as one tidy table.

``run_backtest`` writes a human-readable ``trading_memory.md`` per run whose
header line carries everything a cell was scored on::

    [2024-01-29 | AAPL | Hold | +0.7% | +0.0% | 5d | resolved:2024-02-06]

The sweep JSON only keeps per-rating aggregates, so this recovers the individual
decisions. Without it two arms can only be compared at the level of "the mean
alpha was higher", and there is no way to see that one arm answered Hold twice
while the other never did -- which is the difference that actually matters.

Usage
-----
    python -m repro.cells --arm baseline --arm no_debate
    python -m repro.cells --out ../results/cells.csv
"""

from __future__ import annotations

import argparse
import csv
import json
import re
from pathlib import Path

from repro import config as cfg

# [date | ticker | rating | raw% | alpha% | holding | resolved:...]
HEADER = re.compile(
    r"^\[(?P<date>\d{4}-\d{2}-\d{2})\s*\|\s*(?P<ticker>[A-Z]+)\s*\|\s*"
    r"(?P<rating>[A-Za-z]+)\s*\|\s*(?P<raw>[-+]?[\d.]+)%\s*\|\s*"
    r"(?P<alpha>[-+]?[\d.]+)%\s*\|\s*(?P<holding>\S+)\s*\|\s*resolved:(?P<resolved>\S+)\]")

DIRECTION = {"Buy": 1, "Overweight": 1, "Hold": 0, "Underweight": -1, "Sell": -1}


def _split_run_id(run_id: str) -> tuple[str, int | None, str | None]:
    """(arm, trial, ticker) from a directory name like no_debate_t2_AAPL_20240101."""
    arm = None
    for candidate in cfg.ARMS:
        if run_id.startswith(candidate + "_"):
            arm = candidate
            break
    if arm is None:
        return run_id, None, None
    parts = run_id[len(arm):].strip("_").split("_")
    trial = None
    if parts and re.fullmatch(r"t\d+", parts[0]):
        trial = int(parts[0][1:])
        parts = parts[1:]
    # Anything left is either a ticker, a date slug, or a free-text tag such as
    # "cal"; only keep it if it is not an 8-digit date and not a known tag.
    ticker = None
    if parts and re.fullmatch(r"[A-Z]{1,5}", parts[0]):
        ticker = parts[0]
    return arm, trial, ticker


def admissible_runs(results_dir: str | None = None) -> set[str]:
    """Run ids with a clean saved score in results/sweeps.

    The first sweep died halfway and left logs behind for cells it never scored.
    Matching against the saved results drops that debris, and also drops a cell
    that is still being written, so a table read mid-run stays honest.
    """
    sweeps = Path(results_dir or cfg.RESULTS_DIR) / "sweeps"
    if not sweeps.is_dir():
        return set()
    return {p.stem for p in sweeps.glob("*.json") if "_smoke" not in p.name}


def read_cells(results_dir: str | None = None,
               arms: list[str] | None = None,
               only_scored: bool = True) -> list[dict]:
    base = Path(results_dir or cfg.RESULTS_DIR) / "backtest"
    rows: list[dict] = []
    if not base.is_dir():
        return rows
    scored = admissible_runs(results_dir)
    for log in sorted(base.glob("*/trading_memory.md")):
        run_id = log.parent.name
        if only_scored and run_id not in scored:
            continue
        arm, trial, ticker_hint = _split_run_id(run_id)
        if arms and arm not in arms:
            continue
        for line in log.read_text(encoding="utf-8", errors="replace").splitlines():
            m = HEADER.match(line.strip())
            if not m:
                continue
            rating = m["rating"]
            raw = float(m["raw"]) / 100
            alpha = float(m["alpha"]) / 100
            direction = DIRECTION.get(rating, 0)
            rows.append({
                "run_id": run_id,
                "arm": arm,
                "trial": trial,
                "ticker": m["ticker"] or ticker_hint,
                "date": m["date"],
                "rating": rating,
                "direction": direction,
                "raw_return": raw,
                "alpha": alpha,
                "holding": m["holding"],
                "resolved": m["resolved"],
                # A directional call is right when the alpha it implied came true.
                "hit": (1 if alpha * direction > 0 else 0) if direction else None,
            })
    return rows


def _fmt_pct(x: float | None) -> str:
    return "n/a" if x is None else f"{x:+.2%}"


def render(rows: list[dict]) -> str:
    if not rows:
        return "no cells found"
    lines = [f"{'arm':<11}{'t':<4}{'ticker':<7}{'date':<12}{'rating':<12}"
             f"{'raw':>8}{'alpha':>9}{'hit':>5}"]
    for r in sorted(rows, key=lambda r: (r["arm"] or "", r["trial"] or 0,
                                         r["ticker"] or "", r["date"])):
        hit = "" if r["hit"] is None else ("yes" if r["hit"] else "no")
        lines.append(f"{r['arm']:<11}{str(r['trial']):<4}{r['ticker']:<7}"
                     f"{r['date']:<12}{r['rating']:<12}"
                     f"{_fmt_pct(r['raw_return']):>8}{_fmt_pct(r['alpha']):>9}{hit:>5}")
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--arm", action="append", default=None,
                        help="limit to these arms; default is every run")
    parser.add_argument("--out", default=None, help="write CSV here")
    args = parser.parse_args()

    rows = read_cells(arms=args.arm)
    if args.out:
        path = Path(args.out)
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("w", newline="", encoding="utf-8") as fh:
            writer = csv.DictWriter(fh, fieldnames=list(rows[0].keys()))
            writer.writeheader()
            writer.writerows(rows)
        print(f"wrote {len(rows)} rows -> {path}")
    print(render(rows))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
