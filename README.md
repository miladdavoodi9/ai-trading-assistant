# AI Trading Assistant

> A self-hosted investment dashboard where every screen, every chart, and every data point is a conversation waiting to happen — powered by Claude AI.

**[→ Jump to Setup](#setup)**

---

## The Idea

Most financial dashboards show you data. This one talks back.

The core of this project isn't the portfolio tracker or the live prices — it's the interface. Every surface in the dashboard is an AI entry point. You can ask questions about a stock the moment you click it. You can describe what you're trying to understand and let the system figure out which analyst to route you to. You can paste a screenshot of a chart and ask what it means. The AI isn't a feature bolted on — it's the layer between you and your data.

---

## The Dashboard Interface

Open `http://localhost:8866` after starting the app. Everything runs in the browser, locally, on your machine.

### Portfolio Overview

A live snapshot of your entire portfolio — total value, today's dollar and percent change, updated every 60 seconds. Below it, account cards organized into tabs:

- **All** — every account at once
- **Retirement** — IRAs and 401(k)s
- **Investment** — brokerage and taxable accounts
- **Crypto** — Bitcoin, Ethereum, and any other digital assets

Each card shows live equity, today's change, a visual breakdown of holdings, liabilities (like margin), and informational notes. Cash balances are shown only when non-zero.

### All Holdings Table

A unified table of every position across every account — sortable by any column (symbol, value, gain/loss, % change, etc.). Click any row to open the stock detail panel.

---

## AI Entry Points — Conversations at Every Level

The dashboard has four distinct AI surfaces. Each one is independently conversational, and all of them share memory — so what you've discussed in one place informs the answers you get in another.

---

### 1. Stock Detail Panel — Click Any Ticker

Click any holding (or search any ticker) and a panel slides in from the right showing:

**Interactive Price Chart**
- 12 selectable time windows: All Time, 10Y, 5Y, 3Y, 2Y, 1Y, 6M, 3M, 1M, 3W, 1W, 3D
- Area chart with crosshair hover tooltip
- Switches to hourly resolution automatically for short windows (1W, 3D)

**Period Statistics** — updates instantly when you change the time window:
- Date range, Open, High, Low, Close
- Total % change and dollar change
- High-to-low range, best single period, worst single period
- Up day / Down day count

**Stock Fundamentals** — P/E, forward P/E, P/S, market cap, 52-week range, beta, analyst consensus, price target with implied upside

**Your Holdings** — shares held, average cost, current value, gain/loss, across every account you own it in

**Recent News** — last 5 headlines

**Quick-Launch Agent Buttons** — run any of the seven specialist agents directly from the detail view

**Embedded AI Chat**
At the bottom of the panel is a chat bar: `Ask AI about this stock…`

Type a question and hit Enter. The panel expands to a two-column layout — stock info on the left, AI conversation on the right — each column independently scrollable. The AI routes your question to the most relevant specialist automatically (technical, fundamental, sentiment, options, risk, or thesis) and tells you which analyst responded.

- **Exit Chat** collapses back to single-column without losing the conversation
- **Restart** clears the thread and starts fresh
- Attach a screenshot or data file (📎) and the AI reads it directly
- Paste an image from your clipboard — no file picker needed

---

### 2. Smart Ask — Describe What You Want

In the AI Agents section, below the specialist buttons, there's a plain-text input:

> *"Should I take profits on TSLA given my cost basis?"*
> *"Is the technical setup on NVDA worth adding here?"*
> *"Compare the risk profiles of my two largest positions."*

Type anything. The system routes it through a fast classifier that decides which 1–3 specialist agents are most relevant to your question. Those agents run sequentially, and their outputs are synthesized into a direct answer to what you actually asked. You can see which agents ran, each labeled at the top of their section.

This is the fastest path to insight when you don't know which angle matters most.

---

### 3. Specialist Agent Analysis

If you do know which lens you want, pick one directly:

| Agent | Focus |
|-------|-------|
| ⚡ Quick Snapshot | Signal (Buy/Hold/Sell/Avoid), top bull and bear factors, key levels, one-line thesis |
| 📊 Technical | Trend structure, support and resistance, RSI, MACD, entry zone, stop and targets |
| 🏗 Fundamental | Valuation verdict, growth, margins, financial health, competitive position |
| 🎯 Sentiment | News tone, analyst consensus, short interest, insider and institutional signals |
| 📈 Options | Specific strategies with strikes and expirations based on your directional view |
| 🛡 Risk | Volatility profile, downside scenarios, position sizing with Kelly Criterion |
| 📝 Thesis | Full bull/bear case, catalysts, entry/exit framework, conviction score |

Results stream live to the screen as they generate.

**Follow-up Chat** — when the analysis finishes, a chat input appears at the bottom. Ask follow-up questions, challenge the thesis, request a different scenario. The agent has full context of what it just generated.

**Attach data or images** — paste a brokerage screenshot, upload a CSV of price data, or drop in any image and the AI will incorporate it into its response.

**Export** — download the full analysis as a PDF or pre-fill an email to yourself with one click.

**Regenerate** — force a fresh analysis at any time with the ↺ button, bypassing the cache.

---

### 4. Account Strategy — Your Full Portfolio in Context

Each account card has a **Get Strategy** button. Click it and the AI generates a complete investment strategy for that specific account — aware of:

- Every position, its cost basis, and unrealized gain/loss
- Tax treatment (taxable, IRA, 401k — the strategy changes significantly by account type)
- Tax lots (for accounts where this data is available)
- Available cash
- Liabilities like margin

The strategy opens in a full-screen overlay with a follow-up chat at the bottom. Ask about a specific holding, request a different risk posture, or ask what to do with the cash. The advisor maintains context of the full account throughout the conversation.

- **Minimize** to a floating pill, restore anytime
- **Export as PDF** — print-ready formatting
- **Email** — pre-fills your mail client with the full strategy
- **Regenerate** — force a fresh analysis

---

## Cross-Agent Memory

Every conversation you have — whether in the stock panel chat, the analysis modal, or the account strategy — feeds into a shared context buffer. When you move from one part of the dashboard to another, the AI already knows what you've been exploring.

If you asked about TSLA's cost basis in the stock panel and then open the Morgan Stanley account strategy, the strategy agent knows what you were just discussing. You don't have to re-explain yourself. The session is one continuous conversation across multiple surfaces.

---

## Portfolio Data

The dashboard reads brokerage exports you drop into a folder — no brokerage login, no API connection.

| Brokerage | Format |
|-----------|--------|
| Schwab | CSV (Positions export) |
| E-Trade | CSV (Portfolio download) |
| Fidelity | CSV (Portfolio Positions) |
| Morgan Stanley | XLSX (Home page export) |
| Merrill Lynch | Manual CSV template |

Mix and match — drop multiple files from different brokerages into `portfolio/input/` and the parser merges them automatically.

**Tax Lots** — for positions where you have lot-level cost basis data (e.g., from a brokerage PDF or statement), add them to `portfolio/tax_lots.json`. The AI uses this for precise tax-aware analysis: which lots to sell first, long-term vs. short-term treatment, and exact gain/loss calculations.

---

## Setup

### What You Need

- Mac or Windows PC
- Python 3.8+
- An [Anthropic API key](https://console.anthropic.com)
- A brokerage account at Schwab, E-Trade, Fidelity, Morgan Stanley, or Merrill Lynch

### Install

```bash
git clone https://github.com/miladdavoodi9/ai-trading-assistant.git
cd ai-trading-assistant
pip install fastapi uvicorn anthropic requests openpyxl
```

### Configure

Create a `.env` file in the project root:

```
ANTHROPIC_API_KEY=sk-ant-api03-xxxxxxxxxxxxxxxxxxxxxxxx
```

### Load Your Portfolio

Export your positions CSV from your brokerage and drop it in `portfolio/input/`. Then:

```bash
python parse_schwab.py
```

### Launch

```bash
python dashboard.py
```

Open `http://localhost:8866` in your browser.

Or double-click **`Launch Application.command`** (Mac) / **`Launch Application.bat`** (Windows).

---

## Updating Your Portfolio

Export a fresh file from your brokerage after trades, drop it in `portfolio/input/`, and re-run `python parse_schwab.py`. Day-to-day price changes update automatically every 60 seconds.

---

## Privacy

- Your portfolio data never leaves your machine
- Brokerage CSV/XLSX files are gitignored
- No direct brokerage connection — you control the data
- External calls: live prices (Yahoo Finance) and AI analysis (Anthropic API only)

---

## Coming Soon

**Crypto — Coinbase Integration**
Dedicated crypto tab with Coinbase connection, cold wallet balance lookup by public address, and crypto-specific agents (on-chain sentiment, fear & greed index, whale activity, DeFi yield).

**Remote Access**
Access the dashboard from your phone or any device. Local network access and optional secure remote tunnel via ngrok or Cloudflare.

---

## Disclaimer

This tool is for educational and research purposes only. It is not financial advice. It does not execute trades, manage portfolios, or connect to any brokerage. All analysis is AI-generated based on publicly available information. Always do your own due diligence and consult a licensed financial advisor before making investment decisions.
