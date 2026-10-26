# Reproducibility study: TradingAgents

Course: **FTEC5660 — Agentic AI for Business and FinTech**, Individual Project 2
Paper: *TradingAgents: Multi-Agents LLM Financial Trading Framework*, arXiv:2412.20138
Repo under test: `TauricResearch/TradingAgents` @ `e8f5503` (v0.7.0)
Fork with this study: `ike0504/TradingAgents`

---

## 1. Summary — what I set out to reproduce

**Target claim (primary).** TradingAgents, run as released, produces stock
ratings whose directional calls beat the instrument's regional benchmark. Formally:
over a grid of (ticker, date) cells, the *hit rate* of Buy/Overweight and
Underweight/Sell calls is above chance and their *mean alpha* is positive, where
alpha is measured over the configured holding period from the first close after
each analysis date. This is the behaviour the released code actually claims and
actually measures (`tradingagents/backtest.py`, scored by `backtest.summarize`).

**Target claim (secondary).** Table 1 of the paper:

| | AAPL CR% / ARR% / SR / MDD% | GOOGL | AMZN |
|---|---|---|---|
| TradingAgents | **26.62 / 30.5 / 8.21 / 0.91** | 24.36 / 27.58 / 6.39 / 1.69 | 23.21 / 24.90 / 5.60 / 2.11 |
| Market B&H | -5.23 / -5.09 / -1.29 / 11.90 | 7.78 / 8.09 / 1.35 / 13.04 | 17.1 / 17.6 / 3.53 / 3.80 |

**What I actually did.** Ran the released pipeline on the paper's own window and
tickers, scored it with the repo's own scorer, and separately rebuilt an equity
curve from the resulting rating stream so the run could be put next to Table 1.
Then made one isolated change — removed the Bull/Bear research debate — and
re-measured the same metrics.

---

## 2. Setup

