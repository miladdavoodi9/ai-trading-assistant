#!/usr/bin/env python3
"""
parse_schwab.py  --  Schwab / E-Trade / Morgan Stanley / Fidelity -> portfolio.json

Supported exports:
  Schwab          Accounts -> Positions -> Export (CSV)
  E-Trade         Portfolio -> download icon -> CSV
  Morgan Stanley  Portfolio -> Holdings -> Download (XLSX — no conversion needed)
  Fidelity        Accounts -> Portfolio -> Download -> CSV

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
    import openpyxl
    _OPENPYXL_OK = True
except ImportError:
    _OPENPYXL_OK = False

try:
    import xlrd
    _XLRD_OK = True
except ImportError:
    _XLRD_OK = False


def _load_sheet(filepath) -> list:
    """
    Load the first sheet of an XLSX/XLS file into a list of rows.
    Each row is a list of raw strings (NOT stripped) so callers can
    detect leading whitespace (indentation) used by Morgan Stanley exports.
    Prefers openpyxl (handles modern .xlsx); falls back to xlrd (.xls).
    """
    if _OPENPYXL_OK:
        wb = openpyxl.load_workbook(str(filepath), read_only=True, data_only=True)
        ws = wb.worksheets[0]
        rows = []
        for row in ws.iter_rows(values_only=True):
            rows.append([str(v) if v is not None else "" for v in row])
        wb.close()
        return rows
    if _XLRD_OK:
        wb = xlrd.open_workbook(str(filepath))
        ws = wb.sheet_by_index(0)
        return [
            [str(ws.cell_value(i, j)) for j in range(ws.ncols)]
            for i in range(ws.nrows)
        ]
    return []

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

    # ── Cost Per Share (E-Trade / Fidelity use this; derive total from qty)
    "cost/share":               "cost_per_share",
    "cost basis per share":     "cost_per_share",   # Fidelity
    "price paid":               "cost_per_share",
    "price paid $":             "cost_per_share",
    "avg price":                "cost_per_share",
    "average cost":             "cost_per_share",
    "avg cost/share":           "cost_per_share",

    # ── Gain / Loss $ ──────────────────────────────────────────
    "gain/loss $":                  "gain_loss",
    "gain $ (gain/loss $)":         "gain_loss",
    "gain $":                       "gain_loss",
    "total gain/loss dollar":       "gain_loss",    # Fidelity
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
    "total gain/loss percent":      "gain_loss_pct",  # Fidelity
    "total gain/loss %":            "gain_loss_pct",
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
    if any(k in fname for k in ("merrill", "merrilledge", "merrill_lynch", "manual_positions")):
        return "manual"
    if "portfolio_positions" in fname or "fidelity" in fname:
        return "fidelity"
    if "positions for account" in head:
        return "schwab"
    if "cost/share" in head or "reinvest dividends" in head:
        return "etrade"
    if ("ticker symbol" in head and
            ("security description" in head or "market price" in head)):
        return "morgan_stanley"
    if "unrealized gain/loss" in head and "ticker symbol" in head:
        return "morgan_stanley"
    # Fidelity content signature: has both "account name" and "last price change"
    if "account name" in head and ("last price change" in head or "cost basis per share" in head):
        return "fidelity"
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
                "positions": [], "cash": 0.0, "total_equity": 0.0, "liabilities": [],
            }
            headers = None
            continue

        if _is_header_row(stripped):
            row = next(csv.reader([stripped]))
            headers = [normalize_header(h) for h in row]
            if current is None:
                current = {
                    "account_id": extract_schwab_account_id("", filepath),
                    "positions": [], "cash": 0.0, "total_equity": 0.0, "liabilities": [],
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
    'Account' column per row).  Covers E-Trade, Morgan Stanley, and Fidelity.
    """
    _default_labels = {
        "etrade":         "E-Trade Account",
        "fidelity":       "Fidelity Account",
        "morgan_stanley": "Morgan Stanley Account",
        "manual":         "Merrill Lynch",
    }
    lines      = content.splitlines()
    default_id = extract_generic_account_id(
        lines, filepath,
        default=_default_labels.get(brokerage, "Account"),
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
            acct_name = d.get("account name", "").strip()
            acct_num  = d.get("account number", d.get("account", "")).strip()
            if acct_name and acct_num:
                # Fidelity: combine "Individual" + last-4 of account number
                num_suffix = f"-{acct_num[-4:]}" if len(acct_num) >= 4 else f"-{acct_num}"
                acct_key   = f"{acct_name}{num_suffix}"
            else:
                raw      = (acct_name or acct_num or default_id).strip()
                suffix   = _account_suffix(raw)
                acct_key = re.sub(r'[\s\-]+\d+\s*$', '', raw).strip() or "Account"
                acct_key = f"{acct_key}{suffix}"
        else:
            acct_key = default_id

        if acct_key not in accounts_map:
            accounts_map[acct_key] = {
                "account_id": acct_key,
                "positions": [], "cash": 0.0, "total_equity": 0.0, "liabilities": [],
            }
        current = accounts_map[acct_key]

        sym          = d.get("symbol", "").strip().upper()
        sec_type_raw = d.get("security_type", "").strip().lower()

        # Blank symbol with Type="Cash" (Fidelity cash rows)
        if not sym:
            if sec_type_raw == "cash":
                val = clean_num(d.get("market_value", ""))
                if val is not None:
                    current["cash"] += val
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
                     "cash": 0.0, "total_equity": 0.0, "liabilities": []}]

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
_MS_SKIP_INSTITUTIONS = {"chase", "bank of america", "wells fargo", "citibank", "citi"}


