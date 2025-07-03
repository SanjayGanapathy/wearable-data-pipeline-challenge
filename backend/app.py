import os
from datetime import datetime, timedelta
from typing import Optional, List, Dict, Any

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
import psycopg2  # For PostgreSQL connection
import numpy as np  # For median calculation in imputation
import pandas as pd  # To easily handle time series data for imputation

app = FastAPI(
    title="Wearable Data Backend API",
    description="API to fetch time-series wearable data from TimescaleDB.",
    version="0.1.0",
)

# --- CORS Middleware (Crucial for Frontend) ---
# This allows your frontend (running on a different port/origin) to call this backend API.

origins = [
    "http://localhost",
    "http://localhost:8000",
    "http://localhost:8001",
    "http://localhost:8081",
    "http://127.0.0.1",
    "http://127.0.0.1:8000",
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
    table_override: Optional[str] = Query(
        None, include_in_schema=False
    ),  # Internal parameter to force table selection
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
        raise HTTPException(
            status_code=400, detail="Invalid date format. Use YYYY-MM-DD."
        )

    if start_dt >= end_dt:
        raise HTTPException(
            status_code=400, detail="Start date must be before end date."
        )

    # Determine the duration of the query in days
    duration_days = (end_dt - start_dt).days

    # --- Dynamic Table Selection Logic ---
    table_name = "raw_data"
    select_column = "value_numeric"  # Default for raw_data

    if (
        table_override
    ):  # If override is provided (e.g., from /data/imputed), use it directly
        table_name = table_override
        # Determine select_column based on table_override (assuming 'avg_value_numeric' for aggregates)
        select_column = (
            "value_numeric" if table_name == "raw_data" else "avg_value_numeric"
        )
    else:  # Otherwise, use dynamic logic based on duration
        # Heuristics for choosing aggregate table based on query duration
        # These thresholds can be tuned based on performance testing
        if duration_days > 30:  # More than a month: use daily aggregate
            table_name = "data_1d"
            select_column = (
                "avg_value_numeric"  # Aggregates store average for numeric values
            )
        elif duration_days > 7:  # More than a week: use hourly aggregate
            table_name = "data_1h"
            select_column = "avg_value_numeric"
        elif duration_days > 1:  # More than a day: use minute aggregate
            table_name = "data_1m"
            select_column = "avg_value_numeric"
        # For 1 day or less, use raw_data

    print(
        f"Backend: Querying {table_name} for {metric} from {start_date} to {end_date} for {user_id}"
    )

    # Connect to DB
    conn = get_db_connection()
    cursor = conn.cursor()
    results = []
    total_count = 0

    try:
        # For continuous aggregates, the time column is named 'bucket'
        time_column_name_in_db = "bucket" if table_name != "raw_data" else "timestamp"

        # Conditionally select value_text or NULL for aggregates
        value_text_select = (
            "value_text" if table_name == "raw_data" else "NULL AS value_text"
        )

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
        data_query += ";"  # Add semicolon

        cursor.execute(data_query, (user_id, metric, start_dt, end_dt))

        # Fetch results and format for JSON response
        for row in cursor.fetchall():
            results.append(
                {
                    "timestamp": row[0].isoformat(),  # Convert datetime to ISO string
                    "value_numeric": row[1],
                    "value_text": row[2],  # Will be null for aggregated numeric metrics
                }
            )

        return {
            "data": results,
            "total_count": total_count,
        }  # Return data and total count

    except psycopg2.Error as e:
        print(f"Database query error: {e}")
        raise HTTPException(status_code=500, detail=f"Database query failed: {e}")
    finally:
        cursor.close()
        conn.close()


# --- NEW API Endpoint for Imputed Data ---
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
    Supports 'linear' interpolation or 'median_rolling' (for rolling median).
    """
    # First, get the raw data using the existing logic, forcing 'raw_data' table
    # Imputation needs raw, unaggregated data with original missing points.
    raw_response = await get_time_series_data(
        start_date=start_date,
        end_date=end_date,
        user_id=user_id,
        metric=metric,
        limit=None,  # Fetch all raw data for the range for imputation
        offset=None,
        table_override="raw_data",  # Force querying raw_data for imputation
    )
    raw_data = raw_response["data"]  # Extract 'data' from the response

    if not raw_data:
        return []  # No data to impute

    filtered_raw_data = [d for d in raw_data if d.get("data_type") == metric]

    if not filtered_raw_data:
        print(
            f"DEBUG IMPUTE: No raw data found for metric '{metric}'. Returning empty."
        )
        return []  # No data for this metric to impute

    df = pd.DataFrame(filtered_raw_data)  # Use the filtered data for DataFrame creation

    # Convert to DataFrame for easier time series manipulation
    df = pd.DataFrame(raw_data)
    df["timestamp"] = pd.to_datetime(df["timestamp"])
    df = df.set_index("timestamp")
    print(
        f"DEBUG IMPUTE: DataFrame columns AFTER set_index but BEFORE rename: {df.columns.tolist()}"
    )
    print(f"DEBUG IMPUTE: Metric requested: {metric}")

    if metric in [
        "heart_rate",
        "steps",
        "calories",
        "sleep_total_minutes",
        "sleep_deep_minutes",
        "sleep_light_minutes",
        "sleep_rem_minutes",
        "sleep_wake_minutes",
    ]:
        df.rename(columns={"value_numeric": metric}, inplace=True)

    print(f"DEBUG IMPUTE: DataFrame columns AFTER rename: {df.columns.tolist()}")
    print(f"DEBUG IMPUTE: Does '{metric}' exist in columns? {metric in df.columns}")

    # Store original values to later identify imputed points
    original_values = df[metric].copy()

    # Create a complete time series index if fill_gaps is True
    if fill_gaps:
        # Infer frequency from data (e.g., if 1-minute data, freq='1min')
        # For synthetic data, it's hourly, so '1H' might be better for realistic gaps
        # A more robust solution would infer frequency from data or use a parameter.
        # For this example, assuming hourly data from synthetic generator:
        freq = "1H"

        # Create a full time index covering the range of data at the inferred frequency
        full_index = pd.date_range(start=df.index.min(), end=df.index.max(), freq=freq)
        df = df.reindex(full_index)

    # Apply imputation
    imputed_df = df.copy()
    imputed_df["is_imputed"] = False  # Default to not imputed for all rows

    # Flag original missing values (where the metric column is NaN)
    original_missing_mask = imputed_df[metric].isna()

    # Apply imputation based on chosen method
    # .fillna() only fills NaNs, so original non-NaN values are preserved
    if imputation_method == "linear":
        imputed_df[metric] = imputed_df[metric].interpolate(method="linear")
        print(f"Applying linear interpolation for {metric}.")
    elif imputation_method == "median_rolling":
        # Ensure window_size is odd for center=True and min_periods is reasonable
        window_size_rolling = 5
        imputed_df[metric] = imputed_df[metric].fillna(
            imputed_df[metric]
            .rolling(window=window_size_rolling, center=True, min_periods=1)
            .median()
        )
        print(
            f"Applying rolling median imputation for {metric} with window {window_size_rolling}."
        )
    else:
        raise HTTPException(
            status_code=400,
            detail="Invalid imputation method. Choose 'linear' or 'median_rolling'.",
        )

    # Flag newly imputed values (where it was missing BEFORE imputation AND now has a value)
    # Reindex original_values to match the full_index after reindex()
    # This comparison needs careful handling for NaNs.
    # Imputed points are those that were NaN in the original_values and are now not NaN in imputed_df
    reindexed_original_values = original_values.reindex(imputed_df.index)
    imputed_mask = reindexed_original_values.isna() & imputed_df[metric].notna()
    imputed_df.loc[imputed_mask, "is_imputed"] = True

    # Convert back to list of dicts for response
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
                ),  # Preserve value_text if exists
                "is_imputed": row[
                    "is_imputed"
                ].item(),  # .item() to convert numpy.bool_ to Python bool
            }
        )

    return response_data
