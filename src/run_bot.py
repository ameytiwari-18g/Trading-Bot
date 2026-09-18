from pathlib import Path
import argparse, json, sys
import pandas as pd
sys.path.append(str(Path(__file__).resolve().parents[1]))
from src.data_loader import load_folder
from src.indicators import add_indicators
from src.backtester import backtest
from src.metrics import compute_metrics


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--data-dir', default='data/raw')
    ap.add_argument('--output-dir', default='outputs')
    ap.add_argument('--membership-file', default='data/nifty50_membership.csv')
    args = ap.parse_args()

    out = Path(args.output_dir)
    out.mkdir(parents=True, exist_ok=True)
    raw = load_folder(args.data_dir)
    if not raw:
        raise SystemExit('No CSV files found in data directory.')

    data = {k: add_indicators(v) for k, v in raw.items()}
    market = data.get('NIFTY50')

    membership = None
    membership_path = Path(args.membership_file)
    if membership_path.exists():
        membership = pd.read_csv(membership_path)
        print(f'Using historical NIFTY 50 membership: {membership_path.resolve()}')
    else:
        print('Historical membership file not found. Running with current-universe data.')
        print('Run: python download_constituents.py')

    trades, equity = backtest(data, market, membership=membership)

    for sym, df in data.items():
        df.to_csv(out / f'indicators_{sym}.csv', index=False)
    trades.to_csv(out / 'trade_log.csv', index=False)
    equity.to_csv(out / 'equity_curve.csv', index=False)

    metrics = compute_metrics(equity, trades, 1_000_000.0)
    metrics.to_csv(out / 'performance_summary.csv', index=False)
    metrics.to_json(out / 'performance_summary.json', orient='records', indent=2)

    latest = []
    for sym, df in data.items():
        if sym == 'NIFTY50' or not len(df):
            continue
        r = df.iloc[-1]
        latest.append({
            'Symbol': sym,
            'Date': r['Date'],
            'Signal': bool(__import__('src.strategy', fromlist=['signal_row']).signal_row(r)),
            'RSI14': r['RSI14'],
            'BreakoutStrength': r['BreakoutStrength'],
            'ConfirmationScore': r['ConfirmationScore']
        })
    pd.DataFrame(latest).to_csv(out / 'signals_latest.csv', index=False)
    print(metrics.to_string(index=False))
    print(f'Outputs written to {out.resolve()}')


if __name__ == '__main__':
    main()
