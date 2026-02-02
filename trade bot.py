import alpaca_trade_api as tradeapi
from datetime import datetime
import pytz
from config import *

api = tradeapi.REST(API_KEY, SECRET_KEY, BASE_URL, api_version="v2")

watchlist_name = "My Watchlist"
opening_prices = {}
positions_peak = {}

def get_watchlist_symbols():
    watchlists = api.get_watchlists()
    wl = next(w for w in watchlists if w.name == watchlist_name)
    return [asset.symbol for asset in wl.assets]

def get_price(symbol):
    bar = api.get_latest_bar(symbol)
    return float(bar.c)

def record_opening_prices(symbols):
    for s in symbols:
        if s not in opening_prices:
            opening_prices[s] = get_price(s)

def buy_if_triggered(symbol):
    price = get_price(symbol)
    if price >= opening_prices[symbol] + BUY_TRIGGER:
        api.submit_order(
            symbol=symbol,
            qty=1,
            side="buy",
            type="market",
            time_in_force="gtc"
        )
        positions_peak[symbol] = price
        print(f"BOUGHT {symbol} @ {price}")

def update_trailing_stop(symbol):
    price = get_price(symbol)
    peak = max(positions_peak[symbol], price)
    positions_peak[symbol] = peak

    if price <= peak - TRAILING_STOP:
        api.submit_order(
            symbol=symbol,
            qty=1,
            side="sell",
            type="market",
            time_in_force="gtc"
        )
        del positions_peak[symbol]
        print(f"SOLD {symbol} @ {price}")

def run():
    symbols = get_watchlist_symbols()
    record_opening_prices(symbols)

    positions = {p.symbol for p in api.list_positions()}

    for s in symbols:
        if s not in positions:
            buy_if_triggered(s)

    for s in list(positions_peak.keys()):
        update_trailing_stop(s)

if __name__ == "__main__":
    eastern = pytz.timezone("US/Eastern")
    now = datetime.now(eastern)

    if now.weekday() < 5:  # Mon–Fri
        run()