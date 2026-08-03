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
