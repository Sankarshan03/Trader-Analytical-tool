import asyncio
import json
import logging
from datetime import datetime, timedelta
import pytz
from backend.database.database import SessionLocal, init_db
from backend.database.db_manager import DatabaseManager

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

def test_database_connection():
    """Test database connection and basic operations"""
    try:
        # Initialize database
        init_db()
        db = SessionLocal()
        
        # Test connection
        result = db.execute("SELECT 1").scalar()
        logger.info(f"Database connection test: {'Success' if result == 1 else 'Failed'}")
        
        # Test basic operations
        db_manager = DatabaseManager(db)
        
        # Test saving tick data
        test_tick = {
            'symbol': 'TEST',
            'timestamp': datetime.now(pytz.utc).isoformat(),
            'price': 1000.0,
            'size': 1.0,
            'is_buyer_maker': False,
            'trade_id': 'test_123'
        }
        
        saved_tick = db_manager.save_tick_data(test_tick)
        logger.info(f"Saved test tick: {saved_tick.id}")
        
        # Query the test data
        ticks = db_manager.get_ticks_in_range(
            symbol='TEST',
            start_time=datetime.now(pytz.utc) - timedelta(minutes=5),
            end_time=datetime.now(pytz.utc) + timedelta(minutes=5)
        )
        
        logger.info(f"Found {len(ticks)} test ticks in the database")
        for i, tick in enumerate(ticks[:3], 1):
            logger.info(f"Tick {i}: {tick}")
        
        return True
        
    except Exception as e:
        logger.error(f"Database test failed: {e}")
        return False
    finally:
        db.close()

async def test_websocket_connection():
    """Test WebSocket connection to Binance"""
    import websockets
    
    uri = "wss://fstream.binance.com/ws/btcusdt@trade"
    try:
        async with websockets.connect(uri) as websocket:
            logger.info("Successfully connected to Binance WebSocket")
            
            # Wait for the first message
            message = await asyncio.wait_for(websocket.recv(), timeout=10)
            data = json.loads(message)
            
            if data.get('e') == 'trade':
                logger.info(f"Received trade data: {data['s']} @ {data['p']}")
                return True
            return False
            
    except Exception as e:
        logger.error(f"WebSocket test failed: {e}")
        return False

if __name__ == "__main__":
    logger.info("Running integration tests...")
    
    # Test database connection
    logger.info("Testing database connection...")
    db_ok = test_database_connection()
    
    # Test WebSocket connection
    logger.info("Testing WebSocket connection...")
    ws_ok = asyncio.run(test_websocket_connection())
    
    # Print summary
    logger.info("\n=== Test Summary ===")
    logger.info(f"Database: {'✓' if db_ok else '✗'}")
    logger.info(f"WebSocket: {'✓' if ws_ok else '✗'}")
    
    if db_ok and ws_ok:
        logger.info("\n✅ All tests passed! You can now run the application.")
        logger.info("\nTo start the application, run these commands in separate terminals:")
        print("""
1. Start the backend API:
   cd c:\Users\Admin\Documents\Trader-Analytics\Trader-Analytical-tool\backend
   uvicorn main:app --reload --host 0.0.0.0 --port 8000

2. Start the WebSocket client:
   cd c:\Users\Admin\Documents\Trader-Analytics\Trader-Analytical-tool
   python start_websocket.py

3. Start the frontend:
   cd c:\Users\Admin\Documents\Trader-Analytics\Trader-Analytical-tool\frontend
   streamlit run app.py

Then open http://localhost:8501 in your browser to view the dashboard.
        """)
    else:
        logger.error("\n❌ Some tests failed. Please check the logs above for details.")
        if not db_ok:
            logger.error("- Verify that the database is running and accessible")
            logger.error("- Check the database configuration in backend/database/database.py")
        if not ws_ok:
            logger.error("- Check your internet connection")
            logger.error("- Verify that you can access wss://fstream.binance.com")
            logger.error("- Check if Binance API is currently available")
