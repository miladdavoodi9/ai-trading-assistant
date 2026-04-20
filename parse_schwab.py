#!/usr/bin/env python3
"""
parse_schwab.py -- Schwab Positions CSV -> portfolio.json + portfolio.md

Usage:
    1. Export from Schwab: Accounts -> Positions -> Export icon -> Save CSV
    2. Drop the CSV into portfolio/input/
    3. Run: python parse_schwab.py

Supports single-account and multi-account Schwab exports (including IRA accounts).
Output: portfolio/portfolio.json  +  portfolio/portfolio.md
"""

import csv
import json
import re
import sys
from datetime import datetime
from pathlib import Path

BASE_DIR = Path(__file__).parent
INPUT_DIR = BASE_DIR / "portfolio" / "input"
OUTPUT_JSON = BASE_DIR / "portfolio" / "portfolio.json"
OUTPUT_MD = BASE_DIR / "portfolio" / "portfolio.md"


# ── Column name normalization ─────────────────────────────────────────────────
# Schwab uses verbose names like "Mkt Val (Market Value)" or short names like
# "Market Value" depending on account type. This maps both to a canonical key.

COLUMN_MAP = {
    # Quantity
    "qty": "shares",
    "qty (quantity)": "shares",
    "quantity": "shares",
    # Price
    "price": "price",
    # Market value
    "market value": "market_value",
    "mkt val (market value)": "market_value",
    "mkt val": "market_value",
    # Cost basis
    "cost basis": "cost_basis",
    # Gain/loss dollar
    "gain/loss $": "gain_loss",
    "gain $ (gain/loss $)": "gain_loss",
    "gain $": "gain_loss",
    # Gain/loss percent
    "gain/loss %": "gain_loss_pct",
    "gain % (gain/loss %)": "gain_loss_pct",
    "gain %": "gain_loss_pct",
    # % of account
    "% of account": "pct_of_account",
    "% of acct (% of account)": "pct_of_account",
    "% of acct": "pct_of_account",
    # Security type
    "security type": "security_type",
    "asset type": "security_type",
    # Description
    "description": "name",
    # Symbol
    "symbol": "symbol",
}


def normalize_header(h):
    return COLUMN_MAP.get(h.strip().lower(), h.strip().lower())


def clean_num(s):
    """Strip $, %, commas -> float. Return None if not parseable."""
    if not s or str(s).strip() in ("--", "", "N/A", "n/a"):
        return None
    try:
        return float(re.sub(r"[$%,\s]", "", str(s)))
    except ValueError:
        return None


def extract_account_id(header_line, filepath=None):
    """Build a readable account ID from the CSV filename + last digits from header."""
    label = "Account"

    # Primary: derive label from filename (most reliable)
    # e.g. "Individual 401(k)-Positions-2026-04-20-001626.csv" → "Individual 401(k)"
    if filepath:
        stem = Path(filepath).stem  # strip extension
        m = re.match(r'^(.+?)\s*-\s*Positions', stem, re.IGNORECASE)
        if m:
            label = m.group(1).strip()

    # Get last 3-4 digits from the header line (account number suffix)
    # Handles both "...708" and "…708" (Unicode ellipsis)
    m = re.search(r'[.…]{1,3}(\d{3,4})', header_line)
    suffix = f"-{m.group(1)}" if m else ""

    return f"{label}{suffix}"


# ── Parser ────────────────────────────────────────────────────────────────────

