"""
Rebuild point-in-time NIFTY 50 membership for the backtest.

Primary source:
    aditya-jha/nse-historical-membership
    Derived from public NSE/Nifty Indices press releases/circulars.

This script replaces the previously corrupted monthly reconstruction.
It converts half-open effective-date intervals into a daily-date membership
table for the requested backtest period, then validates exactly 50 members
on every trading day represented by the NIFTY 50 index CSV.

Important ticker mapping:
    The source canonicalises LTIMindtree's rename chain to LTM. NSE changed
    the trading symbol from LTIM to LTM effective 2026-02-27. For historical
    dates before that change, this script maps source symbol LTM back to LTIM
    so it matches the historical Yahoo/NSE price file.

The script downloads only the membership CSV. It does not modify raw OHLCV
files.
"""

from __future__ import annotations

import io
import shutil
import urllib.request
from pathlib import Path

import pandas as pd

SOURCE_URL = (
    "https://raw.githubusercontent.com/aditya-jha/"
    "nse-historical-membership/main/index_history/data/"
    "index_membership_history.csv"
)

START_DATE = pd.Timestamp("2020-01-01")
END_DATE = pd.Timestamp("2026-03-31")

PROJECT = Path(__file__).resolve().parent
DATA = PROJECT / "data"
RAW = DATA / "raw"
OUT = DATA / "nifty50_membership.csv"
AUDIT = DATA / "nifty50_membership_intervals.csv"
SOURCE_NOTE = PROJECT / "MEMBERSHIP_SOURCE.md"

# NSE symbol change: LTIM -> LTM effective 2026-02-27.
# The source repository stores the rename chain canonically as LTM.
LTM_SYMBOL_CHANGE = pd.Timestamp("2026-02-27")


def download_source() -> pd.DataFrame:
    print("Downloading point-in-time NSE membership source...")
    req = urllib.request.Request(
        SOURCE_URL,
        headers={"User-Agent": "NIFTY50-Swing-Trading-Bot/1.0"},
    )
    with urllib.request.urlopen(req, timeout=60) as response:
        raw = response.read()

    print(f"Downloaded source: {len(raw):,} bytes")
    return pd.read_csv(io.BytesIO(raw))


def build_intervals(source: pd.DataFrame) -> pd.DataFrame:
    required = {
        "index_name",
        "symbol",
        "valid_from",
        "valid_to",
        "source",
    }
    missing = required - set(source.columns)
    if missing:
        raise ValueError(f"Source missing columns: {sorted(missing)}")

    d = source[source["index_name"].eq("Nifty 50")].copy()

    d["symbol"] = (
        d["symbol"].astype(str).str.strip().str.upper()
    )
    d["valid_from"] = pd.to_datetime(d["valid_from"], errors="coerce")
    d["valid_to"] = pd.to_datetime(d["valid_to"], errors="coerce")

    d = d.dropna(subset=["valid_from", "symbol"])
    d = d[
        (d["valid_from"] <= END_DATE)
        & (d["valid_to"].isna() | (d["valid_to"] > START_DATE))
    ].copy()

    # Clip intervals to our backtest period.
    d["valid_from"] = d["valid_from"].clip(lower=START_DATE)
    d["valid_to"] = d["valid_to"].fillna(END_DATE + pd.Timedelta(days=1))
    d["valid_to"] = d["valid_to"].clip(upper=END_DATE + pd.Timedelta(days=1))

    # Convert canonical LTM back to the actual historical trading symbol
    # used before 2026-02-27. This avoids treating the same company as a
    # missing stock during the 2023-2026 part of the backtest.
    def historical_symbol(row):
        if row["symbol"] == "LTM" and row["valid_from"] < LTM_SYMBOL_CHANGE:
            return "LTIM"
        return row["symbol"]

    d["Symbol"] = d.apply(historical_symbol, axis=1)

    d = d[
        ["valid_from", "valid_to", "Symbol", "source"]
    ].drop_duplicates()

    return d.sort_values(["valid_from", "Symbol"])


def expand_daily(intervals: pd.DataFrame, trading_dates: pd.DatetimeIndex) -> pd.DataFrame:
    records = []

    for _, row in intervals.iterrows():
        start = max(row["valid_from"], START_DATE)
        end_exclusive = min(row["valid_to"], END_DATE + pd.Timedelta(days=1))

        dates = trading_dates[
            (trading_dates >= start) & (trading_dates < end_exclusive)
        ]

        if len(dates):
            records.append(
                pd.DataFrame(
                    {
                        "Date": dates,
                        "Symbol": row["Symbol"],
                    }
                )
            )

    if not records:
        raise ValueError("No membership records overlap the trading calendar.")

    return pd.concat(records, ignore_index=True).drop_duplicates(
        subset=["Date", "Symbol"]
    )


