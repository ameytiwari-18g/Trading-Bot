import pandas as pd
from src.indicators import add_indicators

dates=pd.date_range('2025-01-01', periods=100, freq='B')
base=pd.Series(range(100),dtype=float)+100
df=pd.DataFrame({'Date':dates,'Open':base,'High':base+2,'Low':base-2,'Close':base+1,'Volume':1000000.0})
x=add_indicators(df)
assert {'EMA20','EMA50','RSI14','ATR14','Prev20High','AvgVolume20','TrendPass','BreakoutPass','RSIPass','VolumePass','ConfirmationScore'}.issubset(x.columns)
print('Smoke test passed.')
