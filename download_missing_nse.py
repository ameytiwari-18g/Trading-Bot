"""
Download missing historical OHLCV files for HDFC Ltd and LTIMindtree.

This version does NOT use Yahoo Finance and does NOT make the initial
GET https://www.nseindia.com/ request that was returning HTTP 403.

It downloads NSE daily bhavcopy archives directly and extracts only the
required securities. NSE documents that its historical reports include
security-wise OHLC and traded quantity data.

Run this file from the NIFTY50_Swing_Trading_Bot project root:

    python download_missing_nse.py

Outputs:
    data/HDFC.csv
    data/LTIM.csv

LTIM is combined from:
    LTIM : through 26-Feb-2026
    LTM  : 27-Feb-2026 onward
"""

from pathlib import Path
from datetime import date, timedelta
import io
import time
import zipfile
import requests
import pandas as pd


PROJECT_DIR = Path(__file__).resolve().parent
DATA_DIR = PROJECT_DIR / "data"

# NSE's current daily bhavcopy archive pattern.
# The script tries the current archives path first and then the older
# nsearchives path if necessary.
BHAVCOPY_URLS = [
    "https://nsearchives.nseindia.com/products/content/sec_bhavdata_full_{date}.csv",
    "https://archives.nseindia.com/content/historical/EQUITIES/{date}/cm{date}bhav.csv.zip",
]

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/142.0.0.0 Safari/537.36"
    ),
    "Accept": "*/*",
    "Accept-Language": "en-US,en;q=0.9",
    "Referer": "https://www.nseindia.com/",
}


def make_session():
    session = requests.Session()
    session.headers.update(HEADERS)
    return session


def daterange(start, end):
    current = start
    while current <= end:
        yield current
        current += timedelta(days=1)


def normalize_columns(df):
    df.columns = [
        str(c).strip().upper().replace(" ", "_")
        for c in df.columns
    ]
    return df


def find_col(df, candidates):
    normalized = {str(c).upper().strip(): c for c in df.columns}

    for candidate in candidates:
        candidate = candidate.upper().strip()
        if candidate in normalized:
            return normalized[candidate]

    # Flexible matching for common NSE variants.
    for col in df.columns:
        c = str(col).upper().strip()
        for candidate in candidates:
            if candidate.upper().strip() in c:
                return col

    return None


def parse_bhavcopy(content, filename):
    """
    Parse either:
      - current NSE full security CSV
      - older zipped bhavcopy CSV
    """
    raw = content

    # ZIP
    if filename.lower().endswith(".zip") or content[:2] == b"PK":
        with zipfile.ZipFile(io.BytesIO(content)) as z:
            csv_files = [
                n for n in z.namelist()
                if n.lower().endswith(".csv")
            ]
            if not csv_files:
                return None
            raw = z.read(csv_files[0])

    # Try standard CSV.
    try:
        df = pd.read_csv(io.BytesIO(raw))
    except Exception:
        try:
            df = pd.read_csv(io.BytesIO(raw), encoding="latin1")
        except Exception:
            return None

    if df.empty:
        return None

    return normalize_columns(df)


def extract_security(df, wanted_symbol):
    symbol_col = find_col(
        df,
        [
            "SYMBOL",
            "CH_SYMBOL",
            "SC_CODE",
        ],
    )

    if symbol_col is None:
        return None

    symbols = (
        df[symbol_col]
        .astype(str)
        .str.strip()
        .str.upper()
    )

    result = df.loc[symbols == wanted_symbol.upper()].copy()

    if result.empty:
        return None

    # Series column, if present, should be EQ.
    series_col = find_col(df, ["SERIES", "CH_SERIES"])

    if series_col is not None:
        eq = result[
            result[series_col].astype(str).str.strip().str.upper() == "EQ"
        ]
        if not eq.empty:
            result = eq

    date_col = find_col(
        result,
        ["TIMESTAMP", "DATE", "CH_TIMESTAMP"],
    )
    open_col = find_col(
        result,
        ["OPEN", "OPEN_PRICE", "CH_OPENING_PRICE"],
    )
    high_col = find_col(
        result,
        ["HIGH", "HIGH_PRICE", "CH_TRADE_HIGH_PRICE"],
    )
    low_col = find_col(
        result,
        ["LOW", "LOW_PRICE", "CH_TRADE_LOW_PRICE"],
    )
    close_col = find_col(
        result,
        ["CLOSE", "CLOSE_PRICE", "CH_CLOSING_PRICE"],
    )
    volume_col = find_col(
        result,
        [
            "TOTTRDQTY",
            "TOTAL_TRADED_QUANTITY",
            "TOT_TRADED_QTY",
            "VOLUME",
            "CH_TOT_TRADED_QTY",
        ],
    )

    required = [
        date_col,
        open_col,
        high_col,
        low_col,
        close_col,
        volume_col,
    ]

    if any(x is None for x in required):
        return None

    output = pd.DataFrame(
        {
            "Date": result[date_col],
            "Open": result[open_col],
            "High": result[high_col],
            "Low": result[low_col],
            "Close": result[close_col],
            "Volume": result[volume_col],
        }
    )

    output["Date"] = pd.to_datetime(
        output["Date"],
        dayfirst=True,
        errors="coerce",
    )

    for col in ["Open", "High", "Low", "Close", "Volume"]:
        output[col] = (
            output[col]
            .astype(str)
            .str.replace(",", "", regex=False)
            .str.strip()
        )
        output[col] = pd.to_numeric(
            output[col],
            errors="coerce",
        )

    output = output.dropna(
        subset=["Date", "Open", "High", "Low", "Close", "Volume"]
    )

    return output


