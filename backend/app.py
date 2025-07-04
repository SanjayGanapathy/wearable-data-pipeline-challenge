# backend/app.py

import os
from prometheus_client import Counter, make_asgi_app
from starlette.middleware.base import BaseHTTPMiddleware
import time
import pandas as pd
import asyncpg
from fastapi import FastAPI, HTTPException, Query, Depends
from fastapi.responses import FileResponse
from pydantic import BaseModel
from statsmodels.tsa.arima.model import ARIMA
from typing import List, Dict, Any
from sklearn.impute import KNNImputer
from datetime import datetime
from prometheus_fastapi_instrumentator import Instrumentator


# Database Connection
DATABASE_URL = "postgresql://user:password@timescaledb:5432/fitbit_data"


async def get_db():
    """Provides a database connection to endpoints."""
    conn = await asyncpg.connect(DATABASE_URL)
    try:
        yield conn
    finally:
        await conn.close()


app = FastAPI()

# This line creates the instrumentator
instrumentator = Instrumentator().instrument(app)

# This line exposes the /metrics endpoint
instrumentator.expose(app)

# Create a custom counter metric

http_requests_total = Counter(
    "http_requests_total",
    "Total number of HTTP requests",
    ["method", "endpoint", "status_code"],
)


class PrometheusMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request, call_next):
        start_time = time.time()
        response = await call_next(request)

        endpoint = (
            request.scope.get("route").path
            if request.scope.get("route")
            else request.scope.get("path")
        )

        http_requests_total.labels(
            method=request.method,
            endpoint=endpoint,
            status_code=str(response.status_code),
        ).inc()

        return response


# Add the middleware to the app
app.add_middleware(PrometheusMiddleware)

# Create a separate app for the /metrics endpoint
metrics_app = make_asgi_app()
app.mount("/metrics", metrics_app)

# Pydantic Models

class TimeSeriesData(BaseModel):
    timestamp: str
    value_numeric: float | None = None
    value_text: str | None = None


class DataResponse(BaseModel):
    data: List[TimeSeriesData]
    total: int


class ContactPayload(BaseModel):
    user_id: str
    reason: str


# Helper Functions


async def insert_data_to_db(data: List[Dict[str, Any]], table_name: str):
    """Helper function to bulk insert records into a specified table."""
    if not data:
        return
    conn = await asyncpg.connect(DATABASE_URL)
    try:
        columns = data[0].keys()
        values = [tuple(d.values()) for d in data]
        await conn.copy_records_to_table(
            table_name, records=values, columns=list(columns)
        )
    finally:
        await conn.close()


# API Endpoints


@app.get("/data", response_model=DataResponse)
async def get_time_series_data(
    start_date: str,
    end_date: str,
    user_id: str,
    metric: str,
    limit: int = 50,
    offset: int = 0,
    db: asyncpg.Connection = Depends(get_db),
):
    """Fetches paginated raw time-series data from the database."""
    query = """
    SELECT timestamp, value_numeric, value_text
    FROM raw_data
    WHERE participant_id = $1 AND data_type = $2 AND timestamp BETWEEN $3 AND $4
    ORDER BY timestamp
    LIMIT $5 OFFSET $6;
    """
    count_query = """
    SELECT COUNT(*)
    FROM raw_data
    WHERE participant_id = $1 AND data_type = $2 AND timestamp BETWEEN $3 AND $4;
    """
    try:
        rows = await db.fetch(
            query, user_id, metric, start_date, end_date, limit, offset
        )
        total_count = await db.fetchval(
            count_query, user_id, metric, start_date, end_date
        )
        return {"data": [dict(row) for row in rows], "total": total_count}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Database query failed: {e}")


