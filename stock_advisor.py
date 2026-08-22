"""
╔══════════════════════════════════════════════════════════════════╗
║      STOCK ADVISOR v3  --  AI-Powered Investment Research        ║
║                                                                  ║
║  DISCLAIMER: Advisory & educational only. Never places trades.   ║
║  Not financial advice. Always do your own research (DYOR).       ║
║                                                                  ║
║  Scoring engine:                                                 ║
║    Fundamentals · Growth · Financial Health · Dividend           ║
║    Momentum · Risk · Sentiment  (7 dimensions, 0-100 each)       ║
╚══════════════════════════════════════════════════════════════════╝

SETUP:
  pip install -r requirements_stocks.txt

USAGE:
  python stock_advisor.py                       # Full analysis + HTML report
  python stock_advisor.py --quick               # Terminal output only (faster)
  python stock_advisor.py --portfolio           # Portfolio overview only
  python stock_advisor.py --ticker AAPL         # Analyze single ticker
  python stock_advisor.py --profile growth      # Use growth investor profile
"""

import os
import json
import time
import warnings
import argparse
from datetime import datetime, timezone, timedelta
from pathlib import Path

import pandas as pd
import yfinance as yf
import feedparser

warnings.filterwarnings("ignore")



# ─────────────────────────────────────────────────────────────
#  CONFIGURATION
# ─────────────────────────────────────────────────────────────
CONFIG = {
    "monthly_budget":    200.0,
    "max_single_pct":     40.0,
    "etf_target_pct":     70.0,
    "report_dir":     "reports",
    "portfolio_file": "portfolio.json",
    "news_hours":          72,
    "request_timeout":     10,
    "default_profile": "balanced",
}

# ─────────────────────────────────────────────────────────────
#  WATCHLIST
# ─────────────────────────────────────────────────────────────
WATCHLIST = {
    "Core ETFs": {
        "tickers": ["VOO", "VTI", "SPY", "QQQ", "SCHD", "VXUS"],
        "risk":    "LOW",
        "note":    "Broad market index funds. The foundation of any long-term portfolio.",
    },
    "Quality Stocks": {
        "tickers": ["MSFT", "AAPL", "GOOGL", "AMZN", "ASML", "NVDA", "COST", "BRK-B"],
        "risk":    "MEDIUM",
        "note":    "High-quality companies with durable competitive advantages.",
    },
    "Dividend / Value": {
        "tickers": ["KO", "JNJ", "PEP", "PG", "HD"],
        "risk":    "LOW-MEDIUM",
        "note":    "Reliable dividend payers. Income + stability.",
    },
}

# ─────────────────────────────────────────────────────────────
#  ETF KNOWLEDGE BASE
#  Static metadata — no API call needed. Expense ratios & sector
#  weights are approximate and subject to fund provider changes.
# ─────────────────────────────────────────────────────────────
ETF_KNOWLEDGE = {
    "VOO": {
        "name": "Vanguard S&P 500 ETF",
        "type": "Index ETF",
        "expense_ratio": 0.03,
        "description": "Tracks the S&P 500 — 500 of the largest US companies across all sectors.",
        "sectors": {"Technology": 29, "Healthcare": 13, "Financials": 13, "Consumer Disc.": 11, "Industrials": 9},
        "overlap": ["SPY", "VTI", "IVV"],
        "why": "Best single starting point for most investors. Extremely low cost, maximum diversification, proven 30+ year track record.",
        "risks": "100% US equity. Subject to full market drawdowns. Concentration in mega-cap tech.",
        "dividend_yield_approx": 1.3,
        "beginner_note": "Buying VOO is like buying a tiny slice of the 500 biggest US companies at once. When the US economy grows, VOO grows.",
    },
    "VTI": {
        "name": "Vanguard Total Stock Market ETF",
        "type": "Index ETF",
        "expense_ratio": 0.03,
        "description": "Total US stock market — ~4000 companies including large, mid, and small cap.",
        "sectors": {"Technology": 28, "Healthcare": 13, "Financials": 13, "Consumer Disc.": 11, "Industrials": 9},
        "overlap": ["VOO", "SPY"],
        "why": "Broader than VOO — adds mid/small cap exposure which can outperform over long horizons.",
        "risks": "Small/mid cap stocks add volatility. Still 100% US.",
        "dividend_yield_approx": 1.3,
        "beginner_note": "Similar to VOO but includes smaller companies too. Good if you want the complete US market.",
    },
    "SPY": {
        "name": "SPDR S&P 500 ETF Trust",
        "type": "Index ETF",
        "expense_ratio": 0.0945,
        "description": "The world's most-traded ETF. Tracks the S&P 500 with exceptional liquidity.",
        "sectors": {"Technology": 29, "Healthcare": 13, "Financials": 13, "Consumer Disc.": 11},
        "overlap": ["VOO", "VTI", "IVV"],
        "why": "Best choice for active traders due to deep liquidity. For long-term holders, VOO is cheaper.",
        "risks": "Higher expense ratio than VOO/IVV. Better suited for trading than buy-and-hold.",
        "dividend_yield_approx": 1.3,
        "beginner_note": "Same as VOO essentially, but slightly more expensive to hold long-term. Great for trading.",
    },
    "QQQ": {
        "name": "Invesco Nasdaq-100 ETF",
        "type": "Growth ETF",
        "expense_ratio": 0.20,
        "description": "Top 100 non-financial Nasdaq companies. Heavy weighting in technology and growth sectors.",
        "sectors": {"Technology": 51, "Consumer Disc.": 18, "Healthcare": 7, "Industrials": 5, "Communication": 9},
        "overlap": ["QQQM", "VOO", "VTI"],
        "why": "Highest long-term growth of major ETFs. Best AI/Tech exposure. Outperformed S&P500 over past decade.",
        "risks": "High tech concentration. Much more volatile than S&P500. Brutal drawdowns in rate hike cycles.",
        "dividend_yield_approx": 0.6,
        "beginner_note": "Think of QQQ as betting on the biggest tech companies: Apple, Microsoft, Nvidia, Amazon, Meta, Google. High growth, high risk.",
    },
    "SCHD": {
        "name": "Schwab US Dividend Equity ETF",
        "type": "Dividend ETF",
        "expense_ratio": 0.06,
        "description": "High-quality US dividend stocks screened for dividend growth, yield, and financial health.",
        "sectors": {"Financials": 17, "Healthcare": 16, "Consumer Staples": 14, "Energy": 13, "Industrials": 12},
        "overlap": ["VYM", "DVY", "HDV"],
        "why": "The gold standard dividend ETF. Combines high yield (~3.5%), dividend growth (~10%/yr), and quality screening.",
        "risks": "Underperforms in pure growth bull markets. Limited tech exposure. Sector-specific risk.",
        "dividend_yield_approx": 3.5,
        "beginner_note": "SCHD pays you every quarter just for holding it (~3.5%/year). Good if you want cash flow from investments.",
    },
    "VXUS": {
        "name": "Vanguard Total International Stock ETF",
        "type": "International ETF",
        "expense_ratio": 0.07,
        "description": "All world stocks EXCLUDING the US. ~8000 companies across Europe, Asia, and Emerging Markets.",
        "sectors": {"Financials": 22, "Industrials": 14, "Technology": 12, "Consumer Disc.": 11, "Healthcare": 9},
        "overlap": ["EFA", "IEFA"],
        "why": "Geographic diversification. Reduces US concentration risk. International stocks often trade at cheaper valuations.",
        "risks": "Currency risk. Political/regulatory risk. Often lags US markets in bull cycles.",
        "dividend_yield_approx": 3.2,
        "beginner_note": "VXUS invests in companies outside the US — Europe, Japan, China, etc. Good for diversifying beyond America.",
    },
    "JEPI": {
        "name": "JPMorgan Equity Premium Income ETF",
        "type": "Income ETF",
        "expense_ratio": 0.35,
        "description": "S&P 500 stocks + covered calls strategy. Generates high monthly income with lower volatility.",
        "sectors": {"Healthcare": 17, "Financials": 14, "Technology": 13, "Utilities": 11, "Industrials": 10},
        "overlap": ["JEPQ", "DIVO"],
        "why": "Very high yield (~7-9% monthly payments). Reduces portfolio volatility. Good for income-focused investors.",
        "risks": "Caps upside in strong bull markets. Higher expense ratio. Complex options strategy. Newer fund (2020).",
        "dividend_yield_approx": 7.5,
        "beginner_note": "JEPI pays monthly dividends — much higher than most funds (~7-9%/year). The trade-off: it won't rise as much in bull markets.",
    },
}

# ─────────────────────────────────────────────────────────────
#  INVESTOR PROFILES
# ─────────────────────────────────────────────────────────────
USER_PROFILES = {
    "beginner": {
        "label": "Beginner Investor",
        "description": "Just starting out. Simplicity and safety first.",
        "etf_pct": 85,
        "max_single_pct": 25,
        "min_score": 62,
        "score_weights": {"fundamentals": 0.20, "growth": 0.15, "health": 0.20,
                          "dividend": 0.10, "trend": 0.15, "risk": 0.15, "sentiment": 0.05},
        "preferred_tickers": ["VOO", "SCHD", "VTI"],
        "advice": "Start with broad ETFs (VOO, VTI, SCHD). Keep it simple. Add individual stocks only after 12+ months.",
        "time_horizon": "5-30 years",
    },
    "conservative": {
        "label": "Conservative Investor",
        "description": "Capital preservation. Steady income. Low volatility.",
        "etf_pct": 80,
        "max_single_pct": 25,
        "min_score": 65,
        "score_weights": {"fundamentals": 0.25, "growth": 0.10, "health": 0.20,
                          "dividend": 0.25, "trend": 0.10, "risk": 0.05, "sentiment": 0.05},
        "preferred_tickers": ["SCHD", "VOO", "VXUS", "KO", "JNJ", "PG"],
        "advice": "Prioritize dividend ETFs and blue-chip value stocks. Avoid high-PE growth names.",
        "time_horizon": "3-15 years",
    },
    "balanced": {
        "label": "Balanced Investor",
        "description": "Mix of growth and income. Moderate risk tolerance.",
        "etf_pct": 70,
        "max_single_pct": 35,
        "min_score": 58,
        "score_weights": {"fundamentals": 0.25, "growth": 0.20, "health": 0.15,
                          "dividend": 0.10, "trend": 0.15, "risk": 0.10, "sentiment": 0.05},
        "preferred_tickers": ["VOO", "SCHD", "MSFT", "GOOGL", "COST"],
        "advice": "Core ETFs (60-70%) + quality individual stocks (30-40%). Rebalance annually.",
        "time_horizon": "5-20 years",
    },
    "growth": {
        "label": "Growth Investor",
        "description": "Maximize long-term capital appreciation. Higher risk tolerance.",
        "etf_pct": 55,
        "max_single_pct": 40,
        "min_score": 55,
        "score_weights": {"fundamentals": 0.15, "growth": 0.35, "health": 0.10,
                          "dividend": 0.02, "trend": 0.22, "risk": 0.11, "sentiment": 0.05},
        "preferred_tickers": ["QQQ", "NVDA", "MSFT", "AMZN", "GOOGL", "ASML"],
        "advice": "Weight towards high-growth stocks and QQQ. Accept higher volatility for higher returns.",
        "time_horizon": "7-25 years",
    },
    "dividend": {
        "label": "Dividend Income Investor",
        "description": "Build a passive income stream through dividend compounding.",
        "etf_pct": 70,
        "max_single_pct": 30,
        "min_score": 60,
        "score_weights": {"fundamentals": 0.20, "growth": 0.08, "health": 0.15,
                          "dividend": 0.40, "trend": 0.08, "risk": 0.05, "sentiment": 0.04},
        "preferred_tickers": ["SCHD", "JEPI", "VOO", "KO", "JNJ", "PEP", "PG"],
        "advice": "Focus on SCHD, JEPI, and dividend growers (KO, JNJ, PG). Reinvest all dividends.",
        "time_horizon": "5-30 years",
    },
    "aggressive": {
        "label": "Aggressive Growth",
        "description": "Maximum returns. High risk. Very long time horizon.",
        "etf_pct": 40,
        "max_single_pct": 45,
        "min_score": 50,
        "score_weights": {"fundamentals": 0.12, "growth": 0.40, "health": 0.08,
                          "dividend": 0.01, "trend": 0.25, "risk": 0.09, "sentiment": 0.05},
        "preferred_tickers": ["QQQ", "NVDA", "AMZN", "MSFT", "GOOGL", "ASML"],
        "advice": "Concentrate in highest-conviction ideas. Accept 40-60% drawdowns. Only invest what you won't need for 10+ years.",
        "time_horizon": "10-30 years",
    },
}

