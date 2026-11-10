# Screen-recording script (≤ 15 min)

Plain-English version — minimal numbers, short sentences, spoken rhythm.
Read it once out loud before recording; the pauses are built in.

Five numbers appear in the whole script. If you can say these five, you
can say the whole thing:

1. 7 out of 19 → 19 out of 19
2. 62% → 26%
3. 2 out of 7
4. minus 7.6 versus minus 5.2 (AAPL only)
5. everything else is a story, not a number

| time | section | what to show on screen |
|---|---|---|
| 0:00 | intro | REPORT.pdf page 1 |
| 1:30 | what I picked | REPRODUCIBILITY.md §1 |
| 3:00 | verdict up front | report §1 verdict table |
| 4:30 | the modification | report §3 setup |
| 7:00 | the two findings | report §4.5, §4.6 |
| 10:00 | why Table 1 fails | report §4.3 |
| 12:00 | lessons | report §6 |
| 13:30 | end | GitHub repo front page |

---

## 0:00 – 1:30 · Intro  *(1.5 min)*

**Show:** REPORT.pdf, page 1 (name visible).

> Hi, I'm Xinyi Ji. This is my reproducibility study for FTEC5660,
> Individual Project 2.
>
> I reproduced TradingAgents — a multi-agent LLM trading framework,
> arXiv 2412.20138. It's a real, actively maintained repo, which turned
> out to matter.
>
> Fifteen minutes, four parts: what I tried to reproduce, what I changed,
> what worked and what didn't, and what I learned. I'll put the verdict
> up front, so you know where this is going.

---

## 1:30 – 3:00 · What I picked and what I aimed at  *(1.5 min)*

**Show:** REPRODUCIBILITY.md, top section.

> The repo trades with a team of LLM agents — analysts, a bull and a bear
> who debate, researchers, a trader, risk management. It rates each stock
> per day, and there's a backtest.
>
> My target had two layers. The primary thing: the rating itself — does
> the direction of the rating actually match the market? The secondary
> thing: the paper's famous Table 1, with returns and Sharpe ratios.
>
> One important note: the paper used OpenAI models. I used DeepSeek,
> because that's what my budget allowed. So I never claimed my absolute
> numbers match the paper's. What I claimed is that my two arms are
> comparable to each other — same model, same window, same everything,
> one difference. And I recorded the whole swap — model, URL, temperature
> zero — so it's a controlled change, not a hidden one.

---

## 3:00 – 4:30 · Verdict up front  *(1.5 min)*

**Show:** report §1, the verdict table.

> Here's the honest summary before the details.
>
> The engineering reproduces. It runs end to end on a laptop, with one
> API key, no GPU. DeepSeek drops in cleanly. My modification — I'll get
> to it — ablates cleanly.
>
> The paper's headline table does not reproduce. And that's the
> interesting half of this talk — not "I failed," but *why* it can't
> reproduce, and how I know it's not my fault. That's a stronger claim
> than it sounds, and I'll prove it with a number that doesn't involve
> any model at all.

---

## 4:30 – 7:00 · The modification and its impact  *(2.5 min)*

**Show:** report §3 (setup), then §4.5.

> My one change: the framework has a bull researcher and a bear
> researcher who debate before deciding. I set the debate to zero rounds
> — effectively removing the bearish side. One flag in the config:
> debate rounds, one to zero. Nothing else touched.
>
> I ran both versions — with debate, and without — on the same nineteen
> stocks-and-days, three times each. Nineteen cells, two arms, zero
> failures.
>
> Here's the first finding, and it's the headline of the whole project.
>
> With the debate on, the system is picky: about a third of the cells
> come back "overweight," and it does say "underweight" sometimes. Its
> direction calls are right about 62 percent of the time.
>
> With the debate off — the bear removed — **all nineteen cells came
> back "overweight."** Every single one. And the direction accuracy fell
> from 62 percent to 26.
>
> So removing the debate didn't make the system more bullish. It made it
> *incapable of saying anything except "buy."* The debate isn't a
> decoration — it's what gives the system the ability to disagree with
> itself.
>
> I checked this statistically — it's a Fisher exact test, it's in
> section 4.5 of the report — and it's far past any reasonable
> significance threshold. This is not noise.

---

## 7:00 – 10:00 · The finding that surprised me  *(3 min)*

**Show:** report §4.6 (repeatability).

