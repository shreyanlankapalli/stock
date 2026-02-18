import os
import json
import time
from datetime import datetime, timedelta, timezone

import pytz
from alpaca.trading.client import TradingClient
from alpaca.trading.enums import OrderSide, TimeInForce
from alpaca.trading.requests import MarketOrderRequest
from alpaca.data.historical import StockHistoricalDataClient
from alpaca.data.requests import StockBarsRequest
from alpaca.data.timeframe import TimeFrame


# =========================
# FILES
# =========================
STATE_FILE = "bot_state.json"
LOG_FILE = "trade_log.jsonl"


# =========================
# CONFIG
# =========================
SYMBOLS = [
    "AAPL", "MSFT", "SPY",

    "NVDA", "TSLA", "AMD", "META", "AMZN",
    "NFLX", "GOOGL", "QQQ", "SMCI", "COIN",
    "PLTR", "INTC", "MU", "AVGO", "ADBE",
    "CRM", "PYPL", "SHOP", "UBER", "SNOW"
]

DOLLARS_PER_TRADE = 250
FAST_SMA = 5
SLOW_SMA = 12
POLL_SECONDS = 60
RUNTIME_HOURS = 5

CENTRAL = pytz.timezone("America/Chicago")


# =========================
# TIME + LOGGING
# =========================
def now_central():
    return datetime.now(tz=timezone.utc).astimezone(CENTRAL)


def log_event(event: dict):
    event = dict(event)
    event["ts"] = now_central().isoformat()
    with open(LOG_FILE, "a", encoding="utf-8") as f:
        f.write(json.dumps(event) + "\n")


# =========================
# STATE MGMT
# =========================
def load_state():
    if not os.path.exists(STATE_FILE):
        return {"holdings": {}, "last_signal": {}}
    with open(STATE_FILE, "r", encoding="utf-8") as f:
        return json.load(f)


def save_state(state):
    tmp = STATE_FILE + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(state, f, indent=2, sort_keys=True)
    os.replace(tmp, STATE_FILE)


# =========================
# MARKET HELPERS
# =========================
def is_market_open(trading_client: TradingClient) -> bool:
    clock = trading_client.get_clock()
    return bool(clock.is_open)


def sma(values, n):
    if len(values) < n:
        return None
    return sum(values[-n:]) / n


def calc_qty_from_dollars(last_price: float) -> int:
    if last_price <= 0:
        return 0
    qty = int(DOLLARS_PER_TRADE // last_price)
    return max(qty, 0)


# =========================
# DATA + ORDERS
# =========================
def fetch_closes(data_client: StockHistoricalDataClient, symbol: str):
    end = datetime.now(timezone.utc)
    start = end - timedelta(minutes=90)

    req = StockBarsRequest(
        symbol_or_symbols=[symbol],
        timeframe=TimeFrame.Minute,
        start=start,
        end=end,
        adjustment="raw",
        feed="iex"
    )

    bars = data_client.get_stock_bars(req).data.get(symbol, [])
    return [b.close for b in bars]


def submit_market_order(trading_client: TradingClient, symbol: str, side: OrderSide, qty: int):
    order = MarketOrderRequest(
        symbol=symbol,
        qty=qty,
        side=side,
        time_in_force=TimeInForce.DAY
    )
    return trading_client.submit_order(order)


# =========================
# MAIN LOOP
# =========================
def main():
    api_key = os.getenv("ALPACA_API_KEY")
    secret_key = os.getenv("ALPACA_SECRET_KEY")

    if not api_key or not secret_key:
        raise RuntimeError("Missing ALPACA_API_KEY / ALPACA_SECRET_KEY env vars")

    trading_client = TradingClient(api_key, secret_key, paper=True)
    data_client = StockHistoricalDataClient(api_key, secret_key)

    state = load_state()

    start_time = datetime.now(timezone.utc)
    end_time = start_time + timedelta(hours=RUNTIME_HOURS)

    log_event({
        "type": "start",
        "runtime_hours": RUNTIME_HOURS,
        "symbols": SYMBOLS
    })

    while datetime.now(timezone.utc) < end_time:
        try:
            if not is_market_open(trading_client):
                log_event({"type": "market_closed", "msg": "Sleeping..."})
                save_state(state)
                time.sleep(POLL_SECONDS)
                continue

            for sym in SYMBOLS:
                closes = fetch_closes(data_client, sym)

                if len(closes) < SLOW_SMA + 2:
                    log_event({
                        "type": "skip",
                        "symbol": sym,
                        "reason": "not_enough_bars"
                    })
                    continue

                fast_now = sma(closes, FAST_SMA)
                slow_now = sma(closes, SLOW_SMA)
                fast_prev = sma(closes[:-1], FAST_SMA)
                slow_prev = sma(closes[:-1], SLOW_SMA)

                if None in (fast_now, slow_now, fast_prev, slow_prev):
                    continue

                last_price = closes[-1]
                holding = state["holdings"].get(sym, {"qty": 0})
                qty_held = int(holding.get("qty", 0))

                signal = "HOLD"

                if fast_prev <= slow_prev and fast_now > slow_now:
                    signal = "BUY"
                elif fast_prev >= slow_prev and fast_now < slow_now:
                    signal = "SELL"

                last_signal = state["last_signal"].get(sym)

                if signal != "HOLD" and signal == last_signal:
                    continue

                if signal == "BUY" and qty_held == 0:
                    qty = calc_qty_from_dollars(last_price)

                    if qty > 0:
                        placed = submit_market_order(
                            trading_client, sym, OrderSide.BUY, qty
                        )

                        state["holdings"][sym] = {
                            "qty": qty,
                            "avg_entry_hint": last_price
                        }

                        state["last_signal"][sym] = "BUY"

                        log_event({
                            "type": "order",
                            "symbol": sym,
                            "side": "BUY",
                            "qty": qty,
                            "price_hint": last_price,
                            "order_id": placed.id
                        })

                elif signal == "SELL" and qty_held > 0:
                    placed = submit_market_order(
                        trading_client, sym, OrderSide.SELL, qty_held
                    )

                    state["holdings"][sym] = {"qty": 0}
                    state["last_signal"][sym] = "SELL"

                    log_event({
                        "type": "order",
                        "symbol": sym,
                        "side": "SELL",
                        "qty": qty_held,
                        "price_hint": last_price,
                        "order_id": placed.id
                    })

                else:
                    state["last_signal"][sym] = signal

            save_state(state)
            time.sleep(POLL_SECONDS)

        except Exception as e:
            log_event({"type": "error", "error": str(e)})
            save_state(state)
            time.sleep(10)

    save_state(state)
    log_event({
        "type": "end",
        "msg": "Finished 5-hour runtime; exiting to allow cache/upload."
    })


if __name__ == "__main__":
    main()