MARKET_TICKERS = {
    "sp500":  "^GSPC",
    "nasdaq": "^IXIC",
    "vix":    "^VIX",
    "yield":  "^TNX",
}

NEWS_FEEDS = [
    {"name": "Yahoo Finance",    "url": "https://finance.yahoo.com/news/rssindex"},
    {"name": "Reuters Business", "url": "https://feeds.reuters.com/reuters/businessNews"},
    {"name": "CNBC Markets",     "url": "https://www.cnbc.com/id/100003114/device/rss/rss.html"},
    {"name": "MarketWatch",      "url": "https://feeds.marketwatch.com/marketwatch/topstories/"},
]

POSITIVE_KW = [
    "growth", "profit", "record", "beat", "strong", "rally", "gain", "surge",
    "rise", "bull", "positive", "upgrade", "outperform", "recovery", "dividend",
    "innovation", "expansion", "earnings beat", "revenue beat", "optimism",
    "buy", "overweight", "raise target", "accelerating", "record revenue",
]
NEGATIVE_KW = [
    "crash", "decline", "loss", "recession", "debt", "fear", "bear",
    "downgrade", "miss", "warning", "layoff", "tariff", "inflation", "rate hike",
    "default", "bankruptcy", "concern", "uncertainty", "slowdown", "contraction",
    "sell", "underweight", "cut target", "disappointing", "guidance cut",
]

SECTOR_THEMES = {
    "Technology":             "AI and cloud infrastructure are secular growth tailwinds",
    "Healthcare":             "aging demographics provide structural long-term demand",
    "Financials":             "interest rate dynamics significantly impact net interest margins",
    "Consumer Staples":       "defensive revenue with pricing power in inflationary environments",
    "Energy":                 "the energy transition creates both disruption risk and opportunity",
    "Industrials":            "nearshoring and infrastructure spending drive multi-year demand",
    "Real Estate":            "rate sensitivity makes entry timing critical for total returns",
    "Utilities":              "bond-like cash flows make this sector highly rate-sensitive",
    "Consumer Discretionary": "sensitive to consumer confidence, credit, and employment trends",
    "Communication Services": "digital advertising dominance drives platform revenue concentration",
    "Materials":              "commodity cycle drives highly cyclical earnings and valuations",
}


# ─────────────────────────────────────────────────────────────
#  DATA FETCHER
# ─────────────────────────────────────────────────────────────
class DataFetcher:
    def get_info(self, ticker: str) -> dict:
        try:
            data = yf.Ticker(ticker).info
            return data if data else {}
        except Exception:
            return {}

    def get_history(self, ticker: str, period: str = "1y") -> pd.DataFrame:
        try:
            df = yf.Ticker(ticker).history(period=period)
            if df.empty:
                return pd.DataFrame()
            df = df[df["Close"] > 0]
            return df if not df.empty else pd.DataFrame()
        except Exception:
            return pd.DataFrame()

    def get_market_data(self) -> dict:
        result = {}
        for name, ticker in MARKET_TICKERS.items():
            try:
                df = yf.Ticker(ticker).history(period="1y")
                if not df.empty:
                    result[name] = df["Close"]
            except Exception:
                pass
        return result

    def get_news(self) -> list:
        articles = []
        for feed in NEWS_FEEDS:
            try:
                parsed = feedparser.parse(feed["url"])
                for entry in parsed.entries[:15]:
                    title = getattr(entry, "title", "")
                    if title:
                        articles.append({"title": title, "source": feed["name"]})
            except Exception:
                pass
        return articles


# ─────────────────────────────────────────────────────────────
#  MARKET REGIME DETECTOR
# ─────────────────────────────────────────────────────────────
class MarketRegimeDetector:
    def detect(self, market_data: dict) -> dict:
        signals  = []
        bull_pts = 0
        bear_pts = 0

        if "sp500" in market_data:
            sp = market_data["sp500"]
            if len(sp) >= 200:
                ma200 = sp.iloc[-200:].mean()
                ma50  = sp.iloc[-50:].mean()
                price = sp.iloc[-1]
                if price > ma200:
                    bull_pts += 2
                    signals.append(("BULLISH", "S&P500 above 200-day average — long-term uptrend intact"))
                else:
                    bear_pts += 2
                    signals.append(("BEARISH", "S&P500 below 200-day average — long-term downtrend warning"))
                if price > ma50:
                    bull_pts += 1
                    signals.append(("BULLISH", "S&P500 above 50-day average — short-term momentum positive"))
                else:
                    bear_pts += 1
                    signals.append(("BEARISH", "S&P500 below 50-day average — short-term momentum negative"))

        if "vix" in market_data:
            vix = market_data["vix"].iloc[-1]
            if vix < 18:
                bull_pts += 2
                signals.append(("BULLISH", f"VIX {vix:.1f} — very low fear, calm institutional environment"))
            elif vix < 25:
                bull_pts += 1
                signals.append(("BULLISH", f"VIX {vix:.1f} — moderate volatility, risk-on sentiment"))
            elif vix > 30:
                bear_pts += 2
                signals.append(("BEARISH", f"VIX {vix:.1f} — elevated fear, defensive positioning warranted"))
            else:
                signals.append(("NEUTRAL", f"VIX {vix:.1f} — moderate uncertainty in the market"))

        if "nasdaq" in market_data and len(market_data["nasdaq"]) >= 200:
            nq    = market_data["nasdaq"]
            ma200 = nq.iloc[-200:].mean()
            if nq.iloc[-1] > ma200:
                bull_pts += 1
                signals.append(("BULLISH", "Nasdaq above 200-day average — technology sector healthy"))
            else:
                bear_pts += 1
                signals.append(("BEARISH", "Nasdaq below 200-day average — technology sector under pressure"))

        if "yield" in market_data:
            y = market_data["yield"].iloc[-1]
            if y > 4.5:
                bear_pts += 1
                signals.append(("CAUTION", f"10-yr Treasury yield {y:.2f}% — high rates pressure equity valuations"))
            elif y > 3.5:
                signals.append(("NEUTRAL", f"10-yr Treasury yield {y:.2f}% — moderate rate environment"))
            else:
                bull_pts += 1
                signals.append(("BULLISH", f"10-yr Treasury yield {y:.2f}% — low rates supportive for equities"))

        if bull_pts >= 4:
            regime = "BULLISH"
        elif bear_pts >= 3:
            regime = "DEFENSIVE"
        else:
            regime = "NEUTRAL"

        advice = {
            "BULLISH":   "Risk-on environment. Growth ETFs and quality stocks look favorable. Full allocation appropriate.",
            "NEUTRAL":   "Balanced approach. Core ETF foundation with selective quality stock exposure.",
            "DEFENSIVE": "Risk-off environment. Favor ETFs, dividend/value stocks. Reduce speculative exposure.",
        }

        return {"regime": regime, "signals": signals, "advice": advice[regime],
                "bull_pts": bull_pts, "bear_pts": bear_pts}


# ─────────────────────────────────────────────────────────────
#  FINANCIAL HEALTH ANALYZER
# ─────────────────────────────────────────────────────────────
class FinancialHealthAnalyzer:
    """Analyzes balance sheet quality, FCF generation, and debt sustainability."""

    def analyze(self, info: dict) -> tuple:
        score = 50.0
        notes = []

        # Free Cash Flow
        fcf = info.get("freeCashflow")
        if fcf is not None:
            fcf_b = fcf / 1e9
            if fcf > 0:
                score += 15
                notes.append(f"Free cash flow ${fcf_b:.1f}B — company generates real cash after capex")
            else:
                score -= 20
                notes.append(f"Negative FCF (${fcf_b:.1f}B) — burning cash, requires monitoring")

        # Debt-to-Equity
        dte = info.get("debtToEquity")
        if dte is not None and dte >= 0:
            if dte < 30:
                score += 18; notes.append(f"Debt/equity {dte:.0f}% — fortress balance sheet")
            elif dte < 80:
                score += 10; notes.append(f"Debt/equity {dte:.0f}% — conservative leverage")
            elif dte < 150:
                score += 2;  notes.append(f"Debt/equity {dte:.0f}% — manageable leverage level")
            elif dte < 300:
                score -= 12; notes.append(f"Debt/equity {dte:.0f}% — elevated leverage, monitor interest coverage")
            else:
                score -= 25; notes.append(f"Debt/equity {dte:.0f}% — high financial leverage, significant risk")

        # Return on Equity
        roe = info.get("returnOnEquity")
        if roe is not None:
            pct = roe * 100
            if pct > 25:
                score += 15; notes.append(f"ROE {pct:.0f}% — exceptional capital efficiency (Buffett benchmark: >15%)")
            elif pct > 15:
                score += 8;  notes.append(f"ROE {pct:.0f}% — solid returns on shareholder capital")
            elif pct > 0:
                score += 2;  notes.append(f"ROE {pct:.0f}% — modest but positive returns on equity")
            else:
                score -= 15; notes.append(f"Negative ROE — not generating returns for shareholders")

        # Current Ratio (short-term liquidity)
        cr = info.get("currentRatio")
        if cr is not None:
            if cr > 2.5:
                score += 8;  notes.append(f"Current ratio {cr:.1f} — very strong short-term liquidity")
            elif cr > 1.5:
                score += 5;  notes.append(f"Current ratio {cr:.1f} — adequate liquidity position")
            elif cr > 1.0:
                score += 1;  notes.append(f"Current ratio {cr:.1f} — acceptable but watch closely")
            else:
                score -= 12; notes.append(f"Current ratio {cr:.1f} — potential short-term liquidity concern")

        return max(0.0, min(100.0, score)), notes


