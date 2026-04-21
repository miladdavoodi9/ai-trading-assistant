# AI Trading Assistant & Researcher

> A personal, self-hosted investment dashboard that knows your actual portfolio and helps you make smarter decisions — powered by AI.

---

## Business Requirements Document (BRD)

### Purpose
The AI Trading Assistant exists to give a self-directed retail investor a private, always-available research environment that understands their actual portfolio — not a generic demo account. The goal is faster, better-informed investment decisions without relying on expensive advisors or generic screener tools.

### Business Problem
Individual investors managing multiple brokerage accounts face three core friction points:
1. **Fragmented data** — holdings, cost basis, and P&L are spread across separate account views with no unified picture.
2. **Generic analysis** — third-party research tools don't know what you own, your cost basis, your tax situation, or your account types.
3. **Decision latency** — by the time a retail investor synthesizes news, technicals, and fundamentals, the opportunity has often moved.

### Business Objectives
| # | Objective | Success Measure |
|---|-----------|----------------|
| 1 | Consolidate all account positions into a single real-time view | All accounts visible in one dashboard with live prices |
| 2 | Deliver AI analysis personalized to the user's actual holdings | Strategy output references specific tickers, cost basis, and account tax treatment |
| 3 | Reduce time-to-insight for any given stock | Full AI analysis available in under 60 seconds per stock |
| 4 | Keep all financial data private and local | Zero portfolio data transmitted outside the local machine |
| 5 | Require no ongoing subscription cost beyond API usage | Runs entirely on user's own hardware and API key |

### Stakeholders
- **Primary User:** Self-directed retail investor managing taxable, IRA, and 401(k) accounts at Schwab
- **No secondary stakeholders** — this is a single-user private tool

### Constraints
- Must run on Windows and Mac without a cloud backend
- No direct brokerage API integration — relies on manual CSV export from Schwab
- AI analysis is for research only; the tool must not execute or recommend specific trades as instructions
- All Anthropic API costs are borne by the user

### Out of Scope
- Trade execution
- Portfolio management or rebalancing automation
- Multi-user access or authentication
- Tax reporting or official financial advice

---

## Product Requirements Document (PRD)

### Overview
A locally-hosted web dashboard built with Python (FastAPI) and a browser frontend. On launch it parses the user's Schwab CSV exports, fetches live prices, and serves a dashboard at `http://localhost:8765`. AI analysis is powered by the Anthropic Claude API.

### User Stories

#### Portfolio Visibility
- As a user, I want to see my total portfolio value and today's change at a glance so I don't have to log into multiple accounts.
- As a user, I want to see each account separately (Taxable, IRA, 401k) with its own value and day change so I can track them independently.
- As a user, I want to see all my positions in one table with live prices, cost basis, unrealized gain/loss, and percentage of my total portfolio.

#### Stock Research
- As a user, I want to click any holding and see a detail panel with price history, valuation metrics, analyst ratings, and news so I can quickly assess a position.
- As a user, I want to search for any ticker — not just ones I hold — and run AI analysis on it.
- As a user, I want to run seven different AI analyses (Quick, Technical, Fundamental, Sentiment, Options, Risk, Thesis) and have results stream to the screen in real time.

#### Account Strategy
- As a user, I want a one-click AI-generated strategy for each account that accounts for my specific holdings, tax treatment, unrealized gains, available cash, and new investment opportunities.
- As a user, I want the strategy to recommend new stocks, ETFs, or sectors I don't currently hold, with suggested position sizes.
- As a user, I want to export or email any strategy or analysis report.

#### Usability
- As a user, I want to launch the entire app by double-clicking a single file on both Mac and Windows.
- As a user, I want the dashboard to auto-refresh prices every 60 seconds without any action on my part.
- As a user, I want today's strategies cached so re-opening them is instant.

### Functional Requirements

