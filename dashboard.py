#!/usr/bin/env python3
"""
dashboard.py — AI Trading Dashboard backend
FastAPI server: live prices, per-account strategy, streaming agent analysis

Run: python dashboard.py
Then open: http://localhost:8866
"""

import json
import os
import time
import asyncio
from pathlib import Path
from datetime import datetime, date
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Dict, List, Optional, Tuple

# Load .env before importing anthropic so the key is available
_env_path = Path(__file__).parent / ".env"
if _env_path.exists():
    for _line in _env_path.read_text(encoding="utf-8-sig").splitlines():
        _line = _line.strip()
        if _line and not _line.startswith("#") and "=" in _line:
            _k, _v = _line.split("=", 1)
            os.environ[_k.strip()] = _v.strip()  # always set, not just default

import anthropic

ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY", "")
if not ANTHROPIC_API_KEY:
    print("WARNING: ANTHROPIC_API_KEY not set — agents will not work")


def _make_client() -> anthropic.Anthropic:
    key = os.environ.get("ANTHROPIC_API_KEY") or ANTHROPIC_API_KEY
    return anthropic.Anthropic(api_key=key)
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


# Common crypto tickers that Yahoo Finance serves as SYMBOL-USD
_CRYPTO_TICKERS = {
    'BTC', 'ETH', 'ADA', 'SOL', 'DOGE', 'XRP', 'BNB', 'AVAX',
    'MATIC', 'DOT', 'LINK', 'LTC', 'UNI', 'ACH',
}

def _crypto_yf_sym(sym: str) -> str:
    """Map a crypto symbol to its Yahoo Finance ticker (e.g. BTC -> BTC-USD)."""
    return sym + '-USD' if sym.upper() in _CRYPTO_TICKERS else sym


def _yf_quote(symbols: List[str]) -> Dict:
    """Batch quote by fetching all symbols concurrently.
    Crypto tickers are looked up as SYMBOL-USD but stored under the original symbol."""
    results = {}
    with ThreadPoolExecutor(max_workers=min(len(symbols), 8)) as ex:
        # Map original symbol -> yahoo ticker
        sym_map = {s: _crypto_yf_sym(s) for s in symbols}
        futures = {ex.submit(_yf_quote_single, yf_sym): orig for orig, yf_sym in sym_map.items()}
        for fut in as_completed(futures):
            orig = futures[fut]
            _yf_sym, data = fut.result()
            if data:
                results[orig] = data  # store under original symbol (BTC, not BTC-USD)
    return results


def _yf_detail(symbol: str) -> dict:
    """Fetch detailed quote summary (v11) for a single ticker."""
    data = _yf_get(
        f"https://query2.finance.yahoo.com/v11/finance/quoteSummary/{_crypto_yf_sym(symbol)}",
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
        f"https://query1.finance.yahoo.com/v8/finance/chart/{_crypto_yf_sym(symbol)}",
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
        params={"q": _crypto_yf_sym(symbol), "newsCount": 6, "enableFuzzyQuery": False},
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


_ALIASES_PATH    = BASE_DIR / "portfolio" / "account_aliases.json"
_TAX_LOTS_PATH   = BASE_DIR / "portfolio" / "tax_lots.json"

def _load_aliases() -> dict:
    try:
        return json.loads(_ALIASES_PATH.read_text(encoding="utf-8"))
    except Exception:
        return {}

def _load_tax_lots() -> dict:
    try:
        return json.loads(_TAX_LOTS_PATH.read_text(encoding="utf-8"))
    except Exception:
        return {}


def enrich_portfolio(data: dict) -> dict:
    symbols   = list({p["symbol"] for a in data["accounts"] for p in a["positions"]})
    prices    = get_live_prices(symbols)
    aliases   = _load_aliases()
    tax_lots  = _load_tax_lots()

    grand_value = 0.0
    grand_day   = 0.0

    for acct in data["accounts"]:
        # Apply display name and flags from aliases file
        alias = aliases.get(acct["account_id"], {})
        acct["display_name"]          = alias.get("display_name", acct["account_id"])
        acct["exclude_from_holdings"] = alias.get("exclude_from_holdings", False)
        acct["display_notes"]         = alias.get("display_notes", [])
        # Normalize liability names (LAL = Leveraged Asset Loan → Margin)
        for l in acct.get("liabilities", []):
            if "lal" in l.get("name", "").lower():
                l["name"] = "Margin"

        acct_lots = tax_lots.get(acct["account_id"], {})
        acct_invested = 0.0
        acct_day      = 0.0
        for pos in acct["positions"]:
            # Fill missing cost basis from tax_lots.json
            lot_data = acct_lots.get(pos["symbol"])
            if lot_data and not pos.get("cost_basis"):
                pos["cost_basis"]        = lot_data["total_cost"]
                pos["avg_cost_per_share"] = lot_data["avg_cost_per_share"]
                pos["tax_lots"]          = lot_data["lots"]
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

        # Compute live percentage of account for every position
        for pos in acct["positions"]:
            lv = pos.get("live_value") or 0
            pos["live_pct_of_account"] = round(lv / acct_invested * 100, 2) if acct_invested else 0

        cash         = acct.get("cash") or 0
        total_liab   = sum(l.get("balance", 0) for l in acct.get("liabilities", []))
        total_assets = sum(a.get("balance", 0) for a in acct.get("assets", []))
        acct["live_invested"]    = round(acct_invested, 2)
        acct["live_liabilities"] = round(total_liab, 2)
        acct["live_value"]       = round(acct_invested + cash + total_assets - total_liab, 2)
        acct["live_day_change"]  = round(acct_day, 2)
        grand_value += acct_invested + cash + total_assets - total_liab
        grand_day   += acct_day

    prev_total = grand_value - grand_day
    data["live_total"]          = round(grand_value, 2)
    data["live_day_change"]     = round(grand_day, 2)
    data["live_day_change_pct"] = round(grand_day / prev_total * 100, 2) if prev_total else 0
    data["prices_at"]           = datetime.now().strftime("%H:%M:%S")
    return data


# ── API Routes ────────────────────────────────────────────────────────────────

@app.get("/api/debug")
def api_debug():
    key = os.environ.get("ANTHROPIC_API_KEY", "")
    return {
        "key_in_env": bool(key),
        "key_length": len(key),
        "key_preview": key[:12] + "..." if len(key) > 12 else "(empty)",
        "module_key_length": len(ANTHROPIC_API_KEY),
    }


# ── Shared conversation memory (cross-agent context) ──────────────────────────
# Stores the last N user messages + agent responses so every agent has context
# of what the user has been exploring across the whole session.
_SHARED_CONTEXT: list[dict] = []   # [{role, content, agent, symbol}]
_SHARED_CTX_MAX = 20               # keep last 20 turns

def _append_shared_context(role: str, content, agent: str = "", symbol: str = ""):
    _SHARED_CONTEXT.append({"role": role, "content": content, "agent": agent, "symbol": symbol})
    if len(_SHARED_CONTEXT) > _SHARED_CTX_MAX:
        _SHARED_CONTEXT.pop(0)

def _build_shared_ctx_summary() -> str:
    """Return a concise summary of recent cross-agent conversation for injection."""
    if not _SHARED_CONTEXT:
        return ""
    lines = ["RECENT CONVERSATION CONTEXT (user's broader session — for continuity):"]
    for item in _SHARED_CONTEXT[-12:]:
        tag = f"[{item['symbol']} / {item['agent']}]" if item.get("symbol") else ""
        role_label = "User" if item["role"] == "user" else f"AI {tag}"
        content = item["content"]
        if isinstance(content, list):
            # Vision content — extract text portions
            content = " ".join(b.get("text", "") for b in content if isinstance(b, dict) and b.get("type") == "text")
        lines.append(f"  {role_label}: {str(content)[:300]}")
    return "\n".join(lines)


@app.post("/api/context/clear")
def clear_shared_context():
    _SHARED_CONTEXT.clear()
    return {"ok": True}


@app.get("/api/portfolio")
def api_portfolio():
    return enrich_portfolio(load_portfolio())


@app.get("/api/prices")
def api_prices():
    data    = load_portfolio()
    symbols = list({p["symbol"] for a in data["accounts"] for p in a["positions"]})
    return get_live_prices(symbols)


@app.get("/api/chart/{symbol}")
def api_chart(symbol: str, period: str = "1y"):
    import time as _time
    from datetime import timedelta

    # (yf_range, interval, intraday)
    PERIODS: dict = {
        "max": ("max", "1mo",  False),
        "10y": ("10y", "1wk",  False),
        "5y":  ("5y",  "1wk",  False),
        "3y":  ("5y",  "1d",   False),
        "2y":  ("2y",  "1d",   False),
        "1y":  ("1y",  "1d",   False),
        "6mo": ("6mo", "1d",   False),
        "3mo": ("3mo", "1d",   False),
        "1mo": ("1mo", "1d",   False),
        "3wk": ("1mo", "1d",   False),
        "1wk": ("5d",  "60m",  True),
        "3d":  ("5d",  "60m",  True),
    }
    yf_range, interval, intraday = PERIODS.get(period, ("1y", "1d", False))

    raw = _yf_get(
        f"https://query1.finance.yahoo.com/v8/finance/chart/{_crypto_yf_sym(symbol)}",
        params={"range": yf_range, "interval": interval},
    )

    out = []
    if raw:
        try:
            result     = raw["chart"]["result"][0]
            timestamps = result.get("timestamp", [])
            closes     = result["indicators"]["quote"][0].get("close", [])
            for ts, c in zip(timestamps, closes):
                if c is None:
                    continue
                # Intraday → Unix timestamp; daily → ISO date string
                t = ts if intraday else str(date.fromtimestamp(ts))
                out.append({"time": t, "value": round(c, 4)})
        except Exception:
            pass

    # Trim derived-range periods
    if period == "3y":
        cutoff = (date.today() - timedelta(days=365 * 3)).isoformat()
        out = [p for p in out if isinstance(p["time"], str) and p["time"] >= cutoff]
    elif period == "3wk":
        cutoff = (date.today() - timedelta(weeks=3)).isoformat()
        out = [p for p in out if isinstance(p["time"], str) and p["time"] >= cutoff]
    elif period == "3d":
        cutoff_ts = int(_time.time()) - 3 * 86400
        out = [p for p in out if isinstance(p["time"], int) and p["time"] >= cutoff_ts]

    return {"symbol": symbol.upper(), "period": period, "data": out}


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

ASSET DATA:
{data}

If the data shows "Asset Class: Cryptocurrency", deliver a crypto-specific fundamental analysis:
1. Monetary properties (store of value, scarcity, max supply vs circulating supply, inflation rate)
2. Network security & decentralization (hashrate for PoW, validators/staked % for PoS)
3. Adoption & on-chain activity (active addresses, transaction volume, layer-2 ecosystem)
4. Market structure (market cap rank, dominance %, correlation to BTC)
5. Macro narrative (regulatory environment, ETF flows, institutional adoption)
6. Verdict: Accumulate / Hold / Reduce — with specific price level rationale

Otherwise, deliver standard equity fundamental analysis:
1. Valuation (P/E vs sector avg, forward P/E, PEG, EV/EBITDA — is it cheap or expensive?)
2. Growth profile (revenue growth trend, earnings trajectory)
3. Profitability (gross/operating/net margins vs industry norms)
4. Financial health (debt/equity, FCF, cash position, interest coverage)
5. Competitive moat (Wide / Narrow / None — with reasoning)
6. Verdict: Undervalued / Fair Value / Overvalued

Fundamental Score: X/100 with 5 sub-scores of 20 each.
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
6. NEW OPPORTUNITIES — 3 to 5 specific stocks, ETFs, sectors, or markets NOT currently held that are worth researching right now. For each, explain the thesis in 1-2 sentences, suggest a position size as a dollar amount or percentage of this account, and note any timing or entry considerations.
7. TOP 3 ACTIONS — the single most important moves ranked (can include new opportunities)

Be direct. Use specific ticker names, prices, and percentages.
DISCLAIMER: Educational purposes only. Not financial advice.""",
}


def _tax_lot_context(sym: str) -> str:
    """Return tax lot detail string for a symbol if available, else empty string."""
    tax_lots = _load_tax_lots()
    for acct_id, positions in tax_lots.items():
        if sym in positions:
            data = positions[sym]
            lots = data.get("lots", [])
            if not lots:
                return ""
            lines = [
                f"TAX LOT DETAIL ({sym} in account {acct_id}):",
                f"  Total: {data['total_shares']} shares | Avg cost ${data['avg_cost_per_share']:.2f} | Total cost ${data['total_cost']:,.2f}",
                f"  All lots are Long Term (held >1 year — qualifies for long-term capital gains rates):",
            ]
            for lot in lots:
                lines.append(
                    f"  {lot['acquired']}: {lot['shares']} sh @ ${lot['unit_cost']:.2f}/sh (cost ${lot['total_cost']:,.2f})"
                )
            return "\n".join(lines)
    return ""


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

    is_crypto = sym.upper() in _CRYPTO_TICKERS
    asset_class_line = "Asset Class: Cryptocurrency — stock-specific metrics (P/E, EPS, dividends) do not apply." if is_crypto else ""

    return f"""Symbol: {sym}
Asset: {quote.get('name', sym)}
{asset_class_line}
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
{news_lines}

{_tax_lot_context(sym)}"""


def _account_tax_label(account_id: str) -> str:
    aid = account_id.upper()
    if "401" in aid:
        return "Solo 401(k) — tax-deferred, no capital gains tax, no wash sale rules, penalty for early withdrawal"
    if "ROLLOVER" in aid or "ROLLOVER IRA" in aid:
        return "Rollover IRA — tax-deferred, no capital gains tax, RMDs apply, penalty for early withdrawal"
    if "ROTH" in aid:
        return "Roth IRA — tax-free growth, no RMDs, contributions already taxed"
    return "Individual Taxable — subject to capital gains tax, wash sale rules apply, long-term gains preferred"


def build_account_context(account: dict) -> str:
    tax_label = _account_tax_label(account["account_id"])
    liabilities = account.get("liabilities", [])
    total_liab  = sum(l.get("balance", 0) for l in liabilities)
    lines = [
        f"Account: {account['account_id']}",
        f"Account Type: {tax_label}",
        f"Total Equity: ${account.get('total_equity', 0):,.2f}",
        f"Cash: ${account.get('cash', 0):,.2f}",
    ]
    if liabilities:
        liab_parts = ', '.join(f"{l['name']} ${l['balance']:,.2f}" for l in liabilities)
        lines.append(f"Liabilities: ${total_liab:,.2f} ({liab_parts})")
        lines.append(f"Net Value: ${account.get('total_equity', 0) - total_liab:,.2f}")
    lines += ["", "POSITIONS:"]
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
        if p.get("tax_lots"):
            lines.append(f"    Tax Lots (all Long Term):")
            for lot in p["tax_lots"]:
                lines.append(
                    f"      {lot['acquired']}: {lot['shares']} sh @ ${lot['unit_cost']:.2f} "
                    f"(cost ${lot['total_cost']:,.2f})"
                )
    return "\n".join(lines)


AGENT_LABELS = {
    "quick":       "Quick Snapshot",
    "technical":   "Technical Analysis",
    "fundamental": "Fundamental Analysis",
    "sentiment":   "Sentiment & Momentum",
    "options":     "Options Strategies",
    "risk":        "Risk Assessment",
    "thesis":      "Investment Thesis",
}

ROUTER_PROMPT = """You are a routing agent. Given a user question about a stock, decide which 1-3 specialist agents are most relevant.

Available agents:
- quick: General overview, price action, key stats, signal
- technical: Chart patterns, RSI, MACD, support/resistance levels
- fundamental: Earnings, revenue, margins, valuation multiples (P/E, EV/EBITDA)
- sentiment: News sentiment, momentum, social buzz, analyst consensus
- options: Options strategies, implied volatility, calls/puts
- risk: Downside risk, volatility, position sizing, portfolio risk
- thesis: Full investment thesis, long-term bull/bear case

User question: {question}
Stock: {symbol}

Respond ONLY with valid JSON — no explanation, no markdown: {{"agents": ["agent1", "agent2"], "reasoning": "one sentence why these agents"}}
Be selective: pick 1-3 agents that best match the question."""


@app.post("/api/stock/{symbol}/chat")
async def stock_chat(symbol: str, body: dict):
    sym      = symbol.upper()
    question = body.get("question", "") or ""
    content  = body.get("content")        # may be string or list (vision)
    history  = body.get("history", [])    # [{role, content}]

    client = _make_client()

    # Route question to best agent type
    try:
        router_resp = client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=150,
            messages=[{"role": "user", "content": ROUTER_PROMPT.format(
                symbol=sym, question=question or "Give me a general overview"
            )}],
        )
        import re as _re2
        raw  = router_resp.content[0].text.strip()
        m    = _re2.search(r'\{.*\}', raw, _re2.DOTALL)
        routing = json.loads(m.group()) if m else {}
    except Exception:
        routing = {}

    chosen     = [a for a in routing.get("agents", []) if a in AGENT_PROMPTS]
    agent_type = chosen[0] if chosen else "quick"

    # Stock context
    stock_ctx = build_stock_context(sym)

    # User's holdings in this symbol
    try:
        portfolio = load_portfolio()
        tax_lots  = _load_tax_lots()
        holdings_lines = []
        for acct in portfolio["accounts"]:
            for pos in acct["positions"]:
                if pos["symbol"] == sym:
                    avg  = pos.get("avg_cost_per_share") or 0
                    mv   = pos.get("market_value") or 0
                    lots = tax_lots.get(acct["account_id"], {}).get(sym)
                    cost = lots["total_cost"] if lots else (pos.get("cost_basis") or 0)
                    holdings_lines.append(
                        f"  {acct['account_id']}: {pos['shares']} sh, "
                        f"avg cost ${avg:.2f}, market value ${mv:,.2f}, cost basis ${cost:,.2f}"
                    )
        holdings_ctx = "\n".join(holdings_lines)
    except Exception:
        holdings_ctx = ""

    shared_ctx = _build_shared_ctx_summary()
    system = (
        f"You are an expert financial analyst specializing in {AGENT_LABELS.get(agent_type, agent_type)} analysis. "
        f"The user is asking about {sym}. Respond conversationally and directly — answer what was asked. "
        "Reference actual numbers from the data. Keep responses concise but thorough.\n\n"
        f"STOCK DATA:\n{stock_ctx}"
        + (f"\n\nUSER'S HOLDINGS IN {sym}:\n{holdings_ctx}" if holdings_ctx else "")
        + (f"\n\n{shared_ctx}" if shared_ctx else "")
        + "\n\nDo NOT use markdown syntax — no asterisks, pound signs, or backticks. "
        "Plain prose only. For tables use | pipe format."
    )

    # Record to shared context
    _append_shared_context("user", content or question, agent=agent_type, symbol=sym)

    # Build API messages
    api_messages = list(history) + [{"role": "user", "content": content or question}]

    full_response: list[str] = []

    async def event_stream():
        yield f"data: {json.dumps({'type': 'agent', 'agent': agent_type})}\n\n"
        try:
            with client.messages.stream(
                model="claude-sonnet-4-6",
                max_tokens=800,
                system=system,
                messages=api_messages,
            ) as stream:
                for chunk in stream.text_stream:
                    full_response.append(chunk)
                    yield f"data: {json.dumps({'type': 'text', 'text': chunk})}\n\n"
                    await asyncio.sleep(0)
        except Exception as e:
            yield f"data: {json.dumps({'type': 'text', 'text': f'Error: {e}'})}\n\n"
        _append_shared_context("assistant", "".join(full_response), agent=agent_type, symbol=sym)
        yield "data: [DONE]\n\n"

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@app.get("/api/analyze/ask")
async def smart_analyze(symbol: str, question: str):
    stock_ctx = build_stock_context(symbol)
    client    = _make_client()

    # Phase 1: Route (fast sync call)
    try:
        router_resp = client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=200,
            messages=[{"role": "user", "content": ROUTER_PROMPT.format(symbol=symbol, question=question)}],
        )
        import re as _re
        raw = router_resp.content[0].text.strip()
        m   = _re.search(r'\{.*\}', raw, _re.DOTALL)
        routing = json.loads(m.group()) if m else {}
    except Exception:
        routing = {}

    chosen    = [a for a in routing.get("agents", []) if a in AGENT_PROMPTS]
    if not chosen:
        chosen = ["quick"]
    reasoning = routing.get("reasoning", "")

    async def event_stream():
        yield f"data: {json.dumps({'type': 'routing', 'agents': chosen, 'reasoning': reasoning})}\n\n"

        agent_texts: dict = {}
        for agent_type in chosen:
            yield f"data: {json.dumps({'type': 'agent_start', 'agent': agent_type})}\n\n"
            prompt   = AGENT_PROMPTS[agent_type].replace("{data}", stock_ctx)
            text_buf = ""
            try:
                with client.messages.stream(
                    model="claude-sonnet-4-6",
                    max_tokens=1500,
                    system=(
                        "You are an expert AI trading analyst. Provide detailed, data-driven analysis. "
                        "Do NOT use markdown syntax — no asterisks, no pound signs, no backticks. "
                        "Use plain prose and numbers. For tables use | pipe format."
                    ),
                    messages=[{"role": "user", "content": prompt}],
                ) as stream:
                    for chunk in stream.text_stream:
                        text_buf += chunk
                        yield f"data: {json.dumps({'type': 'text', 'agent': agent_type, 'text': chunk})}\n\n"
                        await asyncio.sleep(0)
            except Exception as e:
                err_msg = f"Error running {agent_type}: {e}"
                yield f"data: {json.dumps({'type': 'text', 'agent': agent_type, 'text': err_msg})}\n\n"
                text_buf = err_msg
            agent_texts[agent_type] = text_buf

        # Phase 3: Synthesis when multiple agents ran
        if len(chosen) > 1:
            synthesis_ctx = "\n\n".join(
                f"=== {AGENT_LABELS.get(a, a).upper()} ===\n{t}"
                for a, t in agent_texts.items()
            )
            synthesis_prompt = (
                f"The user asked about {symbol}: \"{question}\"\n\n"
                f"Based on the analyses below, answer the user's specific question directly and concisely. "
                f"Do not repeat all the analysis — synthesize only what's relevant to what was asked.\n\n"
                f"{synthesis_ctx}"
            )
            yield f"data: {json.dumps({'type': 'synthesis_start'})}\n\n"
            try:
                with client.messages.stream(
                    model="claude-sonnet-4-6",
                    max_tokens=600,
                    system=(
                        "You are a financial advisor synthesizing analysis to answer a specific question. "
                        "Be direct and concise. Do NOT use markdown — plain prose only."
                    ),
                    messages=[{"role": "user", "content": synthesis_prompt}],
                ) as stream:
                    for chunk in stream.text_stream:
                        yield f"data: {json.dumps({'type': 'text', 'agent': 'synthesis', 'text': chunk})}\n\n"
                        await asyncio.sleep(0)
            except Exception as e:
                yield f"data: {json.dumps({'type': 'text', 'agent': 'synthesis', 'text': f'Error: {e}'})}\n\n"

        yield "data: [DONE]\n\n"

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@app.get("/api/agent/{agent_type}/{symbol}")
async def run_stock_agent(agent_type: str, symbol: str):
    if agent_type not in AGENT_PROMPTS:
        raise HTTPException(400, f"Unknown agent: {agent_type}")

    stock_ctx = build_stock_context(symbol)
    prompt    = AGENT_PROMPTS[agent_type].replace("{data}", stock_ctx)

    async def event_stream():
        client = _make_client()
        try:
            with client.messages.stream(
                model="claude-sonnet-4-6",
                max_tokens=2000,
                system="You are an expert AI trading analyst. Provide detailed, data-driven analysis with specific numbers. Always include scores and clear actionable insights. Do NOT use markdown syntax — no asterisks, no pound signs, no backticks. Use plain section headings, numbers, and prose. For tabular data, use a proper markdown table with | separators so it renders as a formatted table.",
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

    # Refresh prices and apply tax lots
    syms     = [p["symbol"] for p in account["positions"]]
    prices   = get_live_prices(syms)
    tax_lots = _load_tax_lots().get(account_id, {})
    for pos in account["positions"]:
        live = prices.get(pos["symbol"])
        if live:
            pos["price"]        = live["price"]
            pos["market_value"] = round(live["price"] * pos["shares"], 2)
        lot_data = tax_lots.get(pos["symbol"])
        if lot_data and not pos.get("cost_basis"):
            pos["cost_basis"]         = lot_data["total_cost"]
            pos["avg_cost_per_share"] = lot_data["avg_cost_per_share"]
            pos["tax_lots"]           = lot_data["lots"]

    acct_ctx = build_account_context(account)
    cash     = account.get("cash") or 0
    prompt   = AGENT_PROMPTS["guidance"].replace("{data}", acct_ctx).replace("${cash}", f"${cash:,.2f}")

    async def event_stream():
        client = _make_client()
        try:
            with client.messages.stream(
                model="claude-sonnet-4-6",
                max_tokens=1500,
                system="You are a sharp, direct financial advisor who gives specific, actionable guidance. Always reference specific tickers, prices, and percentages. Do NOT use markdown syntax — no asterisks, no pound signs, no backticks. Use plain headings and prose. For tabular data use | pipe tables.",
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


@app.post("/api/agent/{agent_type}/{symbol}/chat")
async def chat_agent(agent_type: str, symbol: str, body: dict):
    messages = body.get("messages", [])
    analysis = body.get("analysis", "")
    shared_ctx = _build_shared_ctx_summary()
    system = (
        f"You are a financial analyst. The user ran a {agent_type} analysis on {symbol} "
        f"and wants to ask follow-up questions. Here is the original analysis:\n\n{analysis}\n\n"
        "Answer questions concisely and directly, referencing specific data points from the analysis. "
        "Stay focused on this stock and analysis — redirect off-topic questions back to it. "
        "Do NOT use markdown syntax — no asterisks, no pound signs, no backticks. Plain prose only. For tables use | pipe format."
        + (f"\n\n{shared_ctx}" if shared_ctx else "")
    )

    # Record last user message to shared context
    last_user = next((m for m in reversed(messages) if m["role"] == "user"), None)
    if last_user:
        _append_shared_context("user", last_user["content"], agent=agent_type, symbol=symbol)

    full_resp: list[str] = []

    async def event_stream():
        client = _make_client()
        try:
            with client.messages.stream(
                model="claude-sonnet-4-6",
                max_tokens=1000,
                system=system,
                messages=messages,
            ) as stream:
                for text in stream.text_stream:
                    full_resp.append(text)
                    yield f"data: {json.dumps({'text': text})}\n\n"
                    await asyncio.sleep(0)
        except Exception as e:
            yield f"data: {json.dumps({'error': str(e)})}\n\n"
        _append_shared_context("assistant", "".join(full_resp), agent=agent_type, symbol=symbol)
        yield "data: [DONE]\n\n"

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@app.post("/api/guidance/{account_id:path}/chat")
async def chat_guidance(account_id: str, body: dict):
    data    = load_portfolio()
    account = next((a for a in data["accounts"] if a["account_id"] == account_id), None)
    if not account:
        raise HTTPException(404, f"Account '{account_id}' not found")

    # Apply tax lots so cost basis is populated
    tax_lots = _load_tax_lots().get(account_id, {})
    for pos in account["positions"]:
        lot_data = tax_lots.get(pos["symbol"])
        if lot_data and not pos.get("cost_basis"):
            pos["cost_basis"]        = lot_data["total_cost"]
            pos["avg_cost_per_share"] = lot_data["avg_cost_per_share"]
            pos["tax_lots"]          = lot_data["lots"]

    syms   = [p["symbol"] for p in account["positions"]]
    prices = get_live_prices(syms)
    for pos in account["positions"]:
        live = prices.get(pos["symbol"])
        if live:
            pos["price"]        = live["price"]
            pos["market_value"] = round(live["price"] * pos["shares"], 2)

    acct_ctx   = build_account_context(account)
    cash       = account.get("cash") or 0
    messages   = body.get("messages", [])
    shared_ctx = _build_shared_ctx_summary()

    system = (
        "You are a sharp, direct financial advisor discussing investment strategy for a specific account. "
        "You have full context of this account's holdings, tax treatment, cost basis, and available cash. "
        "Answer only questions related to this account's investment strategy — if asked about unrelated topics, "
        "redirect the conversation back to the account strategy. "
        "Always reference specific tickers, prices, and percentages. "
        "Do NOT use markdown syntax — no asterisks, no pound signs, no backticks. Plain prose only. For tables use | pipe format. "
        f"\n\nACCOUNT CONTEXT:\n{acct_ctx}\nCash: ${cash:,.2f}"
        + (f"\n\n{shared_ctx}" if shared_ctx else "")
    )

    last_user = next((m for m in reversed(messages) if m["role"] == "user"), None)
    if last_user:
        _append_shared_context("user", last_user["content"], agent="guidance", symbol=account_id)

    full_resp2: list[str] = []

    async def event_stream():
        client = _make_client()
        try:
            with client.messages.stream(
                model="claude-sonnet-4-6",
                max_tokens=1000,
                system=system,
                messages=messages,
            ) as stream:
                for text in stream.text_stream:
                    full_resp2.append(text)
                    yield f"data: {json.dumps({'text': text})}\n\n"
                    await asyncio.sleep(0)
        except Exception as e:
            yield f"data: {json.dumps({'error': str(e)})}\n\n"
        _append_shared_context("assistant", "".join(full_resp2), agent="guidance", symbol=account_id)
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
    print("  URL  : http://localhost:8866")
    print("  Stop : Ctrl+C")
    print("=" * 54 + "\n")
    uvicorn.run(app, host="0.0.0.0", port=8866, reload=False, log_level="warning")
