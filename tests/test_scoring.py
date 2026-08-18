"""
Unit tests for the scoring engine in stock_advisor.py, using synthetic
(hand-built) inputs instead of live yfinance data.

Purpose: catch regressions in the scoring logic itself (e.g. "does a
leveraged, unprofitable company correctly score low on financial health?")
without depending on network access or real market data, which this
environment cannot reach (yfinance's Yahoo Finance hosts are egress-blocked
here — see IMPROVEMENT_LOG.md).

Run with: pytest tests/ -v
"""
import numpy as np
import pandas as pd
import pytest

from stock_advisor import (
    AssetAnalyzer,
    DividendAnalyzer,
    FinancialHealthAnalyzer,
    MarketRegimeDetector,
    RecommendationEngine,
    USER_PROFILES,
)


# ─────────────────────────────────────────────────────────────
#  Helpers to build synthetic OHLCV history
# ─────────────────────────────────────────────────────────────
def make_history(prices, freq="B"):
    """Build a minimal OHLCV DataFrame from a list/array of closing prices."""
    n = len(prices)
    idx = pd.date_range("2024-01-01", periods=n, freq=freq)
    close = pd.Series(prices, index=idx, dtype=float)
    return pd.DataFrame({
        "Open": close, "High": close * 1.001, "Low": close * 0.999, "Close": close,
        "Volume": 1_000_000,
    })


def steady_uptrend(n=260, start=100.0, daily_drift=0.0015, noise=0.0):
    rng = np.random.default_rng(42)
    rets = np.full(n, daily_drift)
    if noise:
        rets = rets + rng.normal(0, noise, n)
    prices = start * np.cumprod(1 + rets)
    return make_history(prices)


def steady_downtrend(n=260, start=100.0, daily_drift=-0.0015, noise=0.0):
    return steady_uptrend(n=n, start=start, daily_drift=daily_drift, noise=noise)


def volatile_series(n=260, start=100.0, daily_vol=0.05):
    rng = np.random.default_rng(7)
    rets = rng.normal(0, daily_vol, n)
    prices = start * np.cumprod(1 + rets)
    return make_history(np.clip(prices, 1, None))


def flat_series(n=260, start=100.0):
    return make_history(np.full(n, start))


# ─────────────────────────────────────────────────────────────
#  FinancialHealthAnalyzer
# ─────────────────────────────────────────────────────────────
class TestFinancialHealthAnalyzer:
    def setup_method(self):
        self.analyzer = FinancialHealthAnalyzer()

    def test_fortress_balance_sheet_scores_high(self):
        info = {
            "freeCashflow": 5e9,
            "debtToEquity": 15,
            "returnOnEquity": 0.30,
            "currentRatio": 3.0,
        }
        score, notes = self.analyzer.analyze(info)
        assert score >= 85
        assert notes  # every branch above should leave an explanatory note

    def test_leveraged_unprofitable_company_scores_low(self):
        """The exact sanity check called out in IMPROVEMENT_LOG.md."""
        info = {
            "freeCashflow": -2e9,
            "debtToEquity": 350,
            "returnOnEquity": -0.10,
            "currentRatio": 0.6,
        }
        score, notes = self.analyzer.analyze(info)
        assert score <= 20
        assert notes

    def test_missing_fields_falls_back_to_neutral_baseline(self):
        score, notes = self.analyzer.analyze({})
        assert score == 50.0
        assert notes == []

    def test_score_always_clamped_to_0_100(self):
        # Stack every negative branch to try to push the raw score below 0.
        info = {
            "freeCashflow": -1e9,
            "debtToEquity": 500,
            "returnOnEquity": -0.5,
            "currentRatio": 0.2,
        }
        score, _ = self.analyzer.analyze(info)
        assert 0.0 <= score <= 100.0


