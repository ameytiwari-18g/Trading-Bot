"""Download historical OHLCV data for the NIFTY 50 backtest universe.

Preferred workflow:
    1) python download_constituents.py
    2) python download_data.py
    3) python src/run_bot.py --data-dir data/raw --output-dir outputs

The downloader reads data/nifty50_membership.csv when present, so the
historical stock universe is based on reconstructed NIFTY 50 membership
rather than today's 50 stocks only.
"""
from pathlib import Path
import sys
import time
import urllib.request
import pandas as pd

try:
    import yfinance as yf
except ImportError:
    print("yfinance is not installed. Run: python -m pip install yfinance")
    sys.exit(1)

START = "2020-01-01"
END = None
PROJECT_ROOT = Path(__file__).resolve().parent
RAW_DIR = PROJECT_ROOT / "data" / "raw"
MEMBERSHIP_FILE = PROJECT_ROOT / "data" / "nifty50_membership.csv"
RAW_DIR.mkdir(parents=True, exist_ok=True)

MEMBERSHIP_URL = "https://github.com/BKKB20/nse-index-history/raw/refs/heads/main/NSE_INDEX_HISTORY_FINAL_V3.xlsx"
MEMBERSHIP_XLSX = PROJECT_ROOT / "data" / "NSE_INDEX_HISTORY_FINAL_V3.xlsx"


# Yahoo Finance ticker aliases for common historical NSE symbol conventions.
# These are ticker-format mappings, not attempts to replace a company's
# historical identity. The saved CSV keeps the membership symbol as filename.
TICKER_ALIASES = {
    "M&M": "M&M.NS",
    "M_M": "M&M.NS",
    "BAJAJ-AUTO": "BAJAJ-AUTO.NS",
    "MCDOWELL-N": "MCDOWELL-N.NS",
    "MCDOWELL-N": "MCDOWELL-N.NS",
    "LUPIN": "LUPIN.NS",
    "HDFC": "HDFC.NS",
    "HDFC LTD": "HDFC.NS",
    "HDFC LTD.": "HDFC.NS",
    "PVR": "PVR.NS",
    "INOXLEISUR": "INOXLEISUR.NS",
    "INFRATEL": "INFRATEL.NS",
    "INDUSINDBK": "INDUSINDBK.NS",
    "ZEEL": "ZEEL.NS",
    "VEDL": "VEDL.NS",
    "TATAMOTORS": "TATAMOTORS.NS",
}

# If membership data is unavailable, retain a fallback current universe.
CURRENT_NIFTY50 = [
    "ADANIENT", "ADANIPORTS", "APOLLOHOSP", "ASIANPAINT", "AXISBANK",
    "BAJAJ-AUTO", "BAJFINANCE", "BAJAJFINSV", "BEL", "BHARTIARTL",
    "CIPLA", "COALINDIA", "DRREDDY", "EICHERMOT", "ETERNAL", "GRASIM",
    "HCLTECH", "HDFCBANK", "HDFCLIFE", "HEROMOTOCO", "HINDALCO",
    "HINDUNILVR", "ICICIBANK", "INDUSINDBK", "INFY", "ITC", "JIOFIN",
    "JSWSTEEL", "KOTAKBANK", "LT", "M&M", "MARUTI", "MAXHEALTH",
    "NESTLEIND", "NTPC", "ONGC", "POWERGRID", "RELIANCE", "SBILIFE",
    "SBIN", "SHRIRAMFIN", "SUNPHARMA", "TATACONSUM", "TATASTEEL", "TCS",
    "TECHM", "TITAN", "TRENT", "ULTRACEMCO", "WIPRO",
]


def clean_download(df):
    if df is None or df.empty:
        return None
    if getattr(df.columns, "nlevels", 1) > 1:
        df.columns = [c[0] if isinstance(c, tuple) else c for c in df.columns]
    required = ["Open", "High", "Low", "Close", "Volume"]
    missing = [c for c in required if c not in df.columns]
    if missing:
        raise ValueError(f"Missing columns: {missing}")
    out = df[required].copy().reset_index()
    out["Date"] = pd.to_datetime(out["Date"], errors="coerce").dt.tz_localize(None)
    out["Date"] = out["Date"].dt.strftime("%Y-%m-%d")
    for col in required:
        out[col] = pd.to_numeric(out[col], errors="coerce")
    out = out.dropna(subset=required)
    return out.drop_duplicates("Date").sort_values("Date")


def yahoo_ticker(symbol):
    symbol = str(symbol).strip().upper()
    if symbol.endswith(".NS"):
        return symbol
    return TICKER_ALIASES.get(symbol, symbol + ".NS")


