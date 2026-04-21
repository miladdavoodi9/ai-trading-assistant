#!/usr/bin/env python3
"""
parse_schwab.py  --  Schwab / E-Trade / Morgan Stanley -> portfolio.json

Supported exports:
  Schwab          Accounts -> Positions -> Export (CSV)
  E-Trade         Portfolio -> download icon -> CSV
  Morgan Stanley  Portfolio -> Holdings -> Download (XLSX — no conversion needed)

Drop any CSV or XLSX files into  portfolio/input/  then run:
    python parse_schwab.py
"""

import csv
import json
import re
import sys
from datetime import datetime
from pathlib import Path

try:
    import xlrd
    _XLRD_OK = True
except ImportError:
    _XLRD_OK = False

BASE_DIR    = Path(__file__).parent
INPUT_DIR   = BASE_DIR / "portfolio" / "input"
OUTPUT_JSON = BASE_DIR / "portfolio" / "portfolio.json"
OUTPUT_MD   = BASE_DIR / "portfolio" / "portfolio.md"


# ── Column name normalization ─────────────────────────────────────────────────
# Maps every known brokerage column variant to a canonical internal key.
COLUMN_MAP = {
    # ── Quantity / Shares ──────────────────────────────────────
    "qty":                      "shares",
    "qty (quantity)":           "shares",
    "qty #":                    "shares",
    "quantity":                 "shares",
    "shares":                   "shares",

    # ── Price ──────────────────────────────────────────────────
    "price":                    "price",
    "last price":               "price",
    "last ($)":                 "price",       # Morgan Stanley XLSX
    "market price":             "price",
    "current price":            "price",
    "closing price":            "price",

    # ── Market Value ───────────────────────────────────────────
    "market value":             "market_value",
    "market value ($)":         "market_value",  # Morgan Stanley XLSX
    "mkt val (market value)":   "market_value",
    "mkt val":                  "market_value",
    "value":                    "market_value",
    "total value":              "market_value",
    "current value":            "market_value",

    # ── Cost Basis (total) ─────────────────────────────────────
    "cost basis":               "cost_basis",
    "total cost":               "cost_basis",
    "total cost ($)":           "cost_basis",    # Morgan Stanley XLSX
    "cost basis total":         "cost_basis",
    "adjusted cost basis":      "cost_basis",
    "adjusted cost ($)":        "cost_basis",    # Morgan Stanley XLSX fallback

    # ── Cost Per Share (E-Trade uses this; derive total from qty)
    "cost/share":               "cost_per_share",
    "price paid":               "cost_per_share",
    "price paid $":             "cost_per_share",
    "avg price":                "cost_per_share",
    "average cost":             "cost_per_share",
    "avg cost/share":           "cost_per_share",

    # ── Gain / Loss $ ──────────────────────────────────────────
    "gain/loss $":                  "gain_loss",
    "gain $ (gain/loss $)":         "gain_loss",
    "gain $":                       "gain_loss",
    "total gain/loss dollar":       "gain_loss",
    "total gain/loss $":            "gain_loss",
    "unrealized gain/loss":         "gain_loss",
    "unrealized gain / loss":       "gain_loss",
    "unrealized gain/loss ($)":     "gain_loss",    # Morgan Stanley XLSX
    "unrealized p&l":               "gain_loss",
    "gain/loss":                    "gain_loss",

    # ── Gain / Loss % ──────────────────────────────────────────
    "gain/loss %":                  "gain_loss_pct",
    "gain % (gain/loss %)":         "gain_loss_pct",
    "gain %":                       "gain_loss_pct",
    "unrealized gain/loss (%)":     "gain_loss_pct",  # Morgan Stanley XLSX
    "total gain/loss percent":  "gain_loss_pct",
    "total gain/loss %":        "gain_loss_pct",
    "% gain/loss":              "gain_loss_pct",
    "unrealized gain/loss %":   "gain_loss_pct",

    # ── % of Account / Portfolio ────────────────────────────────
    "% of account":             "pct_of_account",
    "% of acct (% of account)": "pct_of_account",
    "% of acct":                "pct_of_account",
    "% of portfolio":           "pct_of_account",
    "% portfolio":              "pct_of_account",
    "portfolio %":              "pct_of_account",

    # ── Security Type ───────────────────────────────────────────
    "security type":            "security_type",
    "asset type":               "security_type",
    "asset class":              "security_type",
    "type":                     "security_type",

    # ── Description / Name ─────────────────────────────────────
    "description":              "name",
    "security description":     "name",
    "security name":            "name",
    "name":                     "name",
    "issue description":        "name",

    # ── Symbol / Ticker ─────────────────────────────────────────
    "symbol":                   "symbol",
    "ticker":                   "symbol",
    "ticker symbol":            "symbol",
    "stock symbol":             "symbol",
}