# ─────────────────────────────────────────────────────────────
#  DividendAnalyzer
# ─────────────────────────────────────────────────────────────
class TestDividendAnalyzer:
    def setup_method(self):
        self.analyzer = DividendAnalyzer()

    def test_no_dividend_is_neutral_not_penalized(self):
        score, notes = self.analyzer.analyze({"dividendYield": 0}, pd.DataFrame())
        assert score == 50.0
        assert "growth/reinvestment" in notes[0]

    def test_well_covered_moderate_yield_scores_high(self):
        info = {"dividendYield": 0.035, "payoutRatio": 0.30}
        score, notes = self.analyzer.analyze(info, pd.DataFrame())
        assert score > 70

    def test_yield_trap_flagged_and_penalized_vs_moderate_yield(self):
        trap = {"dividendYield": 0.12, "payoutRatio": 0.30}
        moderate = {"dividendYield": 0.035, "payoutRatio": 0.30}
        trap_score, trap_notes = self.analyzer.analyze(trap, pd.DataFrame())
        moderate_score, _ = self.analyzer.analyze(moderate, pd.DataFrame())
        assert "yield trap" in trap_notes[0].lower()
        assert trap_score < moderate_score

    def test_unsustainable_payout_ratio_penalized(self):
        info = {"dividendYield": 0.04, "payoutRatio": 0.95}
        score, notes = self.analyzer.analyze(info, pd.DataFrame())
        assert any("unsustainable" in n.lower() for n in notes)
        assert score < 50 + 22  # payout penalty should offset the yield bonus


# ─────────────────────────────────────────────────────────────
#  AssetAnalyzer.analyze_fundamentals / analyze_growth
# ─────────────────────────────────────────────────────────────
class TestFundamentalsAndGrowth:
    def setup_method(self):
        self.analyzer = AssetAnalyzer()

    def test_cheap_profitable_stock_scores_high_on_fundamentals(self):
        info = {"trailingPE": 10, "pegRatio": 0.6, "profitMargins": 0.35, "priceToSalesTrailing12Months": 1.5}
        score, _ = self.analyzer.analyze_fundamentals(info)
        assert score >= 90

    def test_expensive_unprofitable_stock_scores_low_on_fundamentals(self):
        info = {"trailingPE": 60, "pegRatio": 3.0, "profitMargins": -0.15, "priceToSalesTrailing12Months": 20}
        score, _ = self.analyzer.analyze_fundamentals(info)
        assert score < 20

    def test_missing_metrics_falls_back_to_neutral(self):
        score, notes = self.analyzer.analyze_fundamentals({})
        assert score == 50.0
        assert notes == []

    def test_hypergrowth_scores_high_on_growth(self):
        info = {"revenueGrowth": 0.45, "earningsGrowth": 0.30}
        score, _ = self.analyzer.analyze_growth(info)
        assert score >= 90

    def test_contracting_revenue_and_earnings_scores_low_on_growth(self):
        info = {"revenueGrowth": -0.25, "earningsGrowth": -0.30}
        score, _ = self.analyzer.analyze_growth(info)
        assert score < 15


# ─────────────────────────────────────────────────────────────
#  AssetAnalyzer.analyze_technicals
# ─────────────────────────────────────────────────────────────
class TestTechnicals:
    def setup_method(self):
        self.analyzer = AssetAnalyzer()

    def test_insufficient_history_returns_neutral_default(self):
        short_history = make_history([100.0] * 20)
        score, notes = self.analyzer.analyze_technicals(short_history)
        assert score == 50
        assert "Insufficient" in notes[0]

    def test_empty_history_returns_neutral_default(self):
        score, notes = self.analyzer.analyze_technicals(pd.DataFrame())
        assert score == 50

    def test_sustained_uptrend_scores_above_neutral(self):
        history = steady_uptrend(n=260, daily_drift=0.002)
        score, notes = self.analyzer.analyze_technicals(history)
        assert score > 60
        assert any("uptrend" in n.lower() for n in notes)

    def test_sustained_downtrend_scores_below_neutral(self):
        history = steady_downtrend(n=260, daily_drift=-0.002)
        score, notes = self.analyzer.analyze_technicals(history)
        assert score < 40
        assert any("downtrend" in n.lower() for n in notes)

    def test_zero_price_63_bars_back_does_not_produce_inf_momentum(self):
        # Regression test for the divide-by-zero bug fixed 2026-08-03
        # (IMPROVEMENT_LOG.md): yfinance occasionally emits a literal 0.0
        # close (not NaN) on thin/halted/recently-relisted tickers. Before
        # the fix, `(price - close.iloc[-63]) / close.iloc[-63]` on a zero
        # denominator produced +inf momentum and a phantom 90/100 score.
        rng = np.random.default_rng(42)
        n = 260
        prices = np.linspace(50.0, 100.0, n) + rng.normal(0, 0.3, n)
        prices[-63] = 0.0  # corrupted data point, 63 bars back from the end
        history = make_history(prices)

        score, notes = self.analyzer.analyze_technicals(history)

        assert np.isfinite(score)
        assert 0.0 <= score <= 100.0
        assert not any("inf" in n.lower() or "nan" in n.lower() for n in notes)


