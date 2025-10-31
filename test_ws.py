import asyncio
import websockets

async def test_connection():
    uri = "wss://fstream.binance.com/ws/btcusdt@trade"
    try:
        async with websockets.connect(uri) as websocket:
            print("Successfully connected to Binance WebSocket!")
            while True:
                message = await websocket.recv()
                print(f"Received message: {message[:100]}...")  # Print first 100 chars
    except Exception as e:
        print(f"Connection failed: {e}")

asyncio.get_event_loop().run_until_complete(test_connection())