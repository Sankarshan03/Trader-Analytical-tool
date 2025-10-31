import logging
import asyncio
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple, Callable
import pandas as pd
import numpy as np
from scipy import stats
from statsmodels.tsa.stattools import adfuller
import pytz

from ..database.db_manager import DatabaseManager
from ..config import TIMEFRAMES, ROLLING_WINDOW, ZSCORE_THRESHOLD, LOGGING_CONFIG

# Configure logging
logging.config.dictConfig(LOGGING_CONFIG)
logger = logging.getLogger(__name__)

class DataProcessor:
    """Handles data processing, resampling, and analytics computation"""
    
    def __init__(self, db_manager: Optional[DatabaseManager] = None):
        """Initialize the data processor"""
        self.db = db_manager or DatabaseManager()
        self.running = False
        self.resample_tasks = {}
        self.analytics_tasks = {}
        self.callbacks = {
            'on_resample': [],
            'on_analytics': [],
            'on_error': []
        }
    
    def add_callback(self, event: str, callback: Callable) -> None:
        """Register a callback for processor events"""
        if event in self.callbacks:
            self.callbacks[event].append(callback)
    
    def _trigger_callbacks(self, event: str, *args, **kwargs) -> None:
        """Trigger all registered callbacks for an event"""
        for callback in self.callbacks.get(event, []):
            try:
                callback(*args, **kwargs)
            except Exception as e:
                logger.error(f"Error in {event} callback: {e}")
    
    async def start_resampling(self, symbol: str, interval: str) -> None:
        """Start resampling task for a symbol and interval"""
        if interval not in TIMEFRAMES:
            raise ValueError(f"Unsupported interval: {interval}")
        
        task_key = f"{symbol}_{interval}"
        if task_key in self.resample_tasks:
            logger.warning(f"Resampling task already running for {task_key}")
            return
        
        self.running = True
        
        async def resample_loop():
            """Run resampling in a loop"""
            while self.running:
                try:
                    # Process resampling
                    self.db.resample_and_save(symbol, interval)
                    
                    # Get the latest resampled data
                    latest = self.db.get_ohlcv(symbol, interval, limit=1)
                    if not latest.empty:
                        self._trigger_callbacks('on_resample', {
                            'symbol': symbol,
                            'interval': interval,
                            'data': latest.iloc[0].to_dict(),
                            'timestamp': datetime.now(pytz.utc)
                        })
                    
                    # Wait until the next interval
                    await asyncio.sleep(self._get_interval_seconds(interval))
                    
                except Exception as e:
                    logger.error(f"Error in resampling loop for {symbol} {interval}: {e}")
                    self._trigger_callbacks('on_error', e)
                    await asyncio.sleep(5)  # Wait before retrying
        
        # Start the resampling task
        task = asyncio.create_task(resample_loop())
        self.resample_tasks[task_key] = task
        logger.info(f"Started resampling task for {symbol} {interval}")
    
    async def stop_resampling(self, symbol: str, interval: str) -> None:
        """Stop resampling for a symbol and interval"""
        task_key = f"{symbol}_{interval}"
        if task_key in self.resample_tasks:
            self.resample_tasks[task_key].cancel()
            try:
                await self.resample_tasks[task_key]
            except asyncio.CancelledError:
                logger.info(f"Stopped resampling task for {task_key}")
            del self.resample_tasks[task_key]
    
    async def start_analytics(self, symbol1: str, symbol2: Optional[str] = None) -> None:
        """Start analytics computation for a symbol or symbol pair"""
        task_key = f"{symbol1}_{symbol2 or 'single'}"
        if task_key in self.analytics_tasks:
            logger.warning(f"Analytics task already running for {task_key}")
            return
        
        self.running = True
        
        async def analytics_loop():
            """Run analytics in a loop"""
            while self.running:
                try:
                    # Compute and save analytics
                    if symbol2:
                        await self._compute_pair_analytics(symbol1, symbol2)
                    else:
                        await self._compute_single_analytics(symbol1)
                    
                    # Run every 5 seconds
                    await asyncio.sleep(5)
                    
                except Exception as e:
                    logger.error(f"Error in analytics loop for {task_key}: {e}")
                    self._trigger_callbacks('on_error', e)
                    await asyncio.sleep(5)  # Wait before retrying
        
        # Start the analytics task
        task = asyncio.create_task(analytics_loop())
        self.analytics_tasks[task_key] = task
        logger.info(f"Started analytics task for {task_key}")
    
    async def stop_analytics(self, symbol1: str, symbol2: Optional[str] = None) -> None:
        """Stop analytics computation for a symbol or symbol pair"""
        task_key = f"{symbol1}_{symbol2 or 'single'}"
        if task_key in self.analytics_tasks:
            self.analytics_tasks[task_key].cancel()
            try:
                await self.analytics_tasks[task_key]
            except asyncio.CancelledError:
                logger.info(f"Stopped analytics task for {task_key}")
            del self.analytics_tasks[task_key]
    
    async def stop_all(self) -> None:
        """Stop all processing tasks"""
        self.running = False
        
        # Stop all resampling tasks
        for task_key, task in list(self.resample_tasks.items()):
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                logger.info(f"Stopped resampling task {task_key}")
        self.resample_tasks.clear()
        
        # Stop all analytics tasks
        for task_key, task in list(self.analytics_tasks.items()):
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                logger.info(f"Stopped analytics task {task_key}")
        self.analytics_tasks.clear()
    
    async def _compute_single_analytics(self, symbol: str) -> None:
        """Compute analytics for a single symbol"""
        # Get the latest data
        df = self.db.get_ohlcv(symbol, '1m', limit=ROLLING_WINDOW * 2)
        if df.empty or len(df) < ROLLING_WINDOW:
            return
        
        # Compute rolling statistics
        close_prices = df['close']
        returns = close_prices.pct_change().dropna()
        
        if len(returns) < ROLLING_WINDOW:
            return
        
        # Compute rolling volatility (annualized)
        rolling_vol = returns.rolling(window=ROLLING_WINDOW).std() * np.sqrt(365 * 24 * 60)  # Annualized
        
        # Compute rolling z-score of returns
        rolling_zscore = (returns - returns.rolling(window=ROLLING_WINDOW).mean()) / returns.rolling(window=ROLLING_WINDOW).std()
        
        # Get the latest values
        latest = df.iloc[-1]
        timestamp = latest.name
        
        # Save the analytics
        if not pd.isna(rolling_vol.iloc[-1]):
            self.db.save_analytics_result(
                metric='volatility',
                symbol1=symbol,
                value=rolling_vol.iloc[-1],
                timestamp=timestamp,
                interval='1m',
                additional_data={
                    'window': ROLLING_WINDOW,
                    'annualized': True
                }
            )
        
        if not pd.isna(rolling_zscore.iloc[-1]):
            self.db.save_analytics_result(
                metric='returns_zscore',
                symbol1=symbol,
                value=rolling_zscore.iloc[-1],
                timestamp=timestamp,
                interval='1m'
            )
            
            # Check for z-score alerts
            if abs(rolling_zscore.iloc[-1]) > ZSCORE_THRESHOLD:
                self._trigger_callbacks('on_alert', {
                    'symbol': symbol,
                    'metric': 'returns_zscore',
                    'value': rolling_zscore.iloc[-1],
                    'threshold': ZSCORE_THRESHOLD,
                    'timestamp': timestamp
                })
    
    async def _compute_pair_analytics(self, symbol1: str, symbol2: str) -> None:
        """Compute analytics for a pair of symbols"""
        # Get the latest data for both symbols
        df1 = self.db.get_ohlcv(symbol1, '1m', limit=ROLLING_WINDOW * 2)
        df2 = self.db.get_ohlcv(symbol2, '1m', limit=ROLLING_WINDOW * 2)
        
        if df1.empty or df2.empty or len(df1) < ROLLING_WINDOW or len(df2) < ROLLING_WINDOW:
            return
        
        # Align the dataframes on their indices
        common_index = df1.index.intersection(df2.index)
        if len(common_index) < ROLLING_WINDOW:
            return
        
        df1_aligned = df1.loc[common_index]
        df2_aligned = df2.loc[common_index]
        
        # Get the close prices
        prices1 = df1_aligned['close']
        prices2 = df2_aligned['close']
        
        # Compute returns
        returns1 = prices1.pct_change().dropna()
        returns2 = prices2.pct_change().dropna()
        
        if len(returns1) < ROLLING_WINDOW or len(returns2) < ROLLING_WINDOW:
            return
        
        # Compute rolling correlation
        rolling_corr = returns1.rolling(window=ROLLING_WINDOW).corr(returns2)
        
        # Compute hedge ratio using OLS (y = hedge_ratio * x + intercept)
        def ols_hedge_ratio(x, y):
            x = x.values.reshape(-1, 1)
            y = y.values.reshape(-1, 1)
            X = np.hstack([x, np.ones_like(x)])
            beta = np.linalg.lstsq(X, y, rcond=None)[0][0][0]
            return beta
        
        hedge_ratio = ols_hedge_ratio(prices1, prices2)
        
        # Compute spread and z-score
        spread = prices1 - hedge_ratio * prices2
        spread_mean = spread.rolling(window=ROLLING_WINDOW).mean()
        spread_std = spread.rolling(window=ROLLING_WINDOW).std()
        zscore = (spread - spread_mean) / spread_std
        
        # Get the latest values
        latest_idx = common_index[-1]
        
        # Save the analytics
        if not pd.isna(rolling_corr.iloc[-1]):
            self.db.save_analytics_result(
                metric='correlation',
                symbol1=symbol1,
                symbol2=symbol2,
                value=rolling_corr.iloc[-1],
                timestamp=latest_idx,
                interval='1m',
                additional_data={
                    'window': ROLLING_WINDOW
                }
            )
        
        if not pd.isna(hedge_ratio):
            self.db.save_analytics_result(
                metric='hedge_ratio',
                symbol1=symbol1,
                symbol2=symbol2,
                value=hedge_ratio,
                timestamp=latest_idx,
                interval='1m'
            )
        
        if not pd.isna(zscore.iloc[-1]):
            self.db.save_analytics_result(
                metric='spread_zscore',
                symbol1=symbol1,
                symbol2=symbol2,
                value=zscore.iloc[-1],
                timestamp=latest_idx,
                interval='1m',
                additional_data={
                    'spread': spread.iloc[-1],
                    'spread_mean': spread_mean.iloc[-1],
                    'spread_std': spread_std.iloc[-1]
                }
            )
            
            # Check for z-score alerts
            if abs(zscore.iloc[-1]) > ZSCORE_THRESHOLD:
                self._trigger_callbacks('on_alert', {
                    'symbol1': symbol1,
                    'symbol2': symbol2,
                    'metric': 'spread_zscore',
                    'value': zscore.iloc[-1],
                    'threshold': ZSCORE_THRESHOLD,
                    'spread': spread.iloc[-1],
                    'timestamp': latest_idx
                })
    
    @staticmethod
    def _get_interval_seconds(interval: str) -> int:
        """Convert interval string to seconds"""
        if interval.endswith('s'):
            return int(interval[:-1])
        elif interval.endswith('m'):
            return int(interval[:-1]) * 60
        elif interval.endswith('h'):
            return int(interval[:-1]) * 3600
        elif interval.endswith('d'):
            return int(interval[:-1]) * 86400
        else:
            return 60  # Default to 1 minute


# Example usage
async def main():
    db = DatabaseManager()
    processor = DataProcessor(db)
    
    # Example callback for resampled data
    def on_resample(data):
        print(f"Resampled {data['symbol']} {data['interval']}: {data['data']}")
    
    # Example callback for alerts
    def on_alert(alert):
        print(f"ALERT: {alert}")
    
    processor.add_callback('on_resample', on_resample)
    processor.add_callback('on_alert', on_alert)
    
    # Start processing
    try:
        await processor.start_resampling('btcusdt', '1m')
        await processor.start_analytics('btcusdt')
        
        # Keep the processor running
        while True:
            await asyncio.sleep(1)
    except KeyboardInterrupt:
        print("\nShutting down...")
        await processor.stop_all()


if __name__ == "__main__":
    import asyncio
    asyncio.run(main())
