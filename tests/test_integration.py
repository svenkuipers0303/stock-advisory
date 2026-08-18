"""
Integration-style tests for StockAdvisor.analyze_all() and
ReportGenerator.generate_html(), using a mocked DataFetcher and synthetic
inputs instead of live yfinance/market data.

Purpose: this is the top-level orchestration layer flagged as an open
test-coverage gap in IMPROVEMENT_LOG.md (2026-08-04/08-05/08-11 entries) —
"better suited to an integration-style test with a mocked DataFetcher" than
synthetic-input unit tests, since StockAdvisor wires together every other
analyzer/engine class. No overlap with the open PRs #5 (tests/test_scoring.py
regression tests), #6 (tests/test_portfolio.py), or #7
(tests/test_investment_brief.py) — different class, different file.

Run with: pytest tests/ -v
"""
from unittest.mock import patch

import numpy as np
import pandas as pd
import pytest

import stock_advisor
from stock_advisor import ReportGenerator, StockAdvisor, USER_PROFILES


def make_history(prices, freq="B"):
    """Build a minimal OHLCV DataFrame from a list/array of closing prices."""
    n = len(prices)
    idx = pd.date_range("2024-01-01", periods=n, freq=freq)
    close = pd.Series(prices, index=idx, dtype=float)
    return pd.DataFrame({
        "Open": close, "High": close * 1.001, "Low": close * 0.999, "Close": close,
        "Volume": 1_000_000,
    })


def make_info(**overrides):
    info = {
        "longName": "Example Corp", "sector": "Technology",
        "trailingPE": 20.0, "forwardPE": 18.0, "pegRatio": 1.2,
        "profitMargins": 0.18, "priceToSalesTrailing12Months": 5.0,
        "revenueGrowth": 0.12, "earningsGrowth": 0.10,
        "beta": 1.1, "dividendYield": 0.0,
    }
    info.update(overrides)
    return info


@pytest.fixture
def advisor(tmp_path):
    with patch.dict(stock_advisor.CONFIG, {"portfolio_file": str(tmp_path / "portfolio.json")}):
        yield StockAdvisor(profile_name="balanced")


# ─────────────────────────────────────────────────────────────
#  StockAdvisor.analyze_all
# ─────────────────────────────────────────────────────────────
class TestAnalyzeAll:
    def test_normal_ticker_produces_a_complete_analysis_record(self, advisor):
        rng = np.random.default_rng(1)
        prices = np.linspace(80, 120, 300) + rng.normal(0, 0.5, 300)
        history = make_history(prices)

        with patch.object(advisor.fetcher, "get_info", return_value=make_info()), \
             patch.object(advisor.fetcher, "get_history", return_value=history), \
             patch("stock_advisor.time.sleep"):
            analyses = advisor.analyze_all(["GOOD"], news=[], quick=True)

        a = analyses["GOOD"]
        assert 0 <= a["score"] <= 100
        assert a["label"] in {"Strong Buy", "Buy", "Hold", "Sell", "Strong Sell"} or isinstance(a["label"], str)
        assert a["risk_label"] in {"LOW", "MEDIUM", "HIGH"}
        assert "narrative" in a and "summary" in a["narrative"]
        for key in ("fund_score", "grow_score", "health_score", "div_score", "trend_score", "risk_score", "sent_score"):
            assert isinstance(a[key], (int, float))

    def test_fetcher_exception_for_one_ticker_falls_back_without_crashing_others(self, advisor):
        rng = np.random.default_rng(2)
        prices = np.linspace(80, 120, 300) + rng.normal(0, 0.5, 300)
        good_history = make_history(prices)

        def get_history_side_effect(ticker, period="1y"):
            if ticker == "BAD":
                raise RuntimeError("simulated network failure")
            return good_history

        with patch.object(advisor.fetcher, "get_info", return_value=make_info()), \
             patch.object(advisor.fetcher, "get_history", side_effect=get_history_side_effect), \
             patch("stock_advisor.time.sleep"):
            analyses = advisor.analyze_all(["GOOD", "BAD"], news=[], quick=True)

        assert set(analyses.keys()) == {"GOOD", "BAD"}
        # GOOD processed normally despite BAD's failure being mid-loop.
        assert 0 <= analyses["GOOD"]["score"] <= 100

        # BAD gets the documented fallback record, not a crash.
        bad = analyses["BAD"]
        assert bad["score"] == 50
        assert bad["label"] == "Hold"
        assert bad["risk_label"] == "MEDIUM"
        assert bad["top_note"] == "Data unavailable"
        assert bad["narrative"] == {}

    def test_fallback_record_has_every_key_write_cache_reads(self, advisor):
        # _write_cache() reads these keys via .get(..., default) for every
        # analysis, including fallback ones — this pins the fallback dict's
        # contract so a future edit can't silently drop a key _write_cache
        # depends on (it wouldn't crash today thanks to .get(), but the
        # displayed data would go quietly wrong).
        with patch.object(advisor.fetcher, "get_info", side_effect=RuntimeError("boom")), \
             patch("stock_advisor.time.sleep"):
            analyses = advisor.analyze_all(["BAD"], news=[], quick=True)

        bad = analyses["BAD"]
        for key in ("score", "label", "color", "risk_label", "category", "top_note", "narrative"):
            assert key in bad