@app.post("/data/run_imputation", status_code=200)
async def run_and_store_imputation(
    user_id: str,
    metric: str,
    start_date: str = "2024-01-01",
    end_date: str = "2025-12-31",
    db: asyncpg.Connection = Depends(get_db),
):
    """
    (FINAL, NaN CORRECTED) Imputes data using the best method.
    """
    # 1. Fetch and prepare data
    start_date_dt = datetime.fromisoformat(start_date)
    end_date_dt = datetime.fromisoformat(end_date)
    query = """
    SELECT "timestamp", value_numeric FROM raw_data
    WHERE participant_id = $1 AND data_type = $2 AND "timestamp" BETWEEN $3 AND $4
    ORDER BY "timestamp";
    """
    raw_data_records = await db.fetch(
        query, user_id, metric, start_date_dt, end_date_dt
    )
    raw_data = [dict(record) for record in raw_data_records]

    if not raw_data:
        raise HTTPException(status_code=404, detail="No raw data found.")

    df = (
        pd.DataFrame(raw_data)
        .groupby("timestamp")
        .mean()
        .reset_index()
        .set_index("timestamp")
    )
    df.rename(columns={"value_numeric": metric}, inplace=True)

    # 2. Resample and create gaps
    df_resampled = df.resample("h").asfreq()

    # 3. Choose imputation method
    if metric in ["heart_rate"]:  # Use ARIMA for continuous signals
        imputed_data_list = []
        is_missing = df_resampled[metric].isna()
        if not is_missing.any():
            return {"message": "No gaps found to impute."}
        gaps = (is_missing != is_missing.shift()).cumsum()

        for gap_id in gaps[is_missing].unique():
            gap = df_resampled[gaps == gap_id]
            train_start, train_end = gap.index.min() - pd.Timedelta(
                hours=24
            ), gap.index.min() - pd.Timedelta(hours=1)
            train_data = df[train_start:train_end][metric].dropna()

            if len(train_data) < 12:
                continue

            try:
                model = ARIMA(train_data, order=(5, 1, 0)).fit()
                forecast = model.forecast(steps=len(gap))
                imputed_gap = pd.DataFrame(
                    {"timestamp": gap.index, "value_numeric": forecast}
                )
                imputed_data_list.append(imputed_gap)
            except Exception:
                continue

        if not imputed_data_list:
            return {"message": "Imputation failed for all gaps."}
        final_imputed_df = pd.concat(imputed_data_list)

    else:  # Use ffill and bfill for sparse data like steps
        original_indices = df_resampled[metric].dropna().index

        df_resampled[metric].fillna(method="ffill", inplace=True)  # First, forward-fill
        df_resampled[metric].fillna(
            method="bfill", inplace=True
        )  # Then, back-fill any remaining NaNs

        imputed_mask = ~df_resampled.index.isin(original_indices)
        final_imputed_df = df_resampled[imputed_mask].reset_index()
        final_imputed_df.rename(
            columns={"index": "timestamp", metric: "value_numeric"}, inplace=True
        )

    # 4. Save results
    if final_imputed_df.empty:
        return {"message": "No values were imputed."}

    final_imputed_df.dropna(inplace=True)  # Ensure no NaNs are saved
    final_imputed_df["participant_id"] = user_id
    final_imputed_df["data_type"] = metric
    final_imputed_df["value_text"] = None
    final_imputed_df["is_imputed"] = True

    await insert_data_to_db(final_imputed_df.to_dict("records"), "imputed_data")

    return {
        "message": f"Successfully imputed and stored {len(final_imputed_df)} points for {user_id} - {metric}."
    }


@app.post("/contact/participant")
async def handle_contact_form(payload: ContactPayload):
    """Handles the form submission from the contact page."""
    user_id = payload.user_id
    reason = payload.reason
    email_address = f"{user_id}@example.com"  # Placeholder
    subject = "A Note About Your Study Participation"

    if reason == "low_adherence":
        body = f"Hello {user_id},\n\nWe've noticed a drop in your recent data uploads. Please ensure your Fitbit is charged and syncing regularly.\n\nThank you,\nThe Research Team"
    elif reason == "low_sleep":
        body = f"Hello {user_id},\n\nWe've noticed a low sleep score in your recent data. Please ensure you are wearing your device while sleeping.\n\nThank you,\nThe Research Team"
    else:
        body = f"Hello {user_id},\n\nWe're contacting you regarding your study participation. If you have any questions, please reach out.\n\nThank you,\nThe Research Team"

    print("--- SIMULATING EMAIL ---")
    print(f"TO: {email_address}")
    print(f"SUBJECT: {subject}")
    print(f"BODY: {body}")
    print("------------------------")

    return {"message": f"Contact message queued for {user_id}."}


@app.get("/contact", response_class=FileResponse)
async def read_contact_page():
    """Serves the contact.html page."""
    # This assumes contact.html is in the same directory as app.py
    file_path = os.path.join(os.path.dirname(__file__), "contact.html")
    return FileResponse(file_path)
