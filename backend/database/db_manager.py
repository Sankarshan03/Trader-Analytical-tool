import logging
from typing import List, Dict, Any, Optional, Union
from datetime import datetime, timedelta
import json
import pandas as pd
from sqlalchemy import text, func, and_, or_
from sqlalchemy.orm import Session
import pytz

import sys
from pathlib import Path

# Add the backend directory to the Python path
sys.path.append(str(Path(__file__).parent.parent.absolute()))

from database.models import (
    engine, SessionLocal, TickData, ResampledData, 
    AnalyticsResults, Alert, get_db
)
from config import TIMEFRAMES

logger = logging.getLogger(__name__)

class DatabaseManager:
    """Handles all database operations for the application"""
    
    def __init__(self, db: Optional[Session] = None):
        """Initialize with an optional database session"""
        self.db = db or next(get_db())
    
    # --- Tick Data Operations ---
    
    def save_tick_data(self, tick_data: Dict[str, Any]) -> TickData:
        """Save a single tick data point to the database"""
        try:
            tick = TickData(
                id=f"{tick_data['symbol']}_{tick_data['timestamp']}",
                symbol=tick_data['symbol'],
                timestamp=pd.to_datetime(tick_data['timestamp']),
                price=float(tick_data['price']),
                size=float(tick_data['size'])
            )
            self.db.add(tick)
            self.db.commit()
            return tick
        except Exception as e:
            self.db.rollback()
            logger.error(f"Error saving tick data: {e}")
            raise
    
    def get_latest_tick(self, symbol: str) -> Optional[Dict[str, Any]]:
        """Get the most recent tick for a symbol"""
        tick = self.db.query(TickData)\
            .filter(TickData.symbol == symbol)\
            .order_by(TickData.timestamp.desc())\
            .first()
        
        if tick:
            return {
                'symbol': tick.symbol,
                'timestamp': tick.timestamp,
                'price': tick.price,
                'size': tick.size
            }
        return None
    
    def get_ticks_in_range(
        self, 
        symbol: str, 
        start_time: datetime, 
        end_time: datetime
    ) -> List[Dict[str, Any]]:
        """Get all ticks for a symbol within a time range"""
        ticks = self.db.query(TickData)\
            .filter(
                TickData.symbol == symbol,
                TickData.timestamp >= start_time,
                TickData.timestamp <= end_time
            )\
            .order_by(TickData.timestamp)\
            .all()
        
        return [{
            'symbol': t.symbol,
            'timestamp': t.timestamp,
            'price': t.price,
            'size': t.size
        } for t in ticks]
    
    # --- Resampled Data Operations ---
    
    def resample_and_save(self, symbol: str, interval: str):
        """Resample tick data and save OHLCV data for the specified interval"""
        if interval not in TIMEFRAMES:
            raise ValueError(f"Unsupported interval: {interval}. Must be one of {list(TIMEFRAMES.keys())}")
        
        # Get the most recent resampled data point for this symbol and interval
        latest_resampled = self.db.query(ResampledData)\
            .filter(
                ResampledData.symbol == symbol,
                ResampledData.interval == interval
            )\
            .order_by(ResampledData.timestamp.desc())\
            .first()
        
        # Get the start time for resampling (last resampled timestamp or None)
        start_time = latest_resampled.timestamp if latest_resampled else None
        
        # Get raw tick data since the last resampled point
        query = self.db.query(TickData)\
            .filter(TickData.symbol == symbol)
            
        if start_time:
            query = query.filter(TickData.timestamp > start_time)
        
        # Convert to pandas DataFrame for resampling
        df = pd.read_sql(
            query.statement,
            self.db.bind,
            parse_dates=['timestamp'],
            index_col='timestamp'
        )
        
        if df.empty:
            logger.info(f"No new tick data to resample for {symbol} {interval}")
            return
        
        # Resample to OHLCV
        ohlcv = df['price'].resample(TIMEFRAMES[interval]).ohlc()
        ohlcv['volume'] = df['size'].resample(TIMEFRAMES[interval]).sum()
        ohlcv['vwap'] = (df['price'] * df['size']).resample(TIMEFRAMES[interval]).sum() / \
                        df['size'].resample(TIMEFRAMES[interval]).sum()
        
        # Save resampled data
        for ts, row in ohlcv.iterrows():
            # Skip if we already have this timestamp (can happen with the first point)
            if start_time and ts <= start_time:
                continue
                
            resampled_data = ResampledData(
                id=f"{symbol}_{interval}_{ts.isoformat()}",
                symbol=symbol,
                interval=interval,
                timestamp=ts,
                open=row['open'],
                high=row['high'],
                low=row['low'],
                close=row['close'],
                volume=row['volume'],
                vwap=row['vwap']
            )
            self.db.merge(resampled_data)
        
        self.db.commit()
    
    def get_ohlcv(
        self, 
        symbol: str, 
        interval: str, 
        start_time: Optional[datetime] = None,
        end_time: Optional[datetime] = None,
        limit: int = 1000
    ) -> pd.DataFrame:
        """Get OHLCV data for a symbol and interval"""
        query = self.db.query(ResampledData)\
            .filter(ResampledData.symbol == symbol)\
            .filter(ResampledData.interval == interval)
        
        if start_time:
            query = query.filter(ResampledData.timestamp >= start_time)
        if end_time:
            query = query.filter(ResampledData.timestamp <= end_time)
        
        query = query.order_by(ResampledData.timestamp.desc()).limit(limit)
        
        df = pd.read_sql(
            query.statement,
            self.db.bind,
            parse_dates=['timestamp']
        )
        
        if not df.empty:
            df = df.sort_values('timestamp')
            df.set_index('timestamp', inplace=True)
            
        return df
    
    # --- Analytics Operations ---
    
    def save_analytics_result(
        self,
        metric: str,
        symbol1: str,
        value: float,
        timestamp: datetime,
        symbol2: Optional[str] = None,
        interval: str = '1m',
        additional_data: Optional[Dict] = None
    ) -> AnalyticsResults:
        """Save the result of an analytics computation"""
        result_id = f"{symbol1}_{symbol2 or ''}_{metric}_{interval}_{timestamp.isoformat()}"
        
        result = AnalyticsResults(
            id=result_id,
            symbol1=symbol1,
            symbol2=symbol2,
            metric=metric,
            interval=interval,
            timestamp=timestamp,
            value=value,
            additional_data=json.dumps(additional_data) if additional_data else None
        )
        
        try:
            self.db.merge(result)
            self.db.commit()
            return result
        except Exception as e:
            self.db.rollback()
            logger.error(f"Error saving analytics result: {e}")
            raise
    
    def get_analytics(
        self,
        metric: str,
        symbol1: str,
        symbol2: Optional[str] = None,
        interval: str = '1m',
        start_time: Optional[datetime] = None,
        end_time: Optional[datetime] = None,
        limit: int = 1000
    ) -> pd.DataFrame:
        """Get analytics results for a metric and symbols"""
        query = self.db.query(AnalyticsResults)\
            .filter(AnalyticsResults.metric == metric)\
            .filter(AnalyticsResults.symbol1 == symbol1)\
            .filter(AnalyticsResults.interval == interval)
        
        if symbol2 is not None:
            query = query.filter(AnalyticsResults.symbol2 == symbol2)
        
        if start_time:
            query = query.filter(AnalyticsResults.timestamp >= start_time)
        if end_time:
            query = query.filter(AnalyticsResults.timestamp <= end_time)
        
        query = query.order_by(AnalyticsResults.timestamp.desc()).limit(limit)
        
        results = query.all()
        
        if not results:
            return pd.DataFrame()
        
        # Convert to DataFrame
        data = [{
            'timestamp': r.timestamp,
            'value': r.value,
            'additional_data': json.loads(r.additional_data) if r.additional_data else {}
        } for r in results]
        
        df = pd.DataFrame(data)
        if not df.empty:
            df = df.sort_values('timestamp')
            df.set_index('timestamp', inplace=True)
        
        return df
    
    # --- Alert Operations ---
    
    def create_alert(
        self,
        name: str,
        condition: str,
        symbol: str,
        is_active: bool = True
    ) -> Alert:
        """Create a new alert"""
        alert = Alert(
            id=f"alert_{symbol}_{name}_{datetime.now(pytz.utc).timestamp()}",
            name=name,
            condition=condition,
            symbol=symbol,
            is_active=is_active
        )
        
        try:
            self.db.add(alert)
            self.db.commit()
            return alert
        except Exception as e:
            self.db.rollback()
            logger.error(f"Error creating alert: {e}")
            raise
    
    def get_active_alerts(self) -> List[Alert]:
        """Get all active alerts"""
        return self.db.query(Alert)\
            .filter(Alert.is_active == True)\
            .all()
    
    def trigger_alert(self, alert_id: str) -> None:
        """Mark an alert as triggered"""
        alert = self.db.query(Alert).filter(Alert.id == alert_id).first()
        if alert:
            alert.triggered_at = datetime.now(pytz.utc)
            self.db.commit()
    
    # --- Maintenance Operations ---
    
    def cleanup_old_data(self, days_to_keep: int = 30) -> None:
        """Remove data older than the specified number of days"""
        cutoff = datetime.now(pytz.utc) - timedelta(days=days_to_keep)
        
        try:
            # Delete old tick data
            self.db.query(TickData)\
                .filter(TickData.timestamp < cutoff)\
                .delete(synchronize_session=False)
            
            # Delete old resampled data (keep only the most recent interval for each symbol)
            # This is more complex and might be better handled with a stored procedure
            # For now, we'll just delete old resampled data
            self.db.query(ResampledData)\
                .filter(ResampledData.timestamp < cutoff)\
                .delete(synchronize_session=False)
            
            # Keep all analytics results for now
            
            self.db.commit()
            logger.info(f"Cleaned up data older than {cutoff}")
        except Exception as e:
            self.db.rollback()
            logger.error(f"Error cleaning up old data: {e}")
            raise

# Singleton instance
db_manager = DatabaseManager()
