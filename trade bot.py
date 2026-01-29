import alpaca_trade_api as tradeapi
import pandas as pd
import numpy as np

# -----------------------------
# SETUP
# -----------------------------
api = tradeapi.REST()  # no base URL here

symbols = ["AAPL", "MSFT", "AMZN", "GOOGL"]
risk_percent = 0.02

account = api.get_account()
account_balance = float(account.cash)

positions = {p.symbol: p for p in api.list_positions()}

# -----------------------------
# LOOP THROUGH STOCKS
# -----------------------------
for symbol in symbols:

    bars = api.get_bars(symbol, tradeapi.TimeFrame.Minute, limit=50).df
    current_price = bars["close"].iloc[-1]
    moving_average = bars["close"].mean()

    # RSI calculation
    delta = bars["close"].diff()
    gain = delta.where(delta > 0, 0).rolling(14).mean()
    loss = -delta.where(delta < 0, 0).rolling(14).mean()
    rs = gain / loss
    rsi = 100 - (100 / (1 + rs))
    rsi_value = rsi.iloc[-1]

    has_position = symbol in positions

    # -----------------------------
    # BUY LOGIC
    # -----------------------------
    if current_price > moving_average and rsi_value < 70 and not has_position:
        qty = int((account_balance * risk_percent) / current_price)

        if qty > 0:
            api.submit_order(
                symbol=symbol,
                qty=qty,
                side="buy",
                type="market",
                time_in_force="gtc"
            )

    # -----------------------------
    # SELL LOGIC
    # -----------------------------
    if has_position:
        position = positions[symbol]
        entry_price = float(position.avg_entry_price)

        stop_loss = entry_price * 0.98
        take_profit = entry_price * 1.04

        if current_price < moving_average:
            api.submit_order(symbol, position.qty, "sell", "market", "gtc")

        if current_price <= stop_loss:
            api.submit_order(symbol, position.qty, "sell", "market", "gtc")

        if current_price >= take_profit:
            api.submit_order(symbol, position.qty, "sell", "market", "gtc")
