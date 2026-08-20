"""
Unit tests for PortfolioManager in stock_advisor.py, using a temp file for
storage and a mocked yfinance.Ticker for pricing — no filesystem side effects
outside pytest's tmp_path, no network access.

Purpose: this class was flagged as an open test-coverage gap in
IMPROVEMENT_LOG.md (2026-08-04/08-05 entries) — "needs filesystem + yfinance
mocking, not synthetic-input unit tests" — since it reads/writes portfolio.json
directly and calls yf.Ticker(...).history() itself rather than going through
DataFetcher.

Run with: pytest tests/ -v
"""
import json
from unittest.mock import patch

import pandas as pd
import pytest

from stock_advisor import PortfolioManager


def _price_history(price):
    """A minimal 5-day OHLCV frame whose last Close is `price`."""
    idx = pd.date_range("2026-01-01", periods=5, freq="B")
    return pd.DataFrame({"Close": [price] * 5}, index=idx)


def _empty_history():
    return pd.DataFrame({"Close": []})


@pytest.fixture
def portfolio_path(tmp_path):
    return str(tmp_path / "portfolio.json")


# ─────────────────────────────────────────────────────────────
#  _ensure_file / load / save
# ─────────────────────────────────────────────────────────────
class TestPersistence:
    def test_ensure_file_creates_default_structure_on_first_use(self, portfolio_path):
        pm = PortfolioManager(portfolio_path)

        data = pm.load()

        assert data["holdings"] == []
        assert "monthly_budget" in data["settings"]
        assert "created" in data["settings"]

    def test_ensure_file_does_not_overwrite_existing_data(self, portfolio_path):
        PortfolioManager(portfolio_path)  # creates the default file
        with open(portfolio_path, "w", encoding="utf-8") as f:
            json.dump({"settings": {}, "holdings": [{"ticker": "AAPL"}]}, f)

        pm = PortfolioManager(portfolio_path)  # __init__ calls _ensure_file again

        assert pm.load()["holdings"] == [{"ticker": "AAPL"}]

    def test_save_then_load_roundtrips(self, portfolio_path):
        pm = PortfolioManager(portfolio_path)
        data = {"settings": {"monthly_budget": 500.0}, "holdings": [
            {"ticker": "VOO", "quantity": 2, "total_invested": 800.0},
        ]}

        pm.save(data)

        assert pm.load() == data


# ─────────────────────────────────────────────────────────────
#  get_summary
# ─────────────────────────────────────────────────────────────
class TestGetSummary:
    def _seed(self, pm, holdings):
        pm.save({"settings": {}, "holdings": holdings})

    def test_computes_price_value_and_pnl_for_a_winning_position(self, portfolio_path):
        pm = PortfolioManager(portfolio_path)
        self._seed(pm, [{"ticker": "AAPL", "quantity": 10, "total_invested": 1000.0}])

        with patch("stock_advisor.yf.Ticker") as mock_ticker:
            mock_ticker.return_value.history.return_value = _price_history(120.0)
            summary = pm.get_summary()

        h = summary["holdings"][0]
        assert h["current_price"] == 120.0
        assert h["current_value"] == 1200.0
        assert h["pnl"] == 200.0
        assert h["pnl_pct"] == 20.0
        assert summary["total_invested"] == 1000.0
        assert summary["total_value"] == 1200.0
        assert summary["total_pnl"] == 200.0
        assert summary["total_pnl_pct"] == 20.0

    def test_computes_pnl_for_a_losing_position(self, portfolio_path):
        pm = PortfolioManager(portfolio_path)
        self._seed(pm, [{"ticker": "TSLA", "quantity": 5, "total_invested": 1000.0}])

        with patch("stock_advisor.yf.Ticker") as mock_ticker:
            mock_ticker.return_value.history.return_value = _price_history(150.0)
            summary = pm.get_summary()

        h = summary["holdings"][0]
        assert h["current_value"] == 750.0
        assert h["pnl"] == -250.0
        assert h["pnl_pct"] == -25.0

    def test_yfinance_exception_falls_back_to_zeroed_holding_not_a_crash(self, portfolio_path):
        pm = PortfolioManager(portfolio_path)
        self._seed(pm, [{"ticker": "BADTICKER", "quantity": 3, "total_invested": 300.0}])

        with patch("stock_advisor.yf.Ticker") as mock_ticker:
            mock_ticker.return_value.history.side_effect = Exception("network error")
            summary = pm.get_summary()

        h = summary["holdings"][0]
        assert h["current_price"] == 0
        assert h["current_value"] == 0
        assert h["pnl"] == 0
        assert h["pnl_pct"] == 0

    def test_empty_price_history_falls_back_to_zero_price_not_an_index_error(self, portfolio_path):
        pm = PortfolioManager(portfolio_path)
        self._seed(pm, [{"ticker": "DELISTED", "quantity": 1, "total_invested": 100.0}])

        with patch("stock_advisor.yf.Ticker") as mock_ticker:
            mock_ticker.return_value.history.return_value = _empty_history()
            summary = pm.get_summary()

        h = summary["holdings"][0]
        assert h["current_price"] == 0.0
        assert h["current_value"] == 0.0

    def test_total_pnl_pct_is_zero_not_a_divide_by_zero_when_nothing_invested(self, portfolio_path):
        pm = PortfolioManager(portfolio_path)
        self._seed(pm, [])

        summary = pm.get_summary()

        assert summary["holdings"] == []
        assert summary["total_invested"] == 0
        assert summary["total_pnl_pct"] == 0

    def test_multiple_holdings_are_summed_independently(self, portfolio_path):
        pm = PortfolioManager(portfolio_path)
        self._seed(pm, [
            {"ticker": "VOO", "quantity": 2, "total_invested": 800.0},
            {"ticker": "QQQ", "quantity": 1, "total_invested": 400.0},
        ])
        prices = {"VOO": 450.0, "QQQ": 380.0}

        with patch("stock_advisor.yf.Ticker") as mock_ticker:
            mock_ticker.side_effect = lambda t: type(
                "T", (), {"history": lambda self, period=None: _price_history(prices[t])}
            )()
            summary = pm.get_summary()

        assert summary["total_invested"] == 1200.0
        assert summary["total_value"] == pytest.approx(2 * 450.0 + 380.0)


