import os
from datetime import datetime, timedelta
from typing import Optional, List, Dict, Any

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
import psycopg2
import numpy as np
import pandas as pd

app = FastAPI(
    title="Wearable Data Backend API",
    description="API to fetch time-series wearable data from TimescaleDB.",
    version="0.1.0",
)

# --- CORS Middleware (Crucial for Frontend) ---
origins = [
    "http://localhost",
    "http://localhost:8000",
    "http://localhost:8081",
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["GET"],
    allow_headers=["*"],
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


# --- API Endpoint for Raw/Aggregated Data ---
@app.get("/data", response_model=Dict[str, Any])
async def get_time_series_data(
    start_date: str = Query(..., description="Start date (YYYY-MM-DD)"),
    end_date: str = Query(..., description="End date (YYYY-MM-DD)"),
    user_id: str = Query(..., description="Participant user ID"),
    metric: str = Query(
        ...,
        description="Metric to fetch (e.g., heart_rate, steps, sleep_total_minutes)",
    ),
    limit: Optional[int] = Query(
        None, description="Maximum number of records to return (for pagination)"
    ),
    offset: Optional[int] = Query(
        None, description="Number of records to skip (for pagination)"
    ),
    table_override: Optional[str] = Query(None, include_in_schema=False),
):
    """
    Fetches time-series data from TimescaleDB for a given participant, date range, and metric,
    automatically selecting the most appropriate aggregate table, with optional pagination.
    """
    try:
        start_dt = datetime.strptime(start_date, "%Y-%m-%d")
        end_dt = datetime.strptime(end_date, "%Y-%m-%d") + timedelta(days=1)
    except ValueError:
        raise HTTPException(
            status_code=400, detail="Invalid date format. Use YYYY-MM-DD."
        )

    if start_dt >= end_dt:
        raise HTTPException(
            status_code=400, detail="Start date must be before end date."
        )

    duration_days = (end_dt - start_dt).days

    table_name = "raw_data"
    select_column = "value_numeric"

    if table_override:
        table_name = table_override
        select_column = (
            "value_numeric" if table_name == "raw_data" else "avg_value_numeric"
        )
    else:
        if duration_days > 30:
            table_name = "data_1d"
            select_column = "avg_value_numeric"
        elif duration_days > 7:
            table_name = "data_1h"
            select_column = "avg_value_numeric"
        elif duration_days > 1:
            table_name = "data_1m"
            select_column = "avg_value_numeric"

    conn = get_db_connection()
    cursor = conn.cursor()
    results = []
    total_count = 0

    try:
        time_column_name_in_db = "bucket" if table_name != "raw_data" else "timestamp"
        value_text_select = (
            "value_text" if table_name == "raw_data" else "NULL AS value_text"
        )

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
        if limit is not None:
            data_query += f" LIMIT {limit}"
        if offset is not None:
            data_query += f" OFFSET {offset}"
        data_query += ";"

        cursor.execute(data_query, (user_id, metric, start_dt, end_dt))

        for row in cursor.fetchall():
            results.append(
                {
                    "timestamp": row[0].isoformat(),
                    "value_numeric": row[1],
                    "value_text": row[2],
                }
            )

        return {"data": results, "total_count": total_count}

    except psycopg2.Error as e:
        raise HTTPException(status_code=500, detail=f"Database query failed: {e}")
    finally:
        cursor.close()
        conn.close()


# --- API Endpoint for Imputed Data ---
@app.get("/data/imputed", response_model=List[Dict[str, Any]])
async def get_imputed_time_series_data(
    start_date: str = Query(..., description="Start date (YYYY-MM-DD)"),
    end_date: str = Query(..., description="End date (YYYY-MM-DD)"),
    user_id: str = Query(..., description="Participant user ID"),
    metric: str = Query(..., description="Metric to fetch (e.g., heart_rate, steps)"),
    window_size: int = Query(
        5, description="Window size for median imputation (number of neighbors)"
    ),
    fill_gaps: bool = Query(
        True, description="Whether to fill gaps in the time series for imputation"
    ),
    imputation_method: str = Query(
        "linear", description="Imputation method: 'linear', 'median_rolling'"
    ),
):
    """
    Fetches time-series data, applies median imputation, and flags imputed values.
    """
    raw_response = await get_time_series_data(
        start_date=start_date,
        end_date=end_date,
        user_id=user_id,
        metric=metric,
        limit=None,
        offset=None,
        table_override="raw_data",
    )
    raw_data = raw_response["data"]

    if not raw_data:
        return []

    df = pd.DataFrame(raw_data)
    df.drop_duplicates(subset=["timestamp"], keep="first", inplace=True)
    df["timestamp"] = pd.to_datetime(df["timestamp"])
    df = df.set_index("timestamp")

    if metric in df.columns:
        original_values = df[metric].copy()
    else:
        # Fallback to value_numeric if the metric column doesn't exist after rename
        df.rename(columns={"value_numeric": metric}, inplace=True)
        original_values = df[metric].copy()

    if fill_gaps:
        # Using 'h' for hourly frequency, which is the correct format for pandas
        full_index = pd.date_range(start=df.index.min(), end=df.index.max(), freq="h")
        df = df.reindex(full_index)

    imputed_df = df.copy()
    imputed_df["is_imputed"] = False

    if imputation_method == "linear":
        imputed_df[metric] = imputed_df[metric].interpolate(method="linear")
    elif imputation_method == "median_rolling":
        imputed_df[metric] = imputed_df[metric].fillna(
            imputed_df[metric].rolling(window=5, center=True, min_periods=1).median()
        )
    else:
        raise HTTPException(
            status_code=400,
            detail="Invalid imputation method. Choose 'linear' or 'median_rolling'.",
        )

    reindexed_original_values = original_values.reindex(imputed_df.index)
    imputed_mask = reindexed_original_values.isna() & imputed_df[metric].notna()
    imputed_df.loc[imputed_mask, "is_imputed"] = True

    response_data = []
    for timestamp, row in imputed_df.iterrows():
        response_data.append(
            {
                "timestamp": timestamp.isoformat(),
                "value_numeric": row[metric] if pd.notna(row[metric]) else None,
                "value_text": (
                    row["value_text"]
                    if "value_text" in row and pd.notna(row["value_text"])
                    else None
                ),
                "is_imputed": row["is_imputed"],
            }
        )

    return response_data
