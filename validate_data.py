from pathlib import Path
import pandas as pd

RAW_DIR = Path("data/raw")

REQUIRED_COLUMNS = {"Date", "Open", "High", "Low", "Close", "Volume"}

print("=" * 70)
print("NIFTY 50 SWING BOT - DATA VALIDATION")
print("=" * 70)

files = sorted(RAW_DIR.glob("*.csv"))

if not files:
    print("ERROR: No CSV files found in data/raw/")
    raise SystemExit(1)

print(f"\nCSV files found: {len(files)}")

total_rows = 0
problems = []

for file in files:
    try:
        df = pd.read_csv(file)

        # Check required columns
        missing_columns = REQUIRED_COLUMNS - set(df.columns)

        if missing_columns:
            problems.append(
                f"{file.name}: missing columns {sorted(missing_columns)}"
            )
            continue

        # Parse dates
        df["Date"] = pd.to_datetime(df["Date"], errors="coerce")

        if df["Date"].isna().any():
            problems.append(f"{file.name}: invalid dates")

        # Duplicate dates
        duplicate_dates = df["Date"].duplicated().sum()

        if duplicate_dates > 0:
            problems.append(
                f"{file.name}: {duplicate_dates} duplicate dates"
            )

        # Missing OHLCV
        missing_values = df[
            ["Open", "High", "Low", "Close", "Volume"]
        ].isna().sum().sum()

        if missing_values > 0:
            problems.append(
                f"{file.name}: {missing_values} missing OHLCV values"
            )

        # OHLC sanity checks
        invalid_ohlc = (
            (df["High"] < df["Low"]) |
            (df["High"] < df["Open"]) |
            (df["High"] < df["Close"]) |
            (df["Low"] > df["Open"]) |
            (df["Low"] > df["Close"])
        ).sum()

        if invalid_ohlc > 0:
            problems.append(
                f"{file.name}: {invalid_ohlc} invalid OHLC rows"
            )

        # Non-positive prices
        invalid_prices = (
            (df["Open"] <= 0) |
            (df["High"] <= 0) |
            (df["Low"] <= 0) |
            (df["Close"] <= 0)
        ).sum()

        if invalid_prices > 0:
            problems.append(
                f"{file.name}: {invalid_prices} non-positive prices"
            )

        # Negative volume
        negative_volume = (df["Volume"] < 0).sum()

        if negative_volume > 0:
            problems.append(
                f"{file.name}: {negative_volume} negative volume rows"
            )

        total_rows += len(df)

    except Exception as e:
        problems.append(f"{file.name}: ERROR - {e}")


print(f"Total rows checked: {total_rows:,}")

print("\n" + "-" * 70)

if problems:
    print(f"PROBLEMS FOUND: {len(problems)}")
    print("-" * 70)

    for problem in problems:
        print("  -", problem)

else:
    print("NO DATA-QUALITY PROBLEMS FOUND.")

print("\n" + "=" * 70)
print("Validation complete.")
print("=" * 70)