# ─────────────────────────────────────────────────────────────
#  DIVIDEND ANALYZER
# ─────────────────────────────────────────────────────────────
class DividendAnalyzer:
    """Analyzes dividend yield, sustainability, and growth quality."""

    def analyze(self, info: dict, history: pd.DataFrame) -> tuple:
        score = 50.0
        notes = []

        div_yield    = info.get("dividendYield") or 0
        payout_ratio = info.get("payoutRatio") or 0
        div_rate     = info.get("dividendRate") or 0
        ex_div_date  = info.get("exDividendDate")

        if div_yield <= 0:
            return 50.0, ["No dividend — growth/reinvestment focused company"]

        yield_pct = div_yield * 100

        # Yield quality
        if yield_pct > 8:
            score -= 5
            notes.append(f"Yield {yield_pct:.1f}% — very high, potential 'yield trap' (verify sustainability)")
        elif yield_pct > 4:
            score += 22; notes.append(f"Yield {yield_pct:.1f}% — attractive income, well above inflation")
        elif yield_pct > 2.5:
            score += 15; notes.append(f"Yield {yield_pct:.1f}% — solid dividend income")
        elif yield_pct > 1:
            score += 8;  notes.append(f"Yield {yield_pct:.1f}% — modest income component")
        else:
            score += 3;  notes.append(f"Yield {yield_pct:.1f}% — token dividend, primarily a growth stock")

        # Payout sustainability
        if payout_ratio > 0:
            pr = payout_ratio * 100
            if pr < 35:
                score += 18; notes.append(f"Payout ratio {pr:.0f}% — significant room for future dividend growth")
            elif pr < 60:
                score += 10; notes.append(f"Payout ratio {pr:.0f}% — well-covered, sustainable dividend")
            elif pr < 80:
                score += 3;  notes.append(f"Payout ratio {pr:.0f}% — dividend stretched, earnings growth needed")
            else:
                score -= 18; notes.append(f"Payout ratio {pr:.0f}% — dividend may be unsustainable")

        if ex_div_date:
            notes.append(f"Ex-dividend date on record")

        return max(0.0, min(100.0, score)), notes


# ─────────────────────────────────────────────────────────────
#  ASSET ANALYZER  (7 dimensions)
# ─────────────────────────────────────────────────────────────
class AssetAnalyzer:
    """
    Scores each asset across 7 dimensions:
      Fundamentals · Growth · Financial Health · Dividend
      Trend/Momentum · Risk · Sentiment
    """

    def __init__(self):
        self.health_analyzer   = FinancialHealthAnalyzer()
        self.dividend_analyzer = DividendAnalyzer()

    def analyze_fundamentals(self, info: dict) -> tuple:
        score = 50.0
        notes = []

        pe = info.get("trailingPE") or info.get("forwardPE")
        if pe and pe > 0:
            if pe < 12:
                score += 22; notes.append(f"PE {pe:.1f}x — deep value territory, attractively cheap")
            elif pe < 18:
                score += 15; notes.append(f"PE {pe:.1f}x — fairly valued, reasonable entry point")
            elif pe < 28:
                score += 5;  notes.append(f"PE {pe:.1f}x — slight premium, quality justification needed")
            elif pe < 45:
                score -= 8;  notes.append(f"PE {pe:.1f}x — expensive, requires strong growth delivery")
            else:
                score -= 20; notes.append(f"PE {pe:.1f}x — very expensive, growth must accelerate significantly")

        peg = info.get("pegRatio")
        if peg and peg > 0:
            if peg < 0.8:
                score += 18; notes.append(f"PEG {peg:.2f} — outstanding value relative to growth rate")
            elif peg < 1.5:
                score += 10; notes.append(f"PEG {peg:.2f} — reasonable value for the growth on offer")
            elif peg < 2.5:
                score -= 5;  notes.append(f"PEG {peg:.2f} — paying a premium for growth")
            else:
                score -= 12; notes.append(f"PEG {peg:.2f} — significant premium vs growth, high expectations priced in")

        margin = info.get("profitMargins")
        if margin is not None:
            pct = margin * 100
            if pct > 30:
                score += 15; notes.append(f"Net margin {pct:.1f}% — exceptional pricing power and efficiency")
            elif pct > 15:
                score += 8;  notes.append(f"Net margin {pct:.1f}% — strong profitability above sector average")
            elif pct > 5:
                score += 3;  notes.append(f"Net margin {pct:.1f}% — adequate profitability")
            elif pct < 0:
                score -= 18; notes.append(f"Net margin {pct:.1f}% — unprofitable, loss-making business")

        ps = info.get("priceToSalesTrailing12Months")
        if ps and ps > 0:
            if ps < 2:
                score += 8;  notes.append(f"P/Sales {ps:.1f}x — cheap relative to revenue")
            elif ps > 15:
                score -= 8;  notes.append(f"P/Sales {ps:.1f}x — very high revenue multiple")

        return max(0.0, min(100.0, score)), notes

    def analyze_growth(self, info: dict) -> tuple:
        score = 50.0
        notes = []

        rev_growth = info.get("revenueGrowth")
        if rev_growth is not None:
            pct = rev_growth * 100
            if pct > 30:
                score += 30; notes.append(f"Revenue +{pct:.0f}%/yr — hyper-growth, exceptional execution")
            elif pct > 15:
                score += 22; notes.append(f"Revenue +{pct:.0f}%/yr — strong above-market growth")
            elif pct > 8:
                score += 12; notes.append(f"Revenue +{pct:.0f}%/yr — healthy, above-GDP growth")
            elif pct > 0:
                score += 4;  notes.append(f"Revenue +{pct:.0f}%/yr — modest but positive growth")
            elif pct > -10:
                score -= 15; notes.append(f"Revenue {pct:.0f}%/yr — declining revenue, investigate cause")
            else:
                score -= 25; notes.append(f"Revenue {pct:.0f}%/yr — significant revenue contraction, high risk")

        earn_growth = info.get("earningsGrowth")
        if earn_growth is not None:
            pct = earn_growth * 100
            if pct > 25:
                score += 20; notes.append(f"Earnings +{pct:.0f}%/yr — outstanding profit growth")
            elif pct > 10:
                score += 12; notes.append(f"Earnings +{pct:.0f}%/yr — solid earnings expansion")
            elif pct > 0:
                score += 5;  notes.append(f"Earnings +{pct:.0f}%/yr — modest growth")
            elif pct < -20:
                score -= 20; notes.append(f"Earnings {pct:.0f}%/yr — significant profit decline, caution")
            elif pct < 0:
                score -= 12; notes.append(f"Earnings {pct:.0f}%/yr — earnings shrinking, watch guidance")

        fwd_pe  = info.get("forwardPE")
        trail_pe = info.get("trailingPE")
        if fwd_pe and trail_pe and fwd_pe > 0 and trail_pe > 0:
            earnings_growth_implied = (trail_pe / fwd_pe - 1) * 100
            if earnings_growth_implied > 15:
                score += 8
                notes.append(f"Forward PE implies {earnings_growth_implied:.0f}% earnings growth — analysts bullish")

        return max(0.0, min(100.0, score)), notes

    def analyze_technicals(self, history: pd.DataFrame) -> tuple:
        score = 50.0
        notes = []

        if history.empty or len(history) < 50:
            return score, ["Insufficient price history for technical analysis"]

        close = history["Close"][history["Close"] > 0]
        if len(close) < 50:
            return score, ["Insufficient valid price history for technical analysis"]
        price = close.iloc[-1]
        ma50  = close.iloc[-50:].mean()
        ma200 = close.iloc[-200:].mean() if len(close) >= 200 else close.mean()

        if price > ma200:
            score += 18; notes.append("Price above 200-day MA — long-term uptrend intact")
        else:
            score -= 18; notes.append("Price below 200-day MA — long-term downtrend, caution warranted")

        if price > ma50:
            score += 10; notes.append("Price above 50-day MA — short-term momentum positive")
        else:
            score -= 10; notes.append("Price below 50-day MA — short-term weakness")

        # Golden / Death cross
        if len(close) >= 200:
            if ma50 > ma200:
                score += 5; notes.append("Golden cross active (50d > 200d MA) — technically bullish")
            else:
                score -= 5; notes.append("Death cross active (50d < 200d MA) — technically bearish")

        # 3-month momentum
        if len(close) >= 63 and close.iloc[-63] > 0:
            mom_3m = (price - close.iloc[-63]) / close.iloc[-63] * 100
            if mom_3m > 20:
                score += 15; notes.append(f"Strong 3-month momentum +{mom_3m:.1f}%")
            elif mom_3m > 5:
                score += 8;  notes.append(f"Positive 3-month momentum +{mom_3m:.1f}%")
            elif mom_3m > -5:
                score += 0;  notes.append(f"Flat 3-month momentum {mom_3m:.1f}%")
            else:
                score -= 12; notes.append(f"Negative 3-month momentum {mom_3m:.1f}%")

        # RSI approximation
        if len(close) >= 14:
            delta = close.diff()
            gain  = delta.clip(lower=0).rolling(14).mean()
            loss  = (-delta.clip(upper=0)).rolling(14).mean()
            rs    = gain / loss.replace(0, 1e-9)
            rsi   = (100 - 100 / (1 + rs)).iloc[-1]
            if rsi > 70:
                score -= 8;  notes.append(f"RSI {rsi:.0f} — overbought territory, pullback risk")
            elif rsi < 30:
                score += 10; notes.append(f"RSI {rsi:.0f} — oversold, potential reversal opportunity")
            else:
                notes.append(f"RSI {rsi:.0f} — neutral range")

        return max(0.0, min(100.0, score)), notes

    def analyze_risk(self, history: pd.DataFrame, info: dict) -> tuple:
        score = 50.0
        notes = []

        close = history["Close"][history["Close"] > 0] if not history.empty else pd.Series(dtype=float)

        if len(close) > 20:
            daily_ret = close.pct_change().dropna()
            vol = daily_ret.std() * (252 ** 0.5) * 100

            if vol < 12:
                score += 30; notes.append(f"Annualized volatility {vol:.1f}% — very stable, bond-like")
            elif vol < 20:
                score += 18; notes.append(f"Annualized volatility {vol:.1f}% — low volatility, steady grower")
            elif vol < 30:
                score += 8;  notes.append(f"Annualized volatility {vol:.1f}% — moderate volatility")
            elif vol < 45:
                score -= 10; notes.append(f"Annualized volatility {vol:.1f}% — high volatility, size positions carefully")
            else:
                score -= 25; notes.append(f"Annualized volatility {vol:.1f}% — very high volatility, speculative risk")

            rolling_max = close.cummax()
            drawdown = ((close - rolling_max) / rolling_max).min() * 100
            if drawdown > -8:
                score += 12; notes.append(f"Max drawdown {drawdown:.1f}% — minimal historical losses")
            elif drawdown > -20:
                score += 4;  notes.append(f"Max drawdown {drawdown:.1f}% — contained historical losses")
            elif drawdown > -35:
                score -= 8;  notes.append(f"Max drawdown {drawdown:.1f}% — significant historical losses")
            else:
                score -= 18; notes.append(f"Max drawdown {drawdown:.1f}% — severe historical drawdown")

        beta = info.get("beta")
        if beta is not None:
            if beta < 0.5:
                score += 12; notes.append(f"Beta {beta:.2f} — highly defensive, moves little with market")
            elif beta < 0.9:
                score += 8;  notes.append(f"Beta {beta:.2f} — less volatile than market")
            elif beta < 1.2:
                notes.append(f"Beta {beta:.2f} — moves roughly in line with market")
            elif beta < 1.6:
                score -= 8;  notes.append(f"Beta {beta:.2f} — amplified market moves, higher risk")
            else:
                score -= 18; notes.append(f"Beta {beta:.2f} — very high market sensitivity")

        return max(0.0, min(100.0, score)), notes

    def analyze_sentiment(self, ticker: str, news: list) -> tuple:
        pos = neg = 0
        for article in news:
            text = article["title"].lower()
            for kw in POSITIVE_KW:
                if kw in text:
                    pos += 1
            for kw in NEGATIVE_KW:
                if kw in text:
                    neg += 1

        total = pos + neg
        if total == 0:
            return 50.0, ["No recent news signal — neutral baseline"]

        ratio = pos / total
        score = ratio * 100

        if ratio > 0.7:
            label = "Predominantly positive market headlines"
        elif ratio > 0.55:
            label = "Slightly positive market sentiment"
        elif ratio > 0.45:
            label = "Mixed/neutral market sentiment"
        elif ratio > 0.3:
            label = "Slightly negative market sentiment"
        else:
            label = "Predominantly negative market headlines"

        notes = [f"{label} ({pos}↑ / {neg}↓ keyword signals)",
                 "Sentiment is broad market signal — not ticker-specific"]
        return max(0.0, min(100.0, score)), notes

    def weighted_score(self, scores: dict, profile: dict) -> int:
        weights = profile.get("score_weights", {
            "fundamentals": 0.25, "growth": 0.20, "health": 0.15,
            "dividend": 0.10, "trend": 0.15, "risk": 0.10, "sentiment": 0.05,
        })
        total = (
            scores["fundamentals"] * weights["fundamentals"] +
            scores["growth"]       * weights["growth"]       +
            scores["health"]       * weights["health"]       +
            scores["dividend"]     * weights["dividend"]     +
            scores["trend"]        * weights["trend"]        +
            scores["risk"]         * weights["risk"]         +
            scores["sentiment"]    * weights["sentiment"]
        )
        return int(max(0, min(100, total)))

    def calibrate_score(self, raw: int) -> int:
        """Stretch score distribution to prevent compression around 70-72."""
        if raw >= 78:   return min(100, int(raw * 1.07))
        if raw >= 68:   return int(raw * 1.04)
        if raw >= 58:   return raw
        if raw >= 48:   return max(0, int(raw * 0.96))
        return max(0,   int(raw * 0.88))

    def score_label(self, score: int) -> tuple:
        if score >= 88: return "Strong Buy", "#3fb950"
        if score >= 72: return "Buy",         "#56d364"
        if score >= 55: return "Hold",        "#d29922"
        if score >= 38: return "Reduce",      "#ff9100"
        return               "Avoid",         "#f85149"

    def risk_label(self, risk_score: float, beta: float) -> str:
        if risk_score >= 70: return "LOW"
        if risk_score >= 50: return "MEDIUM"
        if risk_score >= 35: return "HIGH"
        return "VERY HIGH"

    def compute_confidence(self, info: dict, scores: dict, regime_data: dict) -> tuple:
        """
        Compute AI confidence for this analysis (25-88%).
        Capped at 88 — the system never claims perfect certainty.
        """
        # 1. Data quality — how many metrics did yfinance return?
        available = sum(1 for k in [
            'trailingPE', 'revenueGrowth', 'profitMargins',
            'freeCashflow', 'debtToEquity', 'beta', 'returnOnEquity',
        ] if info.get(k) is not None)
        data_quality = available / 7 * 100

        # 2. Signal agreement — fundamentals and trend pointing same direction?
        fund  = scores.get('fundamentals', 50)
        trend = scores.get('trend', 50)
        agreement = max(0, 100 - abs(fund - trend) * 0.8)

        # 3. Regime clarity — how decisive is the market signal?
        bull = regime_data.get('bull_pts', 0)
        bear = regime_data.get('bear_pts', 0)
        clarity = min(100, abs(bull - bear) * 18)

        # 4. Risk penalty — high volatility reduces confidence
        risk = scores.get('risk', 50)

        conf = (data_quality * 0.25 + agreement * 0.25 +
                clarity * 0.20 + risk * 0.30)
        conf = max(25, min(88, round(conf)))

        if conf >= 72: level = "High"
        elif conf >= 55: level = "Medium"
        elif conf >= 40: level = "Low"
        else: level = "Very Low"

        return conf, level


