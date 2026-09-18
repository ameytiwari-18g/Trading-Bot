from dataclasses import dataclass
import pandas as pd
import config
from .strategy import signal_row, score_signal

TOTAL_COST_BPS = config.SLIPPAGE_BPS + config.BROKERAGE_BPS + config.OTHER_COST_BPS


def buy_price(p):
    return p * (1 + TOTAL_COST_BPS / 10000)


def sell_price(p):
    return p * (1 - TOTAL_COST_BPS / 10000)


@dataclass
class Position:
    symbol: str
    entry_date: pd.Timestamp
    entry_price: float
    shares: int
    initial_stop: float
    highest_close: float
    risk_per_share: float
    entry_equity: float
    entry_cost: float


def _build_membership_lookup(membership):
    """
    Supports both the old monthly membership file and the new daily file.

    New file expected:
        Date,Symbol

    Older file may contain:
        Month,Symbol

    Returns:
        ("daily", lookup) or ("monthly", lookup)
    """
    if membership is None or membership.empty:
        return None, {}

    mm = membership.copy()
    mm.columns = [str(c).strip() for c in mm.columns]

    # New validated membership file: one row per
    # trading date x constituent.
    if "Date" in mm.columns and "Symbol" in mm.columns:
        mm["Date"] = pd.to_datetime(mm["Date"], errors="coerce")
        mm["Symbol"] = mm["Symbol"].astype(str).str.strip().str.upper()
        mm = mm.dropna(subset=["Date"])

        lookup = mm.groupby("Date")["Symbol"].apply(set).to_dict()
        return "daily", lookup

    # Backward compatibility with the previous monthly format.
    if "Month" in mm.columns and "Symbol" in mm.columns:
        mm["Month"] = mm["Month"].astype(str)
        mm["Symbol"] = mm["Symbol"].astype(str).str.strip().str.upper()

        lookup = mm.groupby("Month")["Symbol"].apply(set).to_dict()
        return "monthly", lookup

    raise ValueError(
        "Unsupported membership file format. Expected columns "
        "'Date, Symbol' (daily) or 'Month, Symbol' (monthly)."
    )


def _is_active(sym, date, membership_type, membership_lookup):
    if not membership_lookup:
        return True

    sym = str(sym).strip().upper()
    date = pd.Timestamp(date)

    if membership_type == "daily":
        return sym in membership_lookup.get(date, set())

    if membership_type == "monthly":
        month = date.to_period("M").strftime("%Y-%m")
        return sym in membership_lookup.get(month, set())

    return True


