# How to Export Your Schwab Positions

## Step 1 — Export from Schwab

1. Log in to Schwab → **Accounts** tab
2. Click **Positions**
3. Click the **Export** icon (top-right corner, looks like a page with a down-arrow)
4. Save the file (it will be named something like `Positions_XXXX-1234_DATE.csv`)

> If you have multiple accounts, repeat for each account — or use the "All Accounts" view before exporting to get everything in one file.

## Step 2 — Drop the CSV here

Move or copy the downloaded CSV file into this folder:

```
portfolio/input/
```

## Step 3 — Run the parser

From the project root, run:

```bash
python parse_schwab.py
```

This generates:
- `portfolio/portfolio.json` — machine-readable, used by Claude skills
- `portfolio/portfolio.md` — human-readable summary

## Step 4 — Run your skills

```
/trade guidance     ← profit-taking + income recommendations
/trade portfolio    ← full allocation analysis + rebalancing
```

---

## How often should I update?

Re-export and re-run `parse_schwab.py` whenever you:
- Make trades
- Want fresh analysis (weekly is a good cadence)
- See a "data is stale" warning from a skill

The skills will warn you if your data is more than 3 days old.
