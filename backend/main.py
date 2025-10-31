import uvicorn
from fastapi import FastAPI, Depends
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
import os
from pathlib import Path

import sys
from pathlib import Path

# Add the backend directory to the Python path
sys.path.append(str(Path(__file__).parent.absolute()))

# Now import using absolute imports
from api.routes import router as api_router
from database.models import init_db
from config import LOGGING_CONFIG, DATA_DIR
import logging.config

# Configure logging
logging.config.dictConfig(LOGGING_CONFIG)
logger = logging.getLogger(__name__)

# Initialize the database
init_db()

# Create FastAPI app
app = FastAPI(
    title="Trading Analytics API",
    description="Real-time trading analytics and alerting system",
    version="1.0.0",
    docs_url="/api/docs",
    redoc_url="/api/redoc",
    openapi_url="/api/openapi.json"
)

# Configure CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # In production, replace with the actual frontend URL
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include API routes
app.include_router(api_router, prefix="/api")

# Serve static files for the frontend
frontend_dir = os.path.join(Path(__file__).parent.parent, "frontend")
if os.path.exists(frontend_dir):
    app.mount("/", StaticFiles(directory=frontend_dir, html=True), name="frontend")

@app.on_event("startup")
async def startup_event():
    """Run on application startup"""
    logger.info("Starting Trading Analytics API...")
    
    # Ensure data directory exists
    DATA_DIR.mkdir(exist_ok=True, parents=True)
    
    logger.info("Trading Analytics API is ready")

@app.on_event("shutdown")
async def shutdown_event():
    """Run on application shutdown"""
    logger.info("Shutting down Trading Analytics API...")

@app.get("/api/health")
async def health_check():
    """Health check endpoint"""
    return {"status": "ok", "timestamp": datetime.now(pytz.utc).isoformat()}

if __name__ == "__main__":
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True, reload_dirs=[str(Path(__file__).parent.absolute())])
