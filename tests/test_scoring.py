"""
Unit tests for the AssetAnalyzer / FinancialHealthAnalyzer / DividendAnalyzer
scoring engine, using synthetic `info` dicts and price histories — no network
access, no yfinance calls. Verifies the 7-dimension scoring logic lands in the
expected direction for known-good vs known-bad synthetic companies.
"""
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from stock_advisor import (
    AssetAnalyzer,
    DividendAnalyzer,
    FinancialHealthAnalyzer,
    RecommendationEngine,
)


def make_price_history(start=100.0, daily_return=0.0, daily_vol=0.0, n=252):
    """Deterministic synthetic OHLCV history: constant drift + optional noise."""
    rng = np.random.default_rng(42)
    steps = np.full(n, daily_return)
    if daily_vol:
        steps = steps + rng.normal(0, daily_vol, n)
    close = start * np.cumprod(1 + steps)
    return pd.DataFrame({"Close": close})


# ── FinancialHealthAnalyzer ─────────────────────────────────────
class TestFinancialHealthAnalyzer:
    def setup_method(self):
        self.analyzer = FinancialHealthAnalyzer()

    def test_strong_balance_sheet_scores_high(self):
        info = {
            "freeCashflow": 5e9,
            "debtToEquity": 15,
            "returnOnEquity": 0.30,
            "currentRatio": 3.0,
        }
        score, notes = self.analyzer.analyze(info)
        assert score > 80
        assert notes

    def test_leveraged_unprofitable_company_scores_low(self):
        info = {
            "freeCashflow": -2e9,
            "debtToEquity": 350,
            "returnOnEquity": -0.15,
            "currentRatio": 0.6,
        }
        score, _ = self.analyzer.analyze(info)
        assert score < 20

    def test_missing_fields_returns_neutral_baseline(self):
        score, notes = self.analyzer.analyze({})
        assert score == 50.0
        assert notes == []

    def test_score_is_clamped_0_100(self):
        info = {
            "freeCashflow": 1e12,
            "debtToEquity": 1,
            "returnOnEquity": 5.0,
            "currentRatio": 10,
        }
        score, _ = self.analyzer.analyze(info)
        assert 0.0 <= score <= 100.0


# ── DividendAnalyzer ────────────────────────────────────────────
class TestDividendAnalyzer:
    def setup_method(self):
        self.analyzer = DividendAnalyzer()

    def test_no_dividend_returns_neutral(self):
        score, notes = self.analyzer.analyze({"dividendYield": 0}, pd.DataFrame())
        assert score == 50.0
        assert "growth/reinvestment" in notes[0]

    def test_well_covered_dividend_scores_high(self):
        info = {"dividendYield": 0.03, "payoutRatio": 0.30, "dividendRate": 1.5}
        score, _ = self.analyzer.analyze(info, pd.DataFrame())
        assert score > 65

    def test_unsustainable_high_yield_scores_lower_than_well_covered(self):
        trap = {"dividendYield": 0.10, "payoutRatio": 0.95}
        healthy = {"dividendYield": 0.03, "payoutRatio": 0.30}
        trap_score, _ = self.analyzer.analyze(trap, pd.DataFrame())
        healthy_score, _ = self.analyzer.analyze(healthy, pd.DataFrame())
        assert trap_score < healthy_score


# ── AssetAnalyzer: fundamentals / growth ────────────────────────
class TestAssetAnalyzerFundamentalsAndGrowth:
    def setup_method(self):
        self.analyzer = AssetAnalyzer()

    def test_cheap_quality_stock_scores_high_on_fundamentals(self):
        info = {"trailingPE": 10, "pegRatio": 0.6, "profitMargins": 0.35, "priceToSalesTrailing12Months": 1.5}
        score, _ = self.analyzer.analyze_fundamentals(info)
        assert score > 70

    def test_expensive_unprofitable_stock_scores_low_on_fundamentals(self):
        info = {"trailingPE": 60, "pegRatio": 3.0, "profitMargins": -0.10, "priceToSalesTrailing12Months": 20}
        score, _ = self.analyzer.analyze_fundamentals(info)
        assert score < 30

    def test_empty_info_returns_neutral_fundamentals(self):
        score, notes = self.analyzer.analyze_fundamentals({})
        assert score == 50.0
        assert notes == []

    def test_high_growth_scores_high(self):
        info = {"revenueGrowth": 0.40, "earningsGrowth": 0.30}
        score, _ = self.analyzer.analyze_growth(info)
        assert score > 75

    def test_contracting_revenue_and_earnings_scores_low(self):
        info = {"revenueGrowth": -0.20, "earningsGrowth": -0.30}
        score, _ = self.analyzer.analyze_growth(info)
        assert score < 20


# ── AssetAnalyzer: technicals ───────────────────────────────────
class TestAssetAnalyzerTechnicals:
    def setup_method(self):
        self.analyzer = AssetAnalyzer()

    def test_insufficient_history_returns_neutral(self):
        history = make_price_history(n=10)
        score, notes = self.analyzer.analyze_technicals(history)
        assert score == 50
        assert "Insufficient" in notes[0]

    def test_empty_history_returns_neutral(self):
        score, notes = self.analyzer.analyze_technicals(pd.DataFrame())
        assert score == 50

    def test_sustained_uptrend_scores_above_sustained_downtrend(self):
        uptrend = make_price_history(start=100, daily_return=0.003, n=252)
        downtrend = make_price_history(start=100, daily_return=-0.003, n=252)
        up_score, _ = self.analyzer.analyze_technicals(uptrend)
        down_score, _ = self.analyzer.analyze_technicals(downtrend)
        assert up_score > down_score
        assert up_score > 50
        assert down_score < 50