# ─────────────────────────────────────────────────────────────
#  AssetAnalyzer.analyze_risk
# ─────────────────────────────────────────────────────────────
class TestRisk:
    def setup_method(self):
        self.analyzer = AssetAnalyzer()

    def test_low_volatility_flat_series_scores_high(self):
        history = flat_series(n=260)
        score, notes = self.analyzer.analyze_risk(history, {})
        assert score >= 75

    def test_high_volatility_series_scores_low(self):
        history = volatile_series(n=260, daily_vol=0.06)
        score, _ = self.analyzer.analyze_risk(history, {})
        assert score < 40

    def test_high_beta_reduces_score_vs_low_beta(self):
        history = flat_series(n=260)
        low_beta_score, _ = self.analyzer.analyze_risk(history, {"beta": 0.4})
        high_beta_score, _ = self.analyzer.analyze_risk(history, {"beta": 1.8})
        assert high_beta_score < low_beta_score

    def test_short_history_skips_volatility_but_beta_still_applies(self):
        history = make_history([100.0] * 5)
        score, notes = self.analyzer.analyze_risk(history, {"beta": 0.3})
        # baseline (50) + beta bonus only, since len(history) <= 20 skips the vol/drawdown branch
        assert score == 50 + 12

    def test_zero_price_in_history_does_not_corrupt_risk_score(self):
        # Regression test for the divide-by-zero bug fixed 2026-08-03
        # (IMPROVEMENT_LOG.md): a single 0.0 close made rolling_max's
        # ((close - rolling_max) / rolling_max) drawdown calc produce
        # nan volatility and a phantom -100% "severe drawdown", driving
        # an otherwise-healthy price series down to 7/100.
        rng = np.random.default_rng(42)
        n = 260
        prices = np.linspace(50.0, 100.0, n) + rng.normal(0, 0.3, n)
        prices[-63] = 0.0
        history = make_history(prices)

        score, notes = self.analyzer.analyze_risk(history, {})

        assert np.isfinite(score)
        assert 0.0 <= score <= 100.0
        assert not any("nan" in n.lower() for n in notes)
        assert not any("-100.0%" in n for n in notes)
        # a steady 50->100 uptrend has no real severe drawdown; the glitch
        # must not drag this into "severe historical drawdown" territory
        assert score >= 60


