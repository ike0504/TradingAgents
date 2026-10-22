"""Experiment configuration for the FTEC5660 reproducibility study.

Everything that varies between arms lives here, so the difference between the
baseline and the modified run is one key, and nothing else.

The paper (arXiv 2412.20138, Section 5.1) evaluates on 2024-01-01 .. 2024-03-29
for AAPL / GOOGL / AMZN. We keep the window and the ticker set; what cannot be
kept is the backbone LLM (gpt-4o-mini / o1-preview -> DeepSeek), which the
assignment explicitly permits as a documented controlled variable.
"""

from __future__ import annotations

import os

# ---------------------------------------------------------------------------
# The paper's setting
# ---------------------------------------------------------------------------
WINDOW_START = "2024-01-01"
WINDOW_END = "2024-03-29"
TICKERS = ["AAPL", "GOOGL", "AMZN"]

# Grid step in calendar days. 1 = every calendar day (the paper's daily cadence);
# larger values thin the grid to fit a compute budget. At ~5.5 min per cell on
# DeepSeek, 14 gives 7 decision dates per ticker, which is what a laptop can
# run three trials of in both arms.
EVERY_N_DAYS = int(os.getenv("REPRO_EVERY_N_DAYS", "14"))

# Analysts kept. The paper uses four (fundamentals, sentiment, news, technical).
SELECTED_ANALYSTS = ["market", "social", "news", "fundamentals"]

# ---------------------------------------------------------------------------
# Backbone LLM (the controlled variable)
# ---------------------------------------------------------------------------
# DeepSeek is a first-class provider in this repo (cli/prompts.py) and was not
# the model the paper used, so every number below is labelled "not directly
# comparable to the paper".
LLM_PROVIDER = "deepseek"
QUICK_THINK_LLM = os.getenv("REPRO_QUICK_LLM", "deepseek-flash")
DEEP_THINK_LLM = os.getenv("REPRO_DEEP_LLM", "deepseek-flash")

# Sampling knobs, recorded because the assignment asks for them. None leaves
# each provider at its own default; we set temperature explicitly so runs are
# as repeatable as an LLM gets, and bound output tokens because DeepSeek's
# thinking mode can otherwise emit without bound (see default_config.py #1204).
TEMPERATURE = float(os.getenv("REPRO_TEMPERATURE", "0.0"))
MAX_TOKENS = int(os.getenv("REPRO_MAX_TOKENS", "8192"))

# ---------------------------------------------------------------------------
# The modification under test
# ---------------------------------------------------------------------------
# ARM baseline   : max_debate_rounds = 1 -> Bull Researcher then Bear Researcher
#                  (the released default, and the paper's design)
# ARM no_debate  : max_debate_rounds = 0 -> the graph still starts at the Bull
#                  Researcher, but the router exits immediately, so the Bear
#                  never speaks and the Bull is never rebutted.
# This is the only key that differs between arms.
ARMS = {
    "baseline": {"max_debate_rounds": 1},
    "no_debate": {"max_debate_rounds": 0},
}

# ---------------------------------------------------------------------------
# Paths and trials
# ---------------------------------------------------------------------------
_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RESULTS_DIR = os.getenv("REPRO_RESULTS_DIR",
                        os.path.join(os.path.dirname(_REPO_ROOT), "results"))
N_TRIALS = int(os.getenv("REPRO_N_TRIALS", "3"))


def build_config(arm: str) -> dict:
    """A full TradingAgents config for one arm.

    Imported lazily so importing this module does not require the package's
    dependencies to be resolved.
    """
    from tradingagents.default_config import DEFAULT_CONFIG

    if arm not in ARMS:
        raise ValueError(f"unknown arm {arm!r}; expected one of {sorted(ARMS)}")

    config = DEFAULT_CONFIG.copy()
    config.update({
        "results_dir": RESULTS_DIR,
        "llm_provider": LLM_PROVIDER,
        "quick_think_llm": QUICK_THINK_LLM,
        "deep_think_llm": DEEP_THINK_LLM,
        "temperature": TEMPERATURE,
        "max_tokens": MAX_TOKENS,
        "max_risk_discuss_rounds": 1,   # held constant: only the debate varies
        "checkpoint_enabled": False,
        "output_language": "English",
    })
    config.update(ARMS[arm])
    return config