def ensure_membership_file():
    """Ensure the reconstructed monthly membership CSV exists.

    If the CSV is missing, download the public reconstruction workbook and
    create the CSV automatically. This keeps the entire data-prep workflow
    to a single command.
    """
    if MEMBERSHIP_FILE.exists():
        return True

    print("Historical membership file not found.")
    print("Automatically downloading the reconstructed NIFTY 50 membership dataset...")
    DATA_DIR = PROJECT_ROOT / "data"
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    try:
        urllib.request.urlretrieve(MEMBERSHIP_URL, MEMBERSHIP_XLSX)
        print(f"Saved membership workbook: {MEMBERSHIP_XLSX}")
        book = pd.read_excel(MEMBERSHIP_XLSX, sheet_name=None)

        def norm(x):
            return str(x).strip().lower().replace(" ", "_").replace("-", "_")

        found = None
        for sheet, df in book.items():
            cols = {norm(c): c for c in df.columns}
            date_col = next((c for n, c in cols.items() if n == "date" or "effective_date" in n), None)
            index_col = next((c for n, c in cols.items() if n == "index" or "index_name" in n or "index_type" in n), None)
            symbol_col = next((c for n, c in cols.items() if "symbol" in n or "ticker" in n), None)
            if date_col and index_col and symbol_col:
                found = (sheet, df, date_col, index_col, symbol_col)
                break

        if not found:
            raise ValueError("Could not identify the historical membership table in the workbook.")

        sheet, df, date_col, index_col, symbol_col = found
        out = df[[date_col, index_col, symbol_col]].copy()
        out.columns = ["Date", "Index", "Symbol"]
        out["Date"] = pd.to_datetime(out["Date"], errors="coerce")
        out["Index"] = out["Index"].astype(str).str.strip()
        out["Symbol"] = out["Symbol"].astype(str).str.strip().str.upper()
        out = out[out["Index"].str.replace("-", " ", regex=False).str.replace("_", " ", regex=False).str.contains("NIFTY 50", case=False, na=False)]
        out = out.dropna(subset=["Date", "Symbol"])
        out["Month"] = out["Date"].dt.to_period("M").astype(str)
        out = out[["Month", "Symbol"]].drop_duplicates().sort_values(["Month", "Symbol"])
        out.to_csv(MEMBERSHIP_FILE, index=False)
        print(f"Created membership file: {MEMBERSHIP_FILE}")
        print(f"Membership rows: {len(out):,}; unique symbols: {out['Symbol'].nunique():,}")
        return True
    except Exception as exc:
        print(f"ERROR: Could not create historical membership file: {exc}")
        return False


def historical_symbols():
    if not ensure_membership_file():
        raise RuntimeError("Historical NIFTY 50 membership could not be obtained. Aborting instead of silently using the current universe.")
    membership = pd.read_csv(MEMBERSHIP_FILE)
    if "Symbol" not in membership.columns:
        raise ValueError("Membership file must contain a 'Symbol' column.")
    # Only symbols appearing in the backtest period are needed.
    if "Month" in membership.columns:
        membership["Month"] = membership["Month"].astype(str)
        membership = membership[(membership["Month"] >= START[:7])]
    symbols = sorted({str(s).strip().upper() for s in membership["Symbol"].dropna() if str(s).strip()})
    if not symbols:
        raise ValueError("No historical NIFTY 50 symbols found for the backtest period.")
    return symbols

def download_symbol(symbol):
    ticker = yahoo_ticker(symbol)
    print(f"Downloading {symbol} ({ticker}) ...")
    df = yf.download(
        ticker, start=START, end=END, interval="1d",
        auto_adjust=False, progress=False, threads=False,
    )
    cleaned = clean_download(df)
    if cleaned is None or cleaned.empty:
        print(f"  FAILED: no data returned")
        return False
    # Preserve the membership symbol as the filename/key used by the backtester.
    filename = symbol.replace("/", "_") + ".csv"
    cleaned.to_csv(RAW_DIR / filename, index=False)
    print(f"  OK: {len(cleaned):,} rows -> data/raw/{filename}")
    return True


def download_index():
    print("Downloading NIFTY 50 index (^NSEI) ...")
    df = yf.download(
        "^NSEI", start=START, end=END, interval="1d",
        auto_adjust=False, progress=False, threads=False,
    )
    cleaned = clean_download(df)
    if cleaned is None or cleaned.empty:
        raise RuntimeError("No NIFTY 50 index data returned.")
    cleaned.to_csv(RAW_DIR / "NIFTY50.csv", index=False)
    print(f"  OK: {len(cleaned):,} rows -> data/raw/NIFTY50.csv")


def main():
    print("=" * 70)
    print("NIFTY 50 SWING TRADING BOT - HISTORICAL DATA DOWNLOADER")
    print("=" * 70)
    print(f"Date range: {START} to latest available")
    print(f"Membership file: {MEMBERSHIP_FILE}")
    print(f"Output: {RAW_DIR}")
    print()

    symbols = historical_symbols()
    print(f"Historical membership universe (2020 onward): {len(symbols)} unique symbols")
    print("This downloads every symbol appearing in the reconstructed NIFTY 50 membership file during the backtest period.")
    print()

    try:
        download_index()
    except Exception as exc:
        print(f"INDEX FAILED: {exc}")

    ok, failed = 0, 0
    failed_symbols = []
    for symbol in symbols:
        try:
            if download_symbol(symbol):
                ok += 1
            else:
                failed += 1
                failed_symbols.append(symbol)
        except Exception as exc:
            failed += 1
            failed_symbols.append(symbol)
            print(f"  FAILED: {exc}")
        time.sleep(0.15)

    print()
    print("=" * 70)
    print(f"Finished. Successful: {ok} | Failed: {failed}")
    if failed_symbols:
        print("Failed symbols:")
        print(", ".join(failed_symbols))
    print(f"Files are in: {RAW_DIR}")
    print("=" * 70)
    print("NOTE: Failed/delisted symbols will be reviewed before the final backtest;")
    print("do not interpret a partial download as a final survivorship-bias-free dataset.")


if __name__ == "__main__":
    main()
