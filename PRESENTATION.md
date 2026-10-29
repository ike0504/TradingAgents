# Screen-recording script (≤ 15 min)

Repo on screen throughout: `github.com/ike0504/TradingAgents`
Everything below is timed so the last section lands with a minute to spare.
Commands are live — the point is that a marker can re-run them, not that they
were run once.

Final numbers are in **§4.5 / §4.6 of the report** and in §4.5 / §4.6 of
`REPRODUCIBILITY.md`. If a number is quoted twice below it is because it is
worth saying twice.

| time | section | what to say / show |
|---|---|---|
| 0:00 | — | — |

---

## 0:00 – 1:00 · What I picked and what I aimed at  *(1 min)*

**Show:** `REPRODUCIBILITY.md` §1–2.

> I picked TradingAgents — multi-agent LLM trading framework, arXiv 2412.20138.
> The repo is real and actively maintained, which turned out to matter.
>
> Target claim, two layers. Primary: the capability the released code actually
> measures — per (ticker, date) cells, does the rating's direction beat the
> benchmark? Secondary: Table 1, CR / Sharpe / max drawdown.
>
> Modification: `max_debate_rounds` 1 → 0. Remove the bearish researcher.
> Two arms, three trials each, 38 cells, 0 failures.

---

## 1:00 – 2:30 · Put the verdict up front  *(1.5 min)*

**Show:** report §1 verdict table.

> I'm leading with the verdict because the honest answer is three yes, one
> partial, four no.
>
> Yes: the pipeline runs end to end, laptop, API only, no GPU. Yes: DeepSeek
> drops in through the repo's own provider. Yes: the debate ablates cleanly as
> one isolated change.
>
> No, and these are the interesting ones: Table 1, the paper's Buy & Hold row,
> the news / macro inputs — and that **a run doesn't repeat itself even at
> temperature zero.** That last one I'll come back to; it's the most basic
> reproducibility property there is, and it constrains everything else I say.
>
> The assignment says this is about verifying what works and what doesn't, not
> pass/fail. So I'm reporting the failures with a mechanism for each.

---

## 2:30 – 4:15 · Setup and the model swap  *(1.75 min)*

**Show:** `repro/config.py`, then run the smoke test.

```bash
python -m repro.run_sweep --arm baseline --trial 0 --smoke
```

> Python 3.13, isolated venv, `pip install -e .`. One key, `DEEPSEEK_API_KEY`,
> in `.env` which is gitignored — I'll show that nothing is committed.
>
> The paper used GPT-4o-mini and o1-preview. I used DeepSeek `deepseek-flash`.
> That's a controlled variable and I'm recording it: base URL
> api.deepseek.com, temperature 0, max tokens 8192. **Our numbers are not
> claimed to be comparable to the paper's** — and later I'll show why that
> caveat is not the whole story.
>
> One real side effect: structured output degrades. Watch the log —
> "Research Manager: structured-output invocation failed, retrying as free
> text". I left it, because patching it would change the system under test.

---

## 4:15 – 6:30 · Primary metric and the collapse  *(2.25 min)*

**Show:** `python -m repro.cells`, then report §4.1, §4.2 and the §4.2 matrix.

```bash
python -m repro.aggregate --arm baseline --arm no_debate
```

> This is the authors' own scorer, `backtest.summarize` — I didn't invent it.
> Hit rate: of the directional calls, what fraction had the sign the rating
> implied. Hold carries no direction and isn't scored; that's their rule.
>
> Three trials, because the assignment asks for repeats on stochastic systems.
> And here's a methodological point I want to flag, because I nearly got it
> wrong: **alpha is a market fact.** Same ticker, same date, both arms —
> identical alpha. The modification cannot move alpha. What moves is whether
> the rating called the direction.
>
> And there's a check that I read it right: mean alpha over all cells comes out
> at **−0.93% in both arms**. Both arms cover the same 19 cells, so if alpha
> were being treated as an outcome, that equality would be a miracle. It isn't —
> it's arithmetic, and it confirms the dependent variable.
>
> **Now the headline: with the debate off, all 19 cells came back Overweight.**
> Not "more bullish on average" — structurally incapable of saying anything
> else. Baseline spreads across Hold, Overweight, Underweight; no_debate is one
> value. Hit rate 62.5% → 26.3%.

---

## 6:30 – 8:30 · Is it real, and does it repeat?  *(2 min)*

**Show:** report §4.5, §4.6. **New material — the two strongest slides.**

```bash
python -m repro.stats
```

> Two questions a marker should ask, and I asked them of myself.
>
> **Is the effect real, or is it noise?** Exact tests, because the smallest
> cell is zero, so no normal approximation applies. The collapse: 7/19 versus
> 19/19 Overweight, Fisher exact **p = 3.7e-05**. The hit-rate drop: 10/16
> versus 5/19, **p = 0.044**. Paired by trial the difference is +36.5
> percentage points ± 15.8, and it moved the same way in 3 of 3 trials.
>
> I'll be honest about which result carries: the collapse. The hit-rate number
> is weaker *by construction* — the debate pushes ratings toward Hold, a Hold
> isn't scored, so ablation changes which cells are even counted.
>
> **Then the one that surprised me.** I ran every AAPL cell three times,
> identical inputs, temperature zero — greedy decoding, which is supposed to
> make a run repeatable. **Only 2 of 7 cells gave the same verdict all three
> times.** For 2024-01-01 the three runs said Overweight, Underweight,
> Overweight.
>
> And the two arms fail to repeat in *opposite* ways, which is the finding.
> Without the debate it's perfectly repeatable and perfectly uninformative —
> all 19 cells say Overweight, so agreement is guaranteed and worth nothing.
> With the debate it discriminates, but it doesn't repeat. Repeatability and
> informativeness are in tension, and "the system is reproducible" usually
> conflates them.
>
> It's not the sampler — at temperature 0 that's as deterministic as decoding
> gets. What varies is the transcript, regenerated in full each run and fed
> back into every later agent.

