"""Run one arm of the TradingAgents backtest sweep and score it.

Usage
-----
    python -m repro.run_sweep --arm baseline --trial 1
    python -m repro.run_sweep --arm no_debate --trial 1 --tickers AAPL
    python -m repro.run_sweep --arm baseline --trial 1 --smoke

Each (arm, trial) is its own run id, so ``run_backtest`` re-runs every cell
rather than skipping ones already in that run's log -- which is what makes the
trials independent samples instead of one sample replayed.
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import sys
import time
from pathlib import Path

from repro import config as cfg


def _summary_to_dict(summary) -> dict:
    return {
        "resolved": summary.resolved,
        "pending": summary.pending,
        "unscored": summary.unscored,
        "holding": summary.holding,
        "by_rating": {
            rating: {"n": s.count, "hit_rate": s.hit_rate, "mean_alpha": s.mean_alpha}
            for rating, s in summary.by_rating.items()
        },
    }


def _install_usage_tracker() -> dict:
    """Count tokens actually billed, by wrapping the LLM wrapper itself.

    Every model call in this repo goes through ``langchain_openai.ChatOpenAI``
    (``tradingagents.llm_clients.openai_client`` subclasses it), so patching
    ``_generate`` catches all of them -- including the structured-output retry
    path -- without touching the repo. Totals are read from the provider's own
    ``usage`` block rather than estimated from string length.
    """
    from langchain_openai import ChatOpenAI

    if getattr(ChatOpenAI, "_repro_tracker", None) is not None:
        return ChatOpenAI._repro_tracker

    state = {"calls": 0, "prompt_tokens": 0, "completion_tokens": 0,
             "cached_tokens": 0, "reasoning_tokens": 0}
    original = ChatOpenAI._generate

    def _add(key, value):
        if isinstance(value, (int, float)):
            state[key] = state.get(key, 0) + int(value)

    def wrapped(self, messages, stop=None, run_manager=None, **kwargs):
        out = original(self, messages, stop=stop, run_manager=run_manager, **kwargs)
        try:
            state["calls"] += 1
            llm_output = getattr(out, "llm_output", None) or {}
            usage = llm_output.get("token_usage") or llm_output.get("usage") or {}
            if not usage:
                for gens in getattr(out, "generations", None) or []:
                    for gen in gens:
                        meta = getattr(getattr(gen, "message", None),
                                       "response_metadata", None) or {}
                        usage = meta.get("usage") or meta.get("token_usage") or {}
                        if usage:
                            break
                    if usage:
                        break
            _add("prompt_tokens", usage.get("prompt_tokens"))
            _add("completion_tokens", usage.get("completion_tokens"))
            _add("cached_tokens",
                 (usage.get("prompt_tokens_details") or {}).get("cached_tokens"))
            _add("reasoning_tokens",
                 (usage.get("completion_tokens_details") or {}).get("reasoning_tokens"))
        except Exception:  # never let accounting break an experiment
            pass
        return out

    ChatOpenAI._generate = wrapped
    ChatOpenAI._repro_tracker = state
    return state


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--arm", choices=sorted(cfg.ARMS), required=True)
    parser.add_argument("--trial", type=int, default=1)
    parser.add_argument("--tickers", nargs="*", default=cfg.TICKERS)
    parser.add_argument("--start", default=cfg.WINDOW_START)
    parser.add_argument("--end", default=cfg.WINDOW_END)
    parser.add_argument("--every", type=int, default=cfg.EVERY_N_DAYS)
    parser.add_argument("--smoke", action="store_true",
                        help="run a single cell, to check wiring before a full sweep")
    parser.add_argument("--tag", default=None,
                        help="extra run_id segment, so one ticker can be swept in its "
                             "own process without two processes writing the same log")
    parser.add_argument("--dates", default=None,
                        help="explicit comma-separated decision dates, instead of the "
                             "every-N-days grid. Lets a small budget buy exactly the "
                             "cells an arm still needs.")
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    # The repo reads provider keys from the environment; .env is loaded by the
    # package when present, so no key is ever passed through code.
    from dotenv import load_dotenv
    load_dotenv(Path(cfg._REPO_ROOT) / ".env")

    from tradingagents.backtest import iter_grid, run_backtest, summarize

    config = cfg.build_config(args.arm)
    os.makedirs(cfg.RESULTS_DIR, exist_ok=True)
    # Sweeps are run one process per ticker, so each gets its own data cache
    # rather than several processes racing on the same cache files.
    if args.tag:
        config["data_cache_dir"] = os.path.join(cfg.RESULTS_DIR, "cache", args.tag)
        os.makedirs(config["data_cache_dir"], exist_ok=True)

    dates = ([d.strip() for d in args.dates.split(",") if d.strip()]
             if args.dates
             else iter_grid(args.start, args.end, every_n_days=args.every))
    if args.smoke:
        dates = dates[:1]
        args.tickers = args.tickers[:1]

    # Token accounting is off by default because patching the LLM wrapper is
    # intrusive; set REPRO_TRACK_USAGE=1 to price a cell before committing to a
    # grid, which is how the grid was sized against the API balance.
    tracker = _install_usage_tracker() if os.getenv("REPRO_TRACK_USAGE") == "1" else None

    run_id = f"{args.arm}_t{args.trial}" + (f"_{args.tag}" if args.tag else "") \
             + ("_smoke" if args.smoke else "")
    print(f"[sweep] arm={args.arm} trial={args.trial} tickers={args.tickers} "
          f"dates={len(dates)} ({dates[0]} .. {dates[-1]}) run_id={run_id}")

    started = time.time()
    result = run_backtest(
        tickers=args.tickers,
        dates=dates,
        config=config,
        selected_analysts=cfg.SELECTED_ANALYSTS,
        run_id=run_id,
        progress=lambda done, total, tk, dt: print(f"  cell {done}/{total} {tk} {dt}", flush=True),
    )
    elapsed = time.time() - started

    summary = summarize(result)
    payload = {
        "arm": args.arm,
        "trial": args.trial,
        "tag": args.tag,
        "run_id": run_id,
        "tickers": args.tickers,
        "window": {"start": args.start, "end": args.end, "every_n_days": args.every},
        "dates_requested": len(dates),
        "cells_run": result.cells_run,
        "skipped": result.skipped,
        "failures": result.failures,
        "settlement_failures": result.settlement_failures,
        "elapsed_sec": round(elapsed, 1),
        "llm": {
            "provider": cfg.LLM_PROVIDER,
            "quick": cfg.QUICK_THINK_LLM,
            "deep": cfg.DEEP_THINK_LLM,
            "temperature": cfg.TEMPERATURE,
            "max_tokens": cfg.MAX_TOKENS,
        },
        "modification": cfg.ARMS[args.arm],
        "log_path": str(result.log_path),
        "summary": _summary_to_dict(summary),
    }
    if tracker:
        payload["token_usage"] = dict(tracker)

    out_dir = Path(cfg.RESULTS_DIR) / "sweeps"
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / f"{run_id}.json"
    out_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")

    print(f"\n[done] {elapsed/60:.1f} min, {result.cells_run} cells, "
          f"{len(result.failures)} failures -> {out_path}")
    print(summary.render())
    return 0


if __name__ == "__main__":
    sys.exit(main())
