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

The paper's own window, decision dates every 14 days, **3 trials per arm, 38
cells total, 0 failures**. AAPL is the only ticker carried through all three
trials; GOOGL and AMZN were run for two each, which is enough to put "ours"
rows next to all three columns of Table 1 but not enough to test stability.

The full rendered report is produced by `python -m repro.report` and is not
retyped here, so it cannot drift from the run.

### 4.1 Primary: the repo's own metric (hit rate / mean alpha)

Hit rate = share of *directional* calls whose realised alpha had the sign the
rating implied. Hold carries no direction and is reported but not scored; that
is the repo's own rule in `backtest.summarize`.

| arm | trials | cells | directional calls | hit rate | coverage | mean alpha (all cells) |
|---|---|---|---|---|---|---|
| baseline (Bull + Bear) | 3 | 19 | 16 | **62.5%** | 84% | **−0.93%** |
| no_debate (Bull only) | 3 | 19 | 19 | **26.3%** | 100% | **−0.93%** |

| arm | trial | cells | scored | hits | hit rate |
|---|---|---|---|---|---|
| baseline | 1 | 7 | 5 | 4 | 80.0% |
| baseline | 2 | 7 | 6 | 4 | 66.7% |
| baseline | 3 | 5 | 5 | 2 | 40.0% |
| no_debate | 1 | 7 | 7 | 2 | 28.6% |
| no_debate | 2 | 7 | 7 | 2 | 28.6% |
| no_debate | 3 | 5 | 5 | 1 | 20.0% |

**A methodological trap worth stating, and a check that we did not fall into
it.** Alpha is a market fact: for the same (ticker, date) it is *identical* in
both arms, because it is measured from prices, not from the decision. The two
arms here cover the *same* 19 (ticker, date, trial) cells, so mean alpha over
all cells comes out at −0.93% in **both** — exactly as it must if the metric is
being read correctly. That equality is a useful internal consistency check: it
confirms alpha is not a dependent variable of this modification at all.

What the modification moves is whether the rating *called* the direction. So
hit rate and the rating distribution are the correct dependent variables, and
"ablating the debate changed mean alpha from X to Y" would be a misreading.

### 4.2 What the modification did: the rating distribution collapsed

| arm | Buy | Overweight | Hold | Underweight | Sell | cells |
|---|---|---|---|---|---|---|
| baseline | 0 | 7 | 3 | 9 | 0 | 19 |
| no_debate | 0 | **19** | 0 | 0 | 0 | 19 |

**Every no_debate cell came back Overweight, in all 19 cases across all three
trials.** Without a Bear Researcher the system does not become more bullish on
average — it becomes structurally unable to produce a negative view. That is
the mechanism behind both 4.1 and 4.3.

### 4.3 Secondary: our run vs Table 1

Reconstructed from the rating stream (rating → exposure Buy ±1 / Over-Under
±0.5 / Hold 0; each decision held from the next close until the following one;
no transaction costs). ARR% is omitted: see §7.4.

| ticker | row | CR% | SR | MDD% |
|---|---|---|---|---|
| AAPL | paper — TradingAgents | 26.62 | 8.21 | 0.91 |
| AAPL | paper — Buy & Hold | −5.23 | −1.29 | 11.90 |
| AAPL | **ours — Buy & Hold, same prices** | **−7.63** | −1.57 | 13.41 |
| AAPL | ours — baseline | **−0.30** | −0.29 | 2.66 |
| AAPL | ours — no_debate | **−2.13** | −0.96 | 3.63 |
| GOOGL | paper — TradingAgents | 24.36 | 6.39 | 1.69 |
| GOOGL | paper — Buy & Hold | 7.78 | 1.35 | 13.04 |
| GOOGL | **ours — Buy & Hold, same prices** | **9.23** | 1.46 | 14.40 |
| GOOGL | ours — baseline | **−0.21** | −0.07 | 3.43 |
| GOOGL | ours — no_debate | **0.03** | 0.07 | 6.72 |
| AMZN | paper — TradingAgents | 23.21 | 5.60 | 2.11 |
| AMZN | paper — Buy & Hold | 17.10 | 3.53 | 3.80 |
| AMZN | **ours — Buy & Hold, same prices** | **20.31** | 3.04 | 4.22 |
| AMZN | ours — baseline | **6.69** | 2.30 | 2.12 |
| AMZN | ours — no_debate | **6.69** | 2.30 | 2.12 |

Read against the control. On AAPL our reconstruction beats buy-and-hold by
about 7.3 points of cumulative return in a quarter when buy-and-hold lost
7.63% — the direction of the paper's claim survives while its magnitude does
not. **But it survives on one ticker out of three**: on GOOGL and AMZN the
reconstruction *loses* to the control, and on GOOGL the ablated arm is
marginally the better of the two. We report this rather than averaging it away.

### 4.4 The modification, quantified

