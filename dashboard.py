#!/usr/bin/env python3
"""
dashboard.py — AI Trading Dashboard backend
FastAPI server: live prices, per-account strategy, streaming agent analysis

Run: python dashboard.py
Then open: http://localhost:8765
"""

import json
import time
import asyncio
from pathlib import Path
from datetime import datetime, date
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Dict, List, Optional, Tuple

import anthropic
import requests
import uvicorn
from fastapi import FastAPI, HTTPException
from fastapi.responses import StreamingResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware

# ── Paths ─────────────────────────────────────────────────────────────────────

BASE_DIR       = Path(__file__).parent
PORTFOLIO_JSON = BASE_DIR / "portfolio" / "portfolio.json"
DASHBOARD_DIR  = BASE_DIR / "dashboard"

# ── App ───────────────────────────────────────────────────────────────────────

app = FastAPI(title="AI Trading Dashboard")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

# ── Yahoo Finance helpers ─────────────────────────────────────────────────────

_YF_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    "Accept": "application/json",
}


def _yf_get(url: str, params: dict = None, timeout: int = 10) -> Optional[Dict]:
    try:
        r = requests.get(url, params=params, headers=_YF_HEADERS, timeout=timeout)
        r.raise_for_status()
        return r.json()
    except Exception:
        return None


def _yf_quote_single(sym: str) -> Tuple[str, Optional[Dict]]:
    """Fetch quote for one symbol via the v8 chart meta (always works, no auth needed)."""
    data = _yf_get(
        f"https://query1.finance.yahoo.com/v8/finance/chart/{sym}",
        params={"range": "1d", "interval": "1m"},
    )
    if not data:
        return sym, None
    try:
        meta  = data["chart"]["result"][0]["meta"]
        cur   = meta.get("regularMarketPrice", 0) or 0
        prev  = meta.get("chartPreviousClose") or meta.get("previousClose") or cur
        chg   = round(cur - prev, 2)
        chgp  = round(chg / prev * 100, 2) if prev else 0
        return sym, {
            "price":          round(cur, 2),
            "prev_close":     round(prev, 2),
            "day_change":     chg,
            "day_change_pct": chgp,
            "week52_high":    meta.get("fiftyTwoWeekHigh"),
            "week52_low":     meta.get("fiftyTwoWeekLow"),
            "name":           meta.get("longName") or meta.get("shortName", sym),
        }
    except Exception:
        return sym, None


def _yf_quote(symbols: List[str]) -> Dict:
    """Batch quote by fetching all symbols concurrently."""
    results = {}
    with ThreadPoolExecutor(max_workers=min(len(symbols), 8)) as ex:
        futures = {ex.submit(_yf_quote_single, s): s for s in symbols}
        for fut in as_completed(futures):
            sym, data = fut.result()
            if data:
                results[sym] = data
    return results


def _yf_detail(symbol: str) -> dict:
    """Fetch detailed quote summary (v11) for a single ticker."""
    data = _yf_get(
        f"https://query2.finance.yahoo.com/v11/finance/quoteSummary/{symbol}",
        params={"modules": "summaryDetail,defaultKeyStatistics,assetProfile,recommendationTrend,financialData"},
    )
    out = {}
    if data:
        result = data.get("quoteSummary", {}).get("result", [None])[0] or {}
        profile   = result.get("assetProfile", {})
        fin_data  = result.get("financialData", {})
        key_stats = result.get("defaultKeyStatistics", {})
        summ_d    = result.get("summaryDetail", {})  # noqa: F841

        def raw(d, k):
            v = d.get(k, {})
            return v.get("raw") if isinstance(v, dict) else v

        out = {
            "sector":          profile.get("sector"),
            "industry":        profile.get("industry"),
            "description":     (profile.get("longBusinessSummary") or "")[:400],
            "ps_ratio":        raw(key_stats, "priceToSalesTrailing12Months"),
            "gross_margins":   raw(fin_data, "grossMargins"),
            "operating_margins": raw(fin_data, "operatingMargins"),
            "profit_margins":  raw(fin_data, "profitMargins"),
            "revenue_growth":  raw(fin_data, "revenueGrowth"),
            "total_revenue":   raw(fin_data, "totalRevenue"),
            "free_cashflow":   raw(fin_data, "freeCashflow"),
            "debt_to_equity":  raw(fin_data, "debtToEquity"),
            "roe":             raw(fin_data, "returnOnEquity"),
            "total_cash":      raw(fin_data, "totalCash"),
            "peg_ratio":       raw(key_stats, "pegRatio"),
            "ev_ebitda":       raw(key_stats, "enterpriseToEbitda"),
            "short_pct_float": raw(key_stats, "shortPercentOfFloat"),
            "insider_pct":     raw(key_stats, "heldPercentInsiders"),
            "inst_pct":        raw(key_stats, "heldPercentInstitutions"),
        }
    return out


