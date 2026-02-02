import os

API_KEY = os.getenv("ALPACA_API_KEY")
SECRET_KEY = os.getenv("ALPACA_SECRET_KEY")
BASE_URL = "https://paper-api.alpaca.markets"

BUY_TRIGGER = 5.0          # buy when price increases $5
TRAILING_STOP = 5.0        # sell when price drops $5 from peak