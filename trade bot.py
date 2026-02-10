import alpaca_trade_api as tradeapi
from datetime import datetime
import pytz
from config import *


class AlpacaTrader:
    """
    Automated trading bot using Alpaca API.
    Tracks opening prices, buys on breakout,
    and sells using a $5 trailing stop.
    """

    def __init__(self):
        self.api = tradeapi.REST(
            API_KEY,
            SECRET_KEY,
            BASE_URL,
            api_version="v2"
        )
        self.watchlist_name = "My Watchlist"
        self.opening_prices = {}
        self.positions_peak = {}

    def get_watchlist_symbols(self):
        """Fetch symbols from Alpaca watchlist."""
        watchlists = self.api.get_watchlists()
        wl = next(w for w in watchlists if w.name == self.watchlist_name)
        return [asset.symbol for asset in wl.assets]

    def get_price(self, symbol):
        """Get latest trade price for a symbol."""
        bar = self.api.get_latest_bar(symbol)
        return float(bar.c)

    def record_opening_prices(self, symbols):
        """Store opening prices once per symbol."""
        for symbol in symbols:
            if symbol not in self.opening_prices:
                self.opening_prices[symbol] = self.get_price(symbol)

    def buy_if_triggered(self, symbol):
        """Buy if price exceeds opening by BUY_TRIGGER."""
        price = self.get_price(symbol)

        if price >= self.opening_prices[symbol] + BUY_TRIGGER:
            self.api.submit_order(
                symbol=symbol,
                qty=1,
                side="buy",
                type="market",
                time_in_force="gtc"
            )
            self.positions_peak[symbol] = price
            print(f"BOUGHT {symbol} @ {price}")

    def update_trailing_stop(self, symbol):
        """Sell if price drops TRAILING_STOP from peak."""
        price = self.get_price(symbol)
        peak = max(self.positions_peak[symbol], price)
        self.positions_peak[symbol] = peak

        if price <= peak - TRAILING_STOP:
            self.api.submit_order(
                symbol=symbol,
                qty=1,
                side="sell",
                type="market",
                time_in_force="gtc"
            )
            del self.positions_peak[symbol]
            print(f"SOLD {symbol} @ {price}")

    def run(self):
        """Main trading loop."""
        symbols = self.get_watchlist_symbols()
        self.record_opening_prices(symbols)

        current_positions = {p.symbol for p in self.api.list_positions()}

        for symbol in symbols:
            if symbol not in current_positions:
                self.buy_if_triggered(symbol)

        for symbol in list(self.positions_peak.keys()):
            self.update_trailing_stop(symbol)


if __name__ == "__main__":
    eastern = pytz.timezone("US/Eastern")
    now = datetime.now(eastern)

    if now.weekday() < 5:  # Monday–Friday
        trader = AlpacaTrader()
        trader.run()