def _yf_chart(symbol: str, period: str = "1mo", interval: str = "1d") -> List[Dict]:
    """Fetch OHLCV history as a list of {date, close} dicts."""
    data = _yf_get(
        f"https://query1.finance.yahoo.com/v8/finance/chart/{symbol}",
        params={"range": period, "interval": interval},
    )
    if not data:
        return []
    try:
        result    = data["chart"]["result"][0]
        timestamps = result.get("timestamp", [])
        closes     = result["indicators"]["quote"][0].get("close", [])
        out = []
        for ts, c in zip(timestamps, closes):
            if c is not None:
                out.append({"date": str(date.fromtimestamp(ts)), "close": round(c, 2)})
        return out
    except Exception:
        return []


def _yf_news(symbol: str) -> List[str]:
    """Fetch recent news headlines for a symbol."""
    data = _yf_get(
        "https://query1.finance.yahoo.com/v1/finance/search",
        params={"q": symbol, "newsCount": 6, "enableFuzzyQuery": False},
    )
    titles = []
    if data:
        for item in data.get("news", [])[:5]:
            t = item.get("title", "")
            if t:
                titles.append(t)
    return titles


# ── Price cache (60s TTL) ─────────────────────────────────────────────────────

_price_cache: dict = {}
_cache_ts: float = 0.0
CACHE_TTL = 60


def get_live_prices(symbols: List[str]) -> Dict:
    global _price_cache, _cache_ts
    now = time.time()
    if now - _cache_ts < CACHE_TTL and _price_cache:
        return _price_cache
    prices = _yf_quote(symbols)
    _price_cache = prices
    _cache_ts = now
    return prices


# ── Portfolio helpers ─────────────────────────────────────────────────────────

def load_portfolio() -> dict:
    return json.loads(PORTFOLIO_JSON.read_text(encoding="utf-8"))


def enrich_portfolio(data: dict) -> dict:
    symbols = list({p["symbol"] for a in data["accounts"] for p in a["positions"]})
    prices  = get_live_prices(symbols)

    grand_value = 0.0
    grand_day   = 0.0

    for acct in data["accounts"]:
        acct_invested = 0.0
        acct_day      = 0.0
        for pos in acct["positions"]:
            live = prices.get(pos["symbol"])
            if live and live.get("price"):
                lv  = round(live["price"] * pos["shares"], 2)
                ld  = round(live["day_change"] * pos["shares"], 2)
                lg  = round(lv - (pos["cost_basis"] or 0), 2)
                lgp = round(lg / pos["cost_basis"] * 100, 2) if pos.get("cost_basis") else 0
                pos.update({
                    "live_price":          live["price"],
                    "live_value":          lv,
                    "live_day_change":     ld,
                    "live_day_change_pct": live["day_change_pct"],
                    "live_gain_loss":      lg,
                    "live_gain_loss_pct":  lgp,
                })
                acct_invested += lv
                acct_day      += ld
            else:
                pos.update({
                    "live_price":          pos.get("price"),
                    "live_value":          pos.get("market_value"),
                    "live_day_change":     0,
                    "live_day_change_pct": 0,
                    "live_gain_loss":      pos.get("unrealized_gain_loss"),
                    "live_gain_loss_pct":  pos.get("unrealized_gain_loss_pct"),
                })
                acct_invested += pos.get("market_value") or 0

        cash = acct.get("cash") or 0
        acct["live_invested"] = round(acct_invested, 2)
        acct["live_value"]    = round(acct_invested + cash, 2)
        acct["live_day_change"] = round(acct_day, 2)
        grand_value += acct_invested + cash
        grand_day   += acct_day

    prev_total = grand_value - grand_day
    data["live_total"]          = round(grand_value, 2)
    data["live_day_change"]     = round(grand_day, 2)
    data["live_day_change_pct"] = round(grand_day / prev_total * 100, 2) if prev_total else 0
    data["prices_at"]           = datetime.now().strftime("%H:%M:%S")
    return data


# ── API Routes ────────────────────────────────────────────────────────────────

@app.get("/api/portfolio")
def api_portfolio():
    return enrich_portfolio(load_portfolio())


@app.get("/api/prices")
def api_prices():
    data    = load_portfolio()
    symbols = list({p["symbol"] for a in data["accounts"] for p in a["positions"]})
    return get_live_prices(symbols)