# ─────────────────────────────────────────────────────────────
#  AssetAnalyzer.weighted_score / calibrate_score / score_label / risk_label
# ─────────────────────────────────────────────────────────────
class TestScoreComposition:
    def setup_method(self):
        self.analyzer = AssetAnalyzer()

    def test_weighted_score_matches_manual_calculation(self):
        scores = {"fundamentals": 80, "growth": 60, "health": 70,
                  "dividend": 50, "trend": 90, "risk": 40, "sentiment": 55}
        profile = USER_PROFILES["balanced"]
        expected = sum(scores[k] * profile["score_weights"][k] for k in scores)
        # weighted_score keys off "trend"/"risk" names but the profile dict uses the same keys
        result = self.analyzer.weighted_score(scores, profile)
        assert result == int(max(0, min(100, expected)))

    def test_weighted_score_defaults_when_profile_has_no_weights(self):
        scores = {"fundamentals": 100, "growth": 0, "health": 0,
                  "dividend": 0, "trend": 0, "risk": 0, "sentiment": 0}
        result = self.analyzer.weighted_score(scores, {})
        assert result == 25  # default fundamentals weight is 0.25

    @pytest.mark.parametrize("raw,expected", [
        (100, 100),  # 100*1.07 clamped to 100
        (80, min(100, int(80 * 1.07))),
        (70, int(70 * 1.04)),
        (60, 60),          # 58-67 band passes through unchanged
        (50, int(50 * 0.96)),
        (10, int(10 * 0.88)),
        (0, 0),
    ])
    def test_calibrate_score_bands(self, raw, expected):
        assert self.analyzer.calibrate_score(raw) == expected

    def test_calibrate_score_never_exceeds_100(self):
        assert self.analyzer.calibrate_score(99) <= 100

    @pytest.mark.parametrize("score,label", [
        (95, "Strong Buy"), (88, "Strong Buy"),
        (80, "Buy"), (72, "Buy"),
        (60, "Hold"), (55, "Hold"),
        (45, "Reduce"), (38, "Reduce"),
        (20, "Avoid"), (0, "Avoid"),
    ])
    def test_score_label_boundaries(self, score, label):
        result_label, _color = self.analyzer.score_label(score)
        assert result_label == label

    @pytest.mark.parametrize("score,label", [
        (80, "LOW"), (70, "LOW"),
        (60, "MEDIUM"), (50, "MEDIUM"),
        (40, "HIGH"), (35, "HIGH"),
        (20, "VERY HIGH"),
    ])
    def test_risk_label_boundaries(self, score, label):
        assert self.analyzer.risk_label(score, beta=1.0) == label


# ─────────────────────────────────────────────────────────────
#  AssetAnalyzer.compute_confidence
# ─────────────────────────────────────────────────────────────
class TestComputeConfidence:
    def setup_method(self):
        self.analyzer = AssetAnalyzer()

    def test_confidence_is_always_within_bounds(self):
        rich_info = {
            "trailingPE": 20, "revenueGrowth": 0.1, "profitMargins": 0.2,
            "freeCashflow": 1e9, "debtToEquity": 50, "beta": 1.0, "returnOnEquity": 0.15,
        }
        scores = {"fundamentals": 90, "trend": 10, "risk": 100}
        regime = {"bull_pts": 6, "bear_pts": 0}
        conf, level = self.analyzer.compute_confidence(rich_info, scores, regime)
        assert 25 <= conf <= 88
        assert level in ("High", "Medium", "Low", "Very Low")

    def test_sparse_data_yields_lower_confidence_than_rich_data(self):
        scores = {"fundamentals": 60, "trend": 60, "risk": 60}
        regime = {"bull_pts": 3, "bear_pts": 3}  # no clarity either way
        sparse_conf, _ = self.analyzer.compute_confidence({}, scores, regime)

        rich_info = {
            "trailingPE": 20, "revenueGrowth": 0.1, "profitMargins": 0.2,
            "freeCashflow": 1e9, "debtToEquity": 50, "beta": 1.0, "returnOnEquity": 0.15,
        }
        rich_conf, _ = self.analyzer.compute_confidence(rich_info, scores, regime)
        assert sparse_conf < rich_conf

    def test_confidence_never_exceeds_hard_cap_of_88(self):
        # Try to max out every input component.
        rich_info = {
            "trailingPE": 20, "revenueGrowth": 0.1, "profitMargins": 0.2,
            "freeCashflow": 1e9, "debtToEquity": 50, "beta": 1.0, "returnOnEquity": 0.15,
        }
        scores = {"fundamentals": 100, "trend": 100, "risk": 100}
        regime = {"bull_pts": 10, "bear_pts": 0}
        conf, _ = self.analyzer.compute_confidence(rich_info, scores, regime)
        assert conf <= 88