> The second finding came from the repeats, and it's the one I didn't
> expect.
>
> I ran everything with temperature zero — that's greedy decoding, the
> most deterministic setting an LLM offers. The textbook expectation: the
> same input, run twice, same output.
>
> I ran the same Apple cells three times each, identical inputs. Only
> **2 out of 7** gave the same verdict all three times. One cell said
> overweight, then underweight, then overweight again — same stock, same
> day, same everything.
>
> So even at temperature zero, a run does not repeat itself.
>
> And the two arms fail differently, which is the actual insight. Without
> the debate, it's perfectly repeatable — but only because it always says
> the same thing, so repeating is worthless. With the debate, it makes
> useful distinctions — but it doesn't repeat. Repeatability and
> usefulness are in tension here, and people usually assume you get both.
>
> Why does this happen, if the sampler is deterministic? Because each
> agent regenerates the whole transcript, and everything downstream reads
> that transcript. Tiny differences early amplify through the chain of
> agents. The system isn't one model call — it's a stack of them, and
> each one is a fresh chance to diverge.
>
> The practical consequence: any single run of this system — mine, or the
> paper's — is one draw from a spread. That reframes what "reproducing
> Table 1" even means.

---

## 10:00 – 12:00 · Why the paper's Table 1 fails  *(2 min)*

**Show:** report §4.3.

> Now the paper's Table 1 — returns, Sharpe, drawdown. Three reasons it
> doesn't reproduce, in order of how much they hurt.
>
> One: **it isn't in the code.** The repo's own backtest file says, in a
> comment, "this is not a portfolio simulator." Returns and Sharpe exist
> nowhere in the released code. Any comparison is against my
> reconstruction, and every reconstruction choice is a guess the paper
> never specifies — like how a "buy" rating becomes a position size.
> The paper shows arrows, not the mapping.
>
> Two: two of the data channels are empty. News is empty for every
> historical date I tested. Macro needs a key that isn't set. The agents
> themselves say so in their own decision text: "sentiment unavailable,
> macro unavailable." So the system I ran is prices and technicals — not
> the multimodal system the paper evaluated.
>
> Three — and this is my favorite result of the project: **the paper's
> own Buy & Hold row doesn't reproduce either.** And Buy & Hold needs no
> model. It's just: buy on day one, hold to the end, report the return.
> On Apple, the paper says minus 5.2 percent; the actual prices say
> minus 7.6. Google and Amazon are off by the *same factor* — same ratio,
> twice. That's not noise, that's a different data source or convention.
> I grid-searched start and end dates — no window fixes it.
>
> Why this matters: a number that requires no LLM at all already fails.
> So the gap in the TradingAgents row cannot be blamed on me swapping in
> DeepSeek. This control puts a floor under every other discrepancy.

---

## 12:00 – 13:30 · Lessons  *(1.5 min)*

**Show:** report §6.

> What I'd tell someone starting this project:
>
> First — a reproducibility paper is engineering plus forensics. Getting
> it to run was the easy week. The real work was proving *which part* of
> the mismatch was mine and which was theirs. The Buy & Hold control is
> how you do that: find one number that needs no model, and test it
> first. It's cheap, and it moves the burden of proof.
>
> Second — "reproducible" and "repeatable" are different things, and
> agentic systems break the second one. If you evaluate any multi-agent
> system, run it at least three times per cell, or your numbers are one
> draw from a spread wearing a confident outfit.
>
> Third — the budget is part of the experiment. DeepSeek charges double
> in peak hours; my balance hit zero mid-run and the experiment arm came
> back empty. The fixed driver — off-peak only, balance floor,
> resume-from-where-you-stopped — is committed in the repo. Without that
> engineering, there is no result to report.

---

## 13:30 – 14:30 · Close  *(1 min)*

**Show:** GitHub repo front page.

> To sum up. The engineering of TradingAgents reproduces, and my ablation
> confirms the paper's design claim: the debate is load-bearing — remove
> it, and the system can only say "buy." That's my one clean, controlled
> result, and it stands regardless of the absolute numbers.
>
> The paper's Table 1 doesn't reproduce — partly because it isn't
> implemented, partly because the data channels are empty, and provably
> not because of my model swap.
>
> If the authors are listening: which data vendor, what is ARR, how does
> a rating become a position, and — are the Table 1 numbers one run or an
> average? Given the spread I measured, that last question matters most.
>
> Repo, report, and every command are at github.com/ike0504/TradingAgents.
> Thanks for watching.

---

## If you're running long

Cut, in this order: the "why does it happen" paragraph in the
temperature-zero section → the third lesson (budget) → the
author-questions ending (keep one).

**Never cut:** the 19-out-of-19 result, or the Buy & Hold control.
Those two are the talk.