def _ms_acct_key(raw: str) -> str:
    """Normalize 'AAA - 11031' or 'Stock Plan & Linked Brokerage - 3329' -> clean key."""
    raw = raw.strip().split("\n")[0].strip()
    num_m = re.search(r"(\d{3,})\s*$", raw)
    suffix = f"-{num_m.group(1)[-4:]}" if num_m else ""
    base = re.sub(r"\s*[-–]\s*\d+\s*$", "", raw).strip()
    if "stock plan" in base.lower() or "linked brokerage" in base.lower():
        base = "Stock Plan"
    elif not base or base.lower() == "morgan stanley":
        base = "Morgan Stanley"
    return f"{base}{suffix}"


def _parse_ms_xlsx_home(rows: list) -> list:
    """
    Parse the Morgan Stanley 'Home Page' XLSX export.
    Extracts per-account totals from 'Investment Details' and individual
    securities from 'My Top Holdings', then distributes shares proportionally.
    Also parses the 'Liabilities' section (e.g. LAL credit lines).
    Cost basis is not available in this export format.
    """
    accounts_map = {}   # acct_key -> account dict (with temp _stocks_val/_group)
    top_holdings = []   # [{name, symbol, quantity, price, market_value}]
    # group_name (lowercase) -> list of {name, balance}
    liabilities_by_group = {}

    # ── state machine ──────────────────────────────────────────────────────────
    NONE, INV_DETAILS, TOP_HOLDINGS, LIABILITIES = 0, 1, 2, 3
    state = NONE
    inv_headers = None
    inv_cols = {}          # col-name -> column index for Investment Details
    th_headers = None      # Top Holdings column names (lowercase)
    liab_headers = None
    liab_balance_col = None
    current_group = ""     # tracks group header row for skip/association logic

    for raw_row in rows:
        row_vals = [v.strip() for v in raw_row]
        # Pad to consistent width
        first = row_vals[0] if row_vals else ""
        raw_first = raw_row[0] if raw_row else ""  # un-stripped for indentation detection

        # ── section transitions ────────────────────────────────────────────────
        if "liabilities" in first.lower() and "margin" in first.lower():
            state = LIABILITIES
            liab_headers = None
            liab_balance_col = None
            current_group = ""
            continue

        if "investment details" in first.lower():
            state = INV_DETAILS
            inv_headers = None
            inv_cols = {}
            current_group = ""
            continue

        if "my top holdings" in first.lower():
            state = TOP_HOLDINGS
            th_headers = None
            continue

        # Other section headers reset state
        if first and not first.startswith(" ") and state != NONE:
            other_sections = {
                "available funds", "available cash",
                "monthly projected", "during non-market", "today's change",
                "important notice", "additional information", "©",
            }
            if any(s in first.lower() for s in other_sections):
                state = NONE
                continue

        # ── Liabilities section ────────────────────────────────────────────────
        if state == LIABILITIES:
            if liab_headers is None:
                if "group/account" in first.lower():
                    liab_headers = [v.lower() for v in row_vals]
                    for ci, h in enumerate(liab_headers):
                        if "outstanding" in h or ("balance" in h and "liabilit" in h):
                            liab_balance_col = ci
                            break
                continue

            if not any(row_vals):
                continue

            if not raw_first.startswith(" "):
                current_group = raw_first.strip().lower()
                continue

            # Indented = actual liability line item (e.g. LAL-1412)
            liab_name = raw_first.strip().split("\n")[0].strip()
            if liab_balance_col is not None and liab_balance_col < len(row_vals):
                balance = clean_num(row_vals[liab_balance_col])
                if balance and balance > 0:
                    liabilities_by_group.setdefault(current_group, []).append(
                        {"name": liab_name, "balance": balance}
                    )

        # ── Investment Details section ─────────────────────────────────────────
        elif state == INV_DETAILS:
            if inv_headers is None:
                # Wait for header row ("Group/Account" in first cell)
                if "group/account" in first.lower():
                    inv_headers = [v.lower() for v in row_vals]
                    for ci, h in enumerate(inv_headers):
                        if h == "cash($)":
                            inv_cols["cash"] = ci
                        elif "mmf bank" in h or "mmf" in h:
                            inv_cols["mmf"] = ci
                        elif h == "stocks($)":
                            inv_cols["stocks"] = ci
                        elif h == "positions($)":
                            inv_cols["positions"] = ci
                continue

            if not any(row_vals):
                continue

            if not raw_first.startswith(" "):
                # Group-header row (e.g. "Morgan Stanley", "Chase")
                current_group = raw_first.strip().lower()
                continue

            # Indented = actual account row
            if any(bank in current_group for bank in _MS_SKIP_INSTITUTIONS):
                continue

            acct_key = _ms_acct_key(raw_first)

            def _gcv(col_name):
                ci = inv_cols.get(col_name)
                return clean_num(row_vals[ci]) if ci is not None and ci < len(row_vals) else None

            stocks_val  = _gcv("stocks")   or 0.0
            cash_val    = (_gcv("cash")    or 0.0) + (_gcv("mmf") or 0.0)
            pos_val     = _gcv("positions") or 0.0

            if acct_key not in accounts_map:
                accounts_map[acct_key] = {
                    "account_id":   acct_key,
                    "positions":    [],
                    "cash":         cash_val,
                    "total_equity": round(pos_val + cash_val, 2),
                    "_stocks_val":  stocks_val,
                    "_group":       current_group,
                    "liabilities":  [],
                }

        # ── My Top Holdings section ────────────────────────────────────────────
        elif state == TOP_HOLDINGS:
            if th_headers is None:
                if "name" in first.lower() and any("symbol" in v.lower() for v in row_vals if v):
                    th_headers = [v.lower() for v in row_vals]
                continue

            if not first or any(first.lower().startswith(s) for s in ("during", "please", "*")):
                state = NONE
                continue

            def _th(keyword):
                for ci, h in enumerate(th_headers):
                    if keyword in h:
                        return row_vals[ci] if ci < len(row_vals) else None
                return None

            symbol = (_th("symbol") or "").strip().upper()
            if not symbol or symbol == "-":
                continue

            qty = clean_num(_th("quantity"))
            price = clean_num(_th("latest price"))
            mv = clean_num(_th("market value"))
            if symbol and (qty or mv):
                top_holdings.append({
                    "name": first,
                    "symbol": symbol,
                    "quantity": qty or 0.0,
                    "price": price,
                    "market_value": mv or 0.0,
                })

    if not accounts_map or not top_holdings:
        return []

    # ── Distribute top holdings proportionally across accounts ─────────────────
    total_stocks = sum(a.get("_stocks_val", 0) for a in accounts_map.values())

    for acct in accounts_map.values():
        acct_stocks = acct.pop("_stocks_val", 0)
        acct_group  = acct.pop("_group", "")
        prop = (acct_stocks / total_stocks) if total_stocks > 0 else (1.0 / len(accounts_map))

        for h in top_holdings:
            shares = round(h["quantity"] * prop, 4) if h["quantity"] else None
            mv     = round(h["market_value"] * prop, 2) if h["market_value"] else None
            acct["positions"].append({
                "symbol":                   h["symbol"],
                "name":                     h["name"],
                "shares":                   shares,
                "price":                    h["price"],
                "market_value":             mv,
                "cost_basis":               None,
                "avg_cost_per_share":       None,
                "unrealized_gain_loss":     None,
                "unrealized_gain_loss_pct": None,
                "pct_of_account":           round(mv / acct_stocks * 100, 2) if (acct_stocks and mv) else None,
                "security_type":            "Stock",
            })

        # Assign liabilities from the same institution group (exact match only)
        if acct_group in liabilities_by_group:
            acct["liabilities"] = liabilities_by_group[acct_group]

        if acct["total_equity"] == 0.0:
            acct["total_equity"] = round(
                sum(p.get("market_value") or 0 for p in acct["positions"]) + acct["cash"], 2
            )

    return list(accounts_map.values())


