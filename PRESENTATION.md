# Screen-recording script (≤ 15 min)

Repo on screen throughout: `github.com/ike0504/TradingAgents`
Everything below is timed so the last section lands with a minute to spare.
Commands are live — the point is that a marker can re-run them, not that they
were run once.

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

---

## 1:00 – 2:30 · Put the verdict up front  *(1.5 min)*

**Show:** report §1 verdict table.

> I'm leading with the verdict because the honest answer is three yes, one
> partial, three no.
>
> Yes: the pipeline runs end to end, laptop, API only, no GPU. Yes: DeepSeek
> drops in through the repo's own provider. Yes: the debate ablates cleanly as
> one isolated change.
>
> No, and these are the interesting ones: Table 1, the paper's Buy & Hold row,
> and the news / macro inputs.
>
> The assignment says this is about verifying what works and what doesn't, not
> pass/fail. So I'm reporting the three failures with a mechanism for each.

---

## 2:30 – 4:30 · Setup and the model swap  *(2 min)*

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

## 4:30 – 7:00 · Primary metric  *(2.5 min)*

**Show:** `python -m repro.cells --arm baseline --arm no_debate`, then
`report.html` §4.1.

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
> the rating called the direction. So hit rate and rating distribution are the
> right dependent variables, not mean alpha.

---

## 7:00 – 9:00 · The modification  *(2 min)*

**Show:** report §4.2 rating distribution, §4.4 effect table.

> The headline: with the debate off, **every single cell came back
> Overweight.** Not "more bullish on average" — structurally incapable of
> saying anything else. Baseline spreads across Hold, Overweight,
> Underweight; no_debate is one value.
>
> That's the mechanism. And downstream it's measurable: hit rate, reconstructed
> portfolio CR and Sharpe, all in §4.4.
>
> Also a cost dimension: 23 LLM calls per cell down to 19, prompt tokens down
> about a quarter.
>
> This is a genuine confirmation of the paper's design claim — the debate is
> load-bearing, not decorative. And it's the one result here that's mine alone;
> it doesn't depend on whether the paper's absolute numbers hold up.

---

## 9:00 – 11:30 · Why Table 1 doesn't reproduce  *(2.5 min)*

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

---

## 11:30 – 13:30 · Debug diary  *(2 min)*

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
> Not fixable, only disclosable: no thinking-mode toggle exists in the repo,
> and structured output falls back to free text on this backbone.

---

## 13:30 – 15:00 · Conclusions  *(1.5 min)*

**Show:** report §6, §8.

> What reproduces: the engineering. Runs on a laptop, API only, ratings and
> alphas come out, DeepSeek swaps in, the graph executes as described.
>
> What doesn't, and why: Table 1 isn't implemented; two data channels return
> nothing; Buy & Hold fails deterministically; the ARR column is internally
> inconsistent — GOOGL shows CR 7.78 next to ARR 8.09, which inverts to about
> 0.96 years for a three-month backtest.
>
> What I'd ask the authors: which vendor and price convention? What is ARR?
> How does a rating map to a position size — the paper shows arrows but never
> the mapping, and Table 1 is unreachable without it. And is there a snapshot
> of the news feed for the backtest window?
>
> Last thing: they flagged this themselves. Footnote: "the highest Sharpe
> ratio exceeds our expected empirical range ... we report results as they are
> in our experiments faithfully." A faithful reproduction attempt should expect
> to miss these numbers. The value is in quantifying by how much, and through
> which channel.

---

## Demo cut-list (if short on time)

Drop in this order: §4.4 cost rows → §5 items 6–7 → §6.5 author questions.
Never drop: the Buy & Hold control in §9:00–11:30.
