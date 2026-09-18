from pathlib import Path
import pandas as pd

REQUIRED = ['Date','Open','High','Low','Close','Volume']

def load_csv(path):
    df = pd.read_csv(path)
    cols = {c.strip(): c.strip() for c in df.columns}
    df = df.rename(columns=cols)
    missing = [c for c in REQUIRED if c not in df.columns]
    if missing:
        raise ValueError(f'{path}: missing columns {missing}')
    df['Date'] = pd.to_datetime(df['Date'])
    for c in REQUIRED[1:]: df[c] = pd.to_numeric(df[c], errors='coerce')
    return df[REQUIRED].dropna().sort_values('Date').drop_duplicates('Date').reset_index(drop=True)

def load_folder(folder):
    out = {}
    for p in sorted(Path(folder).glob('*.csv')):
        out[p.stem] = load_csv(p)
    return out
