#!/usr/bin/env python3
"""
parse_schwab.py — Schwab Positions CSV → portfolio.json + portfolio.md

Usage:
    1. Export your positions from Schwab:
       Accounts tab → Positions → Export (top-right icon) → Save as CSV
    2. Drop the CSV into portfolio/input/
    3. Run: python parse_schwab.py

Supports single-account and multi-account Schwab exports.
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


# ── Helpers ──────────────────────────────────────────────────────────────────

def clean_num(s):
    """Strip $, %, commas → float. Return None if not parseable."""
    if not s or str(s).strip() in ("--", "", "N/A", "n/a"):
        return None
    try:
        return float(re.sub(r"[$%,\s]", "", str(s)))
    except ValueError:
        return None


def extract_account_id(line):
    """Pull account number from Schwab header line."""
    # Schwab format: "Positions for account  XXXX-1234 as of ..."
    m = re.search(r'([A-Z0-9*]+-\d{4})', line)
    if m:
        return m.group(1)
    # Fallback: any 4-digit suffix pattern
    m = re.search(r'(\d{4})\b', line)
    return f"Account-{m.group(1)}" if m else "Primary"


# ── Parser ────────────────────────────────────────────────────────────────────

def parse_schwab_csv(filepath):
    """
    Parse one Schwab positions CSV. Returns list of account dicts.
    Handles both single-account and multi-account exports.
    """
    accounts = []
    current = None
    headers = None

    with open(filepath, "r", encoding="utf-8-sig") as f:
        raw = f.read()

    lines = raw.splitlines()

    for line in lines:
        stripped = line.strip()

        # ── Account header ────────────────────────────────────────────────
        if "positions for account" in stripped.lower():
            if current is not None:
                accounts.append(current)
            current = {
                "account_id": extract_account_id(stripped),
                "positions": [],
                "cash": 0.0,
                "total_equity": 0.0,
            }
            headers = None
            continue

        # ── Column header row ─────────────────────────────────────────────
        if '"Symbol"' in stripped or (
            stripped.startswith('"Symbol') or stripped.startswith("Symbol")
        ):
            row = next(csv.reader([stripped]))
            headers = [h.strip().strip('"') for h in row]
            # Lazily create account if file has no account-header line
            if current is None:
                current = {
                    "account_id": "Primary",
                    "positions": [],
                    "cash": 0.0,
                    "total_equity": 0.0,
                }
            continue

        # ── Skip separators / blanks ──────────────────────────────────────
        if not stripped or stripped.replace(",", "").strip() == "":
            continue

        # ── Data rows (need headers) ──────────────────────────────────────
        if headers is None or current is None:
            continue

        try:
            row = next(csv.reader([stripped]))
            row = [c.strip().strip('"') for c in row]
        except Exception:
            continue

        if not row or not row[0]:
            continue

        # Map to dict (pad short rows)
        row += [""] * max(0, len(headers) - len(row))
        d = {headers[i]: row[i] for i in range(len(headers))}
        sym = d.get("Symbol", "").strip()

        # ── Cash / money market line ──────────────────────────────────────
        if not sym or "cash" in sym.lower() or "money market" in sym.lower():
            val = clean_num(d.get("Market Value", ""))
            if val is not None:
                current["cash"] += val
            continue

        # ── Account Total line ────────────────────────────────────────────
        if "account total" in sym.lower() or sym.lower() == "total":
            val = clean_num(d.get("Market Value", ""))
            if val is not None:
                current["total_equity"] = val
            continue

        # ── Regular equity/ETF/bond position ─────────────────────────────
        shares = clean_num(d.get("Qty", ""))
        price = clean_num(d.get("Price", ""))
        mkt_val = clean_num(d.get("Market Value", ""))
        cost = clean_num(d.get("Cost Basis", ""))
        gl_dollar = clean_num(d.get("Gain/Loss $", ""))
        gl_pct = clean_num(d.get("Gain/Loss %", ""))
        pct_acct = clean_num(d.get("% Of Account", ""))

        avg_cost = round(cost / shares, 4) if (cost and shares and shares > 0) else None

        current["positions"].append({
            "symbol": sym,
            "name": d.get("Description", ""),
            "shares": shares,
            "price": price,
            "market_value": mkt_val,
            "cost_basis": cost,
            "avg_cost_per_share": avg_cost,
            "unrealized_gain_loss": gl_dollar,
            "unrealized_gain_loss_pct": gl_pct,
            "pct_of_account": pct_acct,
            "security_type": d.get("Security Type", ""),
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

    # Positions with largest gains (profit-taking candidates)
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
        f"| Total Equity | ${s['total_equity']:>12,.2f} |",
        f"| Total Cash | ${s['total_cash']:>14,.2f} |",
        f"| Market Value (Invested) | ${s['total_invested_market_value']:>6,.2f} |",
        f"| Total Cost Basis | ${s['total_cost_basis']:>10,.2f} |",
        f"| Unrealized Gain/Loss | ${s['total_unrealized_gain_loss']:>+10,.2f} ({s['total_unrealized_gain_loss_pct']:+.1f}%) |",
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
            f"---",
            "",
            f"## Account: {acct['account_id']}",
            "",
            f"**Total Equity:** ${acct['total_equity']:,.2f}  |  **Cash:** ${acct['cash']:,.2f}",
            "",
        ]

        if acct["positions"]:
            lines += [
                "| Symbol | Name | Shares | Price | Mkt Value | Cost Basis | Unreal G/L | G/L % | % Acct |",
                "|--------|------|-------:|------:|----------:|-----------:|-----------:|------:|-------:|",
            ]
            for p in sorted(acct["positions"], key=lambda x: x.get("market_value") or 0, reverse=True):
                def fmt(v, prefix="$", suffix=""):
                    return f"{prefix}{v:,.2f}{suffix}" if v is not None else "N/A"
                def fmtp(v):
                    return f"{v:+.1f}%" if v is not None else "N/A"
                def fmts(v):
                    return f"{v:,.0f}" if v is not None else "N/A"

                lines.append(
                    f"| {p['symbol']} | {p['name'][:28]} | {fmts(p.get('shares'))} | "
                    f"{fmt(p.get('price'))} | {fmt(p.get('market_value'))} | "
                    f"{fmt(p.get('cost_basis'))} | {fmt(p.get('unrealized_gain_loss'), prefix='$')} | "
                    f"{fmtp(p.get('unrealized_gain_loss_pct'))} | "
                    f"{fmtp(p.get('pct_of_account')).replace('+', '')} |"
                )
            lines.append("")

    lines += [
        "---",
        "",
        "*DISCLAIMER: For educational/research purposes only. Not financial advice.*",
    ]

    path.write_text("\n".join(lines), encoding="utf-8")


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    INPUT_DIR.mkdir(parents=True, exist_ok=True)
    OUTPUT_JSON.parent.mkdir(parents=True, exist_ok=True)

    csv_files = sorted(
        list(INPUT_DIR.glob("*.csv")) + list(INPUT_DIR.glob("*.CSV")),
        key=lambda x: x.stat().st_mtime,
        reverse=True,
    )

    if not csv_files:
        print(f"\nNo CSV files found in:  {INPUT_DIR}")
        print("\nSteps to export from Schwab:")
        print("  1. Log in → Accounts tab → Positions")
        print("  2. Click the Export icon (top-right, looks like a page with arrow)")
        print("  3. Save the file")
        print(f"  4. Move it into:  {INPUT_DIR}")
        print("  5. Run this script again\n")
        sys.exit(1)

    latest = csv_files[0]
    print(f"Parsing: {latest.name}")

    accounts = parse_schwab_csv(latest)

    if not accounts or not any(a["positions"] for a in accounts):
        print("\nNo positions found. Make sure this is a Schwab Positions export.")
        print("The file should have a 'Symbol' column with your holdings.")
        sys.exit(1)

    summary = build_summary(accounts)

    data = {
        "last_updated": datetime.now().strftime("%Y-%m-%d %H:%M"),
        "source": f"Schwab — {latest.name}",
        "source_file": latest.name,
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
    print(f"\n  Saved → {OUTPUT_JSON.name}")
    print(f"  Saved → {OUTPUT_MD.name}")
    print(f"\n  Run /trade portfolio  for full allocation analysis")
    print(f"  Run /trade guidance   for profit-taking & income moves\n")


if __name__ == "__main__":
    main()