# ── AssetAnalyzer: risk ─────────────────────────────────────────
class TestAssetAnalyzerRisk:
    def setup_method(self):
        self.analyzer = AssetAnalyzer()

    def test_low_volatility_scores_higher_than_high_volatility(self):
        calm = make_price_history(start=100, daily_return=0.0002, daily_vol=0.003, n=252)
        wild = make_price_history(start=100, daily_return=0.0002, daily_vol=0.08, n=252)
        calm_score, _ = self.analyzer.analyze_risk(calm, {"beta": 0.8})
        wild_score, _ = self.analyzer.analyze_risk(wild, {"beta": 1.8})
        assert calm_score > wild_score

    def test_missing_beta_and_short_history_returns_neutral(self):
        score, notes = self.analyzer.analyze_risk(pd.DataFrame(), {})
        assert score == 50
        assert notes == []


# ── AssetAnalyzer: sentiment ────────────────────────────────────
class TestAssetAnalyzerSentiment:
    def setup_method(self):
        self.analyzer = AssetAnalyzer()

    def test_no_news_returns_neutral(self):
        score, notes = self.analyzer.analyze_sentiment("XYZ", [])
        assert score == 50.0
        assert "neutral" in notes[0].lower()

    def test_all_positive_headlines_scores_high(self):
        news = [{"title": "Company reports record profit and strong growth"},
                {"title": "Analysts upgrade stock on earnings beat"}]
        score, _ = self.analyzer.analyze_sentiment("XYZ", news)
        assert score == 100.0

    def test_all_negative_headlines_scores_low(self):
        news = [{"title": "Company warns of recession and layoff risk"},
                {"title": "Analysts downgrade stock amid bankruptcy fears"}]
        score, _ = self.analyzer.analyze_sentiment("XYZ", news)
        assert score == 0.0


# ── AssetAnalyzer: weighted_score / calibrate_score / labels ───
class TestAssetAnalyzerAggregation:
    def setup_method(self):
        self.analyzer = AssetAnalyzer()

    def test_weighted_score_all_100_is_100(self):
        scores = {k: 100 for k in ("fundamentals", "growth", "health", "dividend", "trend", "risk", "sentiment")}
        assert self.analyzer.weighted_score(scores, {}) == 100

    def test_weighted_score_all_0_is_0(self):
        scores = {k: 0 for k in ("fundamentals", "growth", "health", "dividend", "trend", "risk", "sentiment")}
        assert self.analyzer.weighted_score(scores, {}) == 0

    def test_weighted_score_respects_profile_weights(self):
        scores = {"fundamentals": 100, "growth": 0, "health": 0, "dividend": 0, "trend": 0, "risk": 0, "sentiment": 0}
        profile = {"score_weights": {"fundamentals": 1.0, "growth": 0, "health": 0,
                                      "dividend": 0, "trend": 0, "risk": 0, "sentiment": 0}}
        assert self.analyzer.weighted_score(scores, profile) == 100

    @pytest.mark.parametrize("raw,expected", [
        (90, 96),   # >=78: raw*1.07 -> 96.3 -> int 96
        (70, 72),   # >=68: raw*1.04 -> 72.8 -> int 72
        (60, 60),   # >=58: unchanged
        (50, 48),   # >=48: raw*0.96 -> 48.0 -> int 48
        (20, 17),   # else: raw*0.88 -> 17.6 -> int 17
    ])
    def test_calibrate_score_bands(self, raw, expected):
        assert self.analyzer.calibrate_score(raw) == expected

    @pytest.mark.parametrize("score,expected_label", [
        (95, "Strong Buy"), (88, "Strong Buy"),
        (80, "Buy"), (72, "Buy"),
        (60, "Hold"), (55, "Hold"),
        (45, "Reduce"), (38, "Reduce"),
        (10, "Avoid"),
    ])
    def test_score_label_boundaries(self, score, expected_label):
        label, _color = self.analyzer.score_label(score)
        assert label == expected_label

    @pytest.mark.parametrize("risk_score,expected", [
        (75, "LOW"), (70, "LOW"),
        (60, "MEDIUM"), (50, "MEDIUM"),
        (40, "HIGH"), (35, "HIGH"),
        (10, "VERY HIGH"),
    ])
    def test_risk_label_boundaries(self, risk_score, expected):
        assert self.analyzer.risk_label(risk_score, beta=1.0) == expected


# ── RecommendationEngine ────────────────────────────────────────
class TestRecommendationEngine:
    def setup_method(self):
        self.engine = RecommendationEngine()

    def test_recommend_never_exceeds_budget(self):
        analyses = {
            f"TICK{i}": {"score": 80, "label": "Buy", "color": "#000", "top_note": "x"}
            for i in range(10)
        }
        profile = {"etf_pct": 70, "max_single_pct": 35, "min_score": 50,
                   "preferred_tickers": []}
        recs = self.engine.recommend(analyses, "NEUTRAL", budget=200.0, profile=profile)
        total = sum(r["amount"] for r in recs)
        assert total <= 200.0 + 1e-6
        assert len(recs) <= 5

    def test_recommend_filters_out_low_score_candidates(self):
        analyses = {
            "GOOD": {"score": 90, "label": "Buy", "color": "#000", "top_note": "x"},
            "BAD":  {"score": 10, "label": "Avoid", "color": "#000", "top_note": "x"},
        }
        profile = {"etf_pct": 70, "max_single_pct": 35, "min_score": 50,
                   "preferred_tickers": []}
        recs = self.engine.recommend(analyses, "NEUTRAL", budget=200.0, profile=profile)
        tickers = [r["ticker"] for r in recs]
        assert "GOOD" in tickers
        assert "BAD" not in tickers
