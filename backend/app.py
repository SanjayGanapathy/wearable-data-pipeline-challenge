import os
from datetime import datetime, timedelta
from typing import Optional, List, Dict, Any

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware # Needed for frontend
import psycopg2 # For PostgreSQL connection

app = FastAPI(
    title="Wearable Data Backend API",
    description="API to fetch time-series wearable data from TimescaleDB.",
    version="0.1.0",
)

# --- CORS Middleware (Crucial for Frontend) ---
# This allows your frontend (running on a different port/origin) to call this backend API.
origins = [
    "http://localhost:3000",  # Common port for React dev server
    "http://localhost:8080",  # Common port for other local dev servers
    "http://127.0.0.1:3000",
    "http://127.0.0.1:8080",
    "http://localhost",
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["GET"], # Allow GET requests
    allow_headers=["*"],   # Allow all headers
)

# --- Database Connection Details ---
DB_HOST = os.getenv("DB_HOST", "timescaledb")
DB_NAME = os.getenv("DB_NAME", "fitbit_data")
DB_USER = os.getenv("DB_USER", "user")
DB_PASSWORD = os.getenv("DB_PASSWORD", "password")

# --- Helper function to get database connection ---
def get_db_connection():
    try:
        conn = psycopg2.connect(
            host=DB_HOST,
            database=DB_NAME,
            user=DB_USER,
            password=DB_PASSWORD
        )
        return conn
    except Exception as e:
        print(f"Database connection error: {e}")
        raise HTTPException(status_code=500, detail=f"Database connection failed: {e}")

# --- API Endpoint ---
@app.get("/data", response_model=List[Dict[str, Any]])
async def get_time_series_data(
    start_date: str = Query(..., description="Start date (YYYY-MM-DD)"),
    end_date: str = Query(..., description="End date (YYYY-MM-DD)"),
    user_id: str = Query(..., description="Participant user ID"),
    metric: str = Query(..., description="Metric to fetch (e.g., heart_rate, steps, sleep_total_minutes)")
):
    """
    Fetches time-series data from TimescaleDB for a given participant, date range, and metric.
    """
    # Basic validation of date format (FastAPI Pydantic handles some, but good to ensure)
    try:
        start_dt = datetime.strptime(start_date, "%Y-%m-%d")
        end_dt = datetime.strptime(end_date, "%Y-%m-%d") + timedelta(days=1) # Include end_date fully
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid date format. Use YYYY-MM-DD.")

    if start_dt >= end_dt:
        raise HTTPException(status_code=400, detail="Start date must be before end date.")

    # Connect to DB
    conn = get_db_connection()
    cursor = conn.cursor()
    results = []

    try:
        query = """
        SELECT
            timestamp,
            value_numeric,
            value_text
        FROM
            raw_data
        WHERE
            participant_id = %s AND
            data_type = %s AND
            timestamp >= %s AND
            timestamp < %s
        ORDER BY
            timestamp;
        """
        cursor.execute(query, (user_id, metric, start_dt, end_dt))

        # Fetch results and format for JSON response
        for row in cursor.fetchall():
            results.append({
                "timestamp": row[0].isoformat(), # Convert datetime to ISO string
                "value_numeric": row[1],
                "value_text": row[2]
            })

        return results

    except psycopg2.Error as e:
        print(f"Database query error: {e}")
        raise HTTPException(status_code=500, detail=f"Database query failed: {e}")
    finally:
        cursor.close()
        conn.close()