"""
Unit tests for InvestmentBriefEngine in stock_advisor.py, using synthetic
(hand-built) inputs instead of live yfinance/market data.

This is the engine behind the human-facing "brief" — best pick, confidence
label, allocation split, and narrative text a user actually reads — so a
bug here (bad clamping, an off-by-one in truncation, wrong regime branch)
changes what the tool tells someone to do with real money, even though the
tool itself never trades. Previously untested (see IMPROVEMENT_LOG.md);
no overlap with the open PR #5 (tests/test_scoring.py regression tests) or
PR #6 (tests/test_portfolio.py) — different class, different file.

Run with: pytest tests/ -v
"""
import pytest

from stock_advisor import InvestmentBriefEngine, USER_PROFILES


@pytest.fixture
def engine():
    return InvestmentBriefEngine()


@pytest.fixture
def profile():
    return dict(USER_PROFILES["balanced"])


def make_analysis(score=60, confidence=50, summary="", bear_case=""):
    return {
        "score": score,
        "confidence": confidence,
        "narrative": {"summary": summary, "bear_case": bear_case},
    }


def make_rec(ticker, score=60, reason="Solid setup."):
    return {
        "ticker": ticker, "score": score, "label": "BUY", "color": "#3fb950",
        "amount": 100.0, "type": "Stock", "reason": reason, "etf_info": None,
    }


def make_regime(regime="NEUTRAL", bull=2, bear=2, signals=None):
    advice = {
        "BULLISH": "Risk-on.", "NEUTRAL": "Balanced.", "DEFENSIVE": "Risk-off.",
    }[regime]
    return {
        "regime": regime, "signals": signals or [], "advice": advice,
        "bull_pts": bull, "bear_pts": bear,
    }


# ─────────────────────────────────────────────────────────────
#  _overall_confidence
# ─────────────────────────────────────────────────────────────
class TestOverallConfidence:
    def test_clamped_to_85_ceiling(self, engine):
        analyses = {"A": make_analysis(confidence=100), "B": make_analysis(confidence=100)}
        conf = engine._overall_confidence(analyses, bull=10, bear=0)
        assert conf == 85

    def test_clamped_to_28_floor(self, engine):
        analyses = {"A": make_analysis(confidence=0)}
        conf = engine._overall_confidence(analyses, bull=0, bear=0)
        assert conf == 28

    def test_mixed_regime_and_confidence_blend(self, engine):
        # regime_clarity = min(100, |bull-bear| * 18) = min(100, 2*18) = 36
        # asset_conf = avg(60, 80) = 70
        # conf = 36*0.40 + 70*0.60 = 14.4 + 42 = 56.4 -> round -> 56
        analyses = {"A": make_analysis(confidence=60), "B": make_analysis(confidence=80)}
        conf = engine._overall_confidence(analyses, bull=5, bear=3)
        assert conf == 56

    def test_empty_analyses_does_not_divide_by_zero(self, engine):
        conf = engine._overall_confidence({}, bull=0, bear=0)
        assert conf == 28  # regime_clarity=0, asset_conf defaults via max(len,1)


# ─────────────────────────────────────────────────────────────
#  _conf_label
# ─────────────────────────────────────────────────────────────
class TestConfLabel:
    @pytest.mark.parametrize("conf,expected", [
        (85, "High"), (72, "High"),
        (71, "Medium"), (55, "Medium"),
        (54, "Low"), (40, "Low"),
        (39, "Very Low"), (0, "Very Low"),
    ])
    def test_boundaries(self, engine, conf, expected):
        assert engine._conf_label(conf) == expected


