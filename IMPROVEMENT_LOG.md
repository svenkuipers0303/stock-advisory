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

### 2026-08-02 (test coverage — not yet reflected on main, see PR #1)
A prior run added `tests/test_scoring.py` (46 pytest unit tests, synthetic inputs,
no network) on branch `tests/scoring-engine-coverage` and opened **PR #1**
("Add unit test coverage for the 7-dimension scoring engine"). As of this entry
(2026-08-03) that PR is still open, unreviewed, no CI configured on the repo (0
checks). Nothing to fix there — it's just waiting on a human to look at it. Don't
duplicate this work; if picking a next test-coverage task, build on PR #1's branch
once merged rather than re-adding an overlapping test file.

### 2026-08-03 (bug fix — divide-by-zero on corrupted zero-price data points)
**Data-robustness fix, verified with a before/after repro (see below), not yet
covered by automated tests since PR #1's test file is still pending merge.**

Session context: today's crypto-bot iteration (Crypto_Stockbot) was fully blocked
by an environment-level egress policy (Binance/CoinGecko both 403 in this sandbox
— see that repo's BACKTEST_LOG.md), so time was redirected here per the routine's
"secondary task" instructions. `yfinance` network calls *are* reachable from this
environment (unlike Binance), so this iteration could actually exercise the code,
but this specific fix was found by code review + synthetic repro, not a live run
against a real corrupted ticker (a real one wasn't observed today).

**Bug found**: `AssetAnalyzer.analyze_technicals()`'s 3-month momentum calc
(`(price - close.iloc[-63]) / close.iloc[-63]`) and `AssetAnalyzer.analyze_risk()`'s
max-drawdown calc (`(close - rolling_max) / rolling_max` where `rolling_max =
close.cummax()`) both divide by a historical close price with no guard against
that price being `0` or negative. yfinance does occasionally emit `0.0` (not `NaN`)
for a given day on thin/halted/recently-relisted tickers — pandas doesn't raise on
float division by zero, it silently produces `inf`/`nan`, which then flows into
score arithmetic and into user-facing note strings.

**Confirmed with a synthetic repro** (260 daily closes trending 50→100, one single
day 63-bars back forced to `0.0` — everything else realistic): before the fix,
`analyze_technicals` scored the ticker 90/100 with note `"Strong 3-month momentum
+inf%"`, while `analyze_risk` scored the *same, otherwise-healthy* price series
**7/100** with `"Annualized volatility nan% — very high volatility, speculative
risk"` and `"Max drawdown -100.0% — severe historical drawdown"` — a single bad
data point drove a phantom near-worst-case risk score. After the fix: technicals
83/100, risk 92/100 — sane numbers, unaffected by the glitch (there's still real
signal loss from dropping the corrupted point, hence 83 vs 90, but no more `inf`/
`nan`/`-100%` garbage).

**Fix**: filter to strictly-positive `Close` values at three points — centrally in
`DataFetcher.get_history()` (the live-fetch path), and defensively again inside
`analyze_technicals()` and `analyze_risk()` (so callers that construct/pass a
`history` DataFrame directly — e.g. future tests, or the ETF-list rendering path at
line ~1220 which calls `yf.Ticker(...).history()` directly rather than through
`DataFetcher.get_history()` — are protected too, not just the main fetch path).

**Verification**: `python3 -m py_compile stock_advisor.py` passes. Ran PR #1's
46-test suite (`tests/test_scoring.py`, borrowed from its branch, not committed
here — that file belongs to the separate pending PR) against this change: **46/46
still pass**, no regressions. Ran the before/after repro above directly against
both the stashed original and the patched version to confirm the fix is real, not
just plausible.

**What wasn't done / next step**: this is a defensive fix for a bug found by
inspection, not one observed live today (no real corrupted ticker was hit this
session). A good next-run task: once PR #1 merges, add a regression test for this
exact scenario (zero-price data point 63 bars back) to `tests/test_scoring.py`
rather than creating a second parallel test file. Also worth a grep for other
`/ something.iloc[...]`-shaped divisions in `stock_advisor.py` that assume a
historical price is never exactly zero — the two fixed here were the only ones
found on inspection, but this wasn't an exhaustive audit.

**PR**: opened from branch `fix/zero-price-divide-by-zero` against `main`. Use
`gh pr create` or the GitHub UI if not already open by the time this entry is
read — see the PR itself for the exact diff.

**Status update from the merging session (2026-08-05): this PR (#2) has been
merged into `main`.** The fix described above is live. PR #1 (46 tests) and PR #3
(58 tests, below) are being reconciled next — see that entry for the resolution.

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

**Status update from the merging session (2026-08-05): merged as PR #3.** #1 (46
tests, superseded/strict subset of this PR's 58) was closed rather than merged,
per the coordination-gap entry below.

### 2026-08-05 (process fix — found and flagged a PR-duplication gap, no new code)

**Discovered a coordination bug in this routine's own memory model, not in
`stock_advisor.py`.** This session's first step (per the top of this file) was to
read this log for context — which still only shows the seed entry above. But
`list_pull_requests` on the repo shows **three open, unmerged PRs** with real log
entries written *inside* their diffs (not on `main`):

- **#1** (2026-08-02): 46 tests for the scoring engine, `tests/test_scoring.py`.
- **#2** (2026-08-03): fixes a real divide-by-zero bug (momentum/drawdown scoring
  on zero-price data from `yfinance`) — no file overlap with #1/#3, independently
  mergeable.
- **#3** (2026-08-04): 58 tests for the scoring engine, also `tests/test_scoring.py`
  — written by a session that had no way to know #1 existed, because #1's own log
  entry lives only inside PR #1's diff, invisible from `main`.

**Root cause**: every prior session correctly followed the rule "append a log entry
before finishing" — but appended it *inside the PR branch*, same commit as the code
change. Since none of these PRs have been merged, `main`'s copy of this file never
picked up any of those entries. Each fresh session (this repo's only memory) reads
`main` and sees nothing past the seed entry, so it has no way to know #1/#2/#3
exist without separately checking `list_pull_requests` — which this session did,
but no prior one apparently had reason to.

**Compared #1 vs #3 directly** (both add `tests/test_scoring.py` from scratch): #3
is a strict superset — 58 tests vs 46, covers `MarketRegimeDetector.detect` and
`AssetAnalyzer.compute_confidence` (untested in #1), adds `tests/conftest.py`, and
includes a mutation-testing verification step (flipped a scoring sign, confirmed
the relevant test failed, reverted) that #1 doesn't have. Left a comment on #1
recommending it be closed in favor of #3 — did not close it myself, that's the
repo owner's call, not an autonomous one.

**No new test/code PR opened this run** — with three unmerged, overlapping PRs
already sitting open, adding a fourth would compound the exact problem being
flagged here rather than fix anything. This entry itself is the only change,
opened as its own minimal PR against `main` so it survives independently of
whichever of #1/#2/#3 merges (or doesn't) and first.

**Next step for tomorrow's run — merge order recommendation**: (1) merge #2 first
(bug fix, zero conflict risk with anything else open), (2) merge #3 (more complete
test suite) or #1 if the human prefers it for some reason, (3) close whichever of
#1/#3 doesn't get merged. **Before starting any new work, check
`list_pull_requests` for this repo, not just this file** — until the backlog above
is cleared, `main`'s copy of this log is known to be stale relative to what's
actually in flight. Once #1/#2/#3 resolve, the data-robustness checklist item
(real `--ticker` smoke test once Yahoo Finance egress is unblocked — still blocked
as of this session, same 403-at-CONNECT pattern as Binance in the crypto repo) is
the next substantive item, per #3's own "next step" note.

**Status update from the merging session (2026-08-05): PR #1 was closed (not
merged) in favor of #3, and PR #4 (this entry's own PR) was merged after
resolving a log-append conflict with #2 and #3 — same class of conflict this
entry describes, just one level up (the coordination-gap doc about append
conflicts had its own append conflict). All four PRs are now resolved.

### 2026-08-06 (test coverage — regression tests for the 2026-08-03 zero-price fix)

**Checked `list_pull_requests` first, per this log's own instruction** — clean,
nothing open beyond what's already reflected on `main`.

**Yahoo Finance is still egress-blocked in this cloud environment** (`query1`/
`query2.finance.yahoo.com`, `finance.yahoo.com` — 403 at the CONNECT tunnel
stage, confirmed this session; same wall the Crypto_Stockbot repo hits on
Binance/CoinGecko, both checked from the same environment today). So the
"real `--ticker` smoke test once Yahoo Finance egress is unblocked" item
flagged as next-up in the 2026-08-05 entry still isn't reachable. Picked the
next item that doesn't need network access instead — the specific regression
test the 2026-08-03 entry called out as not-yet-written: *"once PR #1 merges,
add a regression test for this exact scenario (zero-price data point 63 bars
back) to `tests/test_scoring.py`."* PR #1's superseding PR (#3) merged
2026-08-05, so that condition is now met.

**Added two tests to `tests/test_scoring.py`** (`TestTechnicals` and
`TestRisk`), reproducing the exact synthetic repro described in the
2026-08-03 entry (260 daily closes trending 50→100, one point 63 bars back
forced to `0.0`):
- `test_zero_price_63_bars_back_does_not_produce_inf_momentum` — asserts the
  technicals score stays finite and in `[0, 100]`, and no note contains
  `"inf"`/`"nan"`.
- `test_zero_price_in_history_does_not_corrupt_risk_score` — asserts the risk
  score stays finite, in `[0, 100]`, no note contains `"nan"` or the literal
  `"-100.0%"` phantom-drawdown string, and the score doesn't fall below 60
  (a real steady uptrend has no genuine severe drawdown to justify a low
  score).

**Also did the "grep for other similarly-shaped divisions" audit flagged as
not-yet-exhaustive in the 2026-08-03 entry**: searched `stock_advisor.py` for
`/ *.iloc[`, `/ *.mean()`, `/ rolling_max`-shaped patterns. Found only the
two already-fixed sites (technicals momentum, risk drawdown) plus one
already-guarded sentiment ratio (`pos / total`, explicit `if total == 0`
check before the divide) and two in `PortfolioManager` (`total_pnl_pct`,
`alloc` — divide by `total_invested`/`total_value`, which can't legitimately
be zero for an existing holding; out of scope per the 2026-08-04 entry, which
already flagged `PortfolioManager` as needing filesystem+yfinance mocking
rather than a synthetic-input unit test). **No new divide-by-zero sites
found** — the 2026-08-03 fix's three-point patch was complete for the
scoring engine.

**Verification**:
- `pytest tests/ -v` → **60/60 passing** (58 existing + 2 new).
- `python3 -m py_compile stock_advisor.py` — clean (no code changes anyway,
  test-only PR).
- **Mutation-tested both new tests against the pre-fix code**, not just
  confirmed they pass now: reverted the `close > 0` filters in both
  `analyze_technicals` and `analyze_risk` (including the redundant inline
  `close.iloc[-63] > 0` guard inside the momentum branch — removing only the
  top-of-function filter wasn't enough to reproduce the bug, since that
  inline guard independently protects the momentum calc; had to strip both
  to actually hit the `inf`/`nan` path). Confirmed both new tests **fail**
  against the reverted code (`RuntimeWarning: divide by zero`, `"nan"` in
  notes, exactly as the 2026-08-03 entry described), then
  `git checkout -- stock_advisor.py` to restore the fix and re-ran the full
  suite clean (60/60). This is real regression coverage, not tests written
  to match whatever the code already does.

**No changes to `stock_advisor.py`** — test-only PR, same pattern as #1/#3.

**Next step for tomorrow's run**: (1) re-check Yahoo Finance egress before
assuming another blocked day — once reachable, the real `--ticker` smoke
test against genuinely sparse tickers (newly-listed, foreign ADRs, ETFs
missing fundamentals fields) from the 2026-08-04 entry's next-step list is
still the highest-value remaining item and hasn't been attempted with real
data yet. (2) Remaining test-coverage gaps, still open: `NarrativeEngine`
(low priority, no scoring logic to regress), `PortfolioManager` (needs
filesystem + yfinance mocking, not synthetic-input unit tests),
`ReportGenerator`/`StockAdvisor` top-level orchestration (better suited to
an integration-style test with a mocked `DataFetcher`). (3) Check
`list_pull_requests` before starting, per the 2026-08-05 coordination-gap
fix, even though this session found it clean.
