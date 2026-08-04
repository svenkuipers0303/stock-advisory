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

### 2026-08-04 (test coverage — added 58 unit tests for the scoring engine)
**What was tried**: `yfinance`'s data hosts (`query1/query2.finance.yahoo.com`,
`finance.yahoo.com`) are egress-blocked in this cloud environment (403 at CONNECT,
confirmed again this run) — same wall the crypto bot's Binance access hits. No live
data was pullable, so picked the "test coverage" item from this log's checklist,
since it needs no network access.

Read `stock_advisor.py` in full (1962 lines). Wrote `tests/test_scoring.py` (58
tests, pytest) against hand-built synthetic `info` dicts and synthetic OHLCV
`DataFrame`s (steady uptrend/downtrend, flat, volatile price series built with
`numpy`), covering:
- `FinancialHealthAnalyzer.analyze` — including the exact sanity check this log's
  checklist called out: leveraged (D/E 350%) + unprofitable (negative FCF/ROE) +
  illiquid (current ratio 0.6) scores ≤20; a fortress balance sheet scores ≥85.
- `DividendAnalyzer.analyze` — no-dividend neutral baseline, yield-trap penalty,
  unsustainable-payout penalty.
- `AssetAnalyzer.analyze_fundamentals` / `analyze_growth` / `analyze_technicals` /
  `analyze_risk` — cheap-vs-expensive, hypergrowth-vs-contraction, uptrend-vs-
  downtrend, low-vol-vs-high-vol/beta, plus edge cases (missing fields, <50 bars
  of history).
- `weighted_score` / `calibrate_score` / `score_label` / `risk_label` /
  `compute_confidence` — boundary and clamping behavior (confidence hard-capped
  at 88 per the module's own design intent).
- `MarketRegimeDetector.detect` — bullish/defensive/neutral classification from
  synthetic S&P/VIX/Nasdaq/yield series.
- `RecommendationEngine.recommend` — budget allocation respects `max_single_pct`,
  low scorers excluded, capped at 5 recs, regime-dependent score bar (DEFENSIVE
  excludes candidates NEUTRAL would include).

**Verification**: `pytest tests/ -v` → 58/58 passing. `python3 -c "import
stock_advisor"` imports cleanly (no `__main__` side effects to guard against).
`py_compile` syntax check passed. Then mutation-tested the suite itself — flipped
a sign in `FinancialHealthAnalyzer`'s debt-to-equity branch (`score += 18` →
`score -= 18` for the fortress-balance-sheet case), confirmed
`test_fortress_balance_sheet_scores_high` failed (70 vs required ≥85) as expected,
reverted with `git checkout -- stock_advisor.py`. This is real regression coverage,
not tests written to match whatever the code already does.

**No changes to `stock_advisor.py` itself** — test-only PR. Added
`requirements-dev.txt` (pulls in `requirements_stocks.txt` + `pytest`).

PR: https://github.com/svenkuipers0303/stock-advisory/pull/3 (branch
`add-scoring-engine-tests`), subscribed for CI/review follow-up.

**Next step for tomorrow's run**: (1) if Yahoo Finance egress is fixed by then,
resume the checklist's "data robustness" item — `DataFetcher.get_info`/
`get_history` currently swallow all exceptions and return `{}`/empty DataFrame,
worth testing (with real or recorded data) how gracefully the scoring functions
degrade on genuinely sparse tickers (newly-listed, foreign ADRs, ETFs missing
fundamentals fields) rather than just synthetic missing-field cases. (2) Test
coverage gaps still open in this PR's scope: `NarrativeEngine` (text generation,
lower priority — no scoring logic to regress), `PortfolioManager` (needs
filesystem + yfinance, would need mocking), `ReportGenerator`/`StockAdvisor`
(top-level orchestration, better suited to an integration-style test with a
mocked `DataFetcher` than unit tests). (3) Check egress policy status for both
Yahoo Finance and Binance before assuming either can be reached from this
environment — it's been blocked every session since at least 2026-08-02.
