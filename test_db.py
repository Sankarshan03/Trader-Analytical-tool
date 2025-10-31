from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker
import os

# Database URL - make sure this matches your configuration
DATA_DIR = os.path.join(os.path.dirname(__file__), 'data')
if not os.path.exists(DATA_DIR):
    os.makedirs(DATA_DIR, exist_ok=True)

DATABASE_URL = f"sqlite:///{os.path.join(DATA_DIR, 'trading_analytics.db')}"

# Create engine and session
engine = create_engine(DATABASE_URL)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

def check_tables():
    """Check if tables exist and count rows"""
    with engine.connect() as conn:
        # List all tables
        tables = conn.execute(text("""
            SELECT name FROM sqlite_master 
            WHERE type='table' AND name NOT LIKE 'sqlite_%';
        """)).fetchall()
        
        if not tables:
            print("No tables found in the database!")
            return
            
        print("\nFound tables:")
        for table in tables:
            table_name = table[0]
            try:
                count = conn.execute(text(f"SELECT COUNT(*) FROM {table_name}")).scalar()
                print(f"- {table_name}: {count} rows")
                
                # Show first few rows if table is not empty
                if count > 0:
                    rows = conn.execute(text(f"SELECT * FROM {table_name} LIMIT 3")).fetchall()
                    print(f"  Sample data: {rows}")
                    
            except Exception as e:
                print(f"  Error reading {table_name}: {str(e)}")

if __name__ == "__main__":
    print(f"Database path: {DATABASE_URL}")
    check_tables()