def parse_schwab_csv(filepath):
    """Parse one Schwab positions CSV. Returns list of account dicts."""
    accounts = []
    current = None
    headers = None

    with open(filepath, "r", encoding="utf-8-sig") as f:
        raw = f.read()

    for line in raw.splitlines():
        stripped = line.strip()

        # ── Account header ────────────────────────────────────────────────
        if "positions for account" in stripped.lower():
            if current is not None:
                accounts.append(current)
            current = {
                "account_id": extract_account_id(stripped, filepath),
                "positions": [],
                "cash": 0.0,
                "total_equity": 0.0,
            }
            headers = None
            continue

        # ── Column header row ─────────────────────────────────────────────
        if re.search(r'"?Symbol"?', stripped) and "Description" in stripped:
            row = next(csv.reader([stripped]))
            headers = [normalize_header(h) for h in row]
            if current is None:
                current = {
                    "account_id": extract_account_id("", filepath),
                    "positions": [],
                    "cash": 0.0,
                    "total_equity": 0.0,
                }
            continue

        # ── Skip separators / blanks ──────────────────────────────────────
        if not stripped or stripped.replace(",", "").strip() == "":
            continue

        if headers is None or current is None:
            continue

        # ── Parse data row ────────────────────────────────────────────────
        try:
            row = next(csv.reader([stripped]))
            row = [c.strip().strip('"') for c in row]
        except Exception:
            continue

        if not row or not row[0]:
            continue

        row += [""] * max(0, len(headers) - len(row))
        d = {headers[i]: row[i] for i in range(len(headers))}
        sym = d.get("symbol", "").strip()

        # ── Cash line ─────────────────────────────────────────────────────
        if not sym or "cash" in sym.lower() or "money market" in sym.lower():
            val = clean_num(d.get("market_value", ""))
            if val is not None:
                current["cash"] += val
            continue

        # ── Totals line ───────────────────────────────────────────────────
        if any(t in sym.lower() for t in ("account total", "positions total", "total")):
            val = clean_num(d.get("market_value", ""))
            if val is not None:
                current["total_equity"] = val
            continue

        # ── Regular position ──────────────────────────────────────────────
        shares = clean_num(d.get("shares", ""))
        price = clean_num(d.get("price", ""))
        mkt_val = clean_num(d.get("market_value", ""))
        cost = clean_num(d.get("cost_basis", ""))
        gl = clean_num(d.get("gain_loss", ""))
        gl_pct = clean_num(d.get("gain_loss_pct", ""))
        pct_acct = clean_num(d.get("pct_of_account", ""))
        avg_cost = round(cost / shares, 4) if (cost and shares and shares > 0) else None

        current["positions"].append({
            "symbol": sym,
            "name": d.get("name", ""),
            "shares": shares,
            "price": price,
            "market_value": mkt_val,
            "cost_basis": cost,
            "avg_cost_per_share": avg_cost,
            "unrealized_gain_loss": gl,
            "unrealized_gain_loss_pct": gl_pct,
            "pct_of_account": pct_acct,
            "security_type": d.get("security_type", ""),
        })

    if current is not None:
        accounts.append(current)

    return accounts


# ── Summary ───────────────────────────────────────────────────────────────────

def build_summary(accounts):
    all_pos = [p for a in accounts for p in a["positions"]]

    total_equity = sum(a.get("total_equity", 0) or 0 for a in accounts)
    total_cash = sum(a.get("cash", 0) or 0 for a in accounts)
    total_mv = sum(p.get("market_value", 0) or 0 for p in all_pos)
    total_cost = sum(p.get("cost_basis", 0) or 0 for p in all_pos)
    total_gl = sum(p.get("unrealized_gain_loss", 0) or 0 for p in all_pos)
    gl_pct = round(total_gl / total_cost * 100, 2) if total_cost else 0

    top = sorted(
        [p for p in all_pos if p.get("market_value")],
        key=lambda x: x["market_value"],
        reverse=True,
    )[:10]

    gain_candidates = sorted(
        [p for p in all_pos if (p.get("unrealized_gain_loss_pct") or 0) > 20],
        key=lambda x: x.get("unrealized_gain_loss_pct", 0),
        reverse=True,
    )

    return {
        "total_accounts": len(accounts),
        "total_equity": round(total_equity, 2),
        "total_cash": round(total_cash, 2),
        "total_invested_market_value": round(total_mv, 2),
        "total_cost_basis": round(total_cost, 2),
        "total_unrealized_gain_loss": round(total_gl, 2),
        "total_unrealized_gain_loss_pct": gl_pct,
        "total_positions": len(all_pos),
        "top_holdings_by_value": [p["symbol"] for p in top],
        "profit_taking_candidates": [p["symbol"] for p in gain_candidates],
    }


# ── Markdown writer ───────────────────────────────────────────────────────────

