from fastapi import APIRouter, HTTPException, Depends, Query
from fastapi.responses import JSONResponse, StreamingResponse
from typing import List, Optional, Dict, Any
from datetime import datetime, timedelta
import pandas as pd
import json
import io
import pytz

from database.db_manager import DatabaseManager, get_db
from database.models import Alert
from config import TIMEFRAMES, ZSCORE_THRESHOLD

router = APIRouter()

@router.get("/symbols")
async def get_symbols(db: DatabaseManager = Depends(get_db)) -> List[str]:
    """Get list of all available symbols"""
    # Get unique symbols from tick data
    from sqlalchemy import text
    result = db.execute(text("SELECT DISTINCT symbol FROM tick_data"))
    symbols = [row[0] for row in result.fetchall()]
    return sorted(symbols)

@router.get("/ticks/{symbol}")
async def get_ticks(
    symbol: str,
    start_time: Optional[datetime] = None,
    end_time: Optional[datetime] = None,
    limit: int = 1000,
    db: DatabaseManager = Depends(get_db)
) -> List[Dict[str, Any]]:
    """Get tick data for a symbol"""
    if not start_time:
        start_time = datetime.now(pytz.utc) - timedelta(hours=24)
    if not end_time:
        end_time = datetime.now(pytz.utc)
    
    # Get database session
    from sqlalchemy.orm import Session
    if not isinstance(db, Session):
        db = next(get_db())
        
    # Use DatabaseManager to get ticks
    db_manager = DatabaseManager(db)
    ticks = db_manager.get_ticks_in_range(symbol, start_time, end_time)[:limit]
    return [{
        'timestamp': t['timestamp'].isoformat(),
        'price': t['price'],
        'size': t['size']
    } for t in ticks]

@router.get("/ohlcv/{symbol}")
async def get_ohlcv(
    symbol: str,
    interval: str = '1m',
    start_time: Optional[datetime] = None,
    end_time: Optional[datetime] = None,
    limit: int = 1000,
    db: DatabaseManager = Depends(get_db)
) -> List[Dict[str, Any]]:
    """Get OHLCV data for a symbol and interval"""
    if interval not in TIMEFRAMES:
        raise HTTPException(status_code=400, detail=f"Invalid interval. Must be one of: {list(TIMEFRAMES.keys())}")
    
    # Get database session
    from sqlalchemy.orm import Session
    if not isinstance(db, Session):
        db = next(get_db())
        
    # Use DatabaseManager to get OHLCV data
    db_manager = DatabaseManager(db)
    df = db_manager.get_ohlcv(symbol, interval, start_time, end_time, limit)
    
    if df.empty:
        return []
    
    # Convert DataFrame to list of dicts
    data = []
    for idx, row in df.iterrows():
        data.append({
            'timestamp': idx.isoformat(),
            'open': row['open'],
            'high': row['high'],
            'low': row['low'],
            'close': row['close'],
            'volume': row['volume'],
            'vwap': row.get('vwap', None)
        })
    
    return data

@router.get("/analytics/{symbol1}")
async def get_analytics(
    symbol1: str,
    symbol2: Optional[str] = None,
    metric: str = 'all',
    interval: str = '1m',
    start_time: Optional[datetime] = None,
    end_time: Optional[datetime] = None,
    limit: int = 1000,
    db: DatabaseManager = Depends(get_db)
) -> Dict[str, Any]:
    """Get analytics for a symbol or symbol pair"""
    if not start_time:
        start_time = datetime.now(pytz.utc) - timedelta(hours=24)
    if not end_time:
        end_time = datetime.now(pytz.utc)
    
    result = {}
    
    if metric in ['all', 'single'] or not symbol2:
        # Get single symbol analytics
        metrics = ['volatility', 'returns_zscore'] if metric == 'all' else [metric]
        
        for m in metrics:
            # Get database session and manager
            from sqlalchemy.orm import Session
            if not isinstance(db, Session):
                db = next(get_db())
                
            db_manager = DatabaseManager(db)
            df = db_manager.get_analytics(m, symbol1, None, interval, start_time, end_time, limit)
            if not df.empty:
                result[m] = [{
                    'timestamp': idx.isoformat(),
                    'value': row['value'],
                    **row['additional_data']
                } for idx, row in df.iterrows()]
    
    if symbol2 and (metric in ['all', 'pair'] or metric in ['correlation', 'hedge_ratio', 'spread_zscore']):
        # Get pair analytics
        metrics = ['correlation', 'hedge_ratio', 'spread_zscore'] if metric in ['all', 'pair'] else [metric]
        
        for m in metrics:
            # Get database session and manager
            from sqlalchemy.orm import Session
            if not isinstance(db, Session):
                db = next(get_db())
                
            db_manager = DatabaseManager(db)
            df = db_manager.get_analytics(m, symbol1, symbol2, interval, start_time, end_time, limit)
            if not df.empty:
                result[f"{symbol1}_{symbol2}_{m}"] = [{
                    'timestamp': idx.isoformat(),
                    'value': row['value'],
                    **row['additional_data']
                } for idx, row in df.iterrows()]
    
    return result

@router.get("/export/csv")
async def export_data(
    symbol: str,
    data_type: str = 'ohlcv',
    interval: str = '1m',
    start_time: Optional[datetime] = None,
    end_time: Optional[datetime] = None,
    db: DatabaseManager = Depends(get_db)
):
    """Export data as CSV"""
    if not start_time:
        start_time = datetime.now(pytz.utc) - timedelta(hours=24)
    if not end_time:
        end_time = datetime.now(pytz.utc)
    
    if data_type == 'ohlcv':
        # Get database session and manager
        from sqlalchemy.orm import Session
        if not isinstance(db, Session):
            db = next(get_db())
            
        db_manager = DatabaseManager(db)
        df = db_manager.get_ohlcv(symbol, interval, start_time, end_time)
        if df.empty:
            raise HTTPException(status_code=404, detail="No data found for the given parameters")
        
        # Create CSV in memory
        stream = io.StringIO()
        df.to_csv(stream, index_label='timestamp')
        
        # Create response
        response = StreamingResponse(
            iter([stream.getvalue()]),
            media_type="text/csv",
            headers={
                "Content-Disposition": f"attachment; filename={symbol}_{interval}_{start_time.date()}_to_{end_time.date()}.csv"
            }
        )
        return response
    
    elif data_type == 'analytics':
        # Get all available metrics
        metrics = ['volatility', 'returns_zscore']
        result = {}
        
        for metric in metrics:
            # Get database session and manager
            from sqlalchemy.orm import Session
            if not isinstance(db, Session):
                db = next(get_db())
                
            db_manager = DatabaseManager(db)
            df = db_manager.get_analytics(metric, symbol, None, interval, start_time, end_time)
            if not df.empty:
                result[metric] = df
        
        if not result:
            raise HTTPException(status_code=404, detail="No analytics data found")
        
        # Combine all metrics into a single DataFrame
        combined = pd.concat(result.values(), axis=1)
        combined.columns = result.keys()
        
        # Create CSV in memory
        stream = io.StringIO()
        combined.to_csv(stream, index_label='timestamp')
        
        # Create response
        response = StreamingResponse(
            iter([stream.getvalue()]),
            media_type="text/csv",
            headers={
                "Content-Disposition": f"attachment; filename={symbol}_analytics_{start_time.date()}_to_{end_time.date()}.csv"
            }
        )
        return response
    
    else:
        raise HTTPException(status_code=400, detail="Invalid data_type. Must be 'ohlcv' or 'analytics'")

@router.get("/alerts", response_model=List[Dict[str, Any]])
async def get_alerts(
    active_only: bool = True,
    symbol: Optional[str] = None,
    db: DatabaseManager = Depends(get_db)
) -> List[Dict[str, Any]]:
    """Get all alerts"""
    from sqlalchemy.orm import Session
    if not isinstance(db, Session):
        db = next(get_db())
        
    query = db.query(Alert)
    
    # Apply filters
    if active_only:
        query = query.filter(Alert.is_active == True)
    if symbol:
        query = query.filter(Alert.symbol == symbol.upper())
        
    # Execute query and return results
    alerts = query.order_by(Alert.created_at.desc()).all()
    return [
        {
            "id": alert.id,
            "name": alert.name,
            "condition": alert.condition,
            "symbol": alert.symbol,
            "is_active": alert.is_active,
            "created_at": alert.created_at.isoformat(),
            "triggered_at": alert.triggered_at.isoformat() if alert.triggered_at else None
        }
        for alert in alerts
    ]

@router.post("/alerts", status_code=201)
async def create_alert(
    name: str,
    condition: str,
    symbol: str,
    is_active: bool = True,
    db: DatabaseManager = Depends(get_db)
) -> Dict[str, str]:
    """Create a new alert"""
    try:
        # Get database session and manager
        from sqlalchemy.orm import Session
        if not isinstance(db, Session):
            db = next(get_db())
            
        db_manager = DatabaseManager(db)
        alert = db_manager.create_alert(name, condition, symbol.upper(), is_active)
        return {"status": "success", "alert_id": alert.id}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

@router.put("/alerts/{alert_id}/trigger")
async def trigger_alert(
    alert_id: str,
    db: DatabaseManager = Depends(get_db)
) -> Dict[str, str]:
    """Mark an alert as triggered"""
    # Get database session
    from sqlalchemy.orm import Session
    if not isinstance(db, Session):
        db = next(get_db())
        
    alert = db.query(Alert).filter(Alert.id == alert_id).first()
    if not alert:
        raise HTTPException(status_code=404, detail="Alert not found")
    
    # Get database session and manager
    from sqlalchemy.orm import Session
    if not isinstance(db, Session):
        db = next(get_db())
        
    db_manager = DatabaseManager(db)
    db_manager.trigger_alert(alert_id)
    return {"status": "success", "message": f"Alert {alert_id} triggered"}

@router.delete("/alerts/{alert_id}")
async def delete_alert(
    alert_id: str,
    db: DatabaseManager = Depends(get_db)
) -> Dict[str, str]:
    """Delete an alert"""
    # Get database session
    from sqlalchemy.orm import Session
    if not isinstance(db, Session):
        db = next(get_db())
        
    alert = db.query(Alert).filter(Alert.id == alert_id).first()
    if not alert:
        raise HTTPException(status_code=404, detail="Alert not found")
    
    try:
        db.delete(alert)
        db.commit()
        return {"status": "success", "message": f"Alert {alert_id} deleted"}
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=400, detail=str(e))
