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
