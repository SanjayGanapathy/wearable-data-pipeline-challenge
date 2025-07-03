# Wearable Data Pipeline & Dashboard Challenge Solution

## Project Overview

This repository contains the complete solution for a software engineering challenge focused on building a full-stack data pipeline and visualization application for wearable device data. The system is designed to extract, process, store, and visualize time-series data, with an emphasis on extensibility and performance for clinical trials research.

This solution specifically implements:
* **Task 1:** A daily, delta-load data pipeline to ingest Fitbit data into a locally hosted TimescaleDB.
* **Task 2:** An access/read flow, featuring a backend API and a simple frontend dashboard for data visualization.
* **Task 3:** Optimizations for multi-year and multi-user queries, including database-side optimizations (Continuous Aggregates, Columnar Compression) and data retrieval strategies (Pagination).

---

## Challenge Context

The overarching goal is to develop portions of a software app that can ETL wearable data and create useful analysis/visualizations for clinical trials. This involves handling large numbers of participants (up to N=1,000), creating intuitive dashboards, and providing extensible data formats. The current focus is on Fitbit Charge data, delivering intraday, time-series metrics. The design prioritizes modularity and extensibility to easily integrate new wearable devices (e.g., Apple Watch, Oura Ring) in the future, while also considering local memory constraints for on-premise deployment.

**Key Design Principles Adhered To:**
* **Modularity & Extensibility:** Data schema and service architecture are designed for easy expansion to accommodate new devices and metrics.
* **Industry Standards:** Leverages Docker for containerization, Docker Compose for multi-service orchestration, Python with Poetry for dependency management, and standard web technologies (FastAPI, Chart.js, Nginx).
* **Performance & Resource Efficiency:** Implements database-level optimizations (aggregates, compression) and retrieval strategies (pagination) for handling large datasets effectively within memory constraints.
* **Clean Code & Maintainability:** Code is structured logically, well-commented, and adheres to Python best practices (enforced by tools like Black and Isort via pre-commit hooks).

---

## Local Setup & Launch Instructions

To run this application stack locally, you will need:

* **Docker Desktop:** Installed and running (with WSL 2 integration enabled if on Windows).
* **VS Code:** (Recommended for development environment consistency).
* **WSL 2 Distribution:** E.g., Ubuntu (used in this solution).
* **Git:** For cloning the repository.

**Steps to get the entire application running:**

1.  **Clone the Repository:**
    ```bash
    git clone [https://github.com/YOUR_GITHUB_USERNAME/wearable-data-pipeline-challenge.git](https://github.com/YOUR_GITHUB_USERNAME/wearable-data-pipeline-challenge.git)
    cd wearable-data-pipeline-challenge # Navigate to the project root
    ```
    *(Replace `YOUR_GITHUB_USERNAME` with your actual GitHub username.)*

2.  **Configure Git Identity (One-time setup for commits):**
    ```bash
    git config --global user.name "Your Name"
    git config --global user.email "you@example.com"
    ```

