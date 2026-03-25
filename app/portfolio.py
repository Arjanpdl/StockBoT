import math

def compute_position_size(account_equity, risk_per_trade, entry_price, stop_price, max_position_pct):
    if entry_price <= 0:
        return 0
    cap = math.floor((account_equity * max_position_pct) / entry_price)
    if stop_price is None or stop_price >= entry_price:
        return max(0, cap)
    risk_dollars = account_equity * risk_per_trade
    per_share = entry_price - stop_price
    if per_share <= 0:
        return 0
    return max(0, min(cap, math.floor(risk_dollars / per_share)))