# ─────────────────────────────────────────────────────────────
#  generate_warnings
# ─────────────────────────────────────────────────────────────
class TestGenerateWarnings:
    def _summary(self, holdings, total_value):
        return {"total_value": total_value, "holdings": holdings}

    def test_flags_concentration_above_35_percent(self, portfolio_path):
        pm = PortfolioManager(portfolio_path)
        summary = self._summary(
            [{"ticker": "NVDA", "current_value": 400.0, "pnl_pct": 5.0}],
            total_value=1000.0,
        )

        warnings_list = pm.generate_warnings(summary, analyses={})

        assert any("CONCENTRATION" in w and "NVDA" in w for w in warnings_list)

    def test_no_concentration_warning_at_or_below_35_percent(self, portfolio_path):
        pm = PortfolioManager(portfolio_path)
        summary = self._summary(
            [{"ticker": "VOO", "current_value": 350.0, "pnl_pct": 5.0}],
            total_value=1000.0,
        )

        warnings_list = pm.generate_warnings(summary, analyses={})

        assert not any("CONCENTRATION" in w for w in warnings_list)

    def test_flags_loss_alert_below_negative_15_percent(self, portfolio_path):
        pm = PortfolioManager(portfolio_path)
        summary = self._summary(
            [{"ticker": "COIN", "current_value": 100.0, "pnl_pct": -22.5}],
            total_value=1000.0,
        )

        warnings_list = pm.generate_warnings(summary, analyses={})

        assert any("LOSS ALERT" in w and "COIN" in w for w in warnings_list)

    def test_flags_trend_warning_when_analysis_trend_score_is_weak(self, portfolio_path):
        pm = PortfolioManager(portfolio_path)
        summary = self._summary(
            [{"ticker": "META", "current_value": 100.0, "pnl_pct": 2.0}],
            total_value=1000.0,
        )

        warnings_list = pm.generate_warnings(
            summary, analyses={"META": {"trend_score": 25}}
        )

        assert any("TREND WARNING" in w and "META" in w for w in warnings_list)

    def test_no_trend_warning_when_ticker_missing_from_analyses(self, portfolio_path):
        pm = PortfolioManager(portfolio_path)
        summary = self._summary(
            [{"ticker": "META", "current_value": 100.0, "pnl_pct": 2.0}],
            total_value=1000.0,
        )

        warnings_list = pm.generate_warnings(summary, analyses={})

        assert not any("TREND WARNING" in w for w in warnings_list)

    def test_zero_total_value_does_not_raise_a_divide_by_zero(self, portfolio_path):
        pm = PortfolioManager(portfolio_path)
        summary = self._summary(
            [{"ticker": "X", "current_value": 0.0, "pnl_pct": 0.0}],
            total_value=0,
        )

        warnings_list = pm.generate_warnings(summary, analyses={})

        assert isinstance(warnings_list, list)
