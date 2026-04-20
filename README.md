# AI Trading Assistant & Researcher

> Personal AI-powered trading research system built on [Claude Code](https://claude.ai/code). Connects to your Schwab account, knows your actual positions and cost basis, and delivers personalized profit-taking and income guidance — all from your terminal.

---

## What This Is

A private, self-hosted trading research system that combines:

- **Your real portfolio** — Schwab CSV integration loads your actual positions, cost basis, unrealized gains, and cash balances
- **16 Claude Code skills** — quick snapshots, full 5-agent analyses, options strategy, earnings previews, sector rotation, and more
- **Personalized guidance** — profit-taking recommendations with specific share counts and tax notes, income optimization, covered call opportunities
- **Zero brokerage connections** — reads a CSV export you control; never touches your account directly

This is a research and analysis tool. It does not execute trades, manage money, or provide financial advice.

---

## Core Skills

| Command | What It Does |
|---------|-------------|
| `/trade guidance` | **Your personalized playbook** — profit-taking candidates ranked by score, income gap analysis, covered call opportunities, tax-loss harvest suggestions, and a consolidated action plan |
| `/trade portfolio` | Full allocation analysis — sector weights vs benchmark, concentration risk, dividend income summary, rebalancing recommendations |
| `/trade analyze <ticker>` | Flagship deep-dive — 5 parallel AI agents (technical, fundamental, sentiment, risk, thesis) produce a composite Trade Score (0–100) and full report |
| `/trade quick <ticker>` | 60-second stock snapshot with signal and top factors |
| `/trade compare <t1> <t2>` | Head-to-head comparison across all dimensions |
| `/trade options <ticker>` | Options strategy recommendations based on current setup |
| `/trade earnings <ticker>` | Pre-earnings analysis and expected move |
| `/trade screen <criteria>` | Stock screener — momentum, value, dividend, growth, or custom |
| `/trade thesis <ticker>` | Full investment thesis with bull/bear cases and entry/exit plan |
| `/trade risk <ticker>` | Risk assessment and position sizing |
| `/trade sector <sector>` | Sector rotation and momentum analysis |
| `/trade technical <ticker>` | Technical analysis — price action, indicators, patterns |
| `/trade fundamental <ticker>` | Fundamental analysis — valuation, growth, moat |
| `/trade sentiment <ticker>` | News, analyst ratings, insider activity |
| `/trade watchlist` | Build a scored, ranked watchlist |
| `/trade report-pdf` | Generate a professional 6-page PDF investment report |

---

## Schwab Integration

The system reads a positions CSV you export directly from Schwab. No API keys. No brokerage connection. You control the data.

### Export Steps

1. Log in to Schwab → **Accounts** tab → **Positions**
2. Click the **Export** icon (top-right, page with down-arrow)
3. Save the CSV file
4. Drop it into `portfolio/input/`
5. Run the parser:

```bash
python parse_schwab.py
```

This generates `portfolio/portfolio.json` — the structured data file all skills read from. From that point, every `/trade guidance` and `/trade portfolio` run uses your actual positions.

---

## Guidance Output Example

```
╔══════════════════════════════════════════════════════════════╗
║  YOUR PERSONALIZED ACTION PLAN                               ║
║  Generated: 2026-04-19 | Portfolio: $284,500                 ║
╚══════════════════════════════════════════════════════════════╝

PROFIT-TAKING ACTIONS
──────────────────────────────────────────────────────────────
1. NVDA — Trim 33% (~28 shares) | Locks in ~$18,400 gain
   RSI 77, position 19% of portfolio, near 52W high
   Tax: Long-term gain — qualifies for 15/20% rate

2. AAPL — Trim 20% (~15 shares) | Locks in ~$4,200 gain
   Near analyst avg target, modest overbought signal

INCOME ACTIONS
──────────────────────────────────────────────────────────────
1. Deploy $32K cash → SGOV (T-bill ETF, ~5.1%) = +$1,632/yr
2. Sell 1 NVDA covered call (30 DTE, 10% OTM) = ~$420 premium

AFTER THESE MOVES:
  Annual income: $8,240/yr ($687/month)
  Locked-in profits: $22,600
  Cash available: $47,500

──────────────────────────────────────────────────────────────
DISCLAIMER: Educational/research only. Not financial advice.
══════════════════════════════════════════════════════════════
```

---

## Setup

### Prerequisites

- [Claude Code](https://claude.ai/code) with an active Anthropic API key
- Python 3.8+
- A Schwab brokerage account

### Install

```bash
# 1. Clone this repo
git clone https://github.com/YOUR_USERNAME/ai-trading-assistant.git
cd ai-trading-assistant

# 2. Install the base trading skills (16 skills, 5 agents)
bash ai-trading-claude/install.sh

# 3. Install the custom skills (guidance + updated portfolio)
cp -r skills/trade-guidance ~/.claude/skills/
cp skills/trade-portfolio/SKILL.md ~/.claude/skills/trade-portfolio/SKILL.md

# 4. Install PDF dependencies (optional)
pip install reportlab
```

### First Run

```bash
# Drop your Schwab CSV into portfolio/input/
# Then parse it:
python parse_schwab.py

# Launch Claude Code and run:
# /trade guidance
# /trade portfolio
```

---

## How It Works

```
Schwab Export (.csv)
        │
        ▼
parse_schwab.py
        │
        ▼
portfolio/portfolio.json   ←── contains: positions, cost basis,
        │                       unrealized gains, cash, account totals
        │
   ┌────┴──────────────────────┐
   │                           │
   ▼                           ▼
/trade guidance          /trade portfolio
   │                           │
   ├─ Profit-taking scores     ├─ Sector allocation
   ├─ Tax treatment notes      ├─ Correlation matrix
   ├─ Income gap analysis      ├─ Dividend analysis
   ├─ Covered call ideas       ├─ Benchmark comparison
   └─ Action plan              └─ Rebalancing plan
```

For any individual ticker, the full analysis pipeline:

```
/trade analyze <ticker>
        │
   ┌────┼────┬──────┬──────┐
   ▼    ▼    ▼      ▼      ▼
 Tech Fund Sent  Risk Thesis  ← 5 parallel agents
   └────┴────┴──────┴──────┘
                │
                ▼
      Composite Trade Score (0–100)
      Grade (A+ → F) + Signal
      Full report saved as .md
```

---

## Project Structure

```
.
├── README.md
├── parse_schwab.py          # Schwab CSV → portfolio.json
├── portfolio/
│   ├── input/               # Drop Schwab CSV exports here (gitignored)
│   └── HOW_TO_EXPORT.md     # Step-by-step Schwab export guide
├── skills/
│   ├── trade-guidance/
│   │   └── SKILL.md         # Personalized profit-taking + income skill
│   └── trade-portfolio/
│       └── SKILL.md         # Updated portfolio skill (auto-reads portfolio.json)
└── ai-trading-claude/       # Base skills repo (submodule)
```

---

## Privacy & Security

- `portfolio/input/` is gitignored — your CSV exports never leave your machine
- `portfolio/portfolio.json` is gitignored — your positions and cost basis stay local
- No API connections to Schwab or any brokerage
- No data leaves your environment except standard Claude API calls for analysis

---

## Disclaimer

This tool is for **educational and research purposes only**. It is **not** financial advice. It does **not** execute trades, manage portfolios, or connect to any brokerage. All analysis is AI-generated based on publicly available information. Markets are unpredictable. Past performance does not indicate future results. Always do your own due diligence and consult a licensed financial advisor before making investment decisions.