def backtest(data, market=None, membership=None):
    symbols = [s for s in data if s != "NIFTY50"]

    all_date_sets = [set(df["Date"]) for df in data.values() if not df.empty]
    dates = sorted(set().union(*all_date_sets)) if all_date_sets else []

    if not dates:
        raise ValueError("No dates found")

    membership_type, membership_lookup = _build_membership_lookup(membership)

    if membership_type:
        print(f"Membership mode: {membership_type}")

    market_regime = {}

    if market is not None and not market.empty:
        m = market.set_index("Date").sort_index().copy()
        m["EMA50"] = m["Close"].ewm(
            span=config.MARKET_REGIME_EMA,
            adjust=False
        ).mean()
        market_regime = (m["Close"] > m["EMA50"]).to_dict()

    positions = {}
    trades = []
    equity_rows = []
    cash = config.INITIAL_CAPITAL
    pending = {}

    for i, date in enumerate(dates):

        # ------------------------------------------------------------
        # ENTER SIGNALS GENERATED ON PREVIOUS SESSION
        # ------------------------------------------------------------
        for sym, row in list(pending.pop(date, [])):

            if sym in positions or len(positions) >= config.MAX_POSITIONS:
                continue

            # A position can only be entered if the stock is still an
            # active NIFTY 50 constituent on the entry date.
            if not _is_active(
                sym,
                date,
                membership_type,
                membership_lookup
            ):
                continue

            px = float(row["Open"])

            if px <= 0:
                continue

            position_values = 0.0

            for p in positions.values():
                current = data[p.symbol]
                rr = current[current["Date"] == date]

                if not rr.empty:
                    position_values += (
                        p.shares * float(rr.iloc[0]["Close"])
                    )

            equity = cash + position_values

            atr = float(row["ATR14"])

            if pd.isna(atr) or atr <= 0:
                continue

            stop = px - config.INITIAL_ATR_MULTIPLIER * atr
            risk_per_share = px - stop

            # Risk is 1% of CURRENT equity.
            risk_budget = equity * config.RISK_PER_TRADE

            shares = int(
                min(
                    risk_budget / risk_per_share,
                    (equity * config.MAX_POSITION_PCT) / px
                )
            )

            if shares < 1:
                continue

            cost = shares * buy_price(px)

            if cost > cash:
                shares = int(cash / buy_price(px))
                cost = shares * buy_price(px)

            if shares < 1:
                continue

            cash -= cost

            positions[sym] = Position(
                sym,
                date,
                buy_price(px),
                shares,
                stop,
                float(row["Close"]),
                risk_per_share,
                equity,
                cost
            )

        # ------------------------------------------------------------
        # MANAGE EXISTING POSITIONS
        # ------------------------------------------------------------
        for sym, p in list(positions.items()):

            df = data[sym]
            rr = df[df["Date"] == date]

            # Some stocks do not have a candle on every union date.
            if rr.empty:
                continue

            row = rr.iloc[0]

            close = float(row["Close"])
            high = float(row["High"])
            low = float(row["Low"])

            p.highest_close = max(p.highest_close, close)

            atr = (
                float(row["ATR14"])
                if pd.notna(row["ATR14"])
                else 0
            )

            trail_active = (
                close
                >= p.entry_price
                + config.TRAIL_ACTIVATION_R * p.risk_per_share
            )

            stop = p.initial_stop

            if trail_active and atr > 0:
                stop = max(
                    p.initial_stop,
                    p.highest_close
                    - config.TRAILING_ATR_MULTIPLIER * atr
                )

            exit_reason = None
            exit_raw = None

            # Conservative same-day ordering:
            # if the low breached the stop, assume stop was hit.
            if low <= stop:
                exit_reason = "Stop/Trailing Stop"
                exit_raw = stop

            elif float(row["EMA20"]) <= float(row["EMA50"]):
                exit_reason = "EMA Exit"
                exit_raw = close

            elif float(row["RSI14"]) < 45:
                exit_reason = "RSI Exit"
                exit_raw = close

            else:
                held_sessions = (
                    len(
                        df[
                            (df["Date"] >= p.entry_date)
                            & (df["Date"] <= date)
                        ]
                    ) - 1
                )

                if held_sessions >= config.MAX_HOLDING_SESSIONS:
                    exit_reason = "Max Holding"
                    exit_raw = close

            if exit_reason:

                ep = sell_price(exit_raw)
                proceeds = p.shares * ep
                cash += proceeds
                pnl = proceeds - p.entry_cost

                holding_sessions = (
                    len(
                        df[
                            (df["Date"] >= p.entry_date)
                            & (df["Date"] <= date)
                        ]
                    ) - 1
                )

                trades.append(
                    {
                        "Symbol": sym,
                        "EntryDate": p.entry_date,
                        "ExitDate": date,
                        "EntryPrice": p.entry_price,
                        "ExitPrice": ep,
                        "Shares": p.shares,
                        "PnL": pnl,
                        "ReturnPct": pnl / p.entry_cost,
                        "HoldingSessions": holding_sessions,
                        "ExitReason": exit_reason,
                    }
                )

                del positions[sym]

        # ------------------------------------------------------------
        # GENERATE TODAY'S EOD SIGNALS FOR NEXT TRADING DAY
        # ------------------------------------------------------------
        if i + 1 < len(dates):

            next_date = dates[i + 1]
            candidates = []

            regime_ok = (
                True
                if not config.USE_MARKET_REGIME_FILTER
                else market_regime.get(date, False)
            )

            if regime_ok:

                for sym in symbols:

                    if sym in positions:
                        continue

                    # Daily historical NIFTY 50 membership filter.
                    if not _is_active(
                        sym,
                        date,
                        membership_type,
                        membership_lookup
                    ):
                        continue

                    rr = data[sym][data[sym]["Date"] == date]

                    if rr.empty:
                        continue

                    row = rr.iloc[0]

                    if signal_row(row):
                        candidates.append(
                            (
                                score_signal(row),
                                sym,
                                row
                            )
                        )

                candidates.sort(
                    reverse=True,
                    key=lambda z: z[0]
                )

                pending[next_date] = [
                    (sym, row)
                    for _, sym, row
                    in candidates[:config.MAX_POSITIONS]
                ]

        # ------------------------------------------------------------
        # DAILY EQUITY
        # ------------------------------------------------------------
        market_value = 0.0

        for p in positions.values():
            rr = data[p.symbol][
                data[p.symbol]["Date"] == date
            ]

            if not rr.empty:
                market_value += (
                    p.shares * float(rr.iloc[0]["Close"])
                )

        equity_rows.append(
            {
                "Date": date,
                "Cash": cash,
                "PositionsValue": market_value,
                "Equity": cash + market_value,
            }
        )

    # ------------------------------------------------------------
    # FORCE CLOSE REMAINING POSITIONS AT FINAL CLOSE
    # ------------------------------------------------------------
    if dates:

        date = dates[-1]

        for sym, p in list(positions.items()):

            rr = data[sym][data[sym]["Date"] == date]

            if rr.empty:
                continue

            row = rr.iloc[0]

            ep = sell_price(float(row["Close"]))
            proceeds = p.shares * ep
            cash += proceeds
            pnl = proceeds - p.entry_cost

            holding_sessions = (
                len(
                    data[sym][
                        (data[sym]["Date"] >= p.entry_date)
                        & (data[sym]["Date"] <= date)
                    ]
                ) - 1
            )

            trades.append(
                {
                    "Symbol": sym,
                    "EntryDate": p.entry_date,
                    "ExitDate": date,
                    "EntryPrice": p.entry_price,
                    "ExitPrice": ep,
                    "Shares": p.shares,
                    "PnL": pnl,
                    "ReturnPct": pnl / p.entry_cost,
                    "HoldingSessions": holding_sessions,
                    "ExitReason": "End of Backtest",
                }
            )

    return pd.DataFrame(trades), pd.DataFrame(equity_rows)