| ID | Requirement |
|----|-------------|
| F1 | Parse one or more Schwab CSV exports and merge into a unified portfolio JSON |
| F2 | Fetch live prices via Yahoo Finance on page load and every 60 seconds |
| F3 | Display portfolio header: total value, day change ($  and %), account count, position count |
| F4 | Display per-account cards with live equity, day change, cash, and holdings breakdown |
| F5 | Display all positions in a sortable, searchable table with live price, value, cost basis, G/L, day change, and % of total portfolio |
| F6 | Slide-in detail panel for any stock: sparkline, valuation metrics, analyst data, holdings across accounts, news, AI agent buttons — hiding rows with no data |
| F7 | Seven streaming AI agent analyses for any ticker |
| F8 | Per-account AI strategy with tax-aware context, new opportunity recommendations, and position sizing guidance |
| F9 | Strategy modal with minimize, export PDF, and email actions; cached in localStorage per day |
| F10 | `.env` file support for `ANTHROPIC_API_KEY`; key never committed to version control |
| F11 | One-click launchers: `Launch Application.command` (Mac), `Launch Application.bat` (Windows) — both auto-parse CSVs before starting |

### Non-Functional Requirements

| ID | Requirement |
|----|-------------|
| N1 | Portfolio data must never leave the local machine |
| N2 | AI analysis must complete and begin streaming within 10 seconds of request |
| N3 | Price refresh must not block UI interaction |
| N4 | Dashboard must load in under 3 seconds on localhost |
| N5 | Compatible with Python 3.8+ on macOS and Windows |

### Current Tech Stack
| Layer | Technology |
|-------|-----------|
| Backend | Python 3.8+, FastAPI, Uvicorn |
| AI | Anthropic Claude API (claude-sonnet-4-6) |
| Market Data | yfinance (Yahoo Finance) |
| Frontend | Vanilla HTML/CSS/JS, Chart.js (sparklines) |
| Data | Schwab CSV → JSON via parse_schwab.py |
| Launch | Shell script (Mac), Batch file (Windows) |

### Roadmap

| Feature | Status |
|---------|--------|
| Live portfolio dashboard with 7 AI agents | Shipped |
| Per-account strategy with tax context and new opportunities | Shipped |
| Mac + Windows one-click launcher | Shipped |
| Crypto tab (Coinbase + cold wallets) | Planned |
| Remote access (ngrok / Cloudflare tunnel) | Planned |
| Mobile-responsive layout | Planned |
| Automated portfolio sync (no manual CSV export) | Planned |

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

A private trading research dashboard that runs entirely on your own computer. It reads your real Schwab portfolio, tracks your positions with live prices, and lets you run AI-powered analysis on any stock — all through a clean browser-based interface.

This is a **research tool**. It does not execute trades, manage money, or connect to your brokerage. You stay in control.

---

## The Dashboard

Open your browser to `http://localhost:8765` after starting the app. Here's what you'll find:

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
- A brokerage account at Schwab, E-Trade, or Morgan Stanley

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

**Morgan Stanley**
1. Log in → **Accounts** → **Portfolio** → **Gain/Loss** tab
2. Click **Download** → open the file in Excel
3. **File → Save As → CSV (Comma delimited)**
4. Drop the CSV into `portfolio/input/`

You can mix files from different brokerages — drop them all in `portfolio/input/` and the parser handles each automatically.

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

Then open **http://localhost:8765** in your browser.

---

## Updating Your Portfolio

Whenever you make a trade, export a fresh CSV from your brokerage, drop it in `portfolio/input/`, and run `python parse_schwab.py` again. Day-to-day price changes update automatically every 60 seconds — no action needed.

---

## Privacy & Security

- Your portfolio data never leaves your machine
- Schwab CSV exports are gitignored and stay local
- No direct connection to Schwab or any brokerage
- The only external calls are live price lookups (Yahoo Finance) and AI analysis (Anthropic API)

---

## Disclaimer

This tool is for **educational and research purposes only**. It is not financial advice. It does not execute trades, manage portfolios, or connect to any brokerage. All analysis is AI-generated based on publicly available information. Markets are unpredictable. Always do your own due diligence and consult a licensed financial advisor before making investment decisions.
