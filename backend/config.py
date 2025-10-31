import os
from pathlib import Path
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

# Base directory
BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / "data"

# Ensure data directory exists
DATA_DIR.mkdir(exist_ok=True)

# Database configuration
DATABASE_URL = f"sqlite:///{DATA_DIR}/trading_analytics.db"

# Binance WebSocket configuration
BINANCE_WS_URL = "wss://fstream.binance.com/ws/"

# Default symbols to track
DEFAULT_SYMBOLS = ["btcusdt", "ethusdt"]

# Timeframes for resampling
TIMEFRAMES = {
    "1s": "1S",
    "1m": "1T",
    "5m": "5T",
    "15m": "15T",
    "1h": "1H",
    "4h": "4H",
    "1d": "1D"
}

# Z-score parameters for alerts
ZSCORE_THRESHOLD = 2.0
ROLLING_WINDOW = 20

# Logging configuration
LOGGING_CONFIG = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "standard": {
            "format": "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
        },
    },
    "handlers": {
        "console": {
            "class": "logging.StreamHandler",
            "formatter": "standard",
            "level": "INFO",
            "stream": "ext://sys.stdout"
        },
        "file": {
            "class": "logging.handlers.RotatingFileHandler",
            "formatter": "standard",
            "filename": DATA_DIR / "trading_analytics.log",
            "maxBytes": 10485760,  # 10MB
            "backupCount": 5,
            "encoding": "utf8"
        }
    },
    "loggers": {
        "": {
            "handlers": ["console", "file"],
            "level": "INFO",
            "propagate": True
        }
    }
}
