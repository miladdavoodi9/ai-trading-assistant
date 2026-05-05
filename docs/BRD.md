# Business Requirements Document (BRD)
## AI Trading Assistant & Researcher

---

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
