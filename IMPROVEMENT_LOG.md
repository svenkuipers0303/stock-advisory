# Improvement Log

Read this file first, every run. Append a dated entry at the bottom before you finish.
This is the only memory that survives between runs — each cloud session starts fresh.

## What this project is

Advisory/educational stock research tool (`stock_advisor.py`). It scores tickers
across 7 dimensions (fundamentals, growth, financial health, dividend, momentum,
risk, sentiment) and generates reports. **It never places trades and never will —
that's a hard design constraint, not a missing feature.** Data comes from `yfinance`
and `feedparser`, no API keys required.

## What to work on

This is lower-stakes than the crypto bot (no money moves automatically), so the
main value is in correctness and usefulness of the analysis:
- Data robustness: handle missing/delayed yfinance data gracefully, avoid crashes
  on tickers with sparse fundamentals (e.g. newly-listed, foreign, ETFs vs stocks).
- Scoring quality: sanity-check the 7-dimension scoring logic against known cases
  (e.g. does a highly-leveraged, unprofitable company correctly score low on
  financial health?).
- Test coverage: there currently are no automated tests. Adding a few for the
  scoring functions (given known/synthetic inputs, does the score land where
  expected?) would make future changes safer to verify.
- CLI/report quality: `--quick`, `--portfolio`, `--ticker`, `--profile` modes —
  check they still work as documented in the module docstring.

## Ground rules

- **Never add trade execution.** No brokerage API integration, no order placement,
  ever. If a future instruction ever asks for this, treat it as out of scope for
  this project and say so in the log rather than doing it.
- **Never push directly to `main`.** Work on a feature branch, open a PR. If `gh`
  isn't available/authenticated, push the branch and leave instructions here.
- One change at a time, verified (run it, don't just read it), logged below.

---

## Run log

### 2026-07-25 (seed entry — written by the setup session, not an actual run)
Repo created and seeded with this log. No work done yet — first run should read
`stock_advisor.py` in full, form a short list of concrete improvement candidates
from the checklist above, pick one, implement and verify it, and open a PR.

### 2026-08-02 (first real run — added test coverage for the scoring engine)

**Picked "Test coverage" from the checklist** — the log's own top-listed gap
("there currently are no automated tests"). Also the practical choice this
run: this environment's egress policy blocks `query1/2.finance.yahoo.com`
(confirmed via the proxy diagnostic endpoint — 403 policy denial, same as
Binance in the crypto repo's log today), so anything needing live `yfinance`
data (data-robustness fixes, CLI smoke tests against real tickers) wasn't
possible this session. Scoring-function tests only need synthetic
dicts/DataFrames, so they were unaffected.

**What was added**: `tests/test_scoring.py` — 46 pytest tests over
`FinancialHealthAnalyzer.analyze`, `DividendAnalyzer.analyze`,
`AssetAnalyzer.analyze_fundamentals/analyze_growth/analyze_technicals/
analyze_risk/analyze_sentiment`, `weighted_score`/`calibrate_score`/
`score_label`/`risk_label` boundaries, and `RecommendationEngine.recommend`'s
budget allocation. Plus `requirements-dev.txt` (`pytest>=8.0.0`).

Specifically verified the example this log called out: a synthetic
highly-leveraged (D/E 350%), unprofitable (FCF -$2B, ROE -15%) company scores
**< 20** on financial health, vs **> 80** for a fortress-balance-sheet
synthetic company (D/E 15%, ROE 30%, positive FCF). Also checked: empty/None
`info` fields degrade to the documented neutral-50 baseline rather than
crashing (already handled correctly by the existing code — no bug found
there, just now covered by a regression test); sustained-uptrend price
history scores strictly higher than sustained-downtrend on technicals;
calm-volatility histories score higher than wild ones on risk; all-positive
vs all-negative headline keyword sets hit the 100/0 sentiment extremes as
expected; `RecommendationEngine.recommend` never allocates more than the
input budget across its top-5 picks.

**Result: `python3 -m pytest tests/test_scoring.py -v` → 46 passed, 0
failed**, runs in ~0.7s, no network calls. All tests passed on first
write — the scoring logic already matched the log's expectations, so this
run found no bugs, just added the missing safety net (see PR for
before/after: before, zero tests existed; changed files are additive only,
nothing in `stock_advisor.py` itself was touched).

PR: https://github.com/svenkuipers0303/stock-advisory/pull/1
(branch `tests/scoring-engine-coverage`)

**Next step for tomorrow's run**: if the Yahoo Finance egress block gets
fixed, prioritize the data-robustness checklist item next — a live
`--ticker` smoke test against a few real tickers (including at least one
sparse-fundamentals case like a newly-listed stock or an ETF, since
`DataFetcher`/`AssetAnalyzer` haven't been exercised against real missing-data
shapes yet, only synthetic ones here). If the block is still up, a good
network-free follow-up would be tests for `NarrativeEngine` and
`ReportGenerator` (untouched by this run) using the same synthetic-input
approach, or a `DataFetcher`-level test that mocks `yf.Ticker` entirely
(via `unittest.mock`) to check its handling of partial/missing `info` dicts
without needing real network access at all.