# ─────────────────────────────────────────────────────────────
#  MarketRegimeDetector
# ─────────────────────────────────────────────────────────────
class TestMarketRegimeDetector:
    def setup_method(self):
        self.detector = MarketRegimeDetector()

    def _series(self, prices):
        idx = pd.date_range("2024-01-01", periods=len(prices), freq="B")
        return pd.Series(prices, index=idx, dtype=float)

    def test_bullish_inputs_yield_bullish_regime(self):
        sp = self._series(list(np.linspace(90, 110, 220)))   # trending up, above both MAs
        nasdaq = self._series(list(np.linspace(90, 110, 220)))
        vix = self._series([15.0] * 220)                      # low fear
        yield_ = self._series([3.0] * 220)                    # low rates
        market_data = {"sp500": sp, "nasdaq": nasdaq, "vix": vix, "yield": yield_}

        result = self.detector.detect(market_data)
        assert result["regime"] == "BULLISH"
        assert result["bull_pts"] > result["bear_pts"]

    def test_bearish_inputs_yield_defensive_regime(self):
        sp = self._series(list(np.linspace(110, 90, 220)))    # trending down
        nasdaq = self._series(list(np.linspace(110, 90, 220)))
        vix = self._series([35.0] * 220)                      # elevated fear
        yield_ = self._series([5.0] * 220)                    # high rates
        market_data = {"sp500": sp, "nasdaq": nasdaq, "vix": vix, "yield": yield_}

        result = self.detector.detect(market_data)
        assert result["regime"] == "DEFENSIVE"
        assert result["bear_pts"] > result["bull_pts"]

    def test_missing_market_data_defaults_to_neutral(self):
        result = self.detector.detect({})
        assert result["regime"] == "NEUTRAL"
        assert result["signals"] == []


# ─────────────────────────────────────────────────────────────
#  RecommendationEngine — budget/allocation correctness
# ─────────────────────────────────────────────────────────────
class TestRecommendationEngine:
    def setup_method(self):
        self.engine = RecommendationEngine()

    def _analysis(self, score, label="Buy", color="#56d364"):
        return {"score": score, "label": label, "color": color, "narrative": {"summary": "test"}}

    def test_no_recommendation_exceeds_max_single_pct(self):
        analyses = {
            "VOO": self._analysis(90),
            "AAPL": self._analysis(88),
            "MSFT": self._analysis(85),
        }
        profile = USER_PROFILES["balanced"]
        budget = 200.0
        recs = self.engine.recommend(analyses, "NEUTRAL", budget, profile)
        max_single = budget * (profile["max_single_pct"] / 100)
        assert recs  # sanity: something was recommended
        for r in recs:
            assert r["amount"] <= max_single + 1e-6

    def test_low_scoring_assets_are_excluded(self):
        analyses = {
            "JUNK": self._analysis(10, label="Avoid"),
        }
        profile = USER_PROFILES["balanced"]
        recs = self.engine.recommend(analyses, "NEUTRAL", 200.0, profile)
        assert recs == []

    def test_recommendations_capped_at_five(self):
        analyses = {f"TICK{i}": self._analysis(90 - i) for i in range(10)}
        profile = USER_PROFILES["balanced"]
        recs = self.engine.recommend(analyses, "NEUTRAL", 200.0, profile)
        assert len(recs) <= 5

    def test_higher_regime_bar_in_defensive_regime(self):
        # A score that clears NEUTRAL's bar but not DEFENSIVE's should only
        # be recommended in the less demanding regime.
        analyses = {"MID": self._analysis(60)}
        profile = {**USER_PROFILES["balanced"], "min_score": 0}
        neutral_recs = self.engine.recommend(analyses, "NEUTRAL", 200.0, profile)
        defensive_recs = self.engine.recommend(analyses, "DEFENSIVE", 200.0, profile)
        assert len(neutral_recs) == 1
        assert len(defensive_recs) == 0