# ─────────────────────────────────────────────────────────────
#  NARRATIVE ENGINE
#  Generates human-readable explanations from quantitative data
# ─────────────────────────────────────────────────────────────
class NarrativeEngine:

    def generate(self, ticker: str, info: dict, scores: dict, notes: dict,
                 etf_info: dict = None) -> dict:
        is_etf = bool(etf_info)

        summary      = self._summary(ticker, info, scores, notes, is_etf, etf_info)
        bull_case    = self._bull_case(ticker, info, scores, is_etf, etf_info)
        bear_case    = self._bear_case(ticker, info, scores, is_etf)
        beginner     = self._beginner_note(ticker, info, scores, is_etf, etf_info)
        risk_note    = self._risk_note(ticker, info, scores)

        return {
            "summary":      summary,
            "bull_case":    bull_case,
            "bear_case":    bear_case,
            "beginner":     beginner,
            "risk_note":    risk_note,
        }

    def _summary(self, ticker, info, scores, notes, is_etf, etf_info):
        parts = []
        total = scores.get("total", 50)

        if is_etf and etf_info:
            parts.append(etf_info["description"])
            parts.append(etf_info["why"])
            er = etf_info.get("expense_ratio", 0)
            if er:
                cost_label = "ultra-low cost" if er < 0.05 else ("low cost" if er < 0.15 else "moderate cost")
                parts.append(f"Expense ratio {er:.2f}%/year ({cost_label}).")
            dy = etf_info.get("dividend_yield_approx", 0)
            if dy > 1:
                parts.append(f"Pays approximately {dy:.1f}% in annual dividends.")
            overlap = etf_info.get("overlap", [])
            if overlap:
                parts.append(f"Significant overlap with {', '.join(overlap)} — avoid holding duplicates.")
        else:
            name   = info.get("longName", ticker)
            sector = info.get("sector", "")

            if total >= 72:
                parts.append(f"{name} presents a compelling investment case backed by strong fundamentals.")
            elif total >= 58:
                parts.append(f"{name} shows solid characteristics with a balanced risk/reward profile.")
            elif total >= 45:
                parts.append(f"{name} has mixed signals — some strengths but notable risks to consider.")
            else:
                parts.append(f"{name} faces significant headwinds that make it difficult to recommend at current levels.")

            pe = info.get("trailingPE") or info.get("forwardPE")
            if pe and pe > 0:
                if pe < 15:
                    parts.append(f"At {pe:.1f}x earnings it trades well below market average — value opportunity.")
                elif pe < 25:
                    parts.append(f"Fairly valued at {pe:.1f}x earnings — reasonable for a quality business.")
                elif pe < 40:
                    parts.append(f"Premium valuation of {pe:.1f}x earnings demands continued strong execution.")
                else:
                    parts.append(f"Elevated {pe:.1f}x P/E requires exceptional growth to justify the multiple.")

            rev = (info.get("revenueGrowth") or 0) * 100
            if rev > 20:
                parts.append(f"Revenue growing {rev:.0f}%/year — well above market, indicating strong competitive positioning.")
            elif rev > 8:
                parts.append(f"Healthy {rev:.0f}%/year revenue growth supports the long-term investment case.")
            elif rev < -5:
                parts.append(f"Revenue declining {abs(rev):.0f}%/year — monitor for stabilization before adding exposure.")

            margin = (info.get("profitMargins") or 0) * 100
            if margin > 25:
                parts.append(f"Exceptional {margin:.0f}% profit margins signal durable competitive advantages (moat).")
            elif margin > 12:
                parts.append(f"Solid {margin:.0f}% profit margins reflect operational efficiency.")

            if sector in SECTOR_THEMES:
                parts.append(f"As a {sector} company, {SECTOR_THEMES[sector]}.")

        return " ".join(parts)

    def _bull_case(self, ticker, info, scores, is_etf, etf_info):
        bulls = []

        if is_etf and etf_info:
            bulls.append(etf_info["why"])
            dy = etf_info.get("dividend_yield_approx", 0)
            if dy > 2:
                bulls.append(f"~{dy:.1f}% annual dividend yield provides a reliable income floor.")
            er = etf_info.get("expense_ratio", 0)
            if er < 0.10:
                bulls.append(f"Expense ratio of just {er:.2f}% means nearly all returns stay in your pocket.")
        else:
            rev = (info.get("revenueGrowth") or 0) * 100
            earn = (info.get("earningsGrowth") or 0) * 100
            fcf = info.get("freeCashflow") or 0
            div_yield = (info.get("dividendYield") or 0) * 100
            peg = info.get("pegRatio")
            roe = (info.get("returnOnEquity") or 0) * 100

            if scores.get("growth", 50) >= 65:
                if rev > 10:
                    bulls.append(f"{rev:.0f}%/yr revenue growth demonstrates strong business momentum.")
                if earn > 10:
                    bulls.append(f"Earnings growing {earn:.0f}%/yr — operating leverage improving margins.")

            if scores.get("health", 50) >= 65:
                if fcf > 1e9:
                    bulls.append(f"${fcf/1e9:.1f}B free cash flow funds buybacks, dividends, and strategic M&A.")
                if roe > 20:
                    bulls.append(f"ROE of {roe:.0f}% shows exceptional capital allocation by management.")

            if peg and 0 < peg < 1.5:
                bulls.append(f"PEG {peg:.2f} — you're not overpaying relative to the growth rate on offer.")

            if div_yield > 1.5:
                bulls.append(f"{div_yield:.1f}% dividend yield provides income while you wait for price appreciation.")

            if scores.get("trend", 50) >= 65:
                bulls.append("Bullish technical trend confirms institutional accumulation.")

        return " | ".join(bulls[:3]) if bulls else "No strong bull case factors identified at current metrics."

    def _bear_case(self, ticker, info, scores, is_etf):
        bears = []

        pe      = info.get("trailingPE") or info.get("forwardPE") or 0
        beta    = info.get("beta") or 1
        dte     = info.get("debtToEquity") or 0
        rev     = (info.get("revenueGrowth") or 0) * 100
        margin  = (info.get("profitMargins") or 0) * 100

        if not is_etf:
            if pe > 40:
                bears.append(f"High {pe:.0f}x P/E leaves little margin of safety if earnings growth disappoints.")
            if beta > 1.5:
                bears.append(f"Beta {beta:.1f} — significant amplified drawdowns expected in market corrections.")
            if dte > 200:
                bears.append(f"Debt/equity {dte:.0f}% creates vulnerability in prolonged high-interest-rate environments.")
            if rev < -5:
                bears.append(f"Revenue declining {abs(rev):.0f}% raises questions about competitive positioning.")
            if margin < 3 and margin != 0:
                bears.append(f"Thin {margin:.1f}% margins leave little buffer against cost inflation or pricing pressure.")

        if scores.get("trend", 50) < 40:
            bears.append("Weak technical momentum suggests lack of institutional conviction.")
        if scores.get("risk", 50) < 40:
            bears.append("High volatility profile requires strict position sizing discipline.")

        if is_etf:
            bears.append("Market-wide corrections will move the ETF price regardless of individual holding quality.")

        return " | ".join(bears[:3]) if bears else "No significant bear case factors at current levels."

    def _beginner_note(self, ticker, info, scores, is_etf, etf_info):
        if is_etf and etf_info:
            name = etf_info["name"]
            er   = etf_info.get("expense_ratio", 0)
            dy   = etf_info.get("dividend_yield_approx", 0)
            return (
                f"{name} is like a pre-built basket of stocks — one purchase instantly diversifies you "
                f"across hundreds or thousands of companies. It costs just {er:.2f}%/year in fees. "
                + (f"It pays about {dy:.1f}% in dividends per year. " if dy > 0.5 else "")
                + "ETFs are considered the safest and simplest way to invest for most people."
            )
        else:
            name    = info.get("longName", ticker)
            sector  = info.get("sector", "this sector")
            pe      = info.get("trailingPE") or info.get("forwardPE")
            pe_note = f"You're paying ${pe:.0f} for every $1 of annual profit (P/E ratio). " if pe and pe > 0 else ""
            cap     = info.get("marketCap") or 0
            cap_label = ("mega-cap" if cap > 200e9 else "large-cap" if cap > 10e9 else "mid-cap" if cap > 2e9 else "small-cap")
            return (
                f"{name} is a {cap_label} company in the {sector} industry. "
                f"{pe_note}"
                f"Unlike ETFs, a single stock means your money is tied to one company's fortune. "
                f"Even great companies can lose 30-50% in downturns. "
                f"Never put more than 5-10% of your total portfolio in a single stock."
            )

    def _risk_note(self, ticker, info, scores):
        rs   = scores.get("risk", 50)
        beta = info.get("beta") or 1.0

        if rs >= 72:
            level = "LOW RISK"
            note  = "Historically stable. Suitable as a core portfolio holding."
        elif rs >= 55:
            level = "MODERATE RISK"
            note  = "Normal equity volatility. Suitable with a 3+ year investment horizon."
        elif rs >= 38:
            level = "ELEVATED RISK"
            note  = "Above-average volatility. Expect potential 25-40% drawdowns. Size position carefully."
        else:
            level = "HIGH RISK"
            note  = "Significant volatility expected. Experienced investors only. Strict position sizing required."

        return f"{level}: {note} (Beta: {beta:.2f} vs market = 1.0)"


