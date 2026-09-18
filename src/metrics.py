import numpy as np
import pandas as pd

def compute_metrics(equity, trades, initial_capital):
    eq = equity.copy()
    eq['Date'] = pd.to_datetime(eq['Date'])
    eq = eq.sort_values('Date')
    start, end = eq['Equity'].iloc[0], eq['Equity'].iloc[-1]
    days = max((eq['Date'].iloc[-1] - eq['Date'].iloc[0]).days, 1)
    years = days / 365.25
    total_return = end / start - 1
    cagr = (end / start) ** (1 / years) - 1 if years > 0 else np.nan
    peak = eq['Equity'].cummax()
    dd = eq['Equity']/peak - 1
    rets = eq['Equity'].pct_change().dropna()
    sharpe = (rets.mean()/rets.std()) * np.sqrt(252) if rets.std() else np.nan
    t = trades.copy()
    n = len(t)
    wins = (t['PnL'] > 0).sum() if n else 0
    gross_profit = t.loc[t['PnL'] > 0, 'PnL'].sum() if n else 0
    gross_loss = -t.loc[t['PnL'] < 0, 'PnL'].sum() if n else 0
    return pd.DataFrame([{
        'Initial Capital': initial_capital, 'Final Equity': end, 'Total Return': total_return,
        'CAGR': cagr, 'Max Drawdown': dd.min(), 'Annualized Volatility': rets.std()*np.sqrt(252),
        'Sharpe Approx': sharpe, 'Total Trades': n, 'Win Rate': wins/n if n else np.nan,
        'Profit Factor': gross_profit/gross_loss if gross_loss else np.nan,
        'Average Trade Return': t['ReturnPct'].mean() if n else np.nan,
        'Average Holding Sessions': t['HoldingSessions'].mean() if n else np.nan,
    }])
