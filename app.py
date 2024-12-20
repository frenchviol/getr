import asyncio
import json
import pytz
from websockets import connect
from termcolor import cprint
from datetime import datetime
import nest_asyncio
from flask import Flask, render_template, jsonify

nest_asyncio.apply()

symbols = ['trxusdt', 'aevousdy']
websocket_base_url = 'wss://stream.binance.com:9443/ws'

# Flask app setup
app = Flask(__name__)

# TradeAggregator class that stores aggregated trades
class TradeAggregator:
    def __init__(self):
        self.trade_buckets = {}

    async def add_trade(self, symbol, timestamp, usd_size, is_buyer_maker):
        trade_key = (symbol, timestamp, is_buyer_maker)
        self.trade_buckets[trade_key] = self.trade_buckets.get(trade_key, 0) + usd_size

    async def check_and_get_trades(self):
        timestamp_now = datetime.now(pytz.timezone('US/Eastern')).strftime("%H:%M:%S")

        trades_to_display = []
        deletions = []
        for trade_key, usd_size in self.trade_buckets.items():
            symbol, timestamp, is_buyer_maker = trade_key
            if timestamp < timestamp_now and usd_size > 50000:
                trade_type = "BUY" if not is_buyer_maker else "SELL"
                display_size = usd_size / 100000
                trades_to_display.append({
                    "trade_type": trade_type,
                    "symbol": symbol,
                    "timestamp": timestamp,
                    "usd_size": f"${display_size:.2f}m",
                })
                deletions.append(trade_key)

        for key in deletions:
            del self.trade_buckets[key]
        
        return trades_to_display


# WebSocket trade handler
async def trade_handler(symbol, trade_aggregator):
    url = f"{websocket_base_url}/{symbol.lower()}@trade"
    try:
        async with connect(url) as websocket:
            while True:
                try:
                    message = await websocket.recv()
                    data = json.loads(message)
                    usd_size = float(data['p']) * float(data['q'])  # Calculate USD size
                    trade_time = datetime.fromtimestamp(data['T'] / 1000, pytz.timezone('US/Eastern')).strftime("%H:%M:%S")

                    await trade_aggregator.add_trade(symbol.upper(), trade_time, usd_size, data['m'])

                except Exception as e:
                    print(f"Error during message processing: {e}")
                    await asyncio.sleep(1)
    except Exception as e:
        print(f"Error connecting to WebSocket: {e}")
        await asyncio.sleep(1)  # Retry after delay


# Route to show aggregated trades on a webpage
@app.route('/')
def index():
    return render_template('index.html')  # Create this HTML page to display data

# Route to fetch aggregated trades as JSON (for use in the front end)
@app.route('/get_trades', methods=['GET'])
def get_trades():
    trades = asyncio.run(trade_aggregator.check_and_get_trades())  # Get trades from the aggregator
    return jsonify(trades)


# Start the asyncio event loop in a background task
async def background_task():
    trade_aggregator = TradeAggregator()
    tasks = [trade_handler(symbol, trade_aggregator) for symbol in symbols]
    await asyncio.gather(*tasks)


if __name__ == '__main__':
    trade_aggregator = TradeAggregator()
    # Run the WebSocket handlers in the background using asyncio
    loop = asyncio.get_event_loop()
    loop.create_task(background_task())  # Start the trade handler in the background
    app.run(debug=True, host='0.0.0.0', port=5000)  # Start Flask app
