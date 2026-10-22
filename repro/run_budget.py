"""Run the paired experiment one cell at a time, only while the API is cheap.

DeepSeek charges double during peak hours (Beijing 09-12 and 14-18 on
weekdays), and the first attempt at this sweep burned its whole balance partly
because nobody was watching the clock. This driver works through a fixed list of
(arm, trial, ticker, date) jobs, sleeping through peak windows instead of paying
for them, so the grid costs half what it would during the working day.

It also honours the balance: before each job it reads the balance and stops
rather than starting a cell it cannot finish.

Usage
-----
    python -m repro.run_budget                 # everything still missing
    python -m repro.run_budget --dry-run       # print the plan and its estimate
    python -m repro.run_budget --min-balance 3 # keep a larger buffer
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

from repro import balance as bal
from repro import config as cfg

# The paper's headline ticker gets the full grid; the other two get one date so
# the comparison still speaks to all three columns of Table 1 without costing
# three times as much.
PRIMARY_TICKER = "AAPL"
PRIMARY_DATES = ["2024-01-01", "2024-01-29", "2024-02-26", "2024-03-11", "2024-03-25"]
SECONDARY = {"GOOGL": ["2024-01-29"], "AMZN": ["2024-01-29"]}
TRIALS = [1, 2, 3]

# Measured on 2024-01-01 with REPRO_TRACK_USAGE=1; see REPRODUCIBILITY.md.
COST_CNY_PER_CELL = {"baseline": 0.455, "no_debate": 0.345}


def plan_jobs() -> list[tuple[str, int, str, str]]:
    jobs = []
    for trial in TRIALS:
        for date in PRIMARY_DATES:
            for arm in sorted(cfg.ARMS):
                jobs.append((arm, trial, PRIMARY_TICKER, date))
    for ticker, dates in SECONDARY.items():
        for trial in TRIALS[:2]:
            for date in dates:
                for arm in sorted(cfg.ARMS):
                    jobs.append((arm, trial, ticker, date))
    return jobs


def already_done(arm: str, trial: int, ticker: str, date: str) -> bool:
    """True if this exact cell already scored cleanly, so a restart never re-pays."""
    sweeps = Path(cfg.RESULTS_DIR) / "sweeps"
    if not sweeps.is_dir():
        return False
    slug = date.replace("-", "")
    for path in sweeps.glob(f"{arm}_t{trial}_{ticker}_*{slug}.json"):
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            continue
        summary = data.get("summary") or {}
        if data.get("failures"):
            continue
        if data.get("dates_requested") == 1 and summary.get("resolved", 0) >= 1:
            return True
    return False


def wait_for_off_peak(log=print) -> None:
    """Block while DeepSeek's peak surcharge is in force."""
    warned = False
    while True:
        now = datetime.now(timezone.utc)
        if not bal.is_peak(now):
            return
        due = bal.next_off_peak(now)
        nap = min(max((due - now).total_seconds() + 30, 30), 600)
        if not warned:
            log(f"[budget] peak rates until {due:%H:%M} Beijing; sleeping", flush=True)
            warned = True
        time.sleep(nap)


def current_balance() -> float | None:
    info = bal.get_balance()
    rows = info.get("balance_infos") or []
    if not rows:
        return None
    try:
        return float(rows[0]["total_balance"])
    except (KeyError, TypeError, ValueError):
        return None


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--min-balance", type=float, default=2.0,
                        help="stop rather than start a cell below this balance")
    args = parser.parse_args()

    jobs = [j for j in plan_jobs() if not already_done(*j)]
    estimate = sum(COST_CNY_PER_CELL.get(arm, 0.5) for arm, *_ in jobs)
    print(f"[budget] {len(jobs)} cells left to run, ~{estimate:.2f} CNY "
          f"at off-peak rates", flush=True)
    if args.dry_run:
        for job in jobs:
            print("  ", job)
        return 0

    start = current_balance()
    print(f"[budget] balance {start:.2f} CNY",
          flush=True) if start is not None else None

    for index, (arm, trial, ticker, date) in enumerate(jobs, 1):
        wait_for_off_peak()
        left = current_balance()
        if left is not None and left < args.min_balance:
            print(f"[budget] balance {left:.2f} below floor "
                  f"{args.min_balance:.2f}; stopping with "
                  f"{len(jobs) - index + 1} cells unrun", flush=True)
            return 1
        print(f"[budget] ({index}/{len(jobs)}) {arm} t{trial} {ticker} {date}",
              flush=True)
        cmd = [sys.executable, "-m", "repro.run_sweep", "--arm", arm,
               "--trial", str(trial), "--tickers", ticker, "--dates", date,
               "--tag", ticker]
        rc = subprocess.run(cmd).returncode
        if rc != 0:
            print(f"[budget] cell failed rc={rc}; continuing", flush=True)
    print("[budget] all planned cells finished", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
