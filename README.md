# NIFTY 50 Swing Trading Bot

Academic backtesting project for a long-only NIFTY 50 swing strategy using daily OHLCV data.

## Strategy
- EMA20 > EMA50 trend filter
- Close > previous 20-day high breakout
- RSI14 > 50 confirmation
- Volume > previous 20-day average confirmation
- NIFTY 50 Close > EMA50 market-regime filter
- Next-day open entry
- Max 5 positions
- Risk 1% of current equity per trade, capped at 20% equity per position
- Initial stop = Entry - 2 ATR(14)
- Trailing stop = highest close - 2 ATR(14), active after +1R
- Exits: stop/trailing stop, EMA20 <= EMA50, RSI14 < 45, 20-session maximum

## Run
pip install -r requirements.txt
python download_data.py
python src/smoke_test.py
python src/run_bot.py --data-dir data/raw --output-dir outputs

The downloader currently uses the current NIFTY 50 universe as a practical baseline. Historical constituent membership should be incorporated or the survivorship-bias limitation disclosed in the final report.

## Historical NIFTY 50 membership

For the academic backtest, run:

```powershell
python -m pip install openpyxl
python download_constituents.py
```

This downloads a third-party reconstructed historical NIFTY 50 membership dataset derived from public NSE/Nifty Indices reconstitution material. It is used to reduce survivorship bias. The dataset is monthly, so the backtest applies the reconstructed universe at monthly resolution. It is not an official NSE data feed.

Then run:

```powershell
python src/run_bot.py --data-dir data/raw --output-dir outputs
```

If `data/nifty50_membership.csv` exists, the backtester uses it automatically.