# ─────────────────────────────────────────────────────────────
#  INVESTMENT BRIEF ENGINE
#  Generates the top-level AI summary shown at dashboard top
# ─────────────────────────────────────────────────────────────
class InvestmentBriefEngine:

    REGIME_COLORS = {
        "BULLISH":   "#3fb950",
        "NEUTRAL":   "#d29922",
        "DEFENSIVE": "#f85149",
    }

    def generate(self, analyses: dict, regime_data: dict,
                 recs: list, profile: dict) -> dict:
        regime    = regime_data["regime"]
        r_color   = self.REGIME_COLORS.get(regime, "#8b949e")
        bull      = regime_data.get("bull_pts", 0)
        bear      = regime_data.get("bear_pts", 0)

        overall_conf = self._overall_confidence(analyses, bull, bear)
        conf_label   = self._conf_label(overall_conf)
        best         = recs[0] if recs else None
        best_reason  = self._best_reason(best, analyses) if best else "—"
        main_risk    = self._main_risk(regime_data, recs, analyses)
        avoid        = [t for t, a in sorted(analyses.items(),
                         key=lambda x: x[1]["score"]) if a["score"] < 45][:3]
        strategy     = self._strategy(regime, profile, overall_conf)
        market_brief = self._market_brief(regime_data, analyses)

        return {
            "date":            datetime.now().strftime("%B %Y"),
            "regime":          regime,
            "regime_color":    r_color,
            "regime_advice":   regime_data["advice"],
            "best_ticker":     best["ticker"] if best else None,
            "best_score":      best["score"]  if best else None,
            "best_reason":     best_reason,
            "main_risk":       main_risk,
            "strategy":        strategy,
            "overall_conf":    overall_conf,
            "conf_label":      conf_label,
            "alloc_etf":       profile["etf_pct"],
            "alloc_stocks":    max(0, 85 - profile["etf_pct"]),
            "alloc_cash":      15,
            "top_picks":       [r["ticker"] for r in recs[:3]],
            "avoid":           avoid,
            "market_brief":    market_brief,
            "signal_count":    {"bull": bull, "bear": bear},
        }

    def _overall_confidence(self, analyses: dict, bull: int, bear: int) -> int:
        regime_clarity = min(100, abs(bull - bear) * 18)
        asset_conf     = (sum(a.get("confidence", 50) for a in analyses.values())
                          / max(len(analyses), 1))
        conf = regime_clarity * 0.40 + asset_conf * 0.60
        return max(28, min(85, round(conf)))

    def _conf_label(self, conf: int) -> str:
        if conf >= 72: return "High"
        if conf >= 55: return "Medium"
        if conf >= 40: return "Low"
        return "Very Low"

    def _best_reason(self, best: dict, analyses: dict) -> str:
        t = best["ticker"]
        if t not in analyses:
            return best.get("reason", "—")
        nav = analyses[t].get("narrative", {})
        s   = nav.get("summary", "") or best.get("reason", "")
        return (s[:160] + "…") if len(s) > 160 else s

    def _main_risk(self, regime_data: dict, recs: list, analyses: dict) -> str:
        # Prefer an explicit bear signal
        for sig_type, sig_text in regime_data.get("signals", []):
            if sig_type in ("BEARISH", "CAUTION"):
                return sig_text
        # Fall back to top pick's bear case
        if recs:
            nav = analyses.get(recs[0]["ticker"], {}).get("narrative", {})
            bc  = nav.get("bear_case", "")
            if bc and bc != "No significant bear case factors at current levels.":
                return bc.split(" | ")[0]
        regime = regime_data.get("regime", "NEUTRAL")
        defaults = {
            "BULLISH":   "Extended valuations reduce margin of safety in this cycle.",
            "NEUTRAL":   "Mixed macro signals warrant selective, disciplined positioning.",
            "DEFENSIVE": "Elevated risk environment — favor capital preservation.",
        }
        return defaults.get(regime, "Monitor volatility and position sizing carefully.")

    def _strategy(self, regime: str, profile: dict, confidence: int) -> str:
        etf_pct = profile["etf_pct"]
        label   = profile["label"]
        if regime == "BULLISH" and confidence >= 58:
            return (f"Risk-on positioning is appropriate for a {label.lower()} investor. "
                    f"Maintain {etf_pct}% ETF core and selectively add high-quality growth exposure on pullbacks.")
        if regime == "DEFENSIVE":
            raised = min(90, etf_pct + 10)
            return (f"Defensive positioning recommended. Raise ETF allocation toward {raised}%. "
                    f"Avoid speculative names. Consider holding 10–15% cash as dry powder.")
        return (f"Balanced approach for a {label.lower()} investor. "
                f"Maintain {etf_pct}% ETF core and add quality stocks selectively. "
                f"Avoid concentration in any single sector until market clarity improves.")

    def _market_brief(self, regime_data: dict, analyses: dict) -> str:
        regime = regime_data["regime"]
        bull   = regime_data.get("bull_pts", 0)
        bear   = regime_data.get("bear_pts", 0)

        intro = {
            "BULLISH":   "Equity markets are in a constructive risk-on environment.",
            "NEUTRAL":   "Markets are sending mixed signals, warranting a balanced approach.",
            "DEFENSIVE": "Macro conditions are signaling elevated caution across risk assets.",
        }.get(regime, "Market conditions are uncertain.")

        parts = [intro]

        # Yield signal
        ys = next((s[1] for s in regime_data.get("signals", [])
                   if "yield" in s[1].lower()), None)
        if ys:
            parts.append(ys + ".")

        # VIX signal
        vs = next((s[1] for s in regime_data.get("signals", [])
                   if "VIX" in s[1]), None)
        if vs:
            parts.append(vs + ".")

        parts.append(
            f"Signal balance: {bull} bullish vs {bear} bearish macro indicators. "
            f"{'Momentum favors risk assets.' if bull > bear else 'Caution flags outweigh positive signals.'}"
        )

        buy_count = sum(1 for a in analyses.values() if a.get("score", 0) >= 72)
        parts.append(
            f"{buy_count} of {len(analyses)} analyzed assets currently meet buy criteria."
        )

        return " ".join(parts)


# ─────────────────────────────────────────────────────────────
#  PORTFOLIO MANAGER
# ─────────────────────────────────────────────────────────────
class PortfolioManager:
    def __init__(self, filepath: str):
        self.filepath = filepath
        self._ensure_file()

    def _ensure_file(self):
        if not Path(self.filepath).exists():
            self.save({
                "settings": {
                    "monthly_budget": CONFIG["monthly_budget"],
                    "currency": "USD",
                    "profile": CONFIG["default_profile"],
                    "created": str(datetime.now().date()),
                },
                "holdings": [],
            })

    def load(self) -> dict:
        with open(self.filepath, encoding="utf-8") as f:
            return json.load(f)

    def save(self, data: dict):
        with open(self.filepath, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)

    def get_summary(self) -> dict:
        portfolio = self.load()
        holdings  = portfolio.get("holdings", [])
        summary   = []

        for h in holdings:
            try:
                info  = yf.Ticker(h["ticker"]).history(period="5d")
                price = info["Close"].iloc[-1] if not info.empty else 0.0
                value    = price * h["quantity"]
                invested = h["total_invested"]
                pnl      = value - invested
                pnl_pct  = (pnl / invested * 100) if invested > 0 else 0
                summary.append({**h,
                    "current_price": round(price, 2),
                    "current_value": round(value, 2),
                    "pnl":           round(pnl, 2),
                    "pnl_pct":       round(pnl_pct, 2),
                })
            except Exception:
                summary.append({**h, "current_price": 0,
                                "current_value": 0, "pnl": 0, "pnl_pct": 0})

        total_invested = sum(h["total_invested"] for h in holdings)
        total_value    = sum(h["current_value"]  for h in summary)

        return {
            "holdings":       summary,
            "total_invested": round(total_invested, 2),
            "total_value":    round(total_value, 2),
            "total_pnl":      round(total_value - total_invested, 2),
            "total_pnl_pct":  round((total_value - total_invested) / total_invested * 100, 2)
                              if total_invested > 0 else 0,
        }

    def generate_warnings(self, summary: dict, analyses: dict) -> list:
        warnings_list = []
        total_value   = summary["total_value"] or 1

        for h in summary["holdings"]:
            ticker = h["ticker"]
            alloc  = h["current_value"] / total_value * 100

            if alloc > 35:
                warnings_list.append(
                    f"CONCENTRATION: {ticker} = {alloc:.1f}% of portfolio — consider trimming to reduce single-stock risk")
            if h["pnl_pct"] < -15:
                warnings_list.append(
                    f"LOSS ALERT: {ticker} is down {h['pnl_pct']:.1f}% — review thesis and position size")
            if ticker in analyses and analyses[ticker].get("trend_score", 50) < 30:
                warnings_list.append(
                    f"TREND WARNING: {ticker} shows weakening technical momentum — consider position review")

        return warnings_list


