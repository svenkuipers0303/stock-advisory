"""
Unit tests for NarrativeEngine in stock_advisor.py — the text-generation
class that turns scores/info dicts into the summary/bull/bear/beginner/risk
strings shown in reports. Purely synthetic inputs, no network access needed
(see IMPROVEMENT_LOG.md — this was the last item on the original
test-coverage checklist, flagged low priority since there's no scoring
logic to regress, but still worth pinning: a future edit that silently
drops a branch or breaks an f-string shouldn't go unnoticed).

Run with: pytest tests/ -v
"""
from stock_advisor import NarrativeEngine


ETF_INFO = {
    "name": "Vanguard S&P 500 ETF",
    "description": "Tracks the S&P 500 index.",
    "why": "Broad, low-cost exposure to large-cap US equities.",
    "expense_ratio": 0.03,
    "dividend_yield_approx": 1.4,
    "overlap": ["SPY", "IVV"],
}


def make_info(**overrides):
    info = {
        "longName": "Example Corp",
        "sector": "Technology",
        "trailingPE": 20.0,
        "forwardPE": None,
        "revenueGrowth": 0.10,
        "earningsGrowth": 0.10,
        "profitMargins": 0.15,
        "freeCashflow": 5e8,
        "dividendYield": 0.01,
        "pegRatio": 1.0,
        "returnOnEquity": 0.10,
        "beta": 1.0,
        "debtToEquity": 50.0,
        "marketCap": 5e9,
    }
    info.update(overrides)
    return info


def make_scores(**overrides):
    scores = {"total": 58, "growth": 50, "health": 50, "trend": 50, "risk": 50}
    scores.update(overrides)
    return scores


class TestSummary:
    def test_stock_score_buckets_pick_distinct_openers(self):
        eng = NarrativeEngine()
        openers = set()
        for total in (80, 60, 50, 30):
            text = eng._summary("XYZ", make_info(), make_scores(total=total), {}, False, None)
            openers.add(text.split(".")[0])
        assert len(openers) == 4

    def test_pe_bucket_labels(self):
        eng = NarrativeEngine()
        cheap = eng._summary("XYZ", make_info(trailingPE=10), make_scores(), {}, False, None)
        expensive = eng._summary("XYZ", make_info(trailingPE=50), make_scores(), {}, False, None)
        assert "value opportunity" in cheap
        assert "Elevated" in expensive

    def test_revenue_growth_and_margin_and_sector_lines_present(self):
        eng = NarrativeEngine()
        text = eng._summary(
            "XYZ", make_info(revenueGrowth=0.25, profitMargins=0.30, sector="Technology"),
            make_scores(), {}, False, None,
        )
        assert "well above market" in text
        assert "moat" in text
        assert "AI and cloud infrastructure" in text

    def test_declining_revenue_line(self):
        eng = NarrativeEngine()
        text = eng._summary("XYZ", make_info(revenueGrowth=-0.10), make_scores(), {}, False, None)
        assert "declining" in text

    def test_unknown_sector_adds_no_theme_line(self):
        eng = NarrativeEngine()
        text = eng._summary("XYZ", make_info(sector="Unobtainium Mining"), make_scores(), {}, False, None)
        assert "Unobtainium" not in text

    def test_etf_path_uses_etf_info_not_stock_fields(self):
        eng = NarrativeEngine()
        text = eng._summary("VOO", {}, make_scores(), {}, True, ETF_INFO)
        assert ETF_INFO["description"] in text
        assert ETF_INFO["why"] in text
        assert "0.03%/year" in text
        assert "ultra-low cost" in text
        assert "1.4%" in text
        assert "SPY, IVV" in text

    def test_etf_cost_label_thresholds(self):
        eng = NarrativeEngine()
        low = eng._summary("X", {}, make_scores(), {}, True, {**ETF_INFO, "expense_ratio": 0.10})
        moderate = eng._summary("X", {}, make_scores(), {}, True, {**ETF_INFO, "expense_ratio": 0.30})
        assert "low cost" in low and "ultra-low" not in low
        assert "moderate cost" in moderate

    def test_etf_zero_dividend_and_no_overlap_omit_those_lines(self):
        eng = NarrativeEngine()
        info = {**ETF_INFO, "dividend_yield_approx": 0, "overlap": []}
        text = eng._summary("X", {}, make_scores(), {}, True, info)
        assert "dividends" not in text
        assert "overlap" not in text


class TestBullCase:
    def test_empty_when_no_factors_clear_thresholds(self):
        eng = NarrativeEngine()
        weak_info = make_info(revenueGrowth=0, earningsGrowth=0, freeCashflow=0,
                               dividendYield=0, returnOnEquity=0, pegRatio=None)
        weak_scores = make_scores(growth=40, health=40, trend=40)
        text = eng._bull_case("XYZ", weak_info, weak_scores, False, None)
        assert text == "No strong bull case factors identified at current metrics."

    def test_growth_and_health_and_trend_factors_included(self):
        eng = NarrativeEngine()
        # Keep to one growth-side factor and skip health entirely so the
        # bull_case()-internal [:3] cap doesn't crowd out the trend line.
        info = make_info(revenueGrowth=0.20, earningsGrowth=0, freeCashflow=0, returnOnEquity=0)
        scores = make_scores(growth=70, health=40, trend=70)
        text = eng._bull_case("XYZ", info, scores, False, None)
        assert "revenue growth" in text
        assert "Bullish technical trend" in text

    def test_capped_at_three_factors(self):
        eng = NarrativeEngine()
        info = make_info(revenueGrowth=0.30, earningsGrowth=0.30, freeCashflow=5e9,
                          returnOnEquity=0.30, pegRatio=0.5, dividendYield=0.05)
        scores = make_scores(growth=80, health=80, trend=80)
        text = eng._bull_case("XYZ", info, scores, False, None)
        assert len(text.split(" | ")) == 3

    def test_etf_path(self):
        eng = NarrativeEngine()
        info = {**ETF_INFO, "dividend_yield_approx": 2.5}
        text = eng._bull_case("VOO", {}, make_scores(), True, info)
        assert ETF_INFO["why"] in text
        assert "annual dividend yield" in text
        assert "Expense ratio of just" in text


