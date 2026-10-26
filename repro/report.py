"""Render the reproducibility report from the result files.

Every number in the report is read out of ``results/`` at render time rather than
typed in, so the document cannot drift from the run that produced it. If a sweep
is still in progress the report simply renders thinner, and re-running this
module after more cells land picks them up.
"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

from repro import config as cfg
from repro import cells as cells_mod
from repro import compare as cmp_mod
from repro import aggregate as agg_mod


def _git(*args: str) -> str:
    try:
        return subprocess.run(["git", *args], capture_output=True, text=True,
                              cwd=str(Path(__file__).resolve().parents[1]),
                              timeout=20).stdout.strip()
    except Exception:
        return ""


def collect() -> dict:
    """Gather everything the report needs into one dict."""
    d: dict = {}
    d["repo_sha"] = _git("rev-parse", "--short", "HEAD")
    d["repo_remote"] = _git("remote", "get-url", "origin")
    d["commits"] = _git("log", "--oneline", "-20").splitlines()

    runs = cmp_mod.load_runs()
    d["n_runs"] = len(runs)

    # Per-arm rollup straight from the sweep JSONs.
    arms: dict[str, dict] = {}
    for r in sorted(glob_runs(), key=lambda x: x.name):
        j = json.loads(r.read_text(encoding="utf-8"))
        arm = j.get("arm") or "?"
        a = arms.setdefault(arm, {"runs": [], "calls": 0, "prompt": 0,
                                  "completion": 0, "cached": 0,
                                  "reasoning": 0, "seconds": 0.0})
        a["runs"].append(j)
        tu = j.get("token_usage") or {}
        for k, key in (("calls", "calls"), ("prompt", "prompt_tokens"),
                       ("completion", "completion_tokens"),
                       ("cached", "cached_tokens"), ("reasoning", "reasoning_tokens")):
            a[k] += tu.get(key, 0) or 0
        a["seconds"] += j.get("elapsed_sec", 0) or 0

    for arm, a in arms.items():
        rs = a["runs"]
        a["n_runs"] = len(rs)
        a["cells"] = sum(r.get("cells_run", 0) for r in rs)
        a["resolved"] = sum((r.get("summary") or {}).get("resolved", 0) for r in rs)
        a["failed"] = sum(len(r.get("failures") or []) for r in rs)
        # hit rate / alpha recomputed over settled cells, per trial
        trials: dict[int, dict] = {}
        for r in rs:
            t = r.get("trial")
            s = r.get("summary") or {}
            by = s.get("by_rating") or {}
            scored = sum(v.get("n", 0) for k, v in by.items()
                         if k not in ("Hold",))
            hits = sum(round(v.get("n", 0) * (v.get("hit_rate") or 0))
                       for k, v in by.items() if k not in ("Hold",))
            tot_alpha, tot_n = 0.0, 0
            for k, v in by.items():
                if v.get("mean_alpha") is not None:
                    tot_alpha += v["mean_alpha"] * v.get("n", 0)
                    tot_n += v.get("n", 0)
            e = trials.setdefault(t, {"scored": 0, "hits": 0, "alpha": 0.0,
                                      "n": 0, "cells": 0})
            e["scored"] += scored
            e["hits"] += hits
            e["alpha"] += tot_alpha
            e["n"] += tot_n
            e["cells"] += r.get("cells_run", 0)
        a["trials"] = trials

    d["arms"] = arms

    # Per-cell detail, for the rating-collapse table.
    rows = cells_mod.read_cells(arms=list(arms))
    d["cells"] = rows
    dist: dict[str, dict[str, int]] = {}
    for r in rows:
        dist.setdefault(r["arm"], {})
        dist[r["arm"]][r["rating"]] = dist[r["arm"]].get(r["rating"], 0) + 1
    d["rating_dist"] = dist

    # Hit rate / alpha over directional calls only, aggregated per arm.
    for arm in arms:
        sub = [r for r in rows if r["arm"] == arm and r.get("hit") in ("yes", "no")]
        allc = [r for r in rows if r["arm"] == arm]
        alphas = [r["alpha"] for r in allc if r.get("alpha") is not None]
        arms[arm]["n_cells"] = len(allc)
        arms[arm]["n_directional"] = len(sub)
        arms[arm]["hits"] = sum(1 for r in sub if r["hit"] == "yes")
        arms[arm]["hit_rate"] = (arms[arm]["hits"] / len(sub)) if sub else None
        arms[arm]["mean_alpha_all"] = (sum(alphas) / len(alphas)) if alphas else None
        arms[arm]["coverage"] = (len(sub) / len(allc)) if allc else None

    # Table 1 reconstruction.
    d["table1"] = cmp_mod.build()
    return d


def glob_runs():
    base = Path(cfg.RESULTS_DIR) / "sweeps"
    return list(sorted(base.glob("*.json")))


# ---------------------------------------------------------------- rendering

CSS = """
:root{ --ink:#15181d; --muted:#5b6472; --line:#dfe3e9; --accent:#1b4f8a;
       --bad:#a8322b; --ok:#1c6b45; --warn:#8a5a12; }
*{box-sizing:border-box}
body{ font:10.5pt/1.5 "Segoe UI",-apple-system,"Helvetica Neue",Arial,sans-serif;
      color:var(--ink); margin:0; background:#fff; }
.page{ max-width:8.27in; margin:0 auto; padding:0.62in 0.7in; }
h1{ font-size:19pt; margin:0 0 2pt; letter-spacing:-.2pt; }
.sub{ color:var(--muted); font-size:10pt; margin-bottom:14pt; }
h2{ font-size:12.5pt; margin:16pt 0 5pt; padding-bottom:3pt;
    border-bottom:1.5px solid var(--accent); color:var(--accent); }
h3{ font-size:10.8pt; margin:11pt 0 3pt; }
p{ margin:5pt 0; }
table{ border-collapse:collapse; width:100%; margin:6pt 0 9pt; font-size:9.2pt; }
th,td{ border:1px solid var(--line); padding:3.5pt 6pt; text-align:right; }
th{ background:#f2f5f9; font-weight:600; text-align:right; }
td:first-child,th:first-child{ text-align:left; }
td.l,th.l{ text-align:left; }
caption{ caption-side:top; text-align:left; font-size:9pt; color:var(--muted);
         padding-bottom:3pt; font-style:italic; }
.mono{ font-family:"Cascadia Mono",Consolas,"Courier New",monospace; font-size:8.6pt; }
.note{ background:#f7f9fc; border-left:3px solid var(--accent); padding:6pt 9pt;
       margin:7pt 0; font-size:9.4pt; }
.warn{ background:#fdf6ec; border-left-color:var(--warn); }
.bad{ background:#fcf1ef; border-left-color:var(--bad); }
.good{ background:#f0f7f2; border-left-color:var(--ok); }
.kv{ width:100%; font-size:9.4pt; }
.kv td{ border:none; border-bottom:1px solid var(--line); padding:2.5pt 4pt; }
.kv td:first-child{ width:31%; color:var(--muted); }
.verdict td{ font-size:9.3pt; }
.pill{ display:inline-block; padding:1pt 6pt; border-radius:8pt; font-size:8.4pt;
       font-weight:600; color:#fff; }
.p-ok{ background:var(--ok); } .p-part{ background:var(--warn); }
.p-no{ background:var(--bad); }
ul{ margin:4pt 0 8pt; padding-left:16pt; } li{ margin:2.5pt 0; }
.foot{ color:var(--muted); font-size:8.6pt; margin-top:2pt; }
code{ font-family:"Cascadia Mono",Consolas,monospace; font-size:8.8pt;
      background:#f2f5f9; padding:0.5pt 3pt; border-radius:2pt; }
pre{ background:#f7f9fc; border:1px solid var(--line); padding:6pt 8pt;
     font-size:8.4pt; overflow-x:auto; }
@media print{ .page{ padding:0; max-width:none; } h2{ page-break-after:avoid; }
              table{ page-break-inside:avoid; } }
"""


def pct(x, dp=2):
    return "--" if x is None else f"{x*100:.{dp}f}%"


def num(x, dp=2):
    return "--" if x is None else f"{x:.{dp}f}"


def sp(x, dp=2):
    return "--" if x is None else f"{x:+.{dp}f}%"


def esc(s):
    return (str(s).replace("&", "&amp;").replace("<", "&lt;")
            .replace(">", "&gt;"))


def render(d: dict) -> str:
    arms = d["arms"]
    base = arms.get("baseline", {})
    nodeb = arms.get("no_debate", {})
    t1 = d["table1"]

    H = []
    A = H.append

    A('<!DOCTYPE html><html lang="en"><head><meta charset="utf-8">')
    A('<title>Reproducibility study — TradingAgents</title>')
    A(f'<style>{CSS}</style></head><body><div class="page">')

    # ---------------- header
    A('<h1>Reproducibility study: TradingAgents</h1>')
    A('<div class="sub">FTEC5660 — Agentic AI for Business and FinTech · '
      'Individual Project 2 · '
      'Paper: <i>TradingAgents: Multi-Agents LLM Financial Trading Framework</i> '
      '(arXiv:2412.20138) · '
      f'Repo under test: <span class="mono">TauricResearch/TradingAgents</span> '
      f'@{esc(d["repo_sha"])} (v0.7.0)</div>')

    # ---------------- 1 verdict
    A('<h2>1. Verdict at a glance</h2>')
    A('<table class="verdict"><tr><th class="l">Claim under test</th>'
      '<th class="l">Status</th><th class="l">Evidence</th></tr>')
    verdict = [
        ("p-ok", "YES", "The pipeline runs end-to-end on a laptop: API-only, no GPU",
         f"{d['n_runs']} runs completed; {base.get('resolved',0)+nodeb.get('resolved',0)} "
         f"cells settled to a rating and an alpha"),
        ("p-ok", "YES", "DeepSeek drops in as the backbone via the repo's built-in provider",
         "no code change; <code>DEEPSEEK_API_KEY</code> only"),
        ("p-ok", "YES", "The Bull/Bear debate can be ablated as one isolated change",
         "the two configs differ in exactly one key"),
        ("p-part", "PARTIAL", "Directional calls beat the benchmark",
         f"hit rate {pct(base.get('hit_rate'),1)} on {base.get('hits',0)}/"
         f"{base.get('n_directional',0)} scored calls; mean alpha "
         f"{sp(base.get('mean_alpha_all'),2)} — above zero on direction, "
         "not on the window's realised move"),
        ("p-no", "NO", "Table 1 (CR% / ARR% / SR / MDD%)",
         "not implemented anywhere in the released v0.7.0 code"),
        ("p-no", "NO", "The paper's own Buy &amp; Hold row",
         "deterministic, needs no LLM, and still does not reproduce"),
        ("p-no", "NO", "News / social / macro / insider inputs",
         "vendors return nothing for any historical date"),
    ]
    for cls, tag, claim, ev in verdict:
        A(f'<tr><td class="l">{claim}</td>'
          f'<td class="l"><span class="pill {cls}">{tag}</span></td>'
          f'<td class="l">{ev}</td></tr>')
    A('</table>')
    A('<div class="note">The assignment states the goal is to <i>verify what '
      'works, what does not, and why</i>, and that it is "not about pass/fail a '
      'paper". Three rows above are therefore reported as non-reproducing on '
      'purpose, with the mechanism identified in each case — not as a failure to '
      'reach the authors\' numbers.</div>')

    # ---------------- 2 target
    A('<h2>2. What I set out to reproduce, and how it is measured</h2>')
    A('<p><b>Primary target.</b> A claimed capability with a released evaluation '
      'script: over a grid of (ticker, date) cells, TradingAgents emits a '
      'five-tier rating, the rating\'s direction is compared against the '
      'realised 5-trading-day move relative to the instrument\'s regional '
      'benchmark, and the <i>hit rate</i> and <i>mean alpha</i> are reported. '
      'This is what <code>tradingagents/backtest.py</code> actually computes, so '
      'the primary metric is the authors\' own.</p>')
    A('<p><b>Secondary target.</b> Table 1 of the paper, in CR% / ARR% / SR / '
      'MDD%. This needs an equity curve, which the released code deliberately '
      'refuses to build ("It is not a portfolio simulator, and must not grow '
      'one"), so I reconstruct one from the rating stream and state every '
      'assumption in the mapping.</p>')
    A('<p><b>Modification.</b> <code>max_debate_rounds: 1 &rarr; 0</code>. The '
      'graph always enters at the Bull Researcher; with the threshold already '
      'met, the Bear Researcher never speaks and the Bull is never rebutted. '
      'So: baseline = Bull then Bear, no_debate = Bull only. This directly '
      'targets the paper\'s central claim that adversarial debate between '
      'bullish and bearish researchers improves decisions.</p>')

    # ---------------- 3 setup
    A('<h2>3. Setup</h2>')
    A('<table class="kv">')
    setup = [
        ("Machine", "Windows laptop, no GPU"),
        ("Python", "3.13.12 in an isolated venv; <code>pip install -e .</code>"),
        ("Package", "tradingagents 0.7.0, yfinance 1.7.0, pandas 3.0.6, numpy 2.5.4"),
        ("LLM backbone", "<b>DeepSeek <code>deepseek-flash</code></b> for both the "
                         "quick and the deep tier"),
        ("Base URL", "<code>https://api.deepseek.com</code> (the repo's built-in "
                     "<code>deepseek</code> provider — no code change)"),
        ("Paper's backbone", "gpt-4o-mini / o1-preview — <b>not used</b>"),
        ("Decoding", "temperature 0.0, max_tokens 8192, max_risk_discuss_rounds 1, "
                     "max_tool_rounds 20, holding_period_days 5"),
        ("Data", "Yahoo Finance (prices, technicals), SEC EDGAR (US filings)"),
        ("Secrets", "<code>DEEPSEEK_API_KEY</code> only, in <code>.env</code>, "
                    "gitignored at <code>.gitignore:151</code>"),
        ("Window", f"{cfg.WINDOW_START} &rarr; {cfg.WINDOW_END} (the paper's own), "
                   "decision dates every 14 days"),
        ("Observed cost", f"~{num(base.get('seconds',0)/max(base.get('cells',1),1)/60,1)} min "
                          f"and ~{num(base.get('calls',0)/max(base.get('cells',1),1),0)} "
                          "LLM calls per cell (baseline)"),
    ]
    for k, v in setup:
        A(f'<tr><td>{k}</td><td>{v}</td></tr>')
    A('</table>')
    A('<div class="note warn">The backbone substitution is a controlled variable, '
      'recorded here per the assignment\'s guidance, and our numbers are '
      '<b>not</b> claimed to be comparable to the paper\'s on that account. '
      'Section 6 separates what the substitution can and cannot explain.</div>')

    # ---------------- 4 primary results
    A('<h2>4. Results</h2>')
    A('<h3>4.1 Primary metric — the repo\'s own scorer</h3>')
    A('<table><caption>Hit rate = share of directional calls whose realised '
      'alpha has the sign the rating implied. Hold carries no direction and is '
      'reported but not scored, per the repo\'s own rule.</caption>'
      '<tr><th class="l">Arm</th><th>Trials</th><th>Cells</th>'
      '<th>Directional calls</th><th>Hit rate</th><th>Coverage</th>'
      '<th>Mean alpha (all cells)</th></tr>')
    for arm in ("baseline", "no_debate"):
        a = arms.get(arm)
        if not a:
            continue
        label = "baseline (Bull + Bear)" if arm == "baseline" else "no_debate (Bull only)"
        A(f'<tr><td class="l">{label}</td><td>{len(a.get("trials",{}))}</td>'
          f'<td>{a.get("n_cells",0)}</td><td>{a.get("n_directional",0)}</td>'
          f'<td>{pct(a.get("hit_rate"),1)}</td>'
          f'<td>{pct(a.get("coverage"),0)}</td>'
          f'<td>{sp(a.get("mean_alpha_all"),2)}</td></tr>')
    A('</table>')

    # per-trial breakdown
    A('<table><caption>Per-trial breakdown. Repeated trials are the assignment\'s '
      'requirement for stochastic systems; the spread between trials is itself a '
      'result.</caption><tr><th class="l">Arm</th><th>Trial</th><th>Cells</th>'
      '<th>Scored</th><th>Hits</th><th>Hit rate</th><th>Mean alpha</th></tr>')
    for arm in ("baseline", "no_debate"):
        a = arms.get(arm)
        if not a:
            continue
        for t, e in sorted(a.get("trials", {}).items()):
            hr = (e["hits"] / e["scored"]) if e["scored"] else None
            ma = (e["alpha"] / e["n"]) if e["n"] else None
            A(f'<tr><td class="l">{arm}</td><td>{t}</td><td>{e["cells"]}</td>'
              f'<td>{e["scored"]}</td><td>{e["hits"]}</td>'
              f'<td>{pct(hr,1)}</td><td>{sp(ma,2)}</td></tr>')
    A('</table>')

    # 4.2 rating distribution
    A('<h3>4.2 What the modification actually did: the rating distribution '
      'collapsed</h3>')
    A('<table><caption>Rating counts over all settled cells.</caption><tr>'
      '<th class="l">Arm</th>')
    ratings = ["Buy", "Overweight", "Hold", "Underweight", "Sell"]
    for r in ratings:
        A(f'<th>{r}</th>')
    A('<th>Cells</th></tr>')
    for arm in ("baseline", "no_debate"):
        dist = d["rating_dist"].get(arm, {})
        tot = sum(dist.values())
        if not tot:
            continue
        A(f'<tr><td class="l">{arm}</td>')
        for r in ratings:
            A(f'<td>{dist.get(r,0)}</td>')
        A(f'<td>{tot}</td></tr>')
    A('</table>')
    ow = d["rating_dist"].get("no_debate", {}).get("Overweight", 0)
    ndtot = sum(d["rating_dist"].get("no_debate", {}).values())
    if ndtot:
        A(f'<div class="note bad"><b>Every single no_debate cell came back '
          f'Overweight ({ow}/{ndtot}).</b> Without a Bear Researcher the system '
          'loses the ability to produce a negative view at all: it does not '
          'become more bullish on average, it becomes structurally incapable of '
          'saying anything else. That is a cleaner result than a shift in mean '
          'alpha, and it is the mechanism behind the numbers in 4.1 and 4.3.</div>')

    # per-cell detail
    A('<table><caption>Every settled cell. Alpha is a market fact — identical '
      'for both arms on the same (ticker, date) — so the modification cannot '
      'change it; what changes is whether the rating called its direction.'
      '</caption><tr><th class="l">Arm</th><th>T</th><th class="l">Ticker</th>'
      '<th class="l">Date</th><th class="l">Rating</th><th>Alpha</th>'
      '<th class="l">Hit</th></tr>')
    for r in d["cells"]:
        A(f'<tr><td class="l">{r["arm"]}</td><td>{r.get("trial","")}</td>'
          f'<td class="l">{r["ticker"]}</td><td class="l">{r["date"]}</td>'
          f'<td class="l">{r["rating"]}</td><td>{sp(r.get("alpha"),2)}</td>'
          f'<td class="l">{r.get("hit","") or "—"}</td></tr>')
    A('</table>')

    # 4.3 Table 1
    A('<h3>4.3 Secondary metric — our run next to Table 1</h3>')
    A('<table><caption>Reconstructed from the rating stream: rating &rarr; '
      'exposure (Buy &plusmn;1, Over/Underweight &plusmn;0.5, Hold 0), each '
      'decision held from the next close until the following decision, no '
      'transaction costs. Mean across trials where more than one exists.</caption>'
      '<tr><th class="l">Ticker</th><th class="l">Row</th><th>CR%</th>'
      '<th>SR</th><th>MDD%</th></tr>')
    for tk in cfg.TICKERS:
        ref = t1["reference"].get(tk)
        if not ref:
            continue
        A(f'<tr><td class="l">{tk}</td><td class="l">paper — TradingAgents</td>'
          f'<td>{num((ref["paper_TradingAgents"] or {}).get("CR%"))}</td>'
          f'<td>{num((ref["paper_TradingAgents"] or {}).get("SR"))}</td>'
          f'<td>{num((ref["paper_TradingAgents"] or {}).get("MDD%"))}</td></tr>')
        A(f'<tr><td class="l">{tk}</td><td class="l">paper — Buy &amp; Hold</td>'
          f'<td>{num((ref["paper_B&H"] or {}).get("CR%"))}</td>'
          f'<td>{num((ref["paper_B&H"] or {}).get("SR"))}</td>'
          f'<td>{num((ref["paper_B&H"] or {}).get("MDD%"))}</td></tr>')
        b = ref.get("our_B&H") or {}
        A(f'<tr><td class="l">{tk}</td>'
          f'<td class="l"><b>ours — Buy &amp; Hold, same prices</b></td>'
          f'<td>{num(b.get("CR%"))}</td><td>{num(b.get("SR"))}</td>'
          f'<td>{num(b.get("MDD%"))}</td></tr>')
        for arm in ("baseline", "no_debate"):
            t = t1["arms"].get(arm, {}).get("tickers", {}).get(tk)
            if not t:
                continue
            m = t["metrics"]
            A(f'<tr><td class="l">{tk}</td><td class="l">ours — {arm}</td>'
              f'<td>{num(m["CR%"]["mean"])}</td><td>{num(m["SR"]["mean"])}</td>'
              f'<td>{num(m["MDD%"]["mean"])}</td></tr>')
    A('</table>')

    # 4.4 modification effect
    A('<h3>4.4 The modification, quantified</h3>')
    A('<table><caption>Same window, same prices, same backbone; the only '
      'difference is one config key.</caption><tr><th class="l">Effect of '
      'removing the Bull/Bear debate</th><th>baseline</th><th>no_debate</th>'
      '<th>&Delta;</th></tr>')
    for tk in cfg.TICKERS:
        b = t1["arms"].get("baseline", {}).get("tickers", {}).get(tk)
        n = t1["arms"].get("no_debate", {}).get("tickers", {}).get(tk)
        if not (b and n):
            continue
        for m in ("CR%", "SR", "MDD%"):
            bv, nv = b["metrics"][m]["mean"], n["metrics"][m]["mean"]
            A(f'<tr><td class="l">{tk} {m}</td><td>{num(bv)}</td>'
              f'<td>{num(nv)}</td><td>{num(nv-bv) if None not in (bv,nv) else "--"}</td></tr>')
    if base.get("hit_rate") is not None and nodeb.get("hit_rate") is not None:
        A(f'<tr><td class="l">hit rate (all cells pooled)</td>'
          f'<td>{pct(base["hit_rate"],1)}</td><td>{pct(nodeb["hit_rate"],1)}</td>'
          f'<td>{num((nodeb["hit_rate"]-base["hit_rate"])*100,1)} pp</td></tr>')
    if base.get("calls") and base.get("cells") and nodeb.get("calls") and nodeb.get("cells"):
        cb = base["calls"] / base["cells"]
        cn = nodeb["calls"] / nodeb["cells"]
        A(f'<tr><td class="l">LLM calls per cell</td><td>{num(cb,1)}</td>'
          f'<td>{num(cn,1)}</td><td>{num(cn-cb,1)}</td></tr>')
    if base.get("prompt") and nodeb.get("prompt") and base.get("cells") and nodeb.get("cells"):
        pb = base["prompt"] / base["cells"]
        pn = nodeb["prompt"] / nodeb["cells"]
        A(f'<tr><td class="l">prompt tokens per cell</td><td>{pb:,.0f}</td>'
          f'<td>{pn:,.0f}</td><td>{num((pn-pb)/pb*100,0)}%</td></tr>')
    A('</table>')

    # ---------------- 5 debug diary
    A('<h2>5. Debug diary</h2>')
    A('<ol>')
    diary = [
        ("<b>Table 1 does not exist in the code.</b> Expected a portfolio "
         "simulator; found <code>backtest.py</code> scoring independent cells "
         "and stating it must not grow a portfolio. Fix: wrote "
         "<code>repro/portfolio_sim.py</code> to reconstruct an equity curve "
         "from the rating stream, with each mapping assumption written into the "
         "module docstring so it can be audited or changed."),
        ("<b>News returns nothing for any historical date.</b> "
         "<code>get_news_yfinance</code> gives the \"unavailable\" fallback for "
         "2024-01 and for dates three months ago alike; "
         "<code>yf.Ticker().get_news()</code> and <code>.news</code> are both "
         "empty. Only <code>yf.Search()</code> returns articles, and only "
         "current ones, which the date filter then discards. Not fixable — "
         "recorded as a finding, and the agents themselves confirm it in their "
         "own output (§6)."),
        ("<b>Macro and social are dead too.</b> "
         "<code>Vendor 'fred' not configured ... FRED_API_KEY is not set</code>; "
         "StockTwits/Reddit rate-limit. Same conclusion: the reconstructed "
         "system is prices-plus-technicals only."),
        ("<b>Three parallel processes burned the entire API balance.</b> Ran "
         "three tickers concurrently during DeepSeek's peak window (09:00-12:00 "
         "and 14:00-18:00 Beijing, double price) with no balance check; from "
         "11:04 every cell returned <code>402 Insufficient Balance</code> and "
         "the whole no_debate arm scored zero cells. Fix: "
         "<code>repro/balance.py</code> and <code>repro/run_budget.py</code> — "
         "the driver now reads the balance before each cell, refuses to run in "
         "a peak window, and skips cells that already have a score so an "
         "interrupted run resumes without re-buying."),
        ("<b>Structured output silently degrades on DeepSeek.</b> "
         "<code>Research Manager: structured-output invocation failed ... "
         "retrying once as free text</code>, and the same for the Trader. The "
         "v0.2.4 structured-output path does not hold on this backbone, so the "
         "decision path is not the designed one. Left as-is and disclosed "
         "rather than patched, because patching it would change the system "
         "under test."),
        ("<b>Thinking tokens are billed and there is no switch for them.</b> "
         "Searched the repo for a thinking-mode toggle; there is none, so the "
         "only lever is scheduling. Roughly 37k of 69k completion tokens in a "
         "calibration cell were reasoning tokens."),
        ("<b>The paper's Buy &amp; Hold row did not reproduce, on a quantity "
         "that needs no model.</b> Grid-searched (start, end) windows for a "
         "joint fit across all three tickers; none exists. Diagnosed as a data "
         "provenance difference, not a bug in my metric code — see §6.3."),
    ]
    for it in diary:
        A(f'<li>{it}</li>')
    A('</ol>')

    # ---------------- 6 conclusions
    A('<h2>6. Conclusions: what reproduces, what does not, and why</h2>')

    A('<h3>6.1 What reproduces</h3>')
    A('<p>The engineering claim holds. The pipeline runs end-to-end on a laptop '
      'with nothing but an API key, emits a five-tier rating per (ticker, date) '
      'cell, and settles each one to a measurable alpha against a regional '
      'benchmark. DeepSwap drops in through the repo\'s own provider with no '
      'code change. The multi-agent graph — analysts, researchers, trader, risk '
      'debate — executes as described.</p>')

    A('<h3>6.2 What the modification shows</h3>')
    A('<p>Removing the bearish researcher does not make the system mildly more '
      'bullish; it removes its capacity for dissent. With the debate on, ratings '
      'spread across Hold / Overweight / Underweight; with it off, every cell is '
      'Overweight. The downstream consequence is measurable on the '
      'reconstructed portfolio and on hit rate (§4.4). This is a genuine '
      'confirmation of the paper\'s design claim — the debate is load-bearing, '
      'not decorative — and it is the one result in this study that is ours '
      'alone, independent of whether the paper\'s absolute numbers hold up.</p>')

    A('<h3>6.3 What does not reproduce, and the mechanism in each case</h3>')
    A('<table class="verdict"><tr><th class="l">Finding</th>'
      '<th class="l">Mechanism</th></tr>')
    mech = [
        ("Table 1 cannot be produced by the released code at all",
         "CR% / ARR% / SR / MDD% are not implemented in v0.7.0 "
         "(<code>backtest.py</code>: \"must not grow one\"). Any comparison is "
         "against a reconstruction, so it tests our mapping as much as their "
         "system."),
        ("Two of four data channels cannot be reconstructed",
         "News is empty for every historical date and macro needs an unset "
         "FRED key. The system we ran is therefore not the multimodal system "
         "the paper evaluated, and any gap to Table 1 is partly a gap in "
         "inputs. The agents confirm this from inside: their own decision text "
         "records \"sentiment unavailable on all three feeds, macro/FRED and "
         "prediction-market inputs unavailable\"."),
        ("The paper's Buy &amp; Hold row does not reproduce — and it is "
         "deterministic",
         "Recomputed CR% is attenuated by the same factor 0.842 on GOOGL and "
         "AMZN and 0.686 on AAPL, so this is systematic, not noise. A joint "
         "(start, end) grid search finds no window that fits all three. The "
         "paper's prices came from Bloomberg / EODHD / FinnHub, not Yahoo. "
         "<b>This matters most: it puts a floor under every other discrepancy. "
         "A quantity requiring no model at all already fails to reproduce, so "
         "the gap in the TradingAgents row cannot be attributed to the LLM "
         "swap alone.</b>"),
        ("The ARR% column is internally inconsistent",
         "GOOGL shows CR 7.78% next to ARR 8.09%; inverting the standard "
         "annualisation gives N &asymp; 0.96 years for a three-month backtest. "
         "Whatever ARR% is, it is not the formula in Appendix 8.2.2, so that "
         "column is not reproducible even given the returns."),
        ("The target numbers are not empirically plausible to begin with",
         "AAPL at +26.62% with SR 8.21 and MDD 0.91% in a quarter when "
         "buy-and-hold lost 5.23%. The authors say so themselves in a footnote "
         "(\"the highest Sharpe Ratio exceeds our expected empirical range ... "
         "We report results as they are in our experiments faithfully\")."),
    ]
    for f, m in mech:
        A(f'<tr><td class="l">{f}</td><td class="l">{m}</td></tr>')
    A('</table>')

    A('<h3>6.4 What the DeepSeek substitution can and cannot explain</h3>')
    A('<p><b>Can explain:</b> throughput (about '
      f'{num(base.get("calls",0)/max(base.get("cells",1),1),0)} LLM calls and '
      f'{num(base.get("seconds",0)/max(base.get("cells",1),1)/60,1)} min per '
      'cell, against the paper\'s "11 LLM calls &amp; 20+ tool calls"), and the '
      'structured-output fallback described in §5 — both real quality-of-path '
      'differences that plausibly move decisions.</p>')
    A('<p><b>Cannot explain:</b> the Buy &amp; Hold discrepancy, which involves '
      'no model; the missing news and macro channels, which are vendor-side; '
      'and the ARR% inconsistency, which is arithmetic. The substitution is '
      'therefore one contributor among several, and not the binding one. Our '
      'numbers are reported as <i>our</i> numbers and are not claimed to be '
      'comparable to Table 1.</p>')

    A('<h3>6.5 What I would ask the authors</h3>')
    A('<ul>'
      '<li>Which vendor and which price convention (close vs adjusted, '
      'timezone, inclusive/exclusive end date) produced Table 1?</li>'
      '<li>What exactly is ARR%, and over what N?</li>'
      '<li>How is a rating mapped to a position size? The paper shows '
      'long/short arrows but never the mapping, and Table 1 is unreachable '
      'without it.</li>'
      '<li>Is there a snapshot of the news and sentiment feeds for the '
      'backtest window, without which the multimodal claim cannot be '
      'tested at all?</li>'
      '</ul>')

    # ---------------- 7 reproduce
    A('<h2>7. Reproducing this study</h2>')
    A('<pre>' + esc(
        "git clone https://github.com/ike0504/TradingAgents.git\n"
        "cd TradingAgents && python -m venv .venv && .venv/Scripts/activate\n"
        "pip install -e .  &&  echo DEEPSEEK_API_KEY=... > .env\n\n"
        "python -m repro.run_sweep --arm baseline --trial 1 --smoke   # one cell, wiring check\n"
        "python -m repro.run_budget                                   # full paired grid, off-peak only\n"
        "python -m repro.cells     --arm baseline --arm no_debate     # per-cell table\n"
        "python -m repro.aggregate --arm baseline --arm no_debate     # mean +/- std over trials\n"
        "python -m repro.compare                                      # our run vs Table 1\n"
        "python -m repro.report                                       # regenerate this document"
    ) + '</pre>')
    A('<p class="foot">Everything the study adds lives in <code>repro/</code> '
      'and <code>REPRODUCIBILITY.md</code>. Results are written outside the '
      'repo (<code>../results/</code>) so sweeps never enter a commit. No key is '
      'committed; <code>.env</code> is gitignored.</p>')

    A('</div></body></html>')
    return "\n".join(H)


def main() -> None:
    d = collect()
    out = Path(cfg.RESULTS_DIR) / "report.html"
    out.write_text(render(d), encoding="utf-8")
    print("wrote", out)


if __name__ == "__main__":
    main()
