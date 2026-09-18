import config

def signal_row(row):
    return bool(row.get('TrendPass', False) and row.get('BreakoutPass', False) and row.get('ConfirmationScore', 0) >= config.MIN_CONFIRMATION_SCORE)

def score_signal(row):
    return (int(row.get('ConfirmationScore', 0)), float(row.get('BreakoutStrength', 0) or 0), float(row.get('RSI14', 0) or 0))