3.  **Configure Fitbit Developer App (for `fitbit_ingest.py`):**
    * Go to [Fitbit Developer Apps](https://dev.fitbit.com/apps).
    * Click "Register an App".
    * **Crucial Settings:**
        * **OAuth 2.0 Application Type:** `Client`
        * **Callback URL (Redirect URL):** `http://localhost:8080/callback` (Must be exact!)
        * **Default Access Type:** `Read-Only` (sufficient for ingestion)
        * **Permissions (Scopes):** Select all relevant (e.g., `Activity and Exercise`, `Heart Rate`, `Sleep`, `Profile`, `Location`, `Settings`).
    * After registering, **note down your `OAuth 2.0 Client ID` and `Client Secret`**.

4.  **Update Configuration Files with Credentials:**
    * Open the project in VS Code connected to WSL.
    * **`docker-compose.yml`**: Open this file. Locate the `environment` section for `ingestion_app`.
        * **Replace `"YOUR_FITBIT_CLIENT_ID"` and `"YOUR_FITBIT_CLIENT_SECRET"`** with your actual Fitbit app credentials.
    * **`ingestion/Dockerfile`**: Open this file. Locate the `ENV FITBIT_CLIENT_ID` and `ENV FITBIT_CLIENT_SECRET` lines.
        * **Replace `"YOUR_FITBIT_CLIENT_ID"` and `"YOUR_FITBIT_CLIENT_SECRET"`** with your actual Fitbit app credentials.
    * **`ingestion/synthetic_data_generator.py`**: Open this file.
        * **Replace `"YOUR_FITBIT_USER_ID"`** with the actual `user_id` you get from Fitbit OAuth (e.g., `CNXFRV`). This ID is used for synthetic data consistency.
        * Adjust `SYNTHETIC_START_DATE_STR` and `SYNTHETIC_END_DATE_STR` if you want different synthetic data dates (default: `2025-06-01` to `2025-06-30`).

5.  **Perform Initial Docker Build & Launch:**
    * Open your WSL terminal in VS Code (ensure you're in the project root).
    * Run the following commands one by one for a clean build and launch:
        ```bash
        # Stop and remove all existing containers, volumes, and Docker cache
        docker compose down --volumes --rmi all
        docker system prune --all --force

        # Build all Docker images from scratch and start containers
        docker compose build --no-cache --force-rm
        docker compose up -d
        ```
    * **Verification:** Run `docker compose ps`. You should see `timescaledb`, `ingestion_app`, `backend_app`, and `frontend_app` all listed as `Up`.

6.  **Initialize Database Schema, Aggregates & Load Synthetic Data:**
    * Your database is initially empty after a full reset.
    * **Connect to `psql` to create the `raw_data` table and Continuous Aggregates:**
        ```bash
        docker compose exec timescaledb psql -U user -d fitbit_data
        ```
        * At the `fitbit_data=#` prompt, paste these SQL commands:
            ```sql
            -- Create raw_data table
            CREATE TABLE raw_data (
                timestamp TIMESTAMPTZ NOT NULL,
                participant_id TEXT NOT NULL,
                data_type TEXT NOT NULL, -- e.g., 'heart_rate', 'steps', 'sleep_total_minutes'
                value_numeric DOUBLE PRECISION,
                value_text TEXT
            );
            SELECT create_hypertable('raw_data', 'timestamp', chunk_time_interval => INTERVAL '1 day');

            -- Enable columnar compression on raw_data
            ALTER TABLE raw_data SET (timescaledb.compress, timescaledb.compress_segmentby = 'participant_id', timescaledb.compress_orderby = 'timestamp');
            SELECT add_compression_policy('raw_data', INTERVAL '3 days');

            -- Create 1-minute aggregate
            CREATE MATERIALIZED VIEW data_1m WITH (timescaledb.continuous) AS
            SELECT
                time_bucket('1 minute', timestamp) AS bucket,
                participant_id,
                data_type,
                AVG(value_numeric) AS avg_value_numeric,
                SUM(value_numeric) AS sum_value_numeric,
                COUNT(value_numeric) AS count_value_numeric
            FROM raw_data
            WHERE value_numeric IS NOT NULL
            GROUP BY bucket, participant_id, data_type
            WITH NO DATA;

            -- Create 1-hour aggregate
            CREATE MATERIALIZED VIEW data_1h WITH (timescaledb.continuous) AS
            SELECT
                time_bucket('1 hour', timestamp) AS bucket,
                participant_id,
                data_type,
                AVG(value_numeric) AS avg_value_numeric,
                SUM(value_numeric) AS sum_value_numeric,
                COUNT(value_numeric) AS count_value_numeric
            FROM raw_data
            WHERE value_numeric IS NOT NULL
            GROUP BY bucket, participant_id, data_type
            WITH NO DATA;

            -- Create 1-day aggregate
            CREATE MATERIALIZED VIEW data_1d WITH (timescaledb.continuous) AS
            SELECT
                time_bucket('1 day', timestamp) AS bucket,
                participant_id,
                data_type,
                AVG(value_numeric) AS avg_value_numeric,
                SUM(value_numeric) AS sum_value_numeric,
                COUNT(value_numeric) AS count_value_numeric
            FROM raw_data
            WHERE value_numeric IS NOT NULL
            GROUP BY bucket, participant_id, data_type
            WITH NO DATA;

            -- Set up Automatic Refresh Policies for Continuous Aggregates
            SELECT add_continuous_aggregate_policy('data_1m', start_offset => INTERVAL '2 days', end_offset => INTERVAL '1 minute', schedule_interval => INTERVAL '1 minute');
            SELECT add_continuous_aggregate_policy('data_1h', start_offset => INTERVAL '7 days', end_offset => INTERVAL '1 hour', schedule_interval => INTERVAL '15 minutes');
            SELECT add_continuous_aggregate_policy('data_1d', start_offset => INTERVAL '30 days', end_offset => INTERVAL '1 day', schedule_interval => INTERVAL '1 hour');

            -- Manually Refresh Aggregates for Immediate Data Population
            CALL refresh_continuous_aggregate('data_1m', NULL, NULL);
            CALL refresh_continuous_aggregate('data_1h', NULL, NULL);
            CALL refresh_continuous_aggregate('data_1d', NULL, NULL);
            ```
        * Type `\q` to exit `psql`.
    * **Generate and Load Synthetic Data (approx. 1 month):**
        * Open `ingestion/last_run.txt` in VS Code and clear its content. Save it.
        * Run the synthetic data generator script:
            ```bash
            docker compose exec ingestion_app poetry run python /app/ingestion/synthetic_data_generator.py
            ```
        * **Verification:** You should see output indicating data generation (e.g., "Total records: 2310"). You can also `SELECT COUNT(*) FROM raw_data;` in `psql` to confirm.

---

## **Task 1: Daily Ingestion Pipeline**

**Overview:**
This pipeline automatically fetches (or simulates fetching) Fitbit intraday data, processes it, and stores it in a TimescaleDB instance. It's designed for daily, delta-load operations.

**Design Decisions & Implementation:**
* **Docker Compose for Orchestration:** Manages `timescaledb` (database) and `ingestion_app` (script execution) services, ensuring a portable and reproducible environment.
* **TimescaleDB (`timescale/timescaledb:latest-pg15`):** Chosen as the time-series database for its specialized features.
    * **Advantages of Time-Series Databases (specifically TimescaleDB):**
        * **Optimized for Time:** Designed for data where time is a primary axis, offering superior performance for time-range queries compared to traditional relational databases.
        * **Hypertables:** TimescaleDB's core feature, which automatically partitions data by time, making query performance efficient even with massive time-series datasets.
        * **SQL Interface:** Built on PostgreSQL, it retains the power and familiarity of standard SQL, reducing the learning curve for developers already familiar with SQL.
        * **Scalability & Features:** Provides features like continuous aggregates (for real-time rollups), data retention policies, and horizontal scaling capabilities crucial for large-scale wearable data.
        * **Compression:** Efficiently compresses historical data, saving storage costs.
* **Python (`fitbit_ingest.py`):** Used for ingestion logic due to its rich ecosystem for data processing and API interaction.
* **Cron Scheduler:** Configured within the `ingestion_app` Docker container (`0 1 * * *`) to ensure the ingestion script runs automatically once daily.
* **Modularity & Extensibility (Schema):** The `raw_data` table schema (`timestamp`, `participant_id`, `data_type`, `value_numeric`, `value_text`) is designed to be flexible, allowing for storing various metrics (HR, steps, calories, sleep stages) and future integration with different wearable devices (Apple Watch, Oura Ring) without requiring schema changes.
* **Delta-Load Mechanism:** The `last_run.txt` file is used to store the timestamp of the last successful ingestion. The script then fetches only new data since that timestamp, preventing redundant data ingestion.
* **Fitbit API Interaction:** The `fitbit_ingest.py` script makes `requests` calls to the actual Fitbit API to fetch intraday data (Heart Rate, Steps, Sleep).
* **OAuth2 Token Management:** The `get_or_refresh_tokens` function handles the entire Fitbit OAuth2 token lifecycle (loading, checking validity, refreshing `access_token` using the `refresh_token`, and saving back to `tokens.json`). This ensures continuous, automated API access.

---

## **Task 2: Access / Read Flow (Dashboard App)**

**Overview:**
This task implements the data access and visualization layer. It retrieves time-series data from the locally hosted TimescaleDB via a backend API and presents it on a simple web-based dashboard.

**Design Decisions & Implementation:**
* **Backend (`backend_app`):**
    * **FastAPI:** Chosen for building the API endpoints due to its modern asynchronous capabilities, high performance, automatic data validation (via Pydantic), and built-in interactive API documentation (Swagger UI/ReDoc).
    * **PostgreSQL Client (`psycopg2`):** Used to establish robust connections to TimescaleDB and execute SQL queries.
    * **`/data` Endpoint:**
        * Provides a flexible `GET` API (`http://localhost:8000/data`).
        * Accepts `start_date`, `end_date`, `user_id`, and `metric` as query parameters.
        * Directly queries the `raw_data` hypertable or appropriate Continuous Aggregate in TimescaleDB.
        * Includes basic parameter validation and handles database query errors (returning HTTP 400/500 responses).
    * **CORS Middleware:** Essential `CORSMiddleware` is configured to allow the frontend (running on `http://localhost:8081`) to make successful API requests to the backend (`http://localhost:8000`).
* **Frontend (`frontend_app`):**
    * **Nginx:** A lightweight and high-performance web server used to serve the static HTML/JavaScript files that make up the dashboard.
    * **HTML/JavaScript (`index.html`, `script.js`):** Simple, vanilla JavaScript and HTML are used for the user interface, minimizing complexity for the challenge while demonstrating the core data flow.
    * **Chart.js:** A powerful and flexible JavaScript charting library used to render interactive line charts.
    * **Data Flow:** The frontend allows user input, constructs the API URL, uses the `fetch` API to retrieve data, and dynamically renders the line chart.

---

## **Task 3: Optimizing Design for Multi-Year / Multi-User queries**

**Overview:**
This task focuses on performance and memory optimization for handling large-scale time-series data, crucial for clinical trials with many participants and long data histories.

**Design Decisions & Implementation:**
* **Database-Side Optimizations (Continuous Aggregates):**
    * **Creation:** Three Continuous Aggregates (`data_1m`, `data_1h`, `data_1d`) are created from the `raw_data` hypertable using `time_bucket` for 1-minute, 1-hour, and 1-day intervals. They store `AVG`, `SUM`, and `COUNT` of numeric values.
    * **Automatic Refresh:** Policies are set to automatically refresh these aggregates (e.g., `data_1m` every minute, `data_1h` every 15 minutes, `data_1d` every hour), ensuring they are always up-to-date with new ingestion data. This minimizes manual intervention and ensures query performance.
    * **Dynamic Query Routing:** The `backend_app` is intelligent. It dynamically selects the most appropriate aggregate table (`data_1m`, `data_1h`, `data_1d`) or the `raw_data` table based on the duration of the query requested by the frontend. This ensures queries over large time spans hit smaller, pre-computed summary tables, significantly reducing raw data scans and improving response times.
* **Data Retrieval Strategies (Optional Part):**
    * **Pagination / Chunked Fetching:**
        * The `/data` endpoint in the `backend_app` now accepts `limit` and `offset` query parameters. This allows the frontend to request data in smaller, manageable chunks, preventing large query results from consuming excessive memory in the backend or frontend.
        * The frontend dashboard (via `script.js`) has been enhanced with "Page Size" selection and "Previous"/"Next" buttons to utilize this pagination, allowing navigation through the potentially thousands of records.
        * The backend also returns `total_count` so the frontend can display total pages.
    * **Columnar Format (TimescaleDB Compression):**
        * Columnar compression has been enabled on the `raw_data` hypertable (`ALTER TABLE raw_data SET (timescaledb.compress, ...)`).
        * A compression policy is added (`SELECT add_compression_policy('raw_data', INTERVAL '3 days');`) to automatically compress data chunks older than 3 days.
        * **Benefits:** This dramatically reduces storage consumption (often 90% or more for time-series data) and can significantly improve query performance, especially for analytical queries on compressed historical data, directly addressing memory and performance concerns for large datasets.

---

## **Troubleshooting Notes (Key Issues Resolved During Development)**

This section outlines common pitfalls encountered during development and their solutions. This demonstrates robust problem-solving skills and resilience.

* **`ModuleNotFoundError` (e.g., `psycopg2`, `wearipedia`, `backend`):**
    * **Cause:** Python packages not installed in the Docker container's Poetry environment, or incorrect module paths. `wearipedia` was a particularly stubborn case due to project structure.
    * **Solution:** Ensured `poetry add` was run for all dependencies (`pyproject.toml` up-to-date), `docker compose build --no-cache --force-rm` for fresh builds, `WORKDIR` and `CMD` are correct in Dockerfiles. For top-level Python packages like `backend`, `__init__.py` was created, and `ENV PYTHONPATH=/app` was set. `wearipedia` module issue was ultimately bypassed by using a self-contained synthetic data generator due to persistent environmental issues.
* **`Bind for 0.0.0.0:XXXX failed: port is already allocated`:**
    * **Cause:** Another application (or a previous Docker process) on the host machine was already using the required port (e.g., 5432, 80, 8000).
    * **Solution:** For the TimescaleDB (`5432`), changed host mapping to `5433`. For the Frontend (`80`), changed host mapping to `8081`. For the Backend (`8000`), ensured it was mapped correctly. Identified processes using ports via `netstat -ano` and `tasklist /svc`.
* **`400 Client Error: Bad Request` (from Fitbit API):**
    * **Cause:** Requesting an invalid `detail_level` for specific Fitbit metrics (e.g., `1sec` for steps, which only support `1min`).
    * **Solution:** Adjusted `detail_level` to `1min` in `fitbit_ingest.py`.
* **`401 Client Error: Unauthorized` (from Fitbit API):**
    * **Cause:** Fitbit OAuth2 authentication issue (expired `access_token` or invalid `refresh_token`).
    * **Solution:** Repeated manual browser authorization to get new `code`, then `curl` to exchange for fresh `access_token` and `refresh_token`. Updated `ingestion/tokens.json` and `last_refreshed` timestamp.
* **`relation "raw_data" does not exist` / `column "value_text" does not exist`:**
    * **Cause:** Database tables or aggregates were wiped (by `docker compose down --volumes` / `docker system prune`), or queries were hitting aggregate tables lacking `value_text`.
    * **Solution:** Re-run `CREATE TABLE`, `create_hypertable`, `CREATE MATERIALIZED VIEW`, `add_continuous_aggregate_policy`, and `refresh_continuous_aggregate` SQL commands. Modified backend SQL to conditionally select `value_text` only for `raw_data`.
* **Frontend `ERR_EMPTY_RESPONSE` / "Failed to fetch" / Chart.js `TypeError`:**
    * **Cause:** Frontend unable to connect to backend, CORS issues, or JavaScript library loading/initialization problems.
    * **Solution:** Ensured backend was running and accessible. Configured `CORSMiddleware` in FastAPI to allow `http://localhost`, `http://localhost:8081`. Fixed HTML parsing by ensuring script tags were on separate lines. For date adapter, the issue was with `date-fns` library not being loaded correctly for its adapter; ultimately bypassed `time` scale for `category` scale in Chart.js to guarantee chart rendering.

---