@app.get("/api/stock/{symbol}")
def api_stock(symbol: str):
    sym = symbol.upper()
    try:
        quote     = _yf_quote([sym]).get(sym, {})
        detail    = _yf_detail(sym)
        sparkline = _yf_chart(sym, "1mo", "1d")
        news      = _yf_news(sym)

        return {
            "symbol":          sym,
            "name":            quote.get("name", sym),
            "price":           quote.get("price"),
            "market_cap":      quote.get("market_cap"),
            "pe_ratio":        quote.get("pe_ratio"),
            "fwd_pe":          quote.get("fwd_pe"),
            "ps_ratio":        detail.get("ps_ratio"),
            "week52_high":     quote.get("week52_high"),
            "week52_low":      quote.get("week52_low"),
            "avg_volume":      quote.get("avg_volume"),
            "beta":            quote.get("beta"),
            "sector":          detail.get("sector"),
            "industry":        detail.get("industry"),
            "description":     detail.get("description", ""),
            "analyst_target":  quote.get("analyst_target"),
            "analyst_rating":  quote.get("analyst_rating", ""),
            "gross_margins":   detail.get("gross_margins"),
            "operating_margins": detail.get("operating_margins"),
            "profit_margins":  detail.get("profit_margins"),
            "revenue_growth":  detail.get("revenue_growth"),
            "total_revenue":   detail.get("total_revenue"),
            "free_cashflow":   detail.get("free_cashflow"),
            "debt_to_equity":  detail.get("debt_to_equity"),
            "roe":             detail.get("roe"),
            "short_pct_float": detail.get("short_pct_float"),
            "insider_pct":     detail.get("insider_pct"),
            "inst_pct":        detail.get("inst_pct"),
            "sparkline":       sparkline,
            "news":            news,
        }
    except Exception as e:
        raise HTTPException(400, str(e))


# ── Agent Streaming ───────────────────────────────────────────────────────────

AGENT_PROMPTS = {
    "quick": """You are a rapid stock assessment tool. Deliver a compact, actionable stock scorecard.

STOCK DATA:
{data}

Output a quick snapshot with:
- Signal: BUY / HOLD / SELL / AVOID
- 3 bullish factors (specific, with numbers)
- 3 bearish factors (specific, with numbers)
- Key levels: support, resistance, analyst target
- One-line thesis

Format cleanly with headers. Be specific — use actual numbers from the data.
DISCLAIMER: Educational purposes only. Not financial advice.""",

    "technical": """You are a Technical Analysis specialist.

STOCK DATA:
{data}

Deliver comprehensive technical analysis covering:
1. Trend analysis (price relative to 52-week high/low, where in the range)
2. Key support & resistance levels (3 each, derived from 52w range, round numbers)
3. Momentum assessment
4. Volume signals
5. Overall technical signal: Bullish / Neutral / Bearish
6. Entry zone, stop loss, targets with specific prices

Technical Score: X/100 with sub-scores (Trend/Momentum/Volume/Pattern/Rel.Strength, 20 each).
DISCLAIMER: Educational purposes only. Not financial advice.""",

    "fundamental": """You are a Fundamental Analysis specialist.

STOCK DATA:
{data}

Deliver comprehensive fundamental analysis covering:
1. Valuation (P/E vs sector avg, forward P/E, PEG, EV/EBITDA — is it cheap or expensive?)
2. Growth profile (revenue growth trend, earnings trajectory)
3. Profitability (gross/operating/net margins vs industry norms)
4. Financial health (debt/equity, FCF, cash position, interest coverage)
5. Competitive moat (Wide / Narrow / None — with reasoning)
6. Verdict: Undervalued / Fair Value / Overvalued

Fundamental Score: X/100 with sub-scores (Valuation/Growth/Profitability/Health/Moat, 20 each).
DISCLAIMER: Educational purposes only. Not financial advice.""",

    "sentiment": """You are a Sentiment & Momentum Analysis specialist.

STOCK DATA:
{data}

Based on the provided data, analyze:
1. News sentiment — score each headline as positive/negative/neutral
2. Analyst consensus — rating, targets, implied upside/downside
3. Short interest — short % of float, squeeze potential
4. Insider/institutional ownership signals
5. Overall momentum

Sentiment Score: X/100 with sub-scores (News/Analysts/Institutional/Insider/Momentum, 20 each).
DISCLAIMER: Educational purposes only. Not financial advice.""",

    "options": """You are an Options Strategy Advisor.

STOCK DATA:
{data}

Recommend specific options strategies based on current setup:
1. IV environment assessment (high/low/neutral based on beta and recent moves)
2. Top 2-3 strategy recommendations with specific strikes and expirations
3. Risk/reward for each strategy
4. Which account type suits each strategy (taxable/IRA/401k)
5. Position sizing guidance

Use specific prices relative to current price. Flag which strategies generate income.
DISCLAIMER: Educational purposes only. Not financial advice.""",

    "risk": """You are a Risk Assessment specialist.

STOCK DATA:
{data}

Deliver a risk assessment covering:
1. Volatility profile (beta interpretation, expected daily/weekly range)
2. Downside scenarios — three cases (mild -15%, moderate -30%, severe -50%) with catalysts
3. Position sizing (Kelly Criterion estimate, fixed-%, volatility-adjusted)
4. Macro and sector risks
5. Top 5 risks ranked by probability × impact with mitigating factors

Risk Score: X/100 (higher = lower risk). Sub-scores (Volatility/Downside/Macro/Liquidity/RR, 20 each).
DISCLAIMER: Educational purposes only. Not financial advice.""",

    "thesis": """You are an Investment Thesis specialist.

STOCK DATA:
{data}

Build a complete investment thesis:
1. Core thesis (2-3 sentences: why this stock, why now, what's the edge)
2. Bull case: 5 specific catalysts with price targets and timelines
3. Bear case: 5 specific risks with downside targets
4. Catalyst calendar (upcoming events with estimated dates and direction)
5. Entry/exit strategy (entry zone, stop, T1 conservative, T2 aggressive, timeframe)
6. Conviction level (1-10) and invalidation triggers

Thesis Score: X/100 with sub-scores (Catalyst/Timing/Asymmetry/Edge/Conviction, 20 each).
DISCLAIMER: Educational purposes only. Not financial advice.""",

    "guidance": """You are a sharp, direct personal financial advisor reviewing a portfolio account.

ACCOUNT DATA:
{data}

Provide prioritized, actionable guidance to maximize net worth and income for this account:
1. TRIM — which positions to reduce and why (with tax context for this account type)
2. ADD — which positions to increase and why
3. CASH — how to deploy the available cash (${cash})
4. INCOME — covered call or dividend opportunities
5. RISK — concentration issues, correlation risks
6. TOP 3 ACTIONS — the single most important moves ranked

Be direct. Use specific ticker names, prices, and percentages.
DISCLAIMER: Educational purposes only. Not financial advice.""",
}