def parse_ms_xlsx(filepath) -> list:
    """
    Parse Morgan Stanley's XLSX export.
    Supports two formats:
      - Holdings view: has 'Account Number' and 'Symbol' column headers (detailed, with cost basis)
      - Home Page view: has 'Investment Details' and 'My Top Holdings' sections (summary, no cost basis)
    """
    if not _OPENPYXL_OK and not _XLRD_OK:
        print("  WARNING: no XLSX library installed. Run: pip install openpyxl")
        return []

    rows = _load_sheet(filepath)
    if not rows:
        print(f"  WARNING: could not read {filepath.name}")
        return []

    # ── Try Holdings format first ──────────────────────────────────────────────
    header_row_idx = None
    for i, row in enumerate(rows):
        stripped = [v.strip() for v in row]
        if "Account Number" in stripped and "Symbol" in stripped:
            header_row_idx = i
            break

    if header_row_idx is not None:
        hdr_row   = [v.strip() for v in rows[header_row_idx]]
        headers   = [normalize_header(h) for h in hdr_row]
        raw_hdrs  = [h.lower() for h in hdr_row]
        acct_col  = raw_hdrs.index("account number") if "account number" in raw_hdrs else None
        inst_col  = raw_hdrs.index("institution")    if "institution"    in raw_hdrs else None
        ptype_col = raw_hdrs.index("product type")   if "product type"   in raw_hdrs else None

        accounts_map = {}

        for row_raw in rows[header_row_idx + 1:]:
            row = [v.strip() for v in row_raw]
            if not any(row):
                continue
            first = row[0] if row else ""
            if len(first) > 80 or not re.search(r"\d", first):
                continue
            if first.lower() in ("total", ""):
                continue
            institution = row[inst_col] if inst_col is not None and inst_col < len(row) else ""
            if any(bank in institution.lower() for bank in _MS_SKIP_INSTITUTIONS):
                continue

            raw_acct = row[acct_col] if acct_col is not None and acct_col < len(row) else "Morgan Stanley"
            acct_key = _ms_acct_key(raw_acct)

            if acct_key not in accounts_map:
                accounts_map[acct_key] = {
                    "account_id": acct_key,
                    "positions": [], "cash": 0.0, "total_equity": 0.0, "liabilities": [],
                }
            current = accounts_map[acct_key]

            row += [""] * max(0, len(headers) - len(row))
            d = {headers[j]: row[j] for j in range(len(headers))}

            sym          = d.get("symbol", "").strip().upper()
            product_type = row[ptype_col].strip().lower() if ptype_col is not None and ptype_col < len(row) else ""

            if not sym or sym == "-" or product_type in _MS_CASH_TYPES:
                val = clean_num(d.get("market_value", ""))
                if val is not None:
                    current["cash"] += val
                continue
            if product_type == "other holdings":
                continue

            pos = _build_position(d, sym)
            if pos["shares"] is not None or pos["market_value"] is not None:
                current["positions"].append(pos)

        accounts = list(accounts_map.values())
        for acct in accounts:
            if acct["total_equity"] == 0.0:
                acct["total_equity"] = round(
                    sum(p.get("market_value") or 0 for p in acct["positions"]) + acct["cash"], 2
                )
        return accounts

    # ── Fall back to Home Page format ──────────────────────────────────────────
    print(f"  INFO: {filepath.name} looks like a Home Page export — using summary parser (no cost basis)")
    return _parse_ms_xlsx_home(rows)


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
    elif brokerage == "fidelity":
        return parse_flat_csv(filepath, content, brokerage), "Fidelity"
    elif brokerage == "manual":
        return parse_flat_csv(filepath, content, brokerage), "Merrill Lynch"
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
            if f.name.startswith("~$"):   # skip Excel temp/lock files
                continue
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
        print("  Fidelity:       Accounts -> Portfolio -> Download -> CSV (Portfolio_Positions_*.csv)")
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
