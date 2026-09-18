"""
Rebuild point-in-time NIFTY 50 membership for the swing-trading backtest.

Source:
    vishalvx/nifty-indices-datasets
    https://github.com/vishalvx/nifty-indices-datasets

That repository states that its NIFTY 50 history is reconstructed monthly
from public Nifty Indices/NSE reconstitution material. It is used here as a
practical historical-universe source, not as an official NSE data feed.

The script deliberately validates the result before replacing the existing
membership file. It expects exactly 50 unique constituents for every month
in the requested backtest period.
"""

from __future__ import annotations

import io
import re
import shutil
import tempfile
import urllib.request
import zipfile
from pathlib import Path

import pandas as pd


REPO_ZIP = (
    "https://github.com/vishalvx/nifty-indices-datasets/"
    "archive/refs/heads/main.zip"
)

START_MONTH = "2020-01"
END_MONTH = "2026-03"

PROJECT_DIR = Path(__file__).resolve().parent
DATA_DIR = PROJECT_DIR / "data"
OUT_FILE = DATA_DIR / "nifty50_membership.csv"
SOURCE_FILE = PROJECT_DIR / "MEMBERSHIP_SOURCE.md"


def normalise_symbol(value) -> str:
    s = str(value).strip().upper()
    s = re.sub(r"\s+", "", s)
    return s


def find_nifty50_csv(root: Path) -> Path:
    candidates = []
    for p in root.rglob("*.csv"):
        name = p.name.lower().replace(" ", "").replace("-", "")
        if "nifty50" in name:
            candidates.append(p)

    if not candidates:
        raise FileNotFoundError(
            "Could not find a CSV containing 'nifty50' in the downloaded repository."
        )

    # Prefer files under a datasets directory.
    candidates.sort(
        key=lambda p: (
            0 if "datasets" in {x.lower() for x in p.parts} else 1,
            len(p.parts),
            len(p.name),
        )
    )
    return candidates[0]


def convert_to_long(df: pd.DataFrame) -> pd.DataFrame:
    cols = {str(c).strip().lower(): c for c in df.columns}

    # Case 1: already long format.
    date_col = next(
        (cols[k] for k in ("month", "date", "effective_date", "effective") if k in cols),
        None,
    )
    symbol_col = next(
        (cols[k] for k in ("symbol", "ticker", "stock") if k in cols),
        None,
    )

    if date_col is not None and symbol_col is not None:
        out = df[[date_col, symbol_col]].copy()
        out.columns = ["Month", "Symbol"]
        out["Month"] = pd.to_datetime(out["Month"], errors="coerce").dt.to_period("M").astype(str)
        out["Symbol"] = out["Symbol"].map(normalise_symbol)
        return out.dropna(subset=["Month", "Symbol"])

    # Case 2: wide binary matrix: first/date column + ticker columns.
    possible_date = next(
        (c for c in df.columns if str(c).strip().lower() in
         {"month", "date", "effective_date", "timestamp"}),
        None,
    )
    if possible_date is None:
        possible_date = df.columns[0]

    dates = pd.to_datetime(df[possible_date], errors="coerce")
    if dates.notna().mean() < 0.80:
        # Sometimes the index/date is the CSV index.
        first = df.iloc[:, 0]
        dates2 = pd.to_datetime(first, errors="coerce")
        if dates2.notna().mean() >= 0.80:
            dates = dates2
        else:
            raise ValueError(
                "Could not identify a date/month column in the NIFTY 50 dataset."
            )

    data_cols = [c for c in df.columns if c != possible_date]

    records = []
    for c in data_cols:
        values = pd.to_numeric(df[c], errors="coerce")
        active = values.fillna(0).astype(float) != 0
        if active.any():
            records.append(
                pd.DataFrame(
                    {
                        "Month": dates[active].dt.to_period("M").astype(str),
                        "Symbol": normalise_symbol(c),
                    }
                )
            )

    if not records:
        raise ValueError("Wide-format dataset contained no active constituent records.")

    return pd.concat(records, ignore_index=True)


