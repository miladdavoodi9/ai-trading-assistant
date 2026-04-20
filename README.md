# AI Trading Assistant & Researcher

> A personal, self-hosted investment dashboard that knows your actual portfolio and helps you make smarter decisions — powered by AI.

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
- Windows PC (to run the server)
- [Python 3.8+](https://www.python.org/)
- An [Anthropic API key](https://console.anthropic.com) (for AI agents)
- A Schwab brokerage account

### Install

```bash
# 1. Clone the repo
git clone https://github.com/miladdavoodi9/ai-trading-assistant.git
cd ai-trading-assistant

# 2. Install dependencies
pip install fastapi uvicorn anthropic requests

# 3. Add your Anthropic API key
# Edit the .env file and paste your key:
# ANTHROPIC_API_KEY=sk-ant-...
```

### Load Your Portfolio

1. Log in to Schwab → **Accounts** → **Positions**
2. Click the **Export** icon (top-right)
3. Save the CSV and drop it into `portfolio/input/`
4. Run the parser:

```bash
python parse_schwab.py
```

Do this for each of your Schwab accounts. The parser automatically handles multiple accounts.

### Launch the Dashboard

Double-click **`Start Dashboard.bat`** — the server starts and your browser opens automatically.

Or from a terminal:
```bash
python dashboard.py
```

Then go to **http://localhost:8765**

---

## Updating Your Portfolio

Whenever you make a trade, export a fresh CSV from Schwab and run `python parse_schwab.py` again. The dashboard will pick up the new positions on the next refresh. Day-to-day price changes update automatically — no action needed.

---

## Privacy & Security

- Your portfolio data never leaves your machine
- Schwab CSV exports are gitignored and stay local
- No direct connection to Schwab or any brokerage
- The only external calls are live price lookups (Yahoo Finance) and AI analysis (Anthropic API)

---

## Disclaimer

This tool is for **educational and research purposes only**. It is not financial advice. It does not execute trades, manage portfolios, or connect to any brokerage. All analysis is AI-generated based on publicly available information. Markets are unpredictable. Always do your own due diligence and consult a licensed financial advisor before making investment decisions.
