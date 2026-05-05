# Product Requirements Document (PRD)
## AI Trading Assistant & Researcher

---

### Overview
A locally-hosted web dashboard built with Python (FastAPI) and a browser frontend. On launch it parses the user's Schwab CSV exports, fetches live prices, and serves a dashboard at `http://localhost:8866`. AI analysis is powered by the Anthropic Claude API.

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
- As a user, I want to interact with the strategy via a follow-up chat to refine or challenge the recommendations.
- As a user, I want to export or email any strategy or analysis report.

#### Usability
- As a user, I want to launch the entire app by double-clicking a single file on both Mac and Windows.
- As a user, I want the dashboard to auto-refresh prices every 60 seconds without any action on my part.
- As a user, I want today's strategies and chat history cached so re-opening them is instant.

### Functional Requirements

| ID | Requirement |
|----|-------------|
| F1 | Parse one or more Schwab/Morgan Stanley CSV and XLSX exports and merge into a unified portfolio JSON |
| F2 | Fetch live prices via Yahoo Finance on page load and every 60 seconds |
| F3 | Display portfolio header: total value, day change ($ and %), account count, position count |
| F4 | Display per-account cards with live equity, day change, cash, and holdings breakdown |
| F5 | Display all positions in a sortable, searchable table with live price, value, cost basis, G/L, day change, and % of total portfolio |
| F6 | Slide-in detail panel for any stock: sparkline, valuation metrics, analyst data, holdings across accounts, news, AI agent buttons — hiding rows with no data |
| F7 | Seven streaming AI agent analyses for any ticker |
| F8 | Per-account AI strategy with tax-aware context, new opportunity recommendations, and position sizing guidance |
| F9 | Strategy modal with interactive follow-up chat, minimize, export PDF, and email actions; cached in localStorage per day |
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
| Data | Schwab/Morgan Stanley CSV/XLSX → JSON via parse_schwab.py |
| Launch | Shell script (Mac), Batch file (Windows) |

### Roadmap

| Feature | Status |
|---------|--------|
| Live portfolio dashboard with 7 AI agents | Shipped |
| Per-account strategy with tax context and new opportunities | Shipped |
| Interactive strategy chat with 24-hour persistence | Shipped |
| Mac + Windows one-click launcher | Shipped |
| Morgan Stanley XLSX import | Shipped |
| Crypto tab (Coinbase + cold wallets) | Planned |
| Remote access (ngrok / Cloudflare tunnel) | Planned |
| Mobile-responsive layout | Planned |
| Automated portfolio sync (no manual CSV export) | Planned |