SYMBOL_COLS = {"symbol", "ticker", "ticker symbol", "stock symbol"}
NAME_COLS   = {"description", "security description", "security name",
               "name", "issue description"}
CASH_KEYWORDS = {"cash", "money market", "mmf", "sweep", "fdic", "spaxx", "swvxx"}
TOTAL_KEYWORDS = {"account total", "positions total", "total", "subtotal"}


def normalize_header(h: str) -> str:
    return COLUMN_MAP.get(h.strip().lower(), h.strip().lower())


def clean_num(s):
    if not s or str(s).strip() in ("--", "", "N/A", "n/a", "n/a*", "-"):
        return None
    try:
        return float(re.sub(r"[$%,\s]", "", str(s)))
    except ValueError:
        return None


def _is_header_row(stripped: str) -> bool:
    """Return True if this line looks like a column header row."""
    try:
        row = next(csv.reader([stripped]))
        lower = {c.strip().lower() for c in row}
        return bool(lower & SYMBOL_COLS) and bool(lower & NAME_COLS)
    except Exception:
        return False


def _build_position(d: dict, sym: str) -> dict:
    shares   = clean_num(d.get("shares", ""))
    price    = clean_num(d.get("price", ""))
    mkt_val  = clean_num(d.get("market_value", ""))
    cost     = clean_num(d.get("cost_basis", ""))
    gl       = clean_num(d.get("gain_loss", ""))
    gl_pct   = clean_num(d.get("gain_loss_pct", ""))
    pct_acct = clean_num(d.get("pct_of_account", ""))

    # E-Trade: derive cost_basis from cost_per_share × shares
    if cost is None:
        cps = clean_num(d.get("cost_per_share", ""))
        if cps and shares:
            cost = round(cps * shares, 2)

    avg_cost = round(cost / shares, 4) if (cost and shares and shares > 0) else None

    return {
        "symbol":                   sym,
        "name":                     d.get("name", ""),
        "shares":                   shares,
        "price":                    price,
        "market_value":             mkt_val,
        "cost_basis":               cost,
        "avg_cost_per_share":       avg_cost,
        "unrealized_gain_loss":     gl,
        "unrealized_gain_loss_pct": gl_pct,
        "pct_of_account":           pct_acct,
        "security_type":            d.get("security_type", ""),
    }


# ── Brokerage detection ───────────────────────────────────────────────────────

def detect_brokerage(content: str, filename: str = "") -> str:
    fname = filename.lower()
    head  = content.lower()[:3000]

    if any(k in fname for k in ("etrade", "e-trade", "e_trade")):
        return "etrade"
    if any(k in fname for k in ("morganstanley", "morgan_stanley", "ms_client", "morgan stanley")):
        return "morgan_stanley"
    if "positions for account" in head:
        return "schwab"
    if "cost/share" in head or "reinvest dividends" in head:
        return "etrade"
    if ("ticker symbol" in head and
            ("security description" in head or "market price" in head)):
        return "morgan_stanley"
    if "unrealized gain/loss" in head and "ticker symbol" in head:
        return "morgan_stanley"
    return "schwab"


# ── Account ID helpers ────────────────────────────────────────────────────────

def _account_suffix(text: str) -> str:
    """Extract last 4 digits as account suffix, e.g. '-1234'."""
    m = re.search(r'(\d{3,})', text)
    return f"-{m.group(1)[-4:]}" if m else ""


def extract_schwab_account_id(header_line: str, filepath=None) -> str:
    label = "Account"
    if filepath:
        stem = Path(filepath).stem
        m = re.match(r'^(.+?)\s*-\s*Positions', stem, re.IGNORECASE)
        if m:
            label = m.group(1).strip()
    m = re.search(r'[.…]{1,3}(\d{3,4})', header_line)
    suffix = f"-{m.group(1)}" if m else ""
    return f"{label}{suffix}"


