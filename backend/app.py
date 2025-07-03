import os
from datetime import datetime, timedelta
from typing import Optional, List, Dict, Any

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
import psycopg2  # For PostgreSQL connection

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
    "http://localhost",  # Frontend typically runs on default port 80
    "http://localhost:8081", # Frontend runs on 8081 for this setup
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["GET"],  # Allow GET requests
    allow_headers=["*"],  # Allow all headers
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
            host=DB_HOST, database=DB_NAME, user=DB_USER, password=DB_PASSWORD
        )
        return conn
    except Exception as e:
        print(f"Database connection error: {e}")
        raise HTTPException(status_code=500, detail=f"Database connection failed: {e}")


# --- API Endpoint ---
@app.get("/data", response_model=Dict[str, Any]) # Response model changed to Dict for total_count
async def get_time_series_data(
    start_date: str = Query(..., description="Start date (YYYY-MM-DD)"),
    end_date: str = Query(..., description="End date (YYYY-MM-DD)"),
    user_id: str = Query(..., description="Participant user ID"),
    metric: str = Query(
        ..., description="Metric to fetch (e.g., heart_rate, steps, sleep_total_minutes)"
    ),
    limit: Optional[int] = Query(None, description="Maximum number of records to return (for pagination)"),
    offset: Optional[int] = Query(None, description="Number of records to skip (for pagination)")
):
    """
    Fetches time-series data from TimescaleDB for a given participant, date range, and metric,
    automatically selecting the most appropriate aggregate table, with optional pagination.
    """
    try:
        start_dt = datetime.strptime(start_date, "%Y-%m-%d")
        # Add 1 day to end_dt to make the query range inclusive up to the end of end_date
        end_dt = datetime.strptime(end_date, "%Y-%m-%d") + timedelta(days=1)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid date format. Use Wayback Machine-MM-DD.")

    if start_dt >= end_dt:
        raise HTTPException(status_code=400, detail="Start date must be before end date.")

    # Determine the duration of the query in days
    duration_days = (end_dt - start_dt).days

    # --- Dynamic Table Selection Logic ---
    table_name = "raw_data"
    select_column = "value_numeric"  # Default for raw_data
    
    # Heuristics for choosing aggregate table based on query duration
    # These thresholds can be tuned based on performance testing
    if duration_days > 30: # More than a month: use daily aggregate
        table_name = "data_1d"
        select_column = "avg_value_numeric" # Aggregates store average for numeric values
    elif duration_days > 7: # More than a week: use hourly aggregate
        table_name = "data_1h"
        select_column = "avg_value_numeric"
    elif duration_days > 1: # More than a day: use minute aggregate
        table_name = "data_1m"
        select_column = "avg_value_numeric"
    # For 1 day or less, use raw_data

    print(f"Backend: Querying {table_name} for {metric} from {start_date} to {end_date} for {user_id}")

    # Connect to DB
    conn = get_db_connection()
    cursor = conn.cursor()
    results = []
    total_count = 0

    try:
        # For continuous aggregates, the time column is named 'bucket'
        time_column_name_in_db = "bucket" if table_name != "raw_data" else "timestamp"

        # Conditionally select value_text or NULL for aggregates
        value_text_select = "value_text" if table_name == "raw_data" else "NULL AS value_text"

        # Query to get total count for pagination metadata
        count_query = f"""
        SELECT COUNT(*)
        FROM {table_name}
        WHERE
            participant_id = %s AND
            data_type = %s AND
            {time_column_name_in_db} >= %s AND
            {time_column_name_in_db} < %s;
        """
        cursor.execute(count_query, (user_id, metric, start_dt, end_dt))
        total_count = cursor.fetchone()[0]

        # Main data query with LIMIT and OFFSET
        data_query = f"""
        SELECT
            {time_column_name_in_db},
            {select_column},
            {value_text_select}
        FROM
            {table_name}
        WHERE
            participant_id = %s AND
            data_type = %s AND
            {time_column_name_in_db} >= %s AND
            {time_column_name_in_db} < %s
        ORDER BY
            {time_column_name_in_db}
        """
        # Add LIMIT and OFFSET if provided
        if limit is not None:
            data_query += f" LIMIT {limit}"
        if offset is not None:
            data_query += f" OFFSET {offset}"
        data_query += ";" # Add semicolon

        cursor.execute(data_query, (user_id, metric, start_dt, end_dt))
        
        # Fetch results and format for JSON response
        for row in cursor.fetchall():
            results.append({
                "timestamp": row[0].isoformat(), # Convert datetime to ISO string
                "value_numeric": row[1],
                "value_text": row[2] # Will be null for aggregated numeric metrics
            })
        
        return {"data": results, "total_count": total_count} # Return data and total count

    except psycopg2.Error as e:
        print(f"Database query error: {e}")
        raise HTTPException(status_code=500, detail=f"Database query failed: {e}")
    finally:
        cursor.close()
        conn.close()