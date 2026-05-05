# AI Trading Assistant & Researcher

> A personal, self-hosted investment dashboard that knows your actual portfolio and helps you make smarter decisions — powered by AI.

---

## Documentation

- [Business Requirements Document (BRD)](docs/BRD.md)
- [Product Requirements Document (PRD)](docs/PRD.md)

---

## Coming Soon

### 🪙 Crypto Tab — Coinbase Integration
A dedicated **Crypto** tab alongside Stocks. Connect to Coinbase to pull live BTC, ETH, and altcoin balances, cost basis, and P&L. Cold wallet balances (hardware wallets) can be entered manually and looked up via public blockchain — all consolidated into a single net worth view.

**Planned:**
- Coinbase OAuth / API key connection
- Manual cold wallet address entry with live on-chain balance lookup
- Crypto-specific AI agents: on-chain sentiment, fear & greed index, whale activity, DeFi yield
- Unified net worth bar: Stocks + Crypto in one number

---

### 🌐 Remote Access — Use It From Anywhere
Access the dashboard from your MacBook, phone, or any device — even when traveling.

**Planned:**
- Local network access (same Wi-Fi as your PC)
- Secure remote tunnel via ngrok or Cloudflare for access on the road
- Optional password protection
- QR code at startup for instant mobile access

---

## What This Is

A private trading research dashboard that runs entirely on your own computer. It reads your real brokerage portfolio from **Schwab, E-Trade, Fidelity, or Morgan Stanley**, tracks your positions with live prices, and lets you run AI-powered analysis on any stock — all through a clean browser-based interface.

This is a **research tool**. It does not execute trades, manage money, or connect to your brokerage. You stay in control.

---

## The Dashboard

Open your browser to `http://localhost:8866` after starting the app. Here's what you'll find:

### Portfolio Overview
The top bar shows your **total portfolio value** and **today's dollar and percentage change**, updated every 60 seconds with live market prices. Below it, three account cards show your Individual brokerage, Solo 401(k), and Rollover IRA — each with live equity values, today's change, and a visual breakdown of your holdings.

### Account Strategy
Each account card has a **"Get Account Strategy"** button. Click it and the AI generates a tailored strategy for that specific account type — taking into account tax treatment (taxable vs. tax-deferred vs. tax-free), your current holdings, unrealized gains, and available cash. The strategy opens in a full-screen overlay you can:
- **Minimize** to a floating pill and restore anytime
- **Export as PDF** — opens a clean print-ready page
- **Email to yourself** — pre-fills your email client with the full analysis
- Strategies are **cached for the day** — click again and it reopens instantly without re-running

### Holdings Table
A live table of all your positions across all three accounts. Sortable, searchable, and updated with real-time prices. Each row shows shares, live price, current value, cost basis, unrealized gain/loss in dollars and percent, and today's change. Click any row to open the stock detail panel.

### Stock Detail Panel
Click any holding to slide open a detail panel showing:
- Current price with a **1-month sparkline chart**
- 52-week high and low, P/E ratio, market cap, beta
- Analyst consensus rating and price target (with implied upside/downside)
- Your holdings in that stock across accounts — shares, average cost, current gain/loss
- Recent news headlines
- Quick-launch buttons for every AI agent

### AI Agents
Select any stock — your holdings *or* any ticker you type in — and run one of seven AI analyses:

| Agent | What It Does |
|-------|-------------|
| ⚡ Quick Snapshot | Fast signal (Buy/Hold/Sell/Avoid), top 3 bull and bear factors, key levels, one-line thesis |
| 📊 Technical | Trend, support & resistance levels, momentum, entry zone, stop loss, and targets |
| 🏗 Fundamental | Valuation verdict, growth profile, margins, financial health, and competitive moat |
| 🎯 Sentiment | News tone, analyst consensus, short interest, insider and institutional signals |
| 📈 Options | Specific options strategies with strikes and expirations based on your directional view |
| 🛡 Risk | Volatility profile, downside scenarios, position sizing with Kelly Criterion |
| 📝 Thesis | Full bull/bear case, catalyst calendar, entry/exit strategy, and conviction score |

Results stream live to the page as they generate. When done, you can **export to PDF** or **email the report**.

---

## Setup

### What You Need
- Mac or Windows PC
- [Python 3.8+](https://www.python.org/)
- An [Anthropic API key](https://console.anthropic.com) — for the AI agents
- A brokerage account at **Schwab**, **E-Trade**, **Fidelity**, or **Morgan Stanley** (mix and match — all four work simultaneously)

### 1 — Clone & Install

```bash
git clone https://github.com/miladdavoodi9/ai-trading-assistant.git
cd ai-trading-assistant
pip install fastapi uvicorn anthropic requests
```

### 2 — Add Your Anthropic API Key

Open the `.env` file in the project root and paste your key:

```
ANTHROPIC_API_KEY=sk-ant-api03-xxxxxxxxxxxxxxxxxxxxxxxx
```

Get your key at [console.anthropic.com](https://console.anthropic.com). Without it, the dashboard loads and shows live prices, but the AI agents won't run.

> Your key is stored only on your machine and is gitignored — it will never be committed to GitHub.

### 3 — Export Your Portfolio CSV

The dashboard reads a positions CSV you export from your brokerage. No brokerage login or API — just a file you download and drop in a folder.

**Schwab**
1. Log in → **Accounts** tab → **Positions**
2. Click the **Export** icon (top-right, looks like a page with a down-arrow)
3. Save the file → drop it into `portfolio/input/`
4. Repeat for each account (Individual, IRA, 401k, etc.)

**E-Trade**
1. Log in → **Portfolio** tab
2. Click the **download icon** (top-right of the positions table)
3. Select **CSV** format → save the file
4. Drop it into `portfolio/input/`

**Fidelity**
1. Log in → **Accounts & Trade** → **Portfolio**
2. Click the **Download** button (top-right of the positions table)
3. Save the file (named `Portfolio_Positions_*.csv`) → drop it into `portfolio/input/`

**Morgan Stanley**
1. Log in → click your name or the account menu → **Home** (the dashboard overview page)
2. Look for a **Download** or **Export** icon (top-right of the page)
3. Save the `.xlsx` file as-is — no Excel conversion needed
4. Drop the `.xlsx` file into `portfolio/input/`

> Note: The Home Page export shows your top holdings but does not include cost basis. Unrealized gain/loss will show as N/A for Morgan Stanley positions.

You can mix files from different brokerages — drop them all into `portfolio/input/` and the parser auto-detects each format and merges them into one view.

### 4 — Parse Your Portfolio

```bash
python parse_schwab.py
```

The parser auto-detects the brokerage format, merges all accounts into one file, and prints a summary. Do this whenever you make trades.

### 5 — Launch the Dashboard

Double-click **`Launch Application.command`** (Mac) or **`Launch Application.bat`** (Windows).

Or from a terminal:
```bash
python dashboard.py
```

Then open **http://localhost:8866** in your browser.

---

## Updating Your Portfolio

Whenever you make a trade, export a fresh file from your brokerage (CSV for Schwab/E-Trade, XLSX for Morgan Stanley), drop it in `portfolio/input/` replacing the old one, and run `python parse_schwab.py` again. Day-to-day price changes update automatically every 60 seconds — no action needed.

---

## Privacy & Security

- Your portfolio data never leaves your machine
- Brokerage exports (CSV/XLSX) are gitignored and stay local
- No direct connection to Schwab, E-Trade, Morgan Stanley, or any brokerage
- The only external calls are live price lookups (Yahoo Finance) and AI analysis (Anthropic API)

---

## Disclaimer

This tool is for **educational and research purposes only**. It is not financial advice. It does not execute trades, manage portfolios, or connect to any brokerage. All analysis is AI-generated based on publicly available information. Markets are unpredictable. Always do your own due diligence and consult a licensed financial advisor before making investment decisions.