# ─────────────────────────────────────────────────────────────
#  RECOMMENDATION ENGINE  (profile-aware)
# ─────────────────────────────────────────────────────────────
class RecommendationEngine:
    """
    Allocates monthly budget based on investor profile + market regime.
    Avoids over-concentration and duplicate ETF exposure.
    """

    def recommend(self, analyses: dict, regime: str,
                  budget: float, profile: dict) -> list:
        min_score = {"BULLISH": 52, "NEUTRAL": 58, "DEFENSIVE": 65}.get(regime, 58)
        min_score = max(min_score, profile.get("min_score", 58))

        etf_tickers = [t for cat in WATCHLIST.values()
                       if cat["risk"] in ("LOW", "LOW-MEDIUM")
                       for t in cat["tickers"]]

        candidates = [(t, a) for t, a in analyses.items()
                      if a.get("score", 0) >= min_score]
        candidates.sort(key=lambda x: x[1]["score"], reverse=True)

        etf_pct      = profile.get("etf_pct", 70) / 100
        etf_budget   = budget * etf_pct
        stock_budget = budget * (1 - etf_pct)
        max_single   = budget * (profile.get("max_single_pct", 35) / 100)

        recs        = []
        etf_spent   = 0.0
        stock_spent = 0.0
        preferred   = set(profile.get("preferred_tickers", []))

        for ticker, analysis in candidates[:10]:
            is_etf    = ticker in etf_tickers
            label, color = analysis["label"], analysis["color"]

            if is_etf:
                available = min(etf_budget - etf_spent, max_single)
            else:
                available = min(stock_budget - stock_spent, max_single)

            if available < 5:
                continue

            # Boost preferred tickers by 20%
            boost  = 1.2 if ticker in preferred else 1.0
            weight = analysis["score"] / 100 * boost
            amount = round(min(available * weight * 1.4, available), 2)
            amount = max(amount, 5.0)

            narrative = analysis.get("narrative", {})
            reason = narrative.get("summary", analysis.get("top_note", ""))[:120]

            recs.append({
                "ticker":  ticker,
                "score":   analysis["score"],
                "label":   label,
                "color":   color,
                "amount":  amount,
                "type":    "ETF/Index" if is_etf else "Stock",
                "reason":  reason,
                "etf_info": ETF_KNOWLEDGE.get(ticker),
            })

            if is_etf:
                etf_spent += amount
            else:
                stock_spent += amount

        return recs[:5]


