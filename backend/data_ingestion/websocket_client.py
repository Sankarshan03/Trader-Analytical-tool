import asyncio
import json
import logging
import logging.config
from typing import Callable, Dict, List, Optional, Set
import websockets
from datetime import datetime
import pytz

from ..database.db_manager import DatabaseManager
from ..config import BINANCE_WS_URL, DEFAULT_SYMBOLS, LOGGING_CONFIG

# Configure logging
logging.config.dictConfig(LOGGING_CONFIG)
logger = logging.getLogger(__name__)

class BinanceWebSocketClient:
    """WebSocket client for Binance Futures market data"""
    
    def __init__(
        self,
        symbols: Optional[List[str]] = None,
        db_manager: Optional[DatabaseManager] = None,
        max_retries: int = 5,
        reconnect_interval: int = 5
    ):
        """
        Initialize the WebSocket client.
        
        Args:
            symbols: List of trading symbols to subscribe to (e.g., ['btcusdt', 'ethusdt'])
            db_manager: Database manager instance for saving data
            max_retries: Maximum number of connection retry attempts
            reconnect_interval: Seconds to wait between reconnection attempts
        """
        self.symbols = symbols or DEFAULT_SYMBOLS
        self.db = db_manager or DatabaseManager()
        self.max_retries = max_retries
        self.reconnect_interval = reconnect_interval
        self.ws_url = BINANCE_WS_URL
        self.websocket = None
        self.running = False
        self.subscription_ids = set()
        self.callbacks = {
            'on_tick': [],
            'on_error': [],
            'on_connect': [],
            'on_disconnect': []
        }
    
    def add_callback(self, event: str, callback: Callable) -> None:
        """Register a callback for WebSocket events"""
        if event in self.callbacks:
            self.callbacks[event].append(callback)
    
    def _trigger_callbacks(self, event: str, *args, **kwargs) -> None:
        """Trigger all registered callbacks for an event"""
        for callback in self.callbacks.get(event, []):
            try:
                callback(*args, **kwargs)
            except Exception as e:
                logger.error(f"Error in {event} callback: {e}")
    
    def _get_stream_url(self) -> str:
        """Build the WebSocket URL for the given symbols"""
        # For Binance's WebSocket, we'll use individual connections for each symbol
        # as the combined stream was causing issues
        if not self.symbols:
            raise ValueError("No symbols provided for WebSocket connection")
            
        # For now, use the first symbol (we'll modify this to handle multiple symbols later)
        symbol = self.symbols[0].lower()
        return f"{self.ws_url}{symbol}@trade"
    
    async def _handle_message(self, message: str) -> None:
        """Process incoming WebSocket messages"""
        try:
            data = json.loads(message)
            
            # Handle direct trade message format
            if data.get('e') == 'trade':
                tick = {
                    'symbol': data['s'],
                    'timestamp': datetime.fromtimestamp(data['E'] / 1000, tz=pytz.utc),
                    'price': float(data['p']),
                    'size': float(data['q']),
                    'is_buyer_maker': data['m'],
                    'trade_id': data['t']
                }
                
                # Save to database
                try:
                    self.db.save_tick_data(tick)
                except Exception as e:
                    logger.error(f"Error saving tick data: {e}")
                
                # Notify callbacks
                self._trigger_callbacks('on_tick', tick)
                
        except json.JSONDecodeError as e:
            logger.error(f"Error decoding message: {e}")
        except Exception as e:
            logger.error(f"Error processing message: {e}")
    
    async def _connect(self) -> bool:
        """Establish WebSocket connection"""
        retries = 0
        while retries < self.max_retries and not self.running:
            try:
                stream_url = self._get_stream_url()
                logger.info(f"Attempting to connect to: {stream_url}")
                
                # Add timeout and ping/pong settings
                self.websocket = await websockets.connect(
                    stream_url,
                    ping_interval=20,  # Send ping every 20 seconds
                    ping_timeout=10,   # Wait 10 seconds for pong
                    close_timeout=1,   # Time to wait for close handshake
                    max_size=10 * 1024 * 1024  # 10MB max message size
                )
                
                # Verify connection is open
                if self.websocket.open:
                    logger.info(f"Successfully connected to Binance WebSocket for symbols: {', '.join(self.symbols)}")
                    self._trigger_callbacks('on_connect')
                    return True
                else:
                    raise Exception("WebSocket connection failed to open")
                    
            except websockets.exceptions.InvalidURI as e:
                logger.error(f"Invalid WebSocket URL: {e}")
                break  # No point in retrying with invalid URL
                
            except websockets.exceptions.WebSocketException as e:
                retries += 1
                logger.error(f"WebSocket error (attempt {retries}/{self.max_retries}): {str(e)}")
                if retries < self.max_retries:
                    await asyncio.sleep(self.reconnect_interval)
                    
            except Exception as e:
                retries += 1
                logger.error(f"Unexpected error (attempt {retries}/{self.max_retries}): {str(e)}")
                if retries < self.max_retries:
                    await asyncio.sleep(self.reconnect_interval)
        
        logger.error("Failed to connect to Binance WebSocket after maximum retries")
        return False
    
    async def _listen(self) -> None:
        """Listen for incoming messages"""
        while self.running:
            try:
                message = await self.websocket.recv()
                await self._handle_message(message)
            except websockets.exceptions.ConnectionClosed as e:
                logger.error(f"WebSocket connection closed: {e}")
                self._trigger_callbacks('on_disconnect')
                await self._reconnect()
            except Exception as e:
                logger.error(f"Error in WebSocket listener: {e}")
                self._trigger_callbacks('on_error', e)
    
    async def _reconnect(self) -> None:
        """Handle reconnection logic"""
        if not self.running:
            return
            
        logger.info("Attempting to reconnect...")
        await asyncio.sleep(self.reconnect_interval)
        
        if await self._connect():
            await self._listen()
    
    async def start(self) -> None:
        """Start the WebSocket client"""
        if self.running:
            logger.warning("WebSocket client is already running")
            return
        
        self.running = True
        
        if not await self._connect():
            logger.error("Failed to connect to Binance WebSocket")
            self.running = False
            return
        
        try:
            await self._listen()
        except Exception as e:
            logger.error(f"Error in WebSocket client: {e}")
            self.running = False
        finally:
            await self.stop()
    
    async def stop(self) -> None:
        """Stop the WebSocket client"""
        self.running = False
        if self.websocket:
            await self.websocket.close()
            self.websocket = None
            logger.info("WebSocket client stopped")
    
    def is_connected(self) -> bool:
        """Check if the WebSocket is connected"""
        return self.websocket is not None and self.websocket.open


async def run_websocket_client(
    symbols: Optional[List[str]] = None,
    db_manager: Optional[DatabaseManager] = None
) -> None:
    """
    Run the WebSocket client with the specified symbols and database manager.
    
    This is a convenience function for simple use cases.
    """
    client = BinanceWebSocketClient(symbols=symbols, db_manager=db_manager)
    
    # Example callback for logging ticks
    def log_tick(tick):
        logger.debug(f"Tick: {tick['symbol']} @ {tick['price']} x {tick['size']}")
    
    client.add_callback('on_tick', log_tick)
    
    try:
        await client.start()
    except KeyboardInterrupt:
        logger.info("Shutting down WebSocket client...")
        await client.stop()
    except Exception as e:
        logger.error(f"Error in WebSocket client: {e}")
        await client.stop()
        raise


if __name__ == "__main__":
    import asyncio
    
    # Example usage
    async def main():
        client = BinanceWebSocketClient()
        
        def on_tick(tick):
            print(f"{tick['timestamp']} - {tick['symbol']}: {tick['price']} x {tick['size']}")
        
        client.add_callback('on_tick', on_tick)
        
        try:
            await client.start()
        except KeyboardInterrupt:
            print("\nShutting down...")
            await client.stop()
    
    asyncio.run(main())