def validate_membership(df: pd.DataFrame) -> None:
    df = df.copy()
    df["Month"] = pd.to_datetime(df["Month"], errors="coerce").dt.to_period("M").astype(str)
    df["Symbol"] = df["Symbol"].map(normalise_symbol)

    df = df[
        (df["Month"] >= START_MONTH) &
        (df["Month"] <= END_MONTH)
    ].drop_duplicates()

    if df.empty:
        raise ValueError("No NIFTY 50 membership records remain in the backtest period.")

    counts = df.groupby("Month")["Symbol"].nunique()

    expected_months = pd.period_range(START_MONTH, END_MONTH, freq="M").astype(str)
    missing_months = sorted(set(expected_months) - set(counts.index))

    if missing_months:
        raise ValueError(
            "Membership dataset is missing months: " + ", ".join(missing_months)
        )

    bad = counts[counts != 50]
    if not bad.empty:
        details = ", ".join(f"{m}={n}" for m, n in bad.items())
        raise ValueError(
            "NIFTY 50 membership validation failed. "
            f"Every month must contain exactly 50 constituents. Found: {details}"
        )

    print("Membership validation PASSED.")
    print(f"Months: {len(counts)} ({counts.index.min()} to {counts.index.max()})")
    print(f"Rows: {len(df):,}")
    print(f"Unique symbols: {df['Symbol'].nunique()}")
    print(f"Constituents per month: {counts.min()}–{counts.max()}")


def write_source_note() -> None:
    text = f"""# Historical NIFTY 50 Membership Source

## Purpose

This project uses a point-in-time NIFTY 50 constituent universe so that the
backtest does not apply today's constituents to historical periods.

## Source

Historical monthly NIFTY 50 constituent reconstruction:

https://github.com/vishalvx/nifty-indices-datasets

The repository states that its NIFTY 50 dataset is reconstructed from 2008
to present using public Nifty Indices media releases and NSE exchange
circulars. It describes the data as a reconstructed/binary approximation,
not an official NSE data feed.

Official NSE/Nifty references:

- NIFTY 50: https://www.nseindia.com/static/products-services/indices-nifty50-index
- NIFTY 50 page: https://www.niftyindices.com/indices/equity/broad-based-indices/nifty--50
- Reconstitution calendar:
  https://www.niftyindices.com/resources/index-rebalancing-schedule

## Backtest period

{START_MONTH} through {END_MONTH}.

## Validation rule

Every month in the backtest period must contain exactly 50 unique NIFTY 50
constituents. The generated file is rejected if this invariant fails.

## Important limitation

The historical universe is reconstructed from public historical
reconstitution information rather than being an official licensed NSE
historical constituent feed. This provenance should be disclosed in the
academic report/viva.
"""
    SOURCE_FILE.write_text(text, encoding="utf-8")


def main() -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)

    print("=" * 70)
    print("REBUILDING POINT-IN-TIME NIFTY 50 MEMBERSHIP")
    print("=" * 70)
    print(f"Backtest period: {START_MONTH} to {END_MONTH}")
    print("Downloading reconstructed historical universe source...")

    with tempfile.TemporaryDirectory() as td:
        temp = Path(td)
        zip_bytes = urllib.request.urlopen(REPO_ZIP, timeout=60).read()

        with zipfile.ZipFile(io.BytesIO(zip_bytes)) as z:
            z.extractall(temp)

        source_csv = find_nifty50_csv(temp)
        print(f"Source CSV: {source_csv}")

        raw = pd.read_csv(source_csv)
        membership = convert_to_long(raw)

    membership["Month"] = pd.to_datetime(
        membership["Month"], errors="coerce"
    ).dt.to_period("M").astype(str)
    membership["Symbol"] = membership["Symbol"].map(normalise_symbol)

    membership = membership[
        (membership["Month"] >= START_MONTH) &
        (membership["Month"] <= END_MONTH)
    ].drop_duplicates().sort_values(["Month", "Symbol"])

    validate_membership(membership)

    # Only replace the old file after validation passes.
    if OUT_FILE.exists():
        backup = OUT_FILE.with_suffix(".csv.previous")
        shutil.copy2(OUT_FILE, backup)
        print(f"Previous membership file backed up to: {backup}")

    membership.to_csv(OUT_FILE, index=False)
    write_source_note()

    print("\nSaved corrected membership:")
    print(f"  {OUT_FILE}")
    print(f"  {SOURCE_FILE}")
    print("\nThe old corrupted reconstruction was NOT used.")
    print("Next step: run validate_membership.py before the backtest.")


if __name__ == "__main__":
    main()
