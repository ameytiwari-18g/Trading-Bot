"""Download a reconstructed historical NIFTY 50 constituent dataset.

Source: BKKB20/nse-index-history (GitHub), which reconstructs historical
NSE index membership from NSE/Nifty Indices circulars. This is a third-party
research dataset, not an official NSE data feed.

Run from project root:
    python download_constituents.py

Output:
    data/nifty50_membership.csv
"""
from pathlib import Path
import sys
import urllib.request
import pandas as pd

URL = "https://github.com/BKKB20/nse-index-history/raw/refs/heads/main/NSE_INDEX_HISTORY_FINAL_V3.xlsx"
ROOT = Path(__file__).resolve().parent
DATA_DIR = ROOT / "data"
RAW_XLSX = DATA_DIR / "NSE_INDEX_HISTORY_FINAL_V3.xlsx"
OUT = DATA_DIR / "nifty50_membership.csv"


def norm(x):
    return str(x).strip().lower().replace(" ", "_").replace("-", "_")


def find_flat_sheet(book):
    for name, df in book.items():
        cols = {norm(c): c for c in df.columns}
        idx = next((c for n, c in cols.items() if "index" in n and ("type" in n or n == "index" or "name" in n)), None)
        sym = next((c for n, c in cols.items() if "symbol" in n or "ticker" in n), None)
        date = next((c for n, c in cols.items() if n == "date" or "effective_date" in n), None)
        if idx and sym and date:
            return name, df, date, idx, sym
    return None


def main():
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    print("Downloading historical NIFTY 50 constituent dataset...")
    print(URL)
    try:
        urllib.request.urlretrieve(URL, RAW_XLSX)
    except Exception as exc:
        print(f"ERROR: Could not download the dataset: {exc}")
        print("You can download the XLSX manually from the GitHub repository and place it at:")
        print(RAW_XLSX)
        sys.exit(1)

    print(f"Saved: {RAW_XLSX}")
    try:
        book = pd.read_excel(RAW_XLSX, sheet_name=None)
    except Exception as exc:
        print(f"ERROR: Could not read XLSX: {exc}")
        print("If this mentions openpyxl, run: python -m pip install openpyxl")
        sys.exit(1)

    found = find_flat_sheet(book)
    if not found:
        print("ERROR: Could not automatically identify the FLAT_LIST sheet.")
        print("Sheets found:", list(book))
        for name, df in book.items():
            print(f"  {name}: {list(df.columns)[:12]}")
        sys.exit(1)

    sheet, df, date_col, index_col, symbol_col = found
    print(f"Using sheet: {sheet}")
    print(f"Columns: date={date_col}, index={index_col}, symbol={symbol_col}")

    out = df[[date_col, index_col, symbol_col]].copy()
    out.columns = ["Date", "Index", "Symbol"]
    out["Date"] = pd.to_datetime(out["Date"], errors="coerce")
    out["Index"] = out["Index"].astype(str).str.strip()
    out["Symbol"] = out["Symbol"].astype(str).str.strip().str.upper()
    out = out[out["Index"].str.replace("-", " ", regex=False).str.replace("_", " ", regex=False).str.contains("NIFTY 50", case=False, na=False)]
    out = out.dropna(subset=["Date", "Symbol"])

    # Normalize common NSE/yfinance naming differences.
    aliases = {
        "M&M": "M&M", "M&MFIN": "M&M", "HDFCBANK": "HDFCBANK",
        "ADANIENT": "ADANIENT", "ADANIPORTS": "ADANIPORTS",
    }
    out["Symbol"] = out["Symbol"].map(lambda x: aliases.get(x, x))
    out["Month"] = out["Date"].dt.to_period("M").astype(str)
    out = out[["Month", "Symbol"]].drop_duplicates().sort_values(["Month", "Symbol"])
    out.to_csv(OUT, index=False)

    print(f"NIFTY 50 membership rows: {len(out):,}")
    print(f"Month range: {out['Month'].min()} to {out['Month'].max()}")
    print(f"Output: {OUT}")
    print("NOTE: Membership is monthly, so the backtest will use the month's reconstructed universe.")


if __name__ == "__main__":
    main()