def download_daily_file(session, trading_day):
    """
    Try the current NSE full-security daily CSV first.
    Then try the older zipped bhavcopy archive.
    """
    ddmmyyyy = trading_day.strftime("%d%m%Y")

    urls = [
        (
            BHAVCOPY_URLS[0].format(date=ddmmyyyy),
            f"sec_bhavdata_full_{ddmmyyyy}.csv",
        ),
        (
            BHAVCOPY_URLS[1].format(date=ddmmyyyy),
            f"cm{ddmmyyyy}bhav.csv.zip",
        ),
    ]

    for url, filename in urls:
        try:
            r = session.get(
                url,
                timeout=30,
            )

            if r.status_code == 200 and len(r.content) > 100:
                return r.content, filename

        except requests.RequestException:
            pass

    return None, None


def collect_symbol(
    session,
    symbol,
    start_date,
    end_date,
):
    """
    Download daily NSE files and extract one security.

    We deliberately do not assume every calendar day is a trading day.
    Missing weekends/holidays are simply skipped when no bhavcopy exists.
    """
    rows = []
    attempted = 0
    found = 0

    total_days = (end_date - start_date).days + 1

    print()
    print(
        f"Downloading {symbol}: "
        f"{start_date} -> {end_date} "
        f"({total_days} calendar days)"
    )

    for trading_day in daterange(start_date, end_date):
        attempted += 1

        content, filename = download_daily_file(
            session,
            trading_day,
        )

        if content is None:
            continue

        df = parse_bhavcopy(content, filename)

        if df is None:
            continue

        security = extract_security(df, symbol)

        if security is not None and not security.empty:
            rows.append(security)
            found += 1

        # Avoid hammering NSE.
        time.sleep(0.08)

        if attempted % 100 == 0:
            print(
                f"  Checked {attempted}/{total_days} days; "
                f"found {found} rows"
            )

    if not rows:
        return pd.DataFrame(
            columns=[
                "Date",
                "Open",
                "High",
                "Low",
                "Close",
                "Volume",
            ]
        )

    result = pd.concat(rows, ignore_index=True)

    result = (
        result
        .drop_duplicates(subset=["Date"])
        .sort_values("Date")
        .reset_index(drop=True)
    )

    return result


def save_csv(df, symbol):
    path = DATA_DIR / f"{symbol}.csv"
    df.to_csv(path, index=False)

    print(f"Saved: {path}")
    print(f"Rows : {len(df)}")

    if not df.empty:
        print(
            f"Range: "
            f"{df['Date'].min().date()} -> "
            f"{df['Date'].max().date()}"
        )

    return path


def main():
    DATA_DIR.mkdir(parents=True, exist_ok=True)

    print("=" * 70)
    print("NSE HISTORICAL DATA DOWNLOADER - BHAVCOPY VERSION")
    print("=" * 70)
    print(f"Project : {PROJECT_DIR}")
    print(f"Output  : {DATA_DIR}")
    print()

    session = make_session()

    # ------------------------------------------------------------
    # HDFC Ltd
    # ------------------------------------------------------------
    # HDFC Ltd was a NIFTY 50 constituent until July 2023.
    hdfc = collect_symbol(
        session,
        "HDFC",
        date(2020, 1, 1),
        date(2023, 7, 13),
    )

    save_csv(hdfc, "HDFC")

    # ------------------------------------------------------------
    # LTIMindtree
    # ------------------------------------------------------------
    # Historical constituent file uses LTIM.
    # NSE symbol changed from LTIM to LTM on 27-Feb-2026.
    old_ltim = collect_symbol(
        session,
        "LTIM",
        date(2023, 9, 1),
        date(2026, 2, 26),
    )

    new_ltm = collect_symbol(
        session,
        "LTM",
        date(2026, 2, 27),
        date(2026, 3, 31),
    )

    ltim = pd.concat(
        [old_ltim, new_ltm],
        ignore_index=True,
    )

    if not ltim.empty:
        ltim = (
            ltim
            .drop_duplicates(subset=["Date"])
            .sort_values("Date")
            .reset_index(drop=True)
        )

    save_csv(ltim, "LTIM")

    print()
    print("=" * 70)
    print("DOWNLOAD COMPLETE")
    print("=" * 70)

    if hdfc.empty:
        print("WARNING: HDFC.csv is empty.")
    if ltim.empty:
        print("WARNING: LTIM.csv is empty.")

    print()
    print("If both files contain data, run:")
    print("    python validate_data.py")
    print()
    print("Do NOT run download_missing_history.py again.")


if __name__ == "__main__":
    main()
