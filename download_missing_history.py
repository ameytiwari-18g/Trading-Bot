import time
from pathlib import Path
import yfinance as yf
import pandas as pd

RAW = Path("data/raw")
RAW.mkdir(parents=True, exist_ok=True)

# Historical NSE symbols required by the point-in-time membership file.
# HDFC = Housing Development Finance Corporation Ltd (merged into HDFC Bank
# effective 2023-07-01). LTIM = LTIMindtree, whose NSE symbol changed to LTM
# only on 2026-02-27, after most of our backtest.
MISSING = {
    "HDFC": "HDFC.NS",
    "LTIM": "LTIM.NS",
}

START = "2020-01-01"
END = "2026-04-01"

print("=" * 70)
print("DOWNLOAD MISSING HISTORICAL NIFTY 50 PRICE FILES")
print("=" * 70)

for symbol, ticker in MISSING.items():
    out = RAW / f"{symbol}.csv"
    print(f"\nDownloading {symbol} ({ticker}) ...")

    success = False

    # Retry because Yahoo can intermittently return DNS/crumb errors.
    for attempt in range(1, 4):
        try:
            df = yf.download(
                ticker,
                start=START,
                end=END,
                auto_adjust=False,
                progress=False,
                threads=False,
            )

            if isinstance(df.columns, pd.MultiIndex):
                df.columns = df.columns.get_level_values(0)

            df = df.reset_index()

            required = {"Date", "Open", "High", "Low", "Close", "Volume"}
            if not required.issubset(df.columns) or len(df) < 100:
                raise ValueError(
                    f"Insufficient/invalid data: rows={len(df)}, "
                    f"columns={list(df.columns)}"
                )

            df = df[["Date", "Open", "High", "Low", "Close", "Volume"]]
            df.to_csv(out, index=False)

            print(
                f"  OK: {len(df):,} rows -> {out}"
            )
            print(
                f"  Range: {df['Date'].min()} to {df['Date'].max()}"
            )
            success = True
            break

        except Exception as e:
            print(f"  Attempt {attempt}/3 failed: {e}")
            if attempt < 3:
                time.sleep(5)

    if not success:
        print(f"  FAILED: {symbol}")

print("\n" + "=" * 70)
print("Done.")
print("Run validate_data.py after both files are downloaded.")
print("=" * 70)