| effect of removing the Bull/Bear debate | baseline | no_debate | Δ |
|---|---|---|---|
| AAPL CR% | −0.30 | −2.13 | −1.82 |
| AAPL SR | −0.29 | −0.96 | −0.67 |
| AAPL MDD% | 2.66 | 3.63 | +0.97 |
| GOOGL CR% | −0.21 | 0.03 | +0.24 |
| GOOGL SR | −0.07 | 0.07 | +0.15 |
| GOOGL MDD% | 3.43 | 6.72 | +3.29 |
| AMZN CR% | 6.69 | 6.69 | 0.00 |
| AMZN SR | 2.30 | 2.30 | 0.00 |
| AMZN MDD% | 2.12 | 2.12 | 0.00 |
| hit rate (pooled) | 62.5% | 26.3% | −36.2 pp |
| LLM calls per cell | 23 | 19 | −4 |
| prompt tokens per cell | 217,126 | 155,274 | −28% |
| completion tokens per cell | 69,190 | 51,606 | −25% |

AMZN shows Δ = 0.00 because it contributed one decision date on which both arms
rated Overweight. GOOGL is the one case where ablation *helped* slightly. The
modification is therefore not uniformly harmful — it is uniformly *discriminating*,
and on these two tickers there was not enough signal for discrimination to pay.

### 4.5 Is the effect real, or is it noise?

`repro/stats.py` computes exact tests (scipy is not installed here, and the
2×2 tables have a zero cell, so no normal approximation applies anyway).

| comparison | baseline | no_debate | two-sided p |
|---|---|---|---|
| ratings that are Overweight | 7 / 19 | 19 / 19 | **3.7e-05** |
| directional calls that hit | 10 / 16 | 5 / 19 | **0.044** |

Paired by trial, the hit-rate difference is **+36.5 pp ± 15.8 pp over 3 trials,
3/3 in the same direction** (+51.4 / +38.1 / +20.0 pp).

The structural result is the strong one and the hit-rate result is the weaker
one — and the reason is worth stating: the debate pushes ratings towards Hold
and Underweight, and a Hold is not scored, so ablation changes which cells are
even counted. Three trials is the minimum the assignment asks for; it is not
enough to separate the effect from run-to-run noise, so the collapse is what
carries the argument.

### 4.6 A run does not repeat itself — and that is a result

Every AAPL cell was run three times with identical inputs, identical code and
`temperature = 0.0`.

| arm | cells unanimous across all 3 runs | share |
|---|---|---|
| baseline | 2 / 7 | 29% |
| no_debate | **7 / 7** | 100% |

| date | realised alpha | baseline t1 | t2 | t3 | no_debate t1 | t2 | t3 |
|---|---|---|---|---|---|---|---|
| 2024-01-01 | −0.50% | Overweight | Underweight | Overweight | Overweight | Overweight | Overweight |
| 2024-01-29 | +0.00% | Hold | Overweight | Overweight | Overweight | Overweight | Overweight |
| 2024-02-26 | −6.90% | Hold | Underweight | Underweight | Overweight | Overweight | Overweight |
| 2024-03-11 | +1.50% | Overweight | Underweight | Underweight | Overweight | Overweight | Overweight |
| 2024-03-25 | −0.20% | Underweight | Underweight | Underweight | Overweight | Overweight | Overweight |

The two arms are stable in opposite ways, and the contrast is the finding.
Without the debate the pipeline is perfectly repeatable and perfectly
uninformative: all 19 cells say Overweight, so agreement across runs is
guaranteed and worth nothing. With the debate it discriminates between cells,
but only 2 of 7 cells returned the same verdict three times — for AAPL, 1 of 5.

The residual non-determinism is not the sampler: at temperature 0 decoding is
as close to deterministic as it gets. What varies is the multi-agent transcript,
which is regenerated in full on every run and feeds back into every downstream
agent. This is also why the paper's own single-run numbers cannot be checked
against anything.

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

### 7.6 The pipeline does not repeat itself, even at temperature 0

Each AAPL cell was run three times with identical inputs and `temperature =
0.0`. Only **2 of 7** cells returned the same rating all three times (for AAPL
itself, 1 of 5); typical disagreement is that 2024-01-01 came back Overweight,
Underweight and Overweight in three runs of the same cell.

This is not the sampler. At temperature 0 the model is as close to
deterministic as decoding allows. What varies is the multi-agent transcript
itself, which is regenerated in full on every run and is the input to every
downstream agent, so the pipeline has no fixed point to return to.

This is the most basic reproducibility property there is, and it fails here for
reasons no model substitution explains. Its consequence is scope-setting: any
single-run figure in the paper — and in this study — is one draw from a
distribution rather than a measurement, which is why three trials are reported
throughout and why §4.5 separates the structural result from the noisy one.

### 7.7 On the plausibility of the target itself

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
| The debate matters: ablating it collapses the rating distribution | ✅ reproduced — 19/19 cells Overweight vs 7/19; Fisher exact p = 3.7e-05; hit rate 62.5% → 26.3% (p = 0.044) |
| Directional calls beat the benchmark | ⚠️ partial — 62.5% hit rate on 16 scored calls; reconstruction beats B&H on AAPL only |
| A run repeats itself at temperature 0 | ❌ not reproducible — 2/7 cells unanimous across 3 runs; the ablated arm is stable only because it never varies in what it says |
| Table 1 CR% / ARR% / SR / MDD% | ❌ not reproducible — not implemented in the released code |
| The paper's Buy & Hold row | ❌ not reproducible — systematic attenuation (ratio 0.842 on GOOGL/AMZN), no window fits |
| The paper's ARR% column | ❌ not reproducible — internally inconsistent with its own CR% |
| The paper's news / macro / social inputs | ❌ not reproducible — vendors return nothing for historical dates |
