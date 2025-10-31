import os
import sys
from pathlib import Path

# Add the backend directory to the Python path
sys.path.append(str(Path(__file__).parent.parent.absolute()))

from sqlalchemy import Column, String, Float, DateTime, create_engine, event, Boolean
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
from datetime import datetime
import pytz
from config import DATABASE_URL

# Create SQLAlchemy engine and session
engine = create_engine(DATABASE_URL, echo=False)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base = declarative_base()

def get_db():
    """Database session dependency"""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

class TickData(Base):
    """Raw tick data from Binance"""
    __tablename__ = 'tick_data'
    
    id = Column(String, primary_key=True)  # symbol_timestamp
    symbol = Column(String, index=True)
    timestamp = Column(DateTime(timezone=True), index=True)
    price = Column(Float)
    size = Column(Float)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(pytz.utc))
    
    def __repr__(self):
        return f"<TickData(symbol={self.symbol}, price={self.price}, size={self.size}, ts={self.timestamp})>"

class ResampledData(Base):
    """Resampled OHLCV data"""
    __tablename__ = 'resampled_data'
    
    id = Column(String, primary_key=True)  # symbol_interval_timestamp
    symbol = Column(String, index=True)
    interval = Column(String)  # e.g., '1m', '5m', '1h', etc.
    timestamp = Column(DateTime(timezone=True), index=True)
    open = Column(Float)
    high = Column(Float)
    low = Column(Float)
    close = Column(Float)
    volume = Column(Float)
    vwap = Column(Float)  # Volume Weighted Average Price
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(pytz.utc))
    
    def __repr__(self):
        return f"<ResampledData({self.symbol} {self.interval} {self.timestamp} O:{self.open} H:{self.high} L:{self.low} C:{self.close} V:{self.volume})>"

class AnalyticsResults(Base):
    """Stores precomputed analytics results"""
    __tablename__ = 'analytics_results'
    
    id = Column(String, primary_key=True)  # symbol1_symbol2_metric_interval_timestamp
    symbol1 = Column(String, index=True)
    symbol2 = Column(String, index=True, nullable=True)  # For pair metrics like correlation
    metric = Column(String)  # e.g., 'zscore', 'correlation', 'hedge_ratio'
    interval = Column(String)  # Timeframe
    timestamp = Column(DateTime(timezone=True), index=True)
    value = Column(Float)  # The computed metric value
    additional_data = Column(String, nullable=True)  # JSON string for additional data
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(pytz.utc))

class Alert(Base):
    """User-defined alerts"""
    __tablename__ = 'alerts'
    
    id = Column(String, primary_key=True)
    name = Column(String)
    condition = Column(String)  # e.g., "zscore > 2"
    symbol = Column(String, index=True)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(pytz.utc))
    triggered_at = Column(DateTime(timezone=True), nullable=True)
    
    def __repr__(self):
        return f"<Alert({self.name} - {self.condition} for {self.symbol})>"

def init_db():
    """Initialize the database with tables"""
    from sqlalchemy.sql import text
    
    # Create all tables
    Base.metadata.create_all(bind=engine)
    
    # Create indexes for better query performance
    with engine.connect() as conn:
        # Create index on tick_data timestamp and symbol
        conn.execute(text(
            "CREATE INDEX IF NOT EXISTS idx_tick_data_symbol_ts "
            "ON tick_data(symbol, timestamp)"
        ))
        
        # Create index on resampled_data for common query patterns
        conn.execute(text(
            "CREATE INDEX IF NOT EXISTS idx_resampled_data_symbol_interval_ts "
            "ON resampled_data(symbol, interval, timestamp)"
        ))
        
        # Commit the transaction
        conn.commit()

# Initialize the database when this module is imported
init_db()
