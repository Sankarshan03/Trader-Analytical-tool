import asyncio
import websockets
import json
import logging
import sys
import os
from datetime import datetime
import pytz

# Add backend directory to Python path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Import database components
try:
    from backend.database.database import SessionLocal, init_db
    from backend.database.db_manager import DatabaseManager
    from backend.database.models import Base, TickData
    DB_AVAILABLE = True
except ImportError:
    DB_AVAILABLE = False
    print("Warning: Database components not found. Running in debug mode without database.")

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Binance WebSocket URL for BTCUSDT trades
WS_URL = "wss://fstream.binance.com/ws/btcusdt@trade"

class BinanceWebSocketClient:
    def __init__(self, db_manager=None):
        self.db = db_manager if db_manager else self._init_db()
        self.running = False
        
    def _init_db(self):
        if not DB_AVAILABLE:
            return None
        try:
            # Initialize database if needed
            init_db()
            return DatabaseManager(SessionLocal())
        except Exception as e:
            logger.error(f"Failed to initialize database: {e}")
            return None

    async def handle_message(self, message):
        """Process incoming WebSocket messages"""
        try:
            data = json.loads(message)
            if data.get('e') == 'trade':
                tick = {
                    'symbol': data['s'],
                    'timestamp': datetime.fromtimestamp(data['E'] / 1000, tz=pytz.utc),
                    'price': float(data['p']),
                    'size': float(data['q']),
                    'is_buyer_maker': data['m'],
                    'trade_id': data['t']
                }
                logger.info(f"Received tick: {tick['symbol']} @ {tick['price']}")
                
                # Save to database if db manager is available
                if self.db:
                    try:
                        # Convert timestamp to string for database storage
                        db_tick = tick.copy()
                        db_tick['timestamp'] = db_tick['timestamp'].isoformat()
                        self.db.save_tick_data(db_tick)
                    except Exception as e:
                        logger.error(f"Error saving to database: {e}")
                
                return tick
        except Exception as e:
            logger.error(f"Error processing message: {e}")

    async def run(self):
        """Run the WebSocket client using context manager"""
        self.running = True
        
        while self.running:
            try:
                async with websockets.connect(WS_URL) as websocket:
                    logger.info("Successfully connected to Binance WebSocket")
                    while self.running:
                        try:
                            message = await asyncio.wait_for(websocket.recv(), timeout=30)
                            await self.handle_message(message)
                        except asyncio.TimeoutError:
                            # Send ping to keep connection alive
                            await websocket.ping()
                            continue
                        except websockets.exceptions.ConnectionClosed:
                            logger.warning("Connection closed, reconnecting...")
                            break
                        except Exception as e:
                            logger.error(f"Error receiving message: {e}")
                            await asyncio.sleep(5)
                            break
            except Exception as e:
                logger.error(f"WebSocket error: {e}. Reconnecting in 5 seconds...")
                await asyncio.sleep(5)

    async def stop(self):
        """Stop the WebSocket client"""
        self.running = False

async def main():
    client = BinanceWebSocketClient()
    
    try:
        logger.info("Starting WebSocket client...")
        await client.run()
    except KeyboardInterrupt:
        logger.info("Shutting down...")
    except Exception as e:
        logger.error(f"Fatal error: {e}")
    finally:
        await client.stop()
        logger.info("WebSocket client stopped")

if __name__ == "__main__":
    asyncio.run(main())
