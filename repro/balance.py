"""Check the DeepSeek balance before spending it, and price a grid.

The sweep died halfway through with ``402 Insufficient Balance`` while three
processes ran in parallel, so the balance is now checked explicitly rather than
discovered from failures. ``GET /user/balance`` is undocumented but free: it
carries no tokens, so polling it costs nothing.

Usage
-----
    python -m repro.balance              # what is left
    python -m repro.balance --cells 16   # what 16 cells would cost
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.error
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path

BALANCE_URL = "https://api.deepseek.com/user/balance"

# api-docs.deepseek.com/quick_start/pricing, deepseek-flash (V4.1 Flash), USD
# per 1M tokens. Peak is 01:00-04:00 and 06:00-10:00 UTC on weekdays, i.e.
# 09:00-12:00 and 14:00-18:00 Beijing; everything else is half price.
PRICE = {
    "peak": {"in_cache_hit": 0.006, "in_cache_miss": 0.30, "out": 1.20},
    "off_peak": {"in_cache_hit": 0.003, "in_cache_miss": 0.15, "out": 0.60},
}
USD_CNY = float(os.getenv("REPRO_USD_CNY", "7.10"))


def get_balance(api_key: str | None = None) -> dict:
    if api_key is None:
        from dotenv import load_dotenv
        load_dotenv(Path(__file__).resolve().parents[1] / ".env")
        api_key = os.environ.get("DEEPSEEK_API_KEY", "")
    if not api_key:
        return {"error": "DEEPSEEK_API_KEY not set (expected in .env)"}
    req = urllib.request.Request(BALANCE_URL, headers={
        "Authorization": f"Bearer {api_key}",
        "Accept": "application/json",
    })
    try:
        with urllib.request.urlopen(req, timeout=20) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        return {"error": f"HTTP {exc.code}: {exc.read()[:300]!r}"}
    except Exception as exc:  # network, DNS, timeout
        return {"error": f"{type(exc).__name__}: {exc}"}


def is_peak(now: datetime | None = None) -> bool:
    """True inside DeepSeek's peak window (UTC 01-04 and 06-10, weekdays)."""
    now = now or datetime.now(timezone.utc)
    if now.weekday() >= 5:
        return False
    hour = now.hour
    return (1 <= hour < 4) or (6 <= hour < 10)


def next_off_peak(now: datetime | None = None) -> datetime:
    """The next moment the off-peak rate applies, in Beijing time."""
    now = now or datetime.now(timezone.utc)
    bj = now.astimezone(timezone(timedelta(hours=8)))
    for candidate in (bj.replace(hour=12, minute=0, second=0, microsecond=0),
                      bj.replace(hour=18, minute=0, second=0, microsecond=0)):
        if candidate > bj:
            return candidate
    return (bj + timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)


def cost_cny(usage: dict, peak: bool, usd_cny: float = USD_CNY) -> float:
    """Price one run's token_usage block, in CNY."""
    rate = PRICE["peak" if peak else "off_peak"]
    cached = usage.get("cached_tokens") or 0
    prompt = usage.get("prompt_tokens") or 0
    miss = max(prompt - cached, 0)
    completion = usage.get("completion_tokens") or 0
    usd = (cached * rate["in_cache_hit"] + miss * rate["in_cache_miss"]
           + completion * rate["out"]) / 1_000_000
    return usd * usd_cny


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--per-cell", default=None,
                        help="path to a sweep JSON whose token_usage is one cell")
    parser.add_argument("--cells", type=int, default=None,
                        help="project the cost of this many cells")
    args = parser.parse_args()

    info = get_balance()
    if "error" in info:
        print(f"balance: {info['error']}")
    else:
        for b in info.get("balance_infos", []):
            print(f"balance: {b['currency']} {b['total_balance']} "
                  f"(granted {b['granted_balance']}, topped up {b['topped_up_balance']})")
        print(f"available: {info.get('is_available')}")

    now = datetime.now(timezone.utc)
    bj = now.astimezone(timezone(timedelta(hours=8)))
    print(f"now: {bj:%Y-%m-%d %H:%M} Beijing -> "
          f"{'PEAK (2x)' if is_peak(now) else 'off-peak (1x)'}")
    if is_peak(now):
        print(f"next off-peak: {next_off_peak(now):%Y-%m-%d %H:%M} Beijing")

    if args.per_cell:
        data = json.loads(Path(args.per_cell).read_text(encoding="utf-8"))
        usage = data.get("token_usage")
        if not usage:
            print(f"no token_usage in {args.per_cell}; rerun that sweep with "
                  f"REPRO_TRACK_USAGE=1")
            return 1
        cells = args.cells or 1
        print(f"per cell: {usage}")
        for label, peak in (("off-peak", False), ("peak", True)):
            one = cost_cny(usage, peak)
            print(f"  {label:8s} {one:7.3f} CNY/cell   x{cells} = {one * cells:8.2f} CNY")
    return 0


if __name__ == "__main__":
    sys.exit(main())