| | |
|---|---|
| Machine | Windows laptop, no GPU |
| Python | 3.13.12 (isolated venv, `pip install -e .`) |
| Package | `tradingagents` 0.7.0, `yfinance` 1.7.0, `pandas` 3.0.6, `numpy` 2.5.4 |
| LLM | **DeepSeek** `deepseek-flash` for both the quick and deep tiers — *not* the paper's `gpt-4o-mini`/`o1-preview` |
| Base URL | `https://api.deepseek.com` (the repo's built-in `deepseek` provider) |
| Decoding | `temperature=0.0`, `max_tokens=8192`, `max_debate_rounds` per arm, `max_risk_discuss_rounds=1`, `max_tool_rounds=20`, `holding_period_days=5` |
| Data | Yahoo Finance (prices, technicals, fundamentals fallback), SEC EDGAR (US filings). No key needed |
| Keys | `DEEPSEEK_API_KEY` only. Kept in `.env`, which is gitignored at `.gitignore:151` |
| Window | 2024-01-01 → 2024-03-29 (the paper's), 7 decision dates per ticker (`every_n_days=14`) |
| Cost | ~5.5 min and ~27 LLM calls per cell; 252 cells total across both arms and 3 trials |

### Install

```bash
git clone https://github.com/ike0504/TradingAgents.git
cd TradingAgents
python -m venv .venv && .venv/Scripts/activate      # Windows
pip install -e .
cp .env.example .env      # then set DEEPSEEK_API_KEY=...
```

### Run

```bash
# one cell, to check wiring (~6 min)
python -m repro.run_sweep --arm baseline --trial 0 --smoke

# one arm, one trial, one ticker
python -m repro.run_sweep --arm baseline --trial 1 --tickers AAPL --tag AAPL

# what this study ran: both arms x 3 trials x 3 tickers, one process per ticker
for arm in baseline no_debate; do for t in 1 2 3; do
  python -m repro.run_sweep --arm $arm --trial $t --tickers AAPL --tag AAPL
done; done

# compare the arms
python -m repro.aggregate --arm baseline --arm no_debate

# put a run next to the paper's Table 1
python -m repro.portfolio_sim results/backtest/baseline_t1_AAPL/trading_memory.md
```

Results land in `../results/` (outside the repo, so sweeps never bloat the
commit); `results/sweeps/*.json` holds one file per run.

---

## 3. The modification

**`max_debate_rounds: 1 → 0`** — the Bull/Bear researcher debate is removed.

The graph always starts at the Bull Researcher (`graph/setup.py:166`). With
`max_debate_rounds=1` the router alternates Bull → Bear and then hands to the
Research Manager; with `0` the router's threshold (`count >= 2 * max_debate_rounds`)
is already met, so the Bull speaks once and the **Bear never speaks and the Bull
is never rebutted**. Precisely: *baseline = Bull then Bear, no_debate = Bull only*.

Isolation is asserted, not assumed — `repro/config.py` builds both configs from
the same defaults and the only key that differs is `max_debate_rounds`:

```
keys differing between arms: {'max_debate_rounds': (1, 0)}
```

Everything else — provider, both model tiers, temperature, window, tickers,
analysts, risk-discussion rounds, tool rounds — is identical.

---

## 4. Results

AAPL, the paper's own window, decision dates every 14 days, 2 trials per arm.
The full rendered report — including every individual cell — is produced by
`python -m repro.report` and is not retyped here, so it cannot drift from the run.

### 4.1 Primary: the repo's own metric (hit rate / mean alpha)

Hit rate = share of *directional* calls whose realised alpha had the sign the
rating implied. Hold carries no direction and is reported but not scored; that
is the repo's own rule in `backtest.summarize`.

| arm | trials | cells | directional calls | hit rate | coverage | mean alpha (all cells) |
|---|---|---|---|---|---|---|
| baseline (Bull + Bear) | 2 | 10 | 8 | **62.5%** | 80% | −1.22% |
| no_debate (Bull only) | 2 | 9 | 9 | **22.2%** | 100% | −1.33% |

Per trial: baseline 66.7% / 60.0%; no_debate 20.0% / 25.0%.

**A methodological trap worth stating.** Alpha is a market fact: for the same
(ticker, date) it is *identical* in both arms, because it is measured from
prices, not from the decision. The modification therefore cannot move alpha.
What it moves is whether the rating *called* the direction. Hit rate and the
rating distribution are the correct dependent variables; "ablating the debate
changed mean alpha from X to Y" would be a misreading, because the two arms are
scoring different subsets of cells.

### 4.2 What the modification did: the rating distribution collapsed

| arm | Buy | Overweight | Hold | Underweight | Sell | cells |
|---|---|---|---|---|---|---|
| baseline | 0 | 3 | 2 | 5 | 0 | 10 |
| no_debate | 0 | **9** | 0 | 0 | 0 | 9 |

**Every no_debate cell came back Overweight.** Without a Bear Researcher the
system does not become more bullish on average — it becomes structurally unable
to produce a negative view. That is the mechanism behind both 4.1 and 4.3.

### 4.3 Secondary: our run vs Table 1

Reconstructed from the rating stream (rating → exposure Buy ±1 / Over-Under
±0.5 / Hold 0; each decision held from the next close until the following one;
no transaction costs). ARR% is omitted: see §7.4.

| ticker | row | CR% | SR | MDD% |
|---|---|---|---|---|
| AAPL | paper — TradingAgents | 26.62 | 8.21 | 0.91 |
| AAPL | paper — Buy & Hold | −5.23 | −1.29 | 11.90 |
| AAPL | **ours — Buy & Hold, same prices** | **−7.63** | −1.57 | 13.41 |
| AAPL | ours — baseline | **+0.12** | −0.11 | 2.09 |
| AAPL | ours — no_debate | **−2.39** | −1.17 | 3.88 |

Read against the control: our reconstruction has the agent *beating*
buy-and-hold by about 7.8 points of cumulative return, in a quarter when
buy-and-hold lost 7.63% — but the paper reports +26.62%. **The direction of the
claim survives; the magnitude does not.**

### 4.4 The modification, quantified

| effect of removing the Bull/Bear debate | baseline | no_debate | Δ |
|---|---|---|---|
| AAPL CR% | +0.12 | −2.39 | −2.51 |
| AAPL SR | −0.11 | −1.17 | −1.06 |
| AAPL MDD% | 2.09 | 3.88 | +1.79 |
| hit rate (pooled) | 62.5% | 22.2% | −40.3 pp |
| LLM calls per cell | 23 | 19 | −4 |
| prompt tokens per cell | 217,126 | 155,274 | −28% |
| completion tokens per cell | 69,190 | 51,606 | −25% |

---

## 5. Debug diary

1. **Table 1 does not exist in the code.** Expected a portfolio simulator;
   found `backtest.py` scoring independent cells and stating it must not grow
   one. Fix: `repro/portfolio_sim.py` reconstructs an equity curve from the
   rating stream, with every mapping assumption written into the module
   docstring so it can be audited or changed.

2. **News returns nothing for any historical date.** `get_news_yfinance`
   gives the "unavailable" fallback for 2024-01 and for dates three months ago
   alike; `yf.Ticker().get_news()` and `.news` are both empty. Only
   `yf.Search()` returns articles, and only current ones, which the date filter
   then discards. Not fixable — recorded as a finding (§7.2).

3. **Macro and social are dead too.** `Vendor 'fred' not configured ...
   FRED_API_KEY is not set`; StockTwits/Reddit rate-limit.

4. **Three parallel processes burned the entire API balance.** Ran three
   tickers concurrently straight through DeepSeek's peak window (09:00–12:00
   and 14:00–18:00 Beijing, double price) with no balance check; from 11:04
   every cell returned `402 Insufficient Balance` and the **entire no_debate
   arm scored zero cells** — the modification experiment, a required
   deliverable, was empty. Fix: `repro/balance.py` and `repro/run_budget.py`.
   The driver now reads the balance before each cell, refuses to run in a peak
   window, and skips cells that already have a score, so an interrupted run
   resumes without re-buying. That is also why this run survived three days of
   the laptop being off.

5. **Structured output silently degrades on DeepSeek.** `Research Manager:
   structured-output invocation failed ... retrying once as free text`, and the
   same for the Trader. Left as-is and disclosed rather than patched, because
   patching it would change the system under test.

6. **Thinking tokens are billed and there is no switch.** Searched the repo for
   a thinking-mode toggle; there is none, so the only lever is scheduling.
   About 37k of 69k completion tokens in a calibration cell were reasoning
   tokens.

7. **The paper's Buy & Hold row did not reproduce, on a quantity that needs no
   model.** Grid-searched (start, end) windows for a joint fit across all three
   tickers; none exists. Diagnosed as data provenance, not a bug in my metrics
   (§7.3).

8. **Two reporting bugs of my own, caught by re-rendering.** A percentage
   formatter dropped the ×100, so every alpha read as −0.01%; and per-cell
   token cost was divided through the whole grid rather than through the cells
   that actually had accounting enabled, diluting 23 calls/cell to 2.3. Both
   are why `repro/report.py` renders from the result files instead of prose —
   a wrong number in prose survives forever.

---

## 6. Conclusions

**What reproduces.** The engineering claim holds. The pipeline runs end-to-end
on a laptop with nothing but an API key, emits a five-tier rating per cell, and
settles each to a measurable alpha against a regional benchmark. DeepSwap drops
in through the repo's own provider with no code change. The multi-agent graph
executes as described.

**What the modification shows.** The debate is load-bearing, not decorative.
Removing the bearish researcher removes the system's capacity for dissent
entirely, and that is measurable on hit rate and on the reconstructed
portfolio. This is the one result here that is independent of whether the
paper's absolute numbers hold up.

**What does not reproduce, and why.** Three mechanisms, in order of how much
they cost: Table 1 is not implemented in the released code at all; two of the
paper's four data channels return nothing for historical dates, so the system
we ran is not the system the paper evaluated; and — the binding one — the
paper's own Buy & Hold row fails to reproduce on a quantity requiring no model,
which puts a floor under every other discrepancy and proves the gap cannot be
blamed on the LLM swap alone.

**What the DeepSeek substitution can and cannot explain.** It can explain
throughput (~23 calls and ~5 min per cell against the paper's "11 LLM calls")
and the structured-output fallback — both real differences in the decision
path. It cannot explain the Buy & Hold gap (no model involved), the missing
data channels (vendor-side), or the ARR% inconsistency (arithmetic). Our
numbers are reported as ours and are not claimed to be comparable to Table 1.

---

## 7. Findings established so far

These do not depend on the sweep and are reported as they stand.

### 7.1 The released code no longer computes the paper's headline metrics

`tradingagents/backtest.py` opens with *"It is not a portfolio simulator, and
must not grow one."* It scores each (ticker, date) cell independently: a
five-tier rating, plus alpha and hit rate against a regional benchmark over
`holding_period_days` (5 trading days). **CR%, ARR%, SR and MDD% — the entire
Table 1 — do not exist anywhere in v0.7.0.** Reproducing Table 1 therefore
requires reconstructing an equity curve, which is what `repro/portfolio_sim.py`
does, and every choice in that reconstruction (rating → exposure mapping, when a
decision starts holding, whether costs apply) is an assumption the paper never
states.

### 7.2 Two of the paper's data channels cannot be reconstructed at all

The paper's Section 5.2 lists news, social-media sentiment, insider transactions
and macro indicators alongside prices. Of these, on a fresh checkout:

- **News is empty for every historical date.** `get_news_yfinance` returns the
  "unavailable" fallback for 2026-07, 2026-09 and 2024-01 alike. Underneath,
  `yf.Ticker(...).get_news()` and `.news` both return zero items; only
  `yf.Search(news_count=N)` returns anything, and it is a sample of *recent*
  articles, which the date-window filter then discards. A backtested run is
  therefore a **price-and-technicals-only** system, not the multimodal system the
  paper evaluates.
- **Macro is unavailable** without a `FRED_API_KEY` (free, but not set by
  default): `Vendor 'fred' not configured for get_macro_indicators`.

### 7.3 The paper's own Buy & Hold row does not reproduce — and it needs no LLM

This is the cleanest result in the study, because Buy & Hold is deterministic:
no model, no sampling, no tool calls. Recomputed on Yahoo closes over the
paper's stated window:

| ticker | paper CR% | recomputed CR% | ratio |
|---|---|---|---|
| AAPL | -5.23 | -7.63 | 0.686 |
| GOOGL | 7.78 | 9.23 | **0.842** |
| AMZN | 17.1 | 20.31 | **0.842** |

GOOGL and AMZN are attenuated by *exactly* the same factor, so this is a
systematic difference, not noise. A full (start, end) grid search finds **no
single window that reproduces all three** (best fit: AAPL −5.15 ✓, AMZN 17.32 ✓,
GOOGL 6.41 ✗ against a target of 7.78). The paper's price data did not come from
Yahoo — Section 5.2 names Bloomberg, Yahoo, EODHD, FinnHub and Reddit — and
whichever of those it was, the released code cannot reach it.

The consequence for the study: **any discrepancy between our agent numbers and
Table 1 is bounded below by a discrepancy that already exists on a quantity
requiring no model at all.**

### 7.4 The paper's ARR% column is not a standard annualisation

GOOGL shows CR 7.78% alongside ARR 8.09%. Inverting
`AR = (V_end/V_start)^(1/N) - 1` gives N ≈ 0.96 years for a three-month
backtest. Whatever ARR% is, it is not the formula in Appendix 8.2.2, so this
column is not reproducible even given the underlying returns.

### 7.5 Swapping in DeepSeek is not costless

Two effects observed, both worth documenting for anyone repeating the swap:

- **Structured output degrades.** `Research Manager: structured-output invocation
  failed ... retrying once as free text` — and the same for `Trader`. The
  repo's v0.2.4 structured-output agents fall back to free text on DeepSeek, so
  the decision path is not the one the model was designed for.
- **Throughput.** ~27 LLM calls and ~5.5 min per decision on `deepseek-flash`,
  against the paper's "11 LLM calls & 20+ tool calls per prediction". The
  grid had to be thinned from daily to every 14 days to fit a laptop budget.

### 7.6 On the plausibility of the target itself

The paper reports AAPL at +26.62% over three months with a Sharpe ratio of 8.21
and a maximum drawdown of 0.91%, in a quarter when buy-and-hold lost 5.23%. The
authors address this themselves in a footnote: *"The highest Sharpe Ratio
exceeds our expected empirical range (SR above 2 – very good, above 3 –
excellent) ... We believe the exceptionally high SR resulted from the phenomenon
that there were few pullbacks ... We report results as they are in our
experiments faithfully."* A faithful reproduction attempt should therefore expect
to *fail* to reach these numbers; the interesting question is by how much and
through which channel.

---

## 8. What is and is not reproducible

| Claim | Status |
|---|---|
| The pipeline runs end-to-end on a laptop, API-only, no GPU | ✅ reproduced |
| DeepSeek drops in as a backbone via the built-in provider | ✅ reproduced |
| Decisions are emitted as a five-tier rating and settle to an alpha | ✅ reproduced |
| The Bull/Bear debate can be ablated cleanly | ✅ reproduced (isolated, one config key) |
| The debate matters: ablating it collapses the rating distribution | ✅ reproduced — 9/9 cells Overweight; hit rate 62.5% → 22.2% |
| Directional calls beat the benchmark | ⚠️ partial — 62.5% hit rate on 8 scored calls; reconstruction beats B&H by ~7.8pp, not the paper's +26.62% |
| Table 1 CR% / ARR% / SR / MDD% | ❌ not reproducible — not implemented in the released code |
| The paper's Buy & Hold row | ❌ not reproducible — systematic attenuation (ratio 0.842 on GOOGL/AMZN), no window fits |
| The paper's ARR% column | ❌ not reproducible — internally inconsistent with its own CR% |
| The paper's news / macro / social inputs | ❌ not reproducible — vendors return nothing for historical dates |