def write_markdown(data, path):
    s = data["summary"]

    def f(v, sign=False):
        if v is None:
            return "N/A"
        return f"${v:+,.2f}" if sign else f"${v:,.2f}"

    def fp(v, sign=False):
        if v is None:
            return "N/A"
        return f"{v:+.1f}%" if sign else f"{v:.1f}%"

    lines = [
        "# Portfolio Summary",
        "",
        f"**Last Updated:** {data['last_updated']}  |  **Source:** {data['source']}",
        "",
        "> DISCLAIMER: For educational/research purposes only. Not financial advice.",
        "",
        "---",
        "",
        "## Overview",
        "",
        "| Metric | Value |",
        "|--------|-------|",
        f"| Total Equity | {f(s['total_equity'])} |",
        f"| Total Cash | {f(s['total_cash'])} |",
        f"| Market Value (Invested) | {f(s['total_invested_market_value'])} |",
        f"| Total Cost Basis | {f(s['total_cost_basis'])} |",
        f"| Unrealized Gain/Loss | {f(s['total_unrealized_gain_loss'], sign=True)} ({fp(s['total_unrealized_gain_loss_pct'], sign=True)}) |",
        f"| Accounts | {s['total_accounts']} |",
        f"| Positions | {s['total_positions']} |",
        "",
    ]

    if s.get("profit_taking_candidates"):
        lines += [
            f"**Profit-Taking Candidates (>20% gain):** {', '.join(s['profit_taking_candidates'])}",
            "",
        ]

    for acct in data["accounts"]:
        lines += [
            "---",
            "",
            f"## Account: {acct['account_id']}",
            "",
            f"**Total Equity:** {f(acct['total_equity'])}  |  **Cash:** {f(acct['cash'])}",
            "",
        ]
        if acct["positions"]:
            lines += [
                "| Symbol | Name | Shares | Price | Mkt Value | Cost Basis | Unreal G/L | G/L % | % Acct |",
                "|--------|------|-------:|------:|----------:|-----------:|-----------:|------:|-------:|",
            ]
            for p in sorted(acct["positions"], key=lambda x: x.get("market_value") or 0, reverse=True):
                sh = f"{p['shares']:,.4f}" if p.get("shares") else "N/A"
                lines.append(
                    f"| {p['symbol']} | {p['name'][:28]} | {sh} | "
                    f"{f(p.get('price'))} | {f(p.get('market_value'))} | "
                    f"{f(p.get('cost_basis'))} | {f(p.get('unrealized_gain_loss'), sign=True)} | "
                    f"{fp(p.get('unrealized_gain_loss_pct'), sign=True)} | "
                    f"{fp(p.get('pct_of_account'))} |"
                )
            lines.append("")

    lines += ["---", "", "*DISCLAIMER: For educational/research purposes only. Not financial advice.*"]
    path.write_text("\n".join(lines), encoding="utf-8")


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    INPUT_DIR.mkdir(parents=True, exist_ok=True)
    OUTPUT_JSON.parent.mkdir(parents=True, exist_ok=True)

    seen = set()
    unique = []
    for f in list(INPUT_DIR.glob("*.csv")) + list(INPUT_DIR.glob("*.CSV")):
        key = f.resolve()
        if key not in seen:
            seen.add(key)
            unique.append(f)
    csv_files = sorted(unique, key=lambda x: x.stat().st_mtime, reverse=True)

    if not csv_files:
        print(f"\nNo CSV files found in: {INPUT_DIR}")
        print("\nSteps to export from Schwab:")
        print("  1. Log in -> Accounts tab -> Positions")
        print("  2. Click the Export icon (top-right)")
        print("  3. Save the file")
        print(f"  4. Move it into: {INPUT_DIR}")
        print("  5. Run this script again\n")
        sys.exit(1)

    accounts = []
    for csv_file in csv_files:
        print(f"Parsing: {csv_file.name}")
        accounts.extend(parse_schwab_csv(csv_file))

    if not accounts or not any(a["positions"] for a in accounts):
        print("\nNo positions found. Make sure these are Schwab Positions exports.")
        sys.exit(1)

    summary = build_summary(accounts)
    source_names = ", ".join(f.name for f in csv_files)

    data = {
        "last_updated": datetime.now().strftime("%Y-%m-%d %H:%M"),
        "source": f"Schwab -- {len(csv_files)} accounts",
        "source_files": [f.name for f in csv_files],
        "accounts": accounts,
        "summary": summary,
    }

    OUTPUT_JSON.write_text(json.dumps(data, indent=2, default=str), encoding="utf-8")
    write_markdown(data, OUTPUT_MD)

    s = summary
    print(f"\n{'='*54}")
    print(f"  Portfolio Loaded")
    print(f"{'='*54}")
    print(f"  Accounts  : {s['total_accounts']}")
    print(f"  Positions : {s['total_positions']}")
    print(f"  Equity    : ${s['total_equity']:>14,.2f}")
    print(f"  Cash      : ${s['total_cash']:>14,.2f}")
    print(f"  Cost Basis: ${s['total_cost_basis']:>14,.2f}")
    print(f"  Unrealized: ${s['total_unrealized_gain_loss']:>+14,.2f}  ({s['total_unrealized_gain_loss_pct']:+.1f}%)")
    if s["profit_taking_candidates"]:
        print(f"  Profit Candidates: {', '.join(s['profit_taking_candidates'])}")
    print(f"{'='*54}")
    print(f"\n  Saved -> {OUTPUT_JSON.name}")
    print(f"  Saved -> {OUTPUT_MD.name}")
    print(f"\n  Run /trade portfolio  for full allocation analysis")
    print(f"  Run /trade guidance   for profit-taking & income moves\n")


if __name__ == "__main__":
    main()