---

## 8:30 – 11:00 · Why Table 1 doesn't reproduce  *(2.5 min)*

**Show:** report §4.3, then §6.3. **This is the core argument — slow down.**

```bash
python -m repro.compare
```

> Three findings, in order of how much they hurt.
>
> First: Table 1 isn't in the code. `backtest.py` opens with "it is not a
> portfolio simulator and must not grow one". CR, Sharpe, max drawdown exist
> nowhere in v0.7.0. So any comparison is against *my* reconstruction — and
> every mapping choice is an assumption the paper never states.
>
> Second: the data channels. News is empty for **every** historical date — I
> tested 2024-01 and dates three months ago. Macro needs an unset FRED key.
> The system I ran is prices plus technicals, not the multimodal system they
> evaluated. And the agents confirm it from inside — their own decision text
> says "sentiment unavailable on all three feeds, macro/FRED unavailable".
>
> Third, and this is the one I'd defend: **the paper's Buy & Hold row doesn't
> reproduce — and it needs no model.** Pure arithmetic on prices.
>
> | | paper CR% | mine CR% | ratio |
> |---|---|---|---|
> | AAPL | −5.23 | −7.63 | 0.686 |
> | GOOGL | 7.78 | 9.23 | **0.842** |
> | AMZN | 17.1 | 20.31 | **0.842** |
>
> GOOGL and AMZN attenuated by *exactly* the same factor. That's systematic,
> not noise. I grid-searched start and end dates jointly across all three —
> no window fits. Their prices came from Bloomberg, EODHD, FinnHub; not Yahoo.
>
> **Why this matters: it puts a floor under every other discrepancy.** A
> quantity requiring no LLM at all already fails. So the gap in the
> TradingAgents row cannot be blamed on my swapping in DeepSeek.
>
> One thing I won't oversell: on AAPL my reconstruction beats buy-and-hold by
> about 7.3 points. On GOOGL and AMZN it **loses** to the control. I'm
> reporting that rather than averaging it away.

---

## 11:00 – 12:45 · Debug diary  *(1.75 min)*

**Show:** report §5, `repro/balance.py`, `repro/run_budget.py`.

> The one that actually cost me: I ran three tickers in parallel straight
> through DeepSeek's peak window. Peak is 9–12 and 2–6 Beijing, double price.
> Balance hit zero, every cell after 11:04 returned 402, and the entire
> no_debate arm scored zero cells — the modification experiment, which is a
> required deliverable, was empty.
>
> Fix is in the repo: the driver checks the clock before every cell and sleeps
> through peak, re-reads the balance and stops below a floor, and skips cells
> that already have a score so an interrupted run resumes without re-buying.
> That's also why this run survived three days of my laptop being off.
>
> Two of my own reporting bugs, recorded in the diary on purpose: a formatter
> dropped the ×100 on every alpha, and per-cell token cost was divided through
> the whole grid instead of through the cells that had accounting on. Both are
> why the report renders from result files rather than from prose.
>
> Not fixable, only disclosable: no thinking-mode toggle exists in the repo,
> and structured output falls back to free text on this backbone.

---

## 12:45 – 14:45 · Conclusions  *(2 min)*

**Show:** report §6, `REPRODUCIBILITY.md` §8.

> What reproduces: the engineering. Runs on a laptop, API only, ratings and
> alphas come out, DeepSeek swaps in, the graph executes as described.
>
> And the one result that's mine alone, independent of all of the above:
> **the debate is load-bearing.** Remove the bear and the system doesn't get
> more bullish, it loses the ability to disagree with itself — 19/19 cells
> Overweight, p = 3.7e-05. That's a genuine confirmation of the paper's design
> claim, and it holds whether or not their absolute numbers do.
>
> What doesn't, and why: Table 1 isn't implemented; two data channels return
> nothing; Buy & Hold fails deterministically; the ARR column is internally
> inconsistent — GOOGL shows CR 7.78 next to ARR 8.09, which inverts to about
> 0.96 years for a three-month backtest; and a run doesn't repeat at
> temperature 0.
>
> What I'd ask the authors: which vendor and price convention? What is ARR?
> How does a rating map to a position size — the paper shows arrows but never
> the mapping, and Table 1 is unreachable without it. Is there a snapshot of
> the news feed for the backtest window? And — **are the Table 1 numbers a
> single run or an average?** Given the run-to-run spread I measure, that
> question alone could move them.
>
> Last thing: they flagged this themselves. Footnote: "the highest Sharpe
> ratio exceeds our expected empirical range ... we report results as they are
> in our experiments faithfully." A faithful reproduction attempt should expect
> to miss these numbers. The value is in quantifying by how much, and through
> which channel.

---

## Demo cut-list (if short on time)

Drop in this order: §4.4 cost rows → §5 items 6–7 → §6.5 author questions →
the per-cell matrix in §4.2.

**Never drop:** the Buy & Hold control in 8:30–11:00, or the temperature-0
finding in 6:30–8:30. Those two are the argument; everything else is
supporting.