class TestBearCase:
    def test_empty_when_nothing_flagged(self):
        eng = NarrativeEngine()
        safe_info = make_info(trailingPE=15, beta=1.0, debtToEquity=50, revenueGrowth=0.1, profitMargins=0.2)
        safe_scores = make_scores(trend=60, risk=60)
        text = eng._bear_case("XYZ", safe_info, safe_scores, False)
        assert text == "No significant bear case factors at current levels."

    def test_high_pe_beta_debt_flagged(self):
        eng = NarrativeEngine()
        risky_info = make_info(trailingPE=50, beta=2.0, debtToEquity=250)
        text = eng._bear_case("XYZ", risky_info, make_scores(), False)
        assert "P/E" in text
        assert "Beta" in text
        assert "Debt/equity" in text

    def test_capped_at_three_factors(self):
        eng = NarrativeEngine()
        risky_info = make_info(trailingPE=50, beta=2.0, debtToEquity=250, revenueGrowth=-0.10, profitMargins=0.01)
        risky_scores = make_scores(trend=30, risk=30)
        text = eng._bear_case("XYZ", risky_info, risky_scores, False)
        assert len(text.split(" | ")) == 3

    def test_zero_margin_does_not_falsely_trigger_thin_margin_line(self):
        # margin == 0 usually means missing data, not a genuinely thin margin —
        # the `margin != 0` guard should suppress this line in that case.
        eng = NarrativeEngine()
        info = make_info(trailingPE=15, beta=1.0, debtToEquity=50, revenueGrowth=0.1, profitMargins=0)
        text = eng._bear_case("XYZ", info, make_scores(trend=60, risk=60), False)
        assert "margins" not in text

    def test_etf_appends_market_correction_line_and_skips_stock_only_checks(self):
        eng = NarrativeEngine()
        text = eng._bear_case("VOO", make_info(trailingPE=50, beta=2.0), make_scores(), True)
        assert "Market-wide corrections" in text
        assert "P/E" not in text


class TestBeginnerNote:
    def test_etf_path_includes_dividend_line_when_meaningful(self):
        eng = NarrativeEngine()
        text = eng._beginner_note("VOO", {}, make_scores(), True, ETF_INFO)
        assert "pre-built basket" in text
        assert "1.4%" in text

    def test_etf_path_omits_dividend_line_when_negligible(self):
        eng = NarrativeEngine()
        text = eng._beginner_note("X", {}, make_scores(), True, {**ETF_INFO, "dividend_yield_approx": 0.1})
        assert "dividends per year" not in text

    def test_stock_path_cap_label_buckets(self):
        eng = NarrativeEngine()
        mega = eng._beginner_note("X", make_info(marketCap=5e11), make_scores(), False, None)
        small = eng._beginner_note("X", make_info(marketCap=5e8), make_scores(), False, None)
        assert "mega-cap" in mega
        assert "small-cap" in small

    def test_stock_path_pe_note_present_and_absent(self):
        eng = NarrativeEngine()
        with_pe = eng._beginner_note("X", make_info(trailingPE=20), make_scores(), False, None)
        without_pe = eng._beginner_note("X", make_info(trailingPE=None, forwardPE=None), make_scores(), False, None)
        assert "P/E ratio" in with_pe
        assert "P/E ratio" not in without_pe


class TestRiskNote:
    def test_all_four_risk_buckets_produce_distinct_levels(self):
        eng = NarrativeEngine()
        levels = {
            eng._risk_note("X", make_info(beta=1.0), make_scores(risk=r)).split(":")[0]
            for r in (80, 60, 45, 20)
        }
        assert levels == {"LOW RISK", "MODERATE RISK", "ELEVATED RISK", "HIGH RISK"}

    def test_beta_formatted_into_note(self):
        eng = NarrativeEngine()
        text = eng._risk_note("X", make_info(beta=1.75), make_scores(risk=50))
        assert "Beta: 1.75" in text


class TestGenerate:
    def test_returns_all_five_keys_for_stock(self):
        eng = NarrativeEngine()
        result = eng.generate("XYZ", make_info(), make_scores(), {}, etf_info=None)
        assert set(result.keys()) == {"summary", "bull_case", "bear_case", "beginner", "risk_note"}
        assert all(isinstance(v, str) and v for v in result.values())

    def test_etf_info_truthy_switches_to_etf_path(self):
        eng = NarrativeEngine()
        result = eng.generate("VOO", {}, make_scores(), {}, etf_info=ETF_INFO)
        assert ETF_INFO["description"] in result["summary"]
        assert "pre-built basket" in result["beginner"]

    def test_empty_etf_info_dict_is_treated_as_not_etf(self):
        # generate() uses `is_etf = bool(etf_info)` — an empty dict is falsy,
        # so this must fall through to the stock path, not crash on missing
        # etf_info keys.
        eng = NarrativeEngine()
        result = eng.generate("XYZ", make_info(), make_scores(), {}, etf_info={})
        assert "pre-built basket" not in result["beginner"]