def extract_generic_account_id(lines, filepath=None, default="Account") -> str:
    """Scan first 15 lines for an account name/number."""
    for line in lines[:15]:
        stripped = line.strip().strip('"')
        m = re.search(
            r'(?:account\s*(?:name|number|#)?)[:\s]+([^,\n]+)',
            stripped, re.IGNORECASE
        )
        if m:
            raw = m.group(1).strip().strip('"')
            suffix = _account_suffix(raw)
            label  = re.sub(r'[\s\-]+\d+\s*$', '', raw).strip() or default
            return f"{label}{suffix}"
    if filepath:
        return Path(filepath).stem
    return default


# ── Schwab parser ─────────────────────────────────────────────────────────────

def parse_schwab_csv(filepath, content: str) -> list:
    accounts = []
    current  = None
    headers  = None

    for line in content.splitlines():
        stripped = line.strip()

        if "positions for account" in stripped.lower():
            if current is not None:
                accounts.append(current)
            current = {
                "account_id": extract_schwab_account_id(stripped, filepath),
                "positions": [], "cash": 0.0, "total_equity": 0.0,
            }
            headers = None
            continue

        if _is_header_row(stripped):
            row = next(csv.reader([stripped]))
            headers = [normalize_header(h) for h in row]
            if current is None:
                current = {
                    "account_id": extract_schwab_account_id("", filepath),
                    "positions": [], "cash": 0.0, "total_equity": 0.0,
                }
            continue

        if not stripped or stripped.replace(",", "").strip() == "":
            continue
        if headers is None or current is None:
            continue

        try:
            row = [c.strip().strip('"') for c in next(csv.reader([stripped]))]
        except Exception:
            continue

        if not row or not row[0]:
            continue

        row += [""] * max(0, len(headers) - len(row))
        d   = {headers[i]: row[i] for i in range(len(headers))}
        sym = d.get("symbol", "").strip()

        if not sym or any(k in sym.lower() for k in CASH_KEYWORDS):
            val = clean_num(d.get("market_value", ""))
            if val is not None:
                current["cash"] += val
            continue

        if any(t in sym.lower() for t in TOTAL_KEYWORDS):
            val = clean_num(d.get("market_value", ""))
            if val is not None:
                current["total_equity"] = val
            continue

        current["positions"].append(_build_position(d, sym))

    if current is not None:
        accounts.append(current)

    return accounts


# ── Generic flat-file parser (E-Trade / Morgan Stanley) ───────────────────────

def parse_flat_csv(filepath, content: str, brokerage: str) -> list:
    """
    Handles brokerages that export a flat CSV (one account per file, or an
    'Account' column per row).  Covers E-Trade and Morgan Stanley.
    """
    lines      = content.splitlines()
    default_id = extract_generic_account_id(
        lines, filepath,
        default=("E-Trade Account" if brokerage == "etrade" else "Morgan Stanley Account"),
    )

    accounts_map: dict = {}
    headers           = None
    has_account_col   = False

    for line in lines:
        stripped = line.strip()
        if not stripped:
            continue

        if headers is None:
            if _is_header_row(stripped):
                row = next(csv.reader([stripped]))
                headers = [normalize_header(h) for h in row]
                has_account_col = bool(
                    {"account", "account name", "account number"} &
                    {h.strip().lower() for h in row}
                )
            continue

        try:
            row = [c.strip().strip('"') for c in next(csv.reader([stripped]))]
        except Exception:
            continue

        if not row or not row[0]:
            continue

        row += [""] * max(0, len(headers) - len(row))
        d   = {headers[i]: row[i] for i in range(len(headers))}

        # Determine which account this row belongs to
        if has_account_col:
            raw = d.get("account", d.get("account name", d.get("account number", default_id))).strip()
            suffix    = _account_suffix(raw)
            acct_key  = re.sub(r'[\s\-]+\d+\s*$', '', raw).strip() or "Account"
            acct_key  = f"{acct_key}{suffix}"
        else:
            acct_key = default_id

        if acct_key not in accounts_map:
            accounts_map[acct_key] = {
                "account_id": acct_key,
                "positions": [], "cash": 0.0, "total_equity": 0.0,
            }
        current = accounts_map[acct_key]

        sym = d.get("symbol", "").strip().upper()
        if not sym:
            continue

        if any(k in sym.lower() for k in CASH_KEYWORDS):
            val = clean_num(d.get("market_value", ""))
            if val is not None:
                current["cash"] += val
            continue

        if any(t in sym.lower() for t in TOTAL_KEYWORDS):
            val = clean_num(d.get("market_value", ""))
            if val is not None:
                current["total_equity"] = val
            continue

        current["positions"].append(_build_position(d, sym))

    accounts = list(accounts_map.values())
    if not accounts:
        accounts = [{"account_id": default_id, "positions": [],
                     "cash": 0.0, "total_equity": 0.0}]

    # Fill total_equity if not found in a totals row
    for acct in accounts:
        if acct["total_equity"] == 0.0:
            acct["total_equity"] = round(
                sum(p.get("market_value") or 0 for p in acct["positions"])
                + acct["cash"], 2
            )

    return accounts


