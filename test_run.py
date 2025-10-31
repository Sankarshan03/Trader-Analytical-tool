import sys
import os
from pathlib import Path

# Add the backend directory to the Python path
sys.path.append(str(Path(__file__).parent / "backend"))

# Now we can import from the backend
from backend.main import app
from backend.database.models import init_db

if __name__ == "__main__":
    print("Testing database initialization...")
    try:
        init_db()
        print("✅ Database initialized successfully!")
    except Exception as e:
        print(f"❌ Error initializing database: {e}")
    
    print("\nTo start the backend server, run:")
    print("cd Trader-Analytical-tool/backend")
    print("python -m uvicorn main:app --reload")
    
    print("\nTo start the frontend, open a new terminal and run:")
    print("cd Trader-Analytical-tool/frontend")
    print("streamlit run app.py")