def validate_daily(membership: pd.DataFrame, trading_dates: pd.DatetimeIndex) -> None:
    counts = membership.groupby("Date")["Symbol"].nunique()

    missing_dates = sorted(set(trading_dates) - set(counts.index))
    bad = counts[counts != 50]

    if missing_dates:
        raise ValueError(
            f"Membership missing {len(missing_dates)} trading dates. "
            f"First missing: {missing_dates[:5]}"
        )

    if not bad.empty:
        sample = ", ".join(
            f"{d.date()}={n}" for d, n in bad.head(20).items()
        )
        raise ValueError(
            "Membership validation failed: every trading day must have "
            f"exactly 50 constituents. Bad dates: {sample}"
        )

    print("Daily membership validation PASSED.")
    print(f"Trading days validated: {len(counts):,}")
    print("Constituents per trading day: exactly 50")


def validate_against_downloads(membership: pd.DataFrame) -> None:
    downloaded = {
        p.stem.upper()
        for p in RAW.glob("*.csv")
    }

    required = set(membership["Symbol"].unique())
    missing = sorted(required - downloaded)

    print("\nPrice-file compatibility:")
    print(f"  Unique membership symbols: {len(required)}")
    print(f"  Downloaded CSV files: {len(downloaded)}")
    print(f"  Missing price files: {len(missing)}")

    if missing:
        print("  Missing symbols:")
        for s in missing:
            print(f"    - {s}")

    # This is intentionally a warning, not a hard failure. Some symbols
    # may need a Yahoo ticker alias or a dedicated historical download.
    return missing


def write_source_note() -> None:
    SOURCE_NOTE.write_text(
        """# NIFTY 50 Historical Membership

## Source

Aditya Jha, *NSE Historical Membership (Point-in-Time)*:
https://github.com/aditya-jha/nse-historical-membership

The dataset is reconstructed from publicly published NSE/Nifty Indices
press releases and circulars and stores membership as effective-date
intervals. It is independent of NSE/Nifty Indices and is not an official
licensed NSE historical constituent feed.

Official NIFTY 50 reference:
https://www.niftyindices.com/indices/equity/broad-based-indices/nifty--50

## Backtest period

2020-01-01 through 2026-03-31.

## Point-in-time method

The backtester receives the constituent set applicable to each trading
date. It does not use today's NIFTY 50 composition for historical dates.

The source uses canonical rename-chain symbols. For the LTIMindtree/LTM
rename, the project converts LTM back to LTIM before 2026-02-27, because
NSE changed the trading symbol from LTIM to LTM effective 2026-02-27.

## Validation

Every trading day represented in the NIFTY 50 index price file must contain
exactly 50 unique constituents. The build is rejected if this invariant
fails.

## Known limitation

The membership source is a third-party reconstruction from public NSE
materials. Its documented coverage is strongest from 2017 onward. The
2020-2026 period used here falls inside its high-confidence coverage
window, but the dataset should still be disclosed as a reconstructed
point-in-time universe in the academic report.
""",
        encoding="utf-8",
    )


def main() -> None:
    DATA.mkdir(parents=True, exist_ok=True)

    print("=" * 70)
    print("NIFTY 50 POINT-IN-TIME MEMBERSHIP REBUILD")
    print("=" * 70)
    print(f"Backtest period: {START_DATE.date()} to {END_DATE.date()}")

    source = download_source()
    intervals = build_intervals(source)

    if intervals.empty:
        raise ValueError("No NIFTY 50 intervals found.")

    # Save an audit-friendly interval file.
    intervals.to_csv(AUDIT, index=False)

    # Use the actual NIFTY 50 index trading calendar when available.
    index_candidates = [
        RAW / "NIFTY50.csv",
        RAW / "^NSEI.csv",
    ]
    index_file = next((p for p in index_candidates if p.exists()), None)

    if index_file is None:
        raise FileNotFoundError(
            "Could not find data/raw/NIFTY50.csv. "
            "The existing index data is required to validate membership "
            "on actual trading days."
        )

    idx = pd.read_csv(index_file)
    if "Date" not in idx.columns:
        raise ValueError(f"{index_file} has no Date column.")

    trading_dates = pd.to_datetime(idx["Date"], errors="coerce").dropna()
    trading_dates = pd.DatetimeIndex(
        sorted(
            d.normalize()
            for d in trading_dates
            if START_DATE <= d.normalize() <= END_DATE
        )
    ).unique()

    print(f"Trading dates from NIFTY 50 index: {len(trading_dates):,}")

    membership = expand_daily(intervals, trading_dates)
    validate_daily(membership, trading_dates)
    missing = validate_against_downloads(membership)

    # Back up existing file only after all membership validation passes.
    if OUT.exists():
        backup = OUT.with_suffix(".csv.previous")
        shutil.copy2(OUT, backup)
        print(f"\nPrevious membership backed up to: {backup}")

    membership.to_csv(OUT, index=False)
    write_source_note()

    print("\n" + "=" * 70)
    print("SUCCESS")
    print("=" * 70)
    print(f"Membership file: {OUT}")
    print(f"Audit intervals: {AUDIT}")
    print(f"Rows: {len(membership):,}")
    print(f"Unique symbols: {membership['Symbol'].nunique()}")

    if missing:
        print(
            "\nWARNING: membership is valid, but some required price files "
            "are missing. Resolve those before the final backtest."
        )
    else:
        print("\nAll required membership symbols have price files.")


if __name__ == "__main__":
    main()