# ── Morgan Stanley XLSX parser ───────────────────────────────────────────────

# Product types to treat as cash rather than positions
_MS_CASH_TYPES = {"cash, mmf and bdp", "cash"}
# Institutions to skip entirely (non-brokerage linked accounts)
_MS_SKIP_INSTITUTIONS = {"chase", "bank of america", "wells fargo", "citibank"}

def parse_ms_xlsx(filepath) -> list:
    """
    Parse Morgan Stanley's native XLSX export (Holdings view).
    Groups rows by 'Account Number' column; skips linked bank accounts.
    """
    if not _XLRD_OK:
        print("  WARNING: xlrd not installed — cannot read XLSX. Run: pip install xlrd==1.2.0")
        return []

    wb = xlrd.open_workbook(str(filepath))
    ws = wb.sheet_by_index(0)

    # Find the header row (contains 'Account Number' and 'Symbol')
    header_row_idx = None
    for i in range(ws.nrows):
        row = [str(ws.cell_value(i, j)).strip() for j in range(ws.ncols)]
        if "Account Number" in row and "Symbol" in row:
            header_row_idx = i
            break

    if header_row_idx is None:
        print(f"  WARNING: could not find header row in {filepath.name}")
        return []

    headers = [normalize_header(str(ws.cell_value(header_row_idx, j)).strip())
               for j in range(ws.ncols)]

    # Also keep raw headers for account number and institution columns
    raw_headers = [str(ws.cell_value(header_row_idx, j)).strip().lower()
                   for j in range(ws.ncols)]
    acct_col  = raw_headers.index("account number") if "account number" in raw_headers else None
    inst_col  = raw_headers.index("institution")    if "institution"    in raw_headers else None
    ptype_col = raw_headers.index("product type")   if "product type"   in raw_headers else None

    accounts_map = {}

    for i in range(header_row_idx + 1, ws.nrows):
        row = [str(ws.cell_value(i, j)).strip() for j in range(ws.ncols)]
        if not any(row):
            continue

        # Skip footnotes / disclaimer rows
        # Valid account IDs are short and always contain digits (e.g. "AAA - 1103")
        first = row[0] if row else ""
        if len(first) > 80 or not re.search(r'\d', first):
            continue
        if first.lower() in ("total", ""):
            continue

        # Skip linked bank accounts (Chase, etc.)
        institution = row[inst_col].strip() if inst_col is not None else ""
        if any(bank in institution.lower() for bank in _MS_SKIP_INSTITUTIONS):
            continue

        # Determine account key
        raw_acct = row[acct_col].strip() if acct_col is not None else "Morgan Stanley"
        # raw_acct looks like "AAA - 1103" or "Stock Plan & Linked Brokerage - 3329"
        # Normalize to a clean label + last-4 suffix
        num_m = re.search(r'(\d{4,})\s*$', raw_acct)
        suffix    = f"-{num_m.group(1)[-4:]}" if num_m else ""
        base_name = re.sub(r'\s*[-–]\s*\d+\s*$', '', raw_acct).strip()
        # Shorten verbose names
        if "stock plan" in base_name.lower() or "linked brokerage" in base_name.lower():
            base_name = "Stock Plan"
        elif not base_name:
            base_name = "Morgan Stanley"
        acct_key = f"{base_name}{suffix}"

        if acct_key not in accounts_map:
            accounts_map[acct_key] = {
                "account_id": acct_key,
                "positions": [], "cash": 0.0, "total_equity": 0.0,
            }
        current = accounts_map[acct_key]

        # Build row dict using normalized headers
        row += [""] * max(0, len(headers) - len(row))
        d = {headers[j]: row[j] for j in range(len(headers))}

        sym = d.get("symbol", "").strip().upper()
        product_type = row[ptype_col].strip().lower() if ptype_col is not None else ""

        # Cash / BDP rows
        if not sym or sym == "-" or product_type in _MS_CASH_TYPES:
            val = clean_num(d.get("market_value", ""))
            if val is not None:
                current["cash"] += val
            continue

        # Skip non-standard holdings (stock plan unvested, etc.)
        if product_type == "other holdings":
            continue

        pos = _build_position(d, sym)
        if pos["shares"] is not None or pos["market_value"] is not None:
            current["positions"].append(pos)

    accounts = list(accounts_map.values())

    for acct in accounts:
        if acct["total_equity"] == 0.0:
            acct["total_equity"] = round(
                sum(p.get("market_value") or 0 for p in acct["positions"])
                + acct["cash"], 2
            )

    return accounts


# ── Dispatcher ────────────────────────────────────────────────────────────────

def parse_csv(filepath) -> tuple:
    """Auto-detect brokerage and return (accounts_list, brokerage_name)."""
    with open(filepath, "r", encoding="utf-8-sig") as f:
        content = f.read()

    brokerage = detect_brokerage(content, filepath.name)

    if brokerage == "schwab":
        return parse_schwab_csv(filepath, content), "Schwab"
    elif brokerage == "etrade":
        return parse_flat_csv(filepath, content, brokerage), "E-Trade"
    else:
        return parse_flat_csv(filepath, content, brokerage), "Morgan Stanley"


# ── Summary ───────────────────────────────────────────────────────────────────

def build_summary(accounts: list) -> dict:
    all_pos = [p for a in accounts for p in a["positions"]]

    total_equity = sum(a.get("total_equity", 0) or 0 for a in accounts)
    total_cash   = sum(a.get("cash", 0)         or 0 for a in accounts)
    total_mv     = sum(p.get("market_value", 0) or 0 for p in all_pos)
    total_cost   = sum(p.get("cost_basis", 0)   or 0 for p in all_pos)
    total_gl     = sum(p.get("unrealized_gain_loss", 0) or 0 for p in all_pos)
    gl_pct       = round(total_gl / total_cost * 100, 2) if total_cost else 0

    top = sorted(
        [p for p in all_pos if p.get("market_value")],
        key=lambda x: x["market_value"], reverse=True,
    )[:10]

    gain_candidates = sorted(
        [p for p in all_pos if (p.get("unrealized_gain_loss_pct") or 0) > 20],
        key=lambda x: x.get("unrealized_gain_loss_pct", 0), reverse=True,
    )

    return {
        "total_accounts":               len(accounts),
        "total_equity":                 round(total_equity, 2),
        "total_cash":                   round(total_cash, 2),
        "total_invested_market_value":  round(total_mv, 2),
        "total_cost_basis":             round(total_cost, 2),
        "total_unrealized_gain_loss":   round(total_gl, 2),
        "total_unrealized_gain_loss_pct": gl_pct,
        "total_positions":              len(all_pos),
        "top_holdings_by_value":        [p["symbol"] for p in top],
        "profit_taking_candidates":     [p["symbol"] for p in gain_candidates],
    }


# ── Markdown writer ───────────────────────────────────────────────────────────