def build_stock_context(symbol: str) -> str:
    sym   = symbol.upper()
    quote = _yf_quote([sym]).get(sym, {})
    detail = _yf_detail(sym)
    chart  = _yf_chart(sym, "3mo", "1wk")
    news   = _yf_news(sym)

    def pct(v):
        return f"{v*100:.1f}%" if v else "N/A"

    def dol(v, scale=1e9, suffix="B"):
        if not v: return "N/A"
        return f"${v/scale:.2f}{suffix}"

    price_hist = "\n".join(f"  {d['date']}: ${d['close']}" for d in chart[-8:]) if chart else "  N/A"
    news_lines = "\n".join(f"  - {n}" for n in news) if news else "  No news available"

    return f"""Symbol: {sym}
Company: {quote.get('name', sym)}
Sector: {detail.get('sector','N/A')} | Industry: {detail.get('industry','N/A')}

PRICE DATA:
  Current Price: ${quote.get('price','N/A')}
  52W High: ${quote.get('week52_high','N/A')} | 52W Low: ${quote.get('week52_low','N/A')}
  Day Change: {quote.get('day_change_pct',0):+.2f}%
  Beta: {quote.get('beta','N/A')}
  Avg Daily Volume: {f"{quote.get('avg_volume',0):,}" if quote.get('avg_volume') else 'N/A'}

VALUATION:
  Market Cap: {dol(quote.get('market_cap'))}
  Trailing P/E: {quote.get('pe_ratio','N/A')}
  Forward P/E: {quote.get('fwd_pe','N/A')}
  P/S Ratio: {detail.get('ps_ratio','N/A')}
  PEG Ratio: {detail.get('peg_ratio','N/A')}
  EV/EBITDA: {detail.get('ev_ebitda','N/A')}

FINANCIALS:
  Revenue (TTM): {dol(detail.get('total_revenue'))}
  Revenue Growth (YoY): {pct(detail.get('revenue_growth'))}
  Gross Margin: {pct(detail.get('gross_margins'))}
  Operating Margin: {pct(detail.get('operating_margins'))}
  Net Margin: {pct(detail.get('profit_margins'))}
  Free Cash Flow: {dol(detail.get('free_cashflow'))}
  Debt/Equity: {detail.get('debt_to_equity','N/A')}
  ROE: {pct(detail.get('roe'))}
  Cash: {dol(detail.get('total_cash'))}

ANALYST & OWNERSHIP:
  Consensus: {quote.get('analyst_rating','N/A').upper()}
  Price Target: ${quote.get('analyst_target','N/A')}
  Short % Float: {pct(detail.get('short_pct_float'))}
  Insider Ownership: {pct(detail.get('insider_pct'))}
  Institutional Ownership: {pct(detail.get('inst_pct'))}

RECENT PRICE HISTORY (weekly):
{price_hist}

RECENT NEWS:
{news_lines}"""