# ─────────────────────────────────────────────────────────────
#  _best_reason
# ─────────────────────────────────────────────────────────────
class TestBestReason:
    def test_uses_narrative_summary_when_present(self, engine):
        analyses = {"AAPL": make_analysis(summary="Strong fundamentals and momentum.")}
        best = make_rec("AAPL", reason="fallback reason")
        assert engine._best_reason(best, analyses) == "Strong fundamentals and momentum."

    def test_falls_back_to_rec_reason_when_no_narrative_summary(self, engine):
        analyses = {"AAPL": make_analysis(summary="")}
        best = make_rec("AAPL", reason="fallback reason")
        assert engine._best_reason(best, analyses) == "fallback reason"

    def test_falls_back_to_rec_reason_when_ticker_missing_from_analyses(self, engine):
        best = make_rec("MSFT", reason="fallback reason")
        assert engine._best_reason(best, {}) == "fallback reason"

    def test_truncates_long_summary_at_160_chars_with_ellipsis(self, engine):
        long_summary = "x" * 200
        analyses = {"AAPL": make_analysis(summary=long_summary)}
        best = make_rec("AAPL")
        result = engine._best_reason(best, analyses)
        assert result == "x" * 160 + "…"
        assert len(result) == 161

    def test_does_not_truncate_summary_at_exactly_160_chars(self, engine):
        summary = "x" * 160
        analyses = {"AAPL": make_analysis(summary=summary)}
        best = make_rec("AAPL")
        assert engine._best_reason(best, analyses) == summary


# ─────────────────────────────────────────────────────────────
#  _main_risk
# ─────────────────────────────────────────────────────────────
class TestMainRisk:
    def test_prefers_explicit_bearish_signal(self, engine):
        regime_data = make_regime(signals=[("BULLISH", "ignored"), ("BEARISH", "Rates rising fast.")])
        assert engine._main_risk(regime_data, [], {}) == "Rates rising fast."

    def test_prefers_explicit_caution_signal(self, engine):
        regime_data = make_regime(signals=[("CAUTION", "High yields pressure valuations.")])
        assert engine._main_risk(regime_data, [], {}) == "High yields pressure valuations."

    def test_falls_back_to_top_pick_bear_case(self, engine):
        regime_data = make_regime(signals=[("BULLISH", "ignored")])
        analyses = {"AAPL": make_analysis(bear_case="Regulatory risk in core market.")}
        recs = [make_rec("AAPL")]
        assert engine._main_risk(regime_data, recs, analyses) == "Regulatory risk in core market."

    def test_skips_top_pick_bear_case_when_it_is_the_no_risk_placeholder(self, engine):
        regime_data = make_regime(regime="NEUTRAL", signals=[])
        analyses = {"AAPL": make_analysis(bear_case="No significant bear case factors at current levels.")}
        recs = [make_rec("AAPL")]
        assert engine._main_risk(regime_data, recs, analyses) == (
            "Mixed macro signals warrant selective, disciplined positioning."
        )

    def test_falls_back_to_regime_default_when_no_signals_or_recs(self, engine):
        regime_data = make_regime(regime="DEFENSIVE", signals=[])
        assert engine._main_risk(regime_data, [], {}) == (
            "Elevated risk environment — favor capital preservation."
        )

    def test_multi_part_bear_case_takes_only_first_segment(self, engine):
        regime_data = make_regime(signals=[])
        analyses = {"AAPL": make_analysis(bear_case="Valuation stretched | Insider selling | Slowing growth")}
        recs = [make_rec("AAPL")]
        assert engine._main_risk(regime_data, recs, analyses) == "Valuation stretched"


# ─────────────────────────────────────────────────────────────
#  _strategy
# ─────────────────────────────────────────────────────────────
class TestStrategy:
    def test_bullish_high_confidence_is_risk_on(self, engine, profile):
        result = engine._strategy("BULLISH", profile, confidence=70)
        assert "Risk-on" in result
        assert f"{profile['etf_pct']}%" in result

    def test_bullish_low_confidence_is_not_risk_on(self, engine, profile):
        result = engine._strategy("BULLISH", profile, confidence=40)
        assert "Risk-on" not in result
        assert "Balanced approach" in result

    def test_defensive_raises_etf_allocation(self, engine, profile):
        result = engine._strategy("DEFENSIVE", profile, confidence=50)
        raised = min(90, profile["etf_pct"] + 10)
        assert f"toward {raised}%" in result
        assert "Defensive positioning" in result

    def test_defensive_allocation_caps_at_90(self, engine):
        profile = dict(USER_PROFILES["beginner"])  # etf_pct=85, +10 would be 95
        result = engine._strategy("DEFENSIVE", profile, confidence=50)
        assert "toward 90%" in result

    def test_neutral_regime_is_balanced(self, engine, profile):
        result = engine._strategy("NEUTRAL", profile, confidence=60)
        assert "Balanced approach" in result