# ─────────────────────────────────────────────────────────────
#  REPORT GENERATOR
# ─────────────────────────────────────────────────────────────
class ReportGenerator:

    def print_header(self):
        print("\n" + "=" * 65)
        print("  STOCK ADVISOR v3  --  AI-Powered Investment Research")
        print("  Advisory only. Never places real trades. Not financial advice.")
        print("=" * 65)

    def print_regime(self, regime_data: dict):
        r = regime_data["regime"]
        print(f"\n  MARKET REGIME: {r}  (Bull:{regime_data['bull_pts']} Bear:{regime_data['bear_pts']})")
        print(f"  {regime_data['advice']}\n")
        for signal_type, text in regime_data["signals"]:
            icon = "▲" if signal_type == "BULLISH" else ("▼" if signal_type == "BEARISH" else "●")
            print(f"  {icon} {text}")

    def print_analysis(self, analyses: dict):
        print(f"\n{'='*65}")
        print(f"  ASSET SCORES  (0-100)")
        print(f"{'='*65}")
        print(f"  {'Ticker':<10} {'Score':>6}  {'Rating':<14}  {'Fund':>5} {'Grwth':>5} {'Health':>6} {'Divid':>5} {'Trend':>5} {'Risk':>5}")
        print(f"  {'-'*63}")
        for ticker, a in sorted(analyses.items(), key=lambda x: x[1]["score"], reverse=True):
            print(f"  {ticker:<10} {a['score']:>5}/100  {a['label']:<14}  "
                  f"{int(a.get('fund_score',50)):>5} {int(a.get('grow_score',50)):>5} "
                  f"{int(a.get('health_score',50)):>6} {int(a.get('div_score',50)):>5} "
                  f"{int(a.get('trend_score',50)):>5} {int(a.get('risk_score',50)):>5}")

    def print_recommendations(self, recs: list, budget: float, profile: dict):
        total = sum(r["amount"] for r in recs)
        print(f"\n{'='*65}")
        print(f"  MONTHLY ALLOCATION  (${budget:.0f} | Profile: {profile['label']})")
        print(f"{'='*65}")
        print(f"  {'Ticker':<10} {'Amount':>8}  {'Type':<12}  Rating")
        print(f"  {'-'*45}")
        for r in recs:
            print(f"  {r['ticker']:<10} ${r['amount']:>7.2f}  {r['type']:<12}  {r['label']}")
        print(f"  {'-'*45}")
        print(f"  {'TOTAL':<10} ${total:>7.2f}  (${budget-total:.2f} unallocated → cash or VOO)")

    def print_portfolio(self, summary: dict):
        if not summary["holdings"]:
            print("\n  Portfolio is empty. Add positions to track performance.")
            return
        print(f"\n{'='*65}")
        print(f"  PORTFOLIO  (invested: ${summary['total_invested']:.2f})")
        print(f"{'='*65}")
        for h in summary["holdings"]:
            sign = "+" if h["pnl"] >= 0 else ""
            print(f"  {h['ticker']:<10} {h['quantity']:.4f} shares  "
                  f"avg ${h['avg_price']:.2f}  now ${h['current_price']:.2f}  "
                  f"{sign}${h['pnl']:.2f} ({sign}{h['pnl_pct']:.1f}%)")
        sign = "+" if summary["total_pnl"] >= 0 else ""
        print(f"  {'─'*55}")
        print(f"  Total: ${summary['total_value']:.2f}  {sign}${summary['total_pnl']:.2f} ({sign}{summary['total_pnl_pct']:.1f}%)")

    def generate_html(self, analyses: dict, regime_data: dict, recs: list,
                      summary: dict, warnings_list: list, news: list,
                      budget: float, profile: dict) -> str:

        regime_color = {"BULLISH": "#3fb950", "NEUTRAL": "#d29922", "DEFENSIVE": "#f85149"}
        r_color = regime_color.get(regime_data["regime"], "#8b949e")
        total_rec = sum(r["amount"] for r in recs)
        now = datetime.now().strftime("%Y-%m-%d %H:%M")

        # --- Asset cards ---
        cards_html = ""
        for ticker, a in sorted(analyses.items(), key=lambda x: x[1]["score"], reverse=True):
            color    = a["color"]
            nav      = a.get("narrative", {})
            etf_info = ETF_KNOWLEDGE.get(ticker)

            # Score bars
            def bar(val, color_hex):
                return (f'<div class="dim-row"><div class="dim-label">{int(val)}</div>'
                        f'<div class="dim-track"><div class="dim-fill" style="width:{val}%;background:{color_hex}66"></div></div></div>')

            scores_html = (
                f'<div class="dim-group">'
                f'<div class="dim-title">Fundamentals</div>{bar(a.get("fund_score",50),"#58a6ff")}'
                f'<div class="dim-title" style="margin-top:4px">Growth</div>{bar(a.get("grow_score",50),"#56d364")}'
                f'<div class="dim-title" style="margin-top:4px">Health</div>{bar(a.get("health_score",50),"#79c0ff")}'
                f'<div class="dim-title" style="margin-top:4px">Dividend</div>{bar(a.get("div_score",50),"#d29922")}'
                f'<div class="dim-title" style="margin-top:4px">Momentum</div>{bar(a.get("trend_score",50),"#a5d6a7")}'
                f'<div class="dim-title" style="margin-top:4px">Risk</div>{bar(a.get("risk_score",50),"#ff9100")}'
                f'</div>'
            )

            summary_text  = nav.get("summary", a.get("top_note", ""))
            bull_text     = nav.get("bull_case", "—")
            bear_text     = nav.get("bear_case", "—")
            beginner_text = nav.get("beginner", "")
            risk_text     = nav.get("risk_note", "")

            etf_block = ""
            if etf_info:
                sector_bars = "".join(
                    f'<div style="margin-bottom:2px"><span style="color:#8b949e;font-size:.7rem;display:inline-block;width:110px">{s}</span>'
                    f'<div style="display:inline-block;background:#21262d;width:100px;height:6px;border-radius:3px;vertical-align:middle">'
                    f'<div style="background:#58a6ff66;width:{pct}%;height:100%;border-radius:3px"></div></div>'
                    f'<span style="color:#8b949e;font-size:.7rem;margin-left:6px">{pct}%</span></div>'
                    for s, pct in list(etf_info.get("sectors", {}).items())[:4]
                )
                overlap = ", ".join(etf_info.get("overlap", [])) or "None"
                etf_block = f"""
                <div class="etf-block">
                  <div style="display:grid;grid-template-columns:1fr 1fr;gap:10px">
                    <div>
                      <div class="note-label">Top Sectors</div>
                      {sector_bars}
                    </div>
                    <div>
                      <div class="note-label">Expense Ratio</div>
                      <div style="font-size:.9rem;color:#f0f6fc;margin-bottom:6px">{etf_info.get('expense_ratio',0):.2f}%/yr</div>
                      <div class="note-label">Div. Yield (approx)</div>
                      <div style="font-size:.9rem;color:#d29922;margin-bottom:6px">~{etf_info.get('dividend_yield_approx',0):.1f}%</div>
                      <div class="note-label">Overlaps With</div>
                      <div style="font-size:.78rem;color:#8b949e">{overlap}</div>
                    </div>
                  </div>
                  <div style="margin-top:8px">
                    <div class="note-label">Risks</div>
                    <div style="font-size:.78rem;color:#8b949e">{etf_info.get('risks','')}</div>
                  </div>
                </div>"""

            cards_html += f"""
            <div class="asset-card">
              <div class="asset-header">
                <span class="asset-ticker">{ticker}</span>
                <span class="score-badge" style="background:{color}22;color:{color};border:1px solid {color}66">
                  {a['score']}/100 — {a['label']}
                </span>
                <span class="risk-tag">{a.get('risk_label','?')} RISK</span>
              </div>
              <div class="asset-grid">
                <div class="asset-left">
                  <p style="font-size:.82rem;color:#c9d1d9;line-height:1.6;margin-bottom:10px">{summary_text}</p>
                  <div class="case-row">
                    <div class="bull-case"><span class="case-label bull-label">▲ Bull Case</span><br>{bull_text}</div>
                    <div class="bear-case"><span class="case-label bear-label">▼ Bear Case</span><br>{bear_text}</div>
                  </div>
                  {f'<div class="beginner-block"><span style="color:#d29922;font-weight:700;font-size:.7rem">BEGINNER NOTE</span><br><span style="color:#8b949e;font-size:.78rem">{beginner_text}</span></div>' if beginner_text else ''}
                  <div style="margin-top:8px;font-size:.75rem;color:#484f58">{risk_text}</div>
                  {etf_block}
                </div>
                <div class="asset-right">
                  {scores_html}
                </div>
              </div>
            </div>"""

        # --- Rec rows ---
        rec_rows = ""
        for r in recs:
            c = r["color"]
            short_reason = (r.get("narrative", {}).get("summary", r.get("reason", "")))[:100]
            rec_rows += f"""<tr>
              <td><strong>{r['ticker']}</strong></td>
              <td><strong>${r['amount']:.2f}</strong></td>
              <td style="font-size:.75rem;color:#8b949e">{r['type']}</td>
              <td><span class="pill" style="background:{c}22;color:{c};border:1px solid {c}66">{r['label']}</span></td>
              <td style="color:#8b949e;font-size:.8rem">{short_reason}</td>
            </tr>"""

        # --- Portfolio rows ---
        port_rows = ""
        if summary["holdings"]:
            for h in summary["holdings"]:
                sign  = "+" if h["pnl"] >= 0 else ""
                color = "#3fb950" if h["pnl"] >= 0 else "#f85149"
                alloc = h["current_value"] / (summary["total_value"] or 1) * 100
                port_rows += f"""<tr>
                  <td><strong>{h['ticker']}</strong></td>
                  <td>{h['quantity']:.4f}</td>
                  <td>${h['avg_price']:.2f}</td>
                  <td>${h['current_price']:.2f}</td>
                  <td>${h['current_value']:.2f}</td>
                  <td style="color:{color}">{sign}${h['pnl']:.2f} ({sign}{h['pnl_pct']:.1f}%)</td>
                  <td>{alloc:.1f}%</td>
                </tr>"""
        else:
            port_rows = '<tr><td colspan="7" style="color:#8b949e;text-align:center;padding:24px">No holdings yet</td></tr>'

        # --- Warnings ---
        warn_html = "".join(f'<div class="warn-item">⚠ {w}</div>' for w in warnings_list)
        if not warn_html:
            warn_html = '<div style="color:#3fb950;font-size:.85rem">✓ No warnings. Portfolio looks healthy.</div>'

        # --- News ---
        news_html = "".join(
            f'<div class="news-item"><span class="news-src">{n["source"]}</span>{n["title"]}</div>'
            for n in news[:20]
        ) or '<div style="color:#8b949e">No recent news loaded.</div>'

        # --- Signals ---
        signal_html = "".join(
            f'<div style="padding:5px 0;border-bottom:1px solid #1c2128;font-size:.84rem;color:'
            f'{"#3fb950" if s[0]=="BULLISH" else "#f85149" if s[0]=="BEARISH" else "#d29922"}">'
            f'{"▲" if s[0]=="BULLISH" else "▼" if s[0]=="BEARISH" else "●"} {s[1]}</div>'
            for s in regime_data["signals"]
        )

        # --- Profile info ---
        profile_html = f"""
        <div style="background:#0d1117;border:1px solid #21262d;border-radius:6px;padding:14px;margin-bottom:16px">
          <div style="font-size:.7rem;color:#8b949e;text-transform:uppercase;letter-spacing:.06em;margin-bottom:6px">
            Investor Profile: {profile['label']}
          </div>
          <div style="font-size:.85rem;color:#c9d1d9;margin-bottom:4px">{profile['description']}</div>
          <div style="font-size:.78rem;color:#58a6ff">{profile['advice']}</div>
          <div style="font-size:.72rem;color:#484f58;margin-top:4px">
            ETF target: {profile['etf_pct']}% · Max single position: {profile['max_single_pct']}% · Horizon: {profile['time_horizon']}
          </div>
        </div>"""

        return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width,initial-scale=1">
  <title>Stock Advisor v3 — {now}</title>
  <style>
    *{{box-sizing:border-box;margin:0;padding:0}}
    body{{background:#0d1117;color:#e6edf3;font-family:'Segoe UI',system-ui,sans-serif;padding:20px}}
    h2{{font-size:.75rem;color:#8b949e;text-transform:uppercase;letter-spacing:.08em;margin-bottom:10px}}
    .header{{background:#161b22;border:1px solid #30363d;border-radius:8px;padding:16px 20px;margin-bottom:16px;display:flex;align-items:center;gap:12px;flex-wrap:wrap}}
    .header h1{{font-size:1.15rem;font-weight:700;color:#f0f6fc}}
    .pill{{display:inline-block;padding:3px 9px;border-radius:10px;font-size:.72rem;font-weight:700}}
    .grid4{{display:grid;grid-template-columns:repeat(auto-fit,minmax(180px,1fr));gap:12px;margin-bottom:16px}}
    .card{{background:#161b22;border:1px solid #30363d;border-radius:8px;padding:16px 18px}}
    .card-lbl{{font-size:.68rem;color:#8b949e;text-transform:uppercase;letter-spacing:.05em;margin-bottom:5px}}
    .card-val{{font-size:1.5rem;font-weight:700}}
    .card-sub{{font-size:.78rem;color:#8b949e;margin-top:3px}}
    .section{{background:#161b22;border:1px solid #30363d;border-radius:8px;padding:18px;margin-bottom:16px}}
    table{{width:100%;border-collapse:collapse}}
    thead th{{padding:9px 12px;text-align:left;font-size:.68rem;color:#8b949e;text-transform:uppercase;background:#0d1117;border-bottom:1px solid #30363d}}
    tbody tr{{border-bottom:1px solid #1c2128}}
    tbody tr:hover{{background:#1c2128}}
    tbody td{{padding:11px 12px;font-size:.85rem}}
    .asset-card{{background:#0d1117;border:1px solid #21262d;border-radius:6px;padding:16px;margin-bottom:10px}}
    .asset-header{{display:flex;align-items:center;gap:10px;margin-bottom:12px;flex-wrap:wrap}}
    .asset-ticker{{font-size:1.05rem;font-weight:700;color:#f0f6fc}}
    .score-badge{{padding:3px 10px;border-radius:10px;font-size:.78rem;font-weight:700}}
    .risk-tag{{font-size:.68rem;color:#8b949e;margin-left:auto}}
    .asset-grid{{display:grid;grid-template-columns:1fr 240px;gap:14px}}
    @media(max-width:700px){{.asset-grid{{grid-template-columns:1fr}}}}
    .case-row{{display:grid;grid-template-columns:1fr 1fr;gap:10px;margin-bottom:8px}}
    .bull-case{{background:#0d1f0e;border:1px solid #2ea04322;border-radius:4px;padding:8px 10px;font-size:.77rem;color:#8b949e;line-height:1.5}}
    .bear-case{{background:#1a0e0e;border:1px solid #da363322;border-radius:4px;padding:8px 10px;font-size:.77rem;color:#8b949e;line-height:1.5}}
    .case-label{{font-size:.68rem;font-weight:700;display:block;margin-bottom:3px}}
    .bull-label{{color:#3fb950}}
    .bear-label{{color:#f85149}}
    .beginner-block{{background:#161b2290;border:1px solid #30363d44;border-radius:4px;padding:8px 10px;margin-top:8px}}
    .etf-block{{background:#0e1a2e;border:1px solid #1f6feb22;border-radius:4px;padding:10px;margin-top:8px}}
    .note-label{{font-size:.68rem;color:#8b949e;text-transform:uppercase;letter-spacing:.05em;margin-bottom:3px}}
    .dim-group{{background:#161b22;border:1px solid #21262d;border-radius:4px;padding:12px}}
    .dim-row{{display:flex;align-items:center;gap:6px;margin-bottom:3px}}
    .dim-label{{font-size:.7rem;color:#8b949e;width:22px;text-align:right;flex-shrink:0}}
    .dim-title{{font-size:.65rem;color:#484f58;text-transform:uppercase;letter-spacing:.04em;margin-top:2px}}
    .dim-track{{flex:1;background:#21262d;border-radius:2px;height:5px;overflow:hidden}}
    .dim-fill{{height:100%;border-radius:2px;transition:width .4s ease}}
    .warn-item{{background:#2b1a1a;border:1px solid #da363344;border-radius:4px;padding:8px 10px;margin-bottom:5px;color:#f85149;font-size:.83rem}}
    .news-item{{padding:7px 0;border-bottom:1px solid #1c2128;font-size:.8rem;line-height:1.4}}
    .news-src{{color:#58a6ff;font-size:.67rem;font-weight:700;margin-right:7px;text-transform:uppercase}}
    .green{{color:#3fb950}} .red{{color:#f85149}}
    .disclaimer{{font-size:.72rem;color:#484f58;margin-top:20px;text-align:center;line-height:1.7;border-top:1px solid #21262d;padding-top:14px}}
  </style>
</head>
<body>
  <div class="header">
    <h1>Stock Advisor v3</h1>
    <span class="pill" style="background:#1f6feb22;color:#58a6ff;border:1px solid #1f6feb66">ADVISORY ONLY</span>
    <span class="pill" style="background:#da363322;color:#f85149;border:1px solid #da363366">NEVER PLACES REAL TRADES</span>
    <span style="margin-left:auto;font-size:.78rem;color:#8b949e">{now}</span>
  </div>

  {profile_html}

  <div class="grid4">
    <div class="card">
      <div class="card-lbl">Market Regime</div>
      <div class="card-val" style="color:{r_color}">{regime_data['regime']}</div>
      <div class="card-sub">{regime_data['advice'][:55]}...</div>
    </div>
    <div class="card">
      <div class="card-lbl">Monthly Budget</div>
      <div class="card-val">${budget:.0f}</div>
      <div class="card-sub">Suggested: ${total_rec:.2f}</div>
    </div>
    <div class="card">
      <div class="card-lbl">Portfolio Value</div>
      <div class="card-val">${summary['total_value']:.2f}</div>
      <div class="card-sub {'green' if summary['total_pnl']>=0 else 'red'}">
        {'+'if summary['total_pnl']>=0 else ''}${summary['total_pnl']:.2f}
        ({'+'if summary['total_pnl_pct']>=0 else ''}{summary['total_pnl_pct']:.1f}%)
      </div>
    </div>
    <div class="card">
      <div class="card-lbl">Assets Analyzed</div>
      <div class="card-val">{len(analyses)}</div>
      <div class="card-sub">{sum(1 for a in analyses.values() if a['score']>=65)} rated Buy+</div>
    </div>
  </div>

  <div class="section">
    <h2>Market Regime Signals</h2>
    {signal_html}
  </div>

  <div class="section">
    <h2>Suggested Monthly Allocation — ${budget:.0f} ({profile['label']})</h2>
    <table>
      <thead><tr><th>Ticker</th><th>Amount</th><th>Type</th><th>Rating</th><th>Key Reason</th></tr></thead>
      <tbody>{rec_rows}</tbody>
    </table>
    <div style="margin-top:10px;font-size:.78rem;color:#8b949e">
      Allocated: ${total_rec:.2f} | Unallocated: ${budget-total_rec:.2f} → keep as cash or add to VOO
    </div>
  </div>

  <div class="section">
    <h2>Portfolio Holdings</h2>
    <table>
      <thead><tr><th>Ticker</th><th>Shares</th><th>Avg Price</th><th>Current</th><th>Value</th><th>P&amp;L</th><th>Allocation</th></tr></thead>
      <tbody>{port_rows}</tbody>
    </table>
  </div>

  <div class="section">
    <h2>Asset Research (7-Dimension Scoring)</h2>
    {cards_html}
  </div>

  <div class="section">
    <h2>Warnings &amp; Alerts</h2>
    {warn_html}
  </div>

  <div class="section">
    <h2>Recent Market Headlines</h2>
    <p style="font-size:.72rem;color:#8b949e;margin-bottom:10px">
      Sentiment uses broad market keyword analysis — treat as a rough signal, not a precise indicator.
    </p>
    {news_html}
  </div>

  <div class="disclaimer">
    DISCLAIMER: This report is for educational purposes only and does not constitute financial advice.<br>
    Past performance does not guarantee future results. Always do your own research (DYOR).<br>
    Never invest money you cannot afford to lose. Consider consulting a qualified financial advisor.
  </div>
</body>
</html>"""

    def save_html(self, content: str, report_dir: str) -> str:
        Path(report_dir).mkdir(exist_ok=True)
        filename = f"report_{datetime.now().strftime('%Y-%m-%d_%H%M')}.html"
        filepath = os.path.join(report_dir, filename)
        with open(filepath, "w", encoding="utf-8") as f:
            f.write(content)
        return filepath


# ─────────────────────────────────────────────────────────────
#  MAIN ORCHESTRATOR
# ─────────────────────────────────────────────────────────────
class StockAdvisor:

    def __init__(self, profile_name: str = None):
        self.fetcher       = DataFetcher()
        self.regime_det    = MarketRegimeDetector()
        self.analyzer      = AssetAnalyzer()
        self.narrative_eng = NarrativeEngine()
        self.brief_engine  = InvestmentBriefEngine()
        self.portfolio     = PortfolioManager(CONFIG["portfolio_file"])
        self.rec_engine    = RecommendationEngine()
        self.reporter      = ReportGenerator()
        self._regime_data  = {}

        profile_key = profile_name or CONFIG["default_profile"]
        if profile_key not in USER_PROFILES:
            print(f"  Unknown profile '{profile_key}' — falling back to 'balanced'.")
            profile_key = "balanced"
        self.profile = dict(USER_PROFILES[profile_key])
        self.profile["key"] = profile_key

    def _get_category(self, ticker: str) -> tuple:
        for cat_name, cat in WATCHLIST.items():
            if ticker in cat["tickers"]:
                return cat_name, cat["risk"]
        return "Unknown", "MEDIUM"

    def _write_cache(self, analyses: dict, regime_data: dict, recs: list,
                     summary: dict, warnings_list: list, budget: float):
        brief = self.brief_engine.generate(analyses, regime_data, recs, self.profile)
        cache = {
            "updated_at": datetime.now().strftime("%Y-%m-%d %H:%M"),
            "brief":      brief,
            "profile": {
                "key":         self.profile.get("key", "balanced"),
                "label":       self.profile["label"],
                "description": self.profile["description"],
                "advice":      self.profile["advice"],
                "etf_pct":     self.profile["etf_pct"],
            },
            "regime": {
                "regime":   regime_data["regime"],
                "advice":   regime_data["advice"],
                "signals":  regime_data["signals"],
                "bull_pts": regime_data.get("bull_pts", 0),
                "bear_pts": regime_data.get("bear_pts", 0),
            },
            "recommendations": [
                {
                    "ticker":   r["ticker"],
                    "amount":   r["amount"],
                    "type":     r["type"],
                    "label":    r["label"],
                    "color":    r.get("color", "#d29922"),
                    "score":    r["score"],
                    "reason":   r.get("reason", ""),
                    "etf_info": ETF_KNOWLEDGE.get(r["ticker"]),
                }
                for r in recs
            ],
            "analyses": {
                t: {
                    "score":         int(a.get("score", 50)),
                    "raw_score":     int(a.get("raw_score", 50)),
                    "label":         a.get("label", "Hold"),
                    "color":         a.get("color", "#d29922"),
                    "risk_label":    a.get("risk_label", "MEDIUM"),
                    "category":      a.get("category", ""),
                    "top_note":      a.get("top_note", ""),
                    "confidence":    int(a.get("confidence",  55)),
                    "conf_label":    a.get("conf_label", "Medium"),
                    "fund_score":    int(a.get("fund_score",   50)),
                    "grow_score":    int(a.get("grow_score",   50)),
                    "health_score":  int(a.get("health_score", 50)),
                    "div_score":     int(a.get("div_score",    50)),
                    "trend_score":   int(a.get("trend_score",  50)),
                    "risk_score":    int(a.get("risk_score",   50)),
                    "sent_score":    int(a.get("sent_score",   50)),
                    "etf_info":      ETF_KNOWLEDGE.get(t),
                    "narrative":     a.get("narrative", {}),
                }
                for t, a in analyses.items()
            },
            "warnings":  warnings_list,
            "budget":    float(budget),
            "portfolio": {
                "total_invested": float(summary.get("total_invested", 0)),
                "total_value":    float(summary.get("total_value",    0)),
                "total_pnl":      float(summary.get("total_pnl",      0)),
                "total_pnl_pct":  float(summary.get("total_pnl_pct",  0)),
            },
        }
        cache_path = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                  "stock_advisor_cache.json")
        with open(cache_path, "w", encoding="utf-8") as f:
            json.dump(cache, f, indent=2, default=str)

    def analyze_all(self, tickers: list, news: list, quick: bool = False) -> dict:
        analyses = {}
        total    = len(tickers)

        for i, ticker in enumerate(tickers, 1):
            print(f"  Analyzing {ticker}... ({i}/{total})", end="\r")
            try:
                info    = self.fetcher.get_info(ticker)
                history = self.fetcher.get_history(ticker, "1y")
                cat, risk_cat = self._get_category(ticker)
                etf_info = ETF_KNOWLEDGE.get(ticker)

                fs, fn = self.analyzer.analyze_fundamentals(info)
                gs, gn = self.analyzer.analyze_growth(info)
                hs, hn = self.analyzer.health_analyzer.analyze(info)
                ds, dn = self.analyzer.dividend_analyzer.analyze(info, history)
                ts, tn = self.analyzer.analyze_technicals(history)
                rs, rn = self.analyzer.analyze_risk(history, info)
                ss, sn = self.analyzer.analyze_sentiment(ticker, news)

                scores_dict = {
                    "fundamentals": fs, "growth": gs, "health": hs,
                    "dividend": ds, "trend": ts, "risk": rs, "sentiment": ss,
                }
                raw_score = self.analyzer.weighted_score(scores_dict, self.profile)
                score     = self.analyzer.calibrate_score(raw_score)
                label, color = self.analyzer.score_label(score)

                beta       = info.get("beta") or 1.0
                risk_label = self.analyzer.risk_label(rs, beta)
                top_note   = fn[0] if fn else (gn[0] if gn else (tn[0] if tn else ""))

                confidence, conf_label = self.analyzer.compute_confidence(
                    info, scores_dict, self._regime_data
                )

                narrative = self.narrative_eng.generate(
                    ticker, info,
                    {**scores_dict, "total": score},
                    {"fund": fn, "grow": gn, "health": hn, "div": dn,
                     "trend": tn, "risk": rn, "sent": sn},
                    etf_info,
                )

                analyses[ticker] = {
                    "score":        score,
                    "raw_score":    raw_score,
                    "label":        label,
                    "color":        color,
                    "risk_label":   risk_label,
                    "category":     cat,
                    "top_note":     top_note,
                    "confidence":   confidence,
                    "conf_label":   conf_label,
                    "fund_score":   fs, "fund_notes":   fn,
                    "grow_score":   gs, "grow_notes":   gn,
                    "health_score": hs, "health_notes": hn,
                    "div_score":    ds, "div_notes":    dn,
                    "trend_score":  ts, "trend_notes":  tn,
                    "risk_score":   rs, "risk_notes":   rn,
                    "sent_score":   ss, "sent_notes":   sn,
                    "narrative":    narrative,
                    "etf_info":     etf_info,
                }

                time.sleep(0.3)

            except Exception as e:
                print(f"\n  Could not analyze {ticker}: {e}")
                analyses[ticker] = {
                    "score": 50, "label": "Hold", "color": "#d29922",
                    "risk_label": "MEDIUM", "category": "Unknown",
                    "top_note": "Data unavailable", "narrative": {},
                }

        print(" " * 60, end="\r")
        return analyses

    def run(self, quick: bool = False, ticker_filter: str = None,
            portfolio_only: bool = False):
        self.reporter.print_header()
        print(f"  Profile: {self.profile['label']} — {self.profile['description']}")

        if portfolio_only:
            summary = self.portfolio.get_summary()
            self.reporter.print_portfolio(summary)
            return

        tickers = ([ticker_filter.upper()] if ticker_filter
                   else [t for cat in WATCHLIST.values() for t in cat["tickers"]])

        budget = self.portfolio.load()["settings"].get("monthly_budget", CONFIG["monthly_budget"])

        print("\n  Fetching market news...")
        news = self.fetcher.get_news()
        print(f"  {len(news)} headlines loaded")

        print("  Detecting market regime...")
        market_data = self.fetcher.get_market_data()
        regime_data        = self.regime_det.detect(market_data)
        self._regime_data  = regime_data  # shared with analyze_all for confidence
        self.reporter.print_regime(regime_data)

        print(f"\n  Analyzing {len(tickers)} assets (7 dimensions each)...")
        analyses = self.analyze_all(tickers, news, quick)

        recs = self.rec_engine.recommend(analyses, regime_data["regime"], budget, self.profile)

        print("  Loading portfolio...")
        summary       = self.portfolio.get_summary()
        warnings_list = self.portfolio.generate_warnings(summary, analyses)

        self.reporter.print_analysis(analyses)
        self.reporter.print_recommendations(recs, budget, self.profile)
        self.reporter.print_portfolio(summary)

        if warnings_list:
            print("\n  WARNINGS:")
            for w in warnings_list:
                print(f"  ⚠ {w}")

        self._write_cache(analyses, regime_data, recs, summary, warnings_list, budget)

        if not quick:
            print("\n  Generating HTML report...")
            html     = self.reporter.generate_html(
                           analyses, regime_data, recs, summary,
                           warnings_list, news, budget, self.profile)
            filepath = self.reporter.save_html(html, CONFIG["report_dir"])
            print(f"  Report saved: {filepath}")

        print(f"\n{'='*65}")
        print("  Advisory only. Never places real trades. DYOR.")
        print(f"{'='*65}\n")


# ─────────────────────────────────────────────────────────────
#  ENTRY POINT
# ─────────────────────────────────────────────────────────────
if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Stock Advisor v3 — AI-Powered Investment Research")
    parser.add_argument("--quick",     action="store_true",
                        help="Terminal output only, skip HTML report")
    parser.add_argument("--portfolio", action="store_true",
                        help="Show portfolio overview only")
    parser.add_argument("--ticker",    default=None,
                        help="Analyze a single ticker, e.g. --ticker AAPL")
    parser.add_argument("--profile",   default=None,
                        choices=list(USER_PROFILES.keys()),
                        help="Investor profile: " + ", ".join(USER_PROFILES.keys()))
    args = parser.parse_args()

    advisor = StockAdvisor(profile_name=args.profile)
    advisor.run(
        quick          = args.quick,
        ticker_filter  = args.ticker,
        portfolio_only = args.portfolio,
    )