def build_account_context(account: dict) -> str:
    lines = [
        f"Account: {account['account_id']}",
        f"Total Equity: ${account.get('total_equity', 0):,.2f}",
        f"Cash: ${account.get('cash', 0):,.2f}",
        "",
        "POSITIONS:",
    ]
    for p in account["positions"]:
        avg  = p.get("avg_cost_per_share") or 0
        cur  = p.get("price") or 0
        gl   = p.get("unrealized_gain_loss_pct") or 0
        mv   = p.get("market_value") or 0
        pct  = p.get("pct_of_account") or 0
        lines.append(
            f"  {p['symbol']}: {p['shares']} sh | avg cost ${avg:.2f} | "
            f"current ${cur:.2f} | G/L {gl:+.1f}% | "
            f"value ${mv:,.0f} | {pct:.1f}% of account"
        )
    return "\n".join(lines)


@app.get("/api/agent/{agent_type}/{symbol}")
async def run_stock_agent(agent_type: str, symbol: str):
    if agent_type not in AGENT_PROMPTS:
        raise HTTPException(400, f"Unknown agent: {agent_type}")

    stock_ctx = build_stock_context(symbol)
    prompt    = AGENT_PROMPTS[agent_type].replace("{data}", stock_ctx)

    async def event_stream():
        client = anthropic.Anthropic()
        try:
            with client.messages.stream(
                model="claude-sonnet-4-6",
                max_tokens=2000,
                system="You are an expert AI trading analyst. Provide detailed, data-driven analysis with specific numbers. Always include scores and clear actionable insights.",
                messages=[{"role": "user", "content": prompt}],
            ) as stream:
                for text in stream.text_stream:
                    yield f"data: {json.dumps({'text': text})}\n\n"
                    await asyncio.sleep(0)
        except Exception as e:
            yield f"data: {json.dumps({'error': str(e)})}\n\n"
        yield "data: [DONE]\n\n"

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@app.get("/api/guidance/{account_id:path}")
async def run_account_guidance(account_id: str):
    data    = load_portfolio()
    account = next((a for a in data["accounts"] if a["account_id"] == account_id), None)
    if not account:
        raise HTTPException(404, f"Account '{account_id}' not found")

    # Refresh prices on positions
    syms   = [p["symbol"] for p in account["positions"]]
    prices = get_live_prices(syms)
    for pos in account["positions"]:
        live = prices.get(pos["symbol"])
        if live:
            pos["price"]        = live["price"]
            pos["market_value"] = round(live["price"] * pos["shares"], 2)

    acct_ctx = build_account_context(account)
    cash     = account.get("cash") or 0
    prompt   = AGENT_PROMPTS["guidance"].replace("{data}", acct_ctx).replace("${cash}", f"${cash:,.2f}")

    async def event_stream():
        client = anthropic.Anthropic()
        try:
            with client.messages.stream(
                model="claude-sonnet-4-6",
                max_tokens=1500,
                system="You are a sharp, direct financial advisor who gives specific, actionable guidance. Always reference specific tickers, prices, and percentages.",
                messages=[{"role": "user", "content": prompt}],
            ) as stream:
                for text in stream.text_stream:
                    yield f"data: {json.dumps({'text': text})}\n\n"
                    await asyncio.sleep(0)
        except Exception as e:
            yield f"data: {json.dumps({'error': str(e)})}\n\n"
        yield "data: [DONE]\n\n"

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


# ── Static Files ──────────────────────────────────────────────────────────────

@app.get("/")
def root():
    return FileResponse(DASHBOARD_DIR / "index.html")

app.mount("/static", StaticFiles(directory=str(DASHBOARD_DIR)), name="static")


# ── Entry Point ───────────────────────────────────────────────────────────────

if __name__ == "__main__":
    print("\n" + "=" * 54)
    print("  AI Trading Dashboard")
    print("=" * 54)
    print("  URL  : http://localhost:8765")
    print("  Stop : Ctrl+C")
    print("=" * 54 + "\n")
    uvicorn.run(app, host="0.0.0.0", port=8765, reload=False, log_level="warning")