def write_markdown(data: dict, path):
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
        "# Portfolio Summary", "",
        f"**Last Updated:** {data['last_updated']}  |  **Source:** {data['source']}", "",
        "> DISCLAIMER: For educational/research purposes only. Not financial advice.", "",
        "---", "", "## Overview", "",
        "| Metric | Value |", "|--------|-------|",
        f"| Total Equity | {f(s['total_equity'])} |",
        f"| Total Cash | {f(s['total_cash'])} |",
        f"| Market Value (Invested) | {f(s['total_invested_market_value'])} |",
        f"| Total Cost Basis | {f(s['total_cost_basis'])} |",
        f"| Unrealized Gain/Loss | {f(s['total_unrealized_gain_loss'], sign=True)} "
        f"({fp(s['total_unrealized_gain_loss_pct'], sign=True)}) |",
        f"| Accounts | {s['total_accounts']} |",
        f"| Positions | {s['total_positions']} |", "",
    ]

    if s.get("profit_taking_candidates"):
        lines += [
            f"**Profit-Taking Candidates (>20% gain):** "
            f"{', '.join(s['profit_taking_candidates'])}", "",
        ]

    for acct in data["accounts"]:
        lines += [
            "---", "",
            f"## Account: {acct['account_id']}", "",
            f"**Total Equity:** {f(acct['total_equity'])}  |  **Cash:** {f(acct['cash'])}", "",
        ]
        if acct["positions"]:
            lines += [
                "| Symbol | Name | Shares | Price | Mkt Value | Cost Basis | "
                "Unreal G/L | G/L % | % Acct |",
                "|--------|------|-------:|------:|----------:|-----------:"
                "|-----------:|------:|-------:|",
            ]
            for p in sorted(
                acct["positions"],
                key=lambda x: x.get("market_value") or 0, reverse=True
            ):
                sh = f"{p['shares']:,.4f}" if p.get("shares") else "N/A"
                lines.append(
                    f"| {p['symbol']} | {p['name'][:28]} | {sh} | "
                    f"{f(p.get('price'))} | {f(p.get('market_value'))} | "
                    f"{f(p.get('cost_basis'))} | "
                    f"{f(p.get('unrealized_gain_loss'), sign=True)} | "
                    f"{fp(p.get('unrealized_gain_loss_pct'), sign=True)} | "
                    f"{fp(p.get('pct_of_account'))} |"
                )
            lines.append("")

    lines += ["---", "",
              "*DISCLAIMER: For educational/research purposes only. Not financial advice.*"]
    path.write_text("\n".join(lines), encoding="utf-8")


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    INPUT_DIR.mkdir(parents=True, exist_ok=True)
    OUTPUT_JSON.parent.mkdir(parents=True, exist_ok=True)

    seen, unique = set(), []
    patterns = ["*.csv", "*.CSV", "*.xlsx", "*.XLSX", "*.xls", "*.XLS"]
    for pat in patterns:
        for f in INPUT_DIR.glob(pat):
            key = f.resolve()
            if key not in seen:
                seen.add(key)
                unique.append(f)
    all_files = sorted(unique, key=lambda x: x.stat().st_mtime, reverse=True)

    if not all_files:
        print(f"\nNo portfolio files found in: {INPUT_DIR}")
        print("\nExport steps:")
        print("  Schwab:         Accounts -> Positions -> Export icon (CSV)")
        print("  E-Trade:        Portfolio -> download icon -> CSV")
        print("  Morgan Stanley: Portfolio -> Holdings -> Download (XLSX, drop as-is)")
        print(f"\nDrop the file(s) into: {INPUT_DIR}")
        print("Then run this script again.\n")
        sys.exit(1)

    accounts  = []
    brokers   = []
    for portfolio_file in all_files:
        ext = portfolio_file.suffix.lower()
        if ext in (".xlsx", ".xls"):
            result = parse_ms_xlsx(portfolio_file)
            broker = "Morgan Stanley"
            print(f"Parsing (Morgan Stanley XLSX): {portfolio_file.name}  ->  {len(result)} account(s)")
        else:
            result, broker = parse_csv(portfolio_file)
            print(f"Parsing ({broker}): {portfolio_file.name}  ->  {len(result)} account(s)")
        accounts.extend(result)
        brokers.append(broker)

    if not accounts or not any(a["positions"] for a in accounts):
        print("\nNo positions found. Check that the CSV is a positions/portfolio export.")
        sys.exit(1)

    summary = build_summary(accounts)
    source  = " + ".join(sorted(set(brokers)))

    data = {
        "last_updated": datetime.now().strftime("%Y-%m-%d %H:%M"),
        "source":       f"{source} — {len(all_files)} file(s)",
        "source_files": [f.name for f in all_files],
        "accounts":     accounts,
        "summary":      summary,
    }

    OUTPUT_JSON.write_text(json.dumps(data, indent=2, default=str), encoding="utf-8")
    write_markdown(data, OUTPUT_MD)

    s = summary
    print(f"\n{'='*54}")
    print(f"  Portfolio Loaded  ({source})")
    print(f"{'='*54}")
    print(f"  Accounts  : {s['total_accounts']}")
    print(f"  Positions : {s['total_positions']}")
    print(f"  Equity    : ${s['total_equity']:>14,.2f}")
    print(f"  Cash      : ${s['total_cash']:>14,.2f}")
    print(f"  Cost Basis: ${s['total_cost_basis']:>14,.2f}")
    print(f"  Unrealized: ${s['total_unrealized_gain_loss']:>+14,.2f}  "
          f"({s['total_unrealized_gain_loss_pct']:+.1f}%)")
    if s["profit_taking_candidates"]:
        print(f"  Profit Candidates: {', '.join(s['profit_taking_candidates'])}")
    print(f"{'='*54}")
    print(f"\n  Saved -> {OUTPUT_JSON.name}")
    print(f"  Saved -> {OUTPUT_MD.name}\n")


if __name__ == "__main__":
    main()
