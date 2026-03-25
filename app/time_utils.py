from datetime import datetime
import pytz

ET = pytz.timezone("US/Eastern")

def now_et():
    return datetime.now(ET)

def is_market_day(dt):
    return dt.weekday() < 5

def is_regular_market_hours(dt):
    return is_market_day(dt) and 930 <= dt.hour * 100 + dt.minute <= 1600

def in_no_trade_zone(dt, first_minutes, last_minutes):
    if not is_market_day(dt):
        return False
    cur = dt.hour * 60 + dt.minute
    open_m = 570
    close_m = 960
    return (open_m <= cur < open_m + first_minutes) or (close_m - last_minutes <= cur <= close_m)