# ─────────────────────────────────────────────────────────────
#  ReportGenerator.generate_html
# ─────────────────────────────────────────────────────────────
class TestGenerateHtml:
    def _analyses(self):
        return {
            "AAA": {
                "score": 82, "label": "Strong Buy", "color": "#3fb950",
                "risk_label": "LOW", "category": "Tech", "top_note": "Great value",
                "fund_score": 80, "grow_score": 75, "health_score": 85,
                "div_score": 40, "trend_score": 78, "risk_score": 70,
                "narrative": {"summary": "Looks solid.", "bull_case": "Growing fast.",
                              "bear_case": "Valuation stretched.", "beginner": "Buy and hold.",
                              "risk_note": "Moderate volatility."},
            },
            "BBB": {
                "score": 35, "label": "Sell", "color": "#f85149",
                "risk_label": "HIGH", "category": "Energy", "top_note": "Weak fundamentals",
                "fund_score": 30, "grow_score": 25, "health_score": 40,
                "div_score": 20, "trend_score": 35, "risk_score": 45,
                "narrative": {},
            },
        }

    def test_html_report_renders_without_crashing_and_includes_both_tickers(self):
        reporter = ReportGenerator()
        regime_data = {"regime": "NEUTRAL", "signals": [], "advice": "Balanced.",
                       "bull_pts": 2, "bear_pts": 2}
        recs = [{"ticker": "AAA", "score": 82, "label": "Strong Buy", "color": "#3fb950",
                 "amount": 150.0, "type": "Stock", "reason": "Great value.", "etf_info": None}]
        summary = {"holdings": [], "total_invested": 0, "total_value": 0,
                   "total_pnl": 0, "total_pnl_pct": 0}
        profile = dict(USER_PROFILES["balanced"])
        profile["key"] = "balanced"

        html = reporter.generate_html(
            self._analyses(), regime_data, recs, summary,
            warnings_list=[], news=[], budget=500.0, profile=profile,
        )

        assert isinstance(html, str) and len(html) > 0
        assert "AAA" in html and "BBB" in html

    def test_html_report_handles_empty_analyses_and_recs(self):
        reporter = ReportGenerator()
        regime_data = {"regime": "DEFENSIVE", "signals": [], "advice": "Caution.",
                       "bull_pts": 0, "bear_pts": 4}
        summary = {"holdings": [], "total_invested": 0, "total_value": 0,
                   "total_pnl": 0, "total_pnl_pct": 0}
        profile = dict(USER_PROFILES["balanced"])
        profile["key"] = "balanced"

        html = reporter.generate_html(
            {}, regime_data, [], summary,
            warnings_list=[], news=[], budget=500.0, profile=profile,
        )

        assert isinstance(html, str) and len(html) > 0