# ─────────────────────────────────────────────────────────────
#  _market_brief
# ─────────────────────────────────────────────────────────────
class TestMarketBrief:
    def test_includes_regime_intro(self, engine):
        regime_data = make_regime(regime="BULLISH", bull=5, bear=1)
        brief = engine._market_brief(regime_data, {})
        assert "constructive risk-on" in brief

    def test_includes_yield_and_vix_signals_when_present(self, engine):
        regime_data = make_regime(signals=[
            ("BULLISH", "10-yr Treasury yield 3.00% — low rates supportive for equities"),
            ("NEUTRAL", "VIX 20.0 — moderate uncertainty in the market"),
        ])
        brief = engine._market_brief(regime_data, {})
        assert "10-yr Treasury yield 3.00%" in brief
        assert "VIX 20.0" in brief

    def test_reports_buy_count_from_analyses(self, engine):
        regime_data = make_regime()
        analyses = {
            "A": make_analysis(score=80), "B": make_analysis(score=72),
            "C": make_analysis(score=50),
        }
        brief = engine._market_brief(regime_data, analyses)
        assert "2 of 3 analyzed assets currently meet buy criteria." in brief

    def test_momentum_phrase_depends_on_bull_vs_bear(self, engine):
        favors = engine._market_brief(make_regime(bull=5, bear=1), {})
        cautions = engine._market_brief(make_regime(bull=1, bear=5), {})
        assert "Momentum favors risk assets." in favors
        assert "Caution flags outweigh positive signals." in cautions


# ─────────────────────────────────────────────────────────────
#  generate() — full integration of the above
# ─────────────────────────────────────────────────────────────
class TestGenerate:
    def test_full_shape_with_recs(self, engine, profile):
        analyses = {
            "AAPL": make_analysis(score=80, confidence=70, summary="Great momentum."),
            "XOM":  make_analysis(score=30, confidence=40),
        }
        recs = [make_rec("AAPL", score=80, reason="Great momentum.")]
        regime_data = make_regime(regime="BULLISH", bull=5, bear=1)

        brief = engine.generate(analyses, regime_data, recs, profile)

        assert brief["best_ticker"] == "AAPL"
        assert brief["best_score"] == 80
        assert brief["top_picks"] == ["AAPL"]
        assert brief["avoid"] == ["XOM"]
        assert brief["alloc_etf"] == profile["etf_pct"]
        assert brief["alloc_stocks"] == max(0, 85 - profile["etf_pct"])
        assert brief["alloc_cash"] == 15
        assert brief["signal_count"] == {"bull": 5, "bear": 1}
        assert brief["regime"] == "BULLISH"

    def test_no_recs_yields_none_best_and_dash_reason(self, engine, profile):
        regime_data = make_regime()
        brief = engine.generate({}, regime_data, [], profile)
        assert brief["best_ticker"] is None
        assert brief["best_score"] is None
        assert brief["best_reason"] == "—"
        assert brief["top_picks"] == []

    def test_avoid_list_excludes_scores_at_or_above_45_and_caps_at_3(self, engine, profile):
        analyses = {
            "A": make_analysis(score=10), "B": make_analysis(score=20),
            "C": make_analysis(score=30), "D": make_analysis(score=44),
            "E": make_analysis(score=45),  # exactly at threshold: excluded
            "F": make_analysis(score=90),
        }
        regime_data = make_regime()
        brief = engine.generate(analyses, regime_data, [], profile)
        assert brief["avoid"] == ["A", "B", "C"]  # sorted ascending, capped at 3
        assert "E" not in brief["avoid"]

    def test_top_picks_capped_at_3_even_with_more_recs(self, engine, profile):
        recs = [make_rec(t, score=s) for t, s in
                [("A", 90), ("B", 85), ("C", 80), ("D", 75), ("E", 70)]]
        regime_data = make_regime()
        brief = engine.generate({}, regime_data, recs, profile)
        assert brief["top_picks"] == ["A", "B", "C"]

    def test_alloc_stocks_never_negative_for_high_etf_pct_profile(self, engine):
        profile = dict(USER_PROFILES["beginner"])
        profile["etf_pct"] = 95  # 85 - 95 would be negative without the max(0, ...) guard
        regime_data = make_regime()
        brief = engine.generate({}, regime_data, [], profile)
        assert brief["alloc_stocks"] == 0
