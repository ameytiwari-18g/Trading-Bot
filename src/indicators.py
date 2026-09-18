import pandas as pd
import config

def add_indicators(df):
    x = df.copy()
    x['EMA20'] = x['Close'].ewm(span=config.EMA_FAST, adjust=False).mean()
    x['EMA50'] = x['Close'].ewm(span=config.EMA_SLOW, adjust=False).mean()
    delta = x['Close'].diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)
    avg_gain = gain.ewm(alpha=1/config.RSI_PERIOD, adjust=False).mean()
    avg_loss = loss.ewm(alpha=1/config.RSI_PERIOD, adjust=False).mean()
    rs = avg_gain / avg_loss.replace(0, pd.NA)
    x['RSI14'] = 100 - (100 / (1 + rs))
    prev_close = x['Close'].shift(1)
    tr = pd.concat([x['High']-x['Low'], (x['High']-prev_close).abs(), (x['Low']-prev_close).abs()], axis=1).max(axis=1)
    x['ATR14'] = tr.ewm(alpha=1/config.ATR_PERIOD, adjust=False).mean()
    x['Prev20High'] = x['High'].shift(1).rolling(config.BREAKOUT_LOOKBACK).max()
    x['AvgVolume20'] = x['Volume'].shift(1).rolling(config.VOLUME_LOOKBACK).mean()
    x['TrendPass'] = x['EMA20'] > x['EMA50']
    x['BreakoutPass'] = x['Close'] > x['Prev20High']
    x['RSIPass'] = x['RSI14'] > 50
    x['VolumePass'] = x['Volume'] > x['AvgVolume20']
    x['ConfirmationScore'] = x['RSIPass'].astype(int) + x['VolumePass'].astype(int)
    x['BreakoutStrength'] = x['Close'] / x['Prev20High'] - 1
    return x
