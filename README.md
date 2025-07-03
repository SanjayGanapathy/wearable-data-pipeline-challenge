# Wearable Data Pipeline & Dashboard Challenge Solution

## Project Overview

This repository contains a comprehensive solution for a software engineering challenge focused on building a full-stack data pipeline and visualization application for wearable device data. The system is designed to extract, process, store, and visualize time-series data, with an emphasis on extensibility for clinical trials research.

This solution specifically implements:
* **Task 1:** A daily, delta-load data pipeline to ingest Fitbit data into a locally hosted TimescaleDB.
* **Task 2:** An access/read flow, featuring a backend API to query the database and a simple frontend dashboard for data visualization.

---

## Challenge Context

The primary goal is to simulate a robust system for handling wearable data, supporting scenarios with a large number of participants (up to N=1,000). The current focus is on Fitbit Charge data, delivering intraday, time-series metrics. The design prioritizes modularity and extensibility to easily integrate new wearable devices (e.g., Apple Watch, Oura Ring) in the future.

**Key Design Principles Adhered To:**
* **Modularity & Extensibility:** Data schema and service architecture are designed for easy expansion to accommodate new devices and metrics.
* **Industry Standards:** Leverages Docker for containerization, Docker Compose for multi-service orchestration, Python with Poetry for dependency management, and standard web technologies (FastAPI, Chart.js).
* **Clean Code & Maintainability:** Code is structured logically, well-commented, and adheres to Python best practices (enforced by tools like Black and Isort via pre-commit hooks).

---

## Local Setup & Launch Instructions

To run this application stack locally, you will need:

* **Docker Desktop:** Installed and running (with WSL 2 integration enabled if on Windows).
* **VS Code:** (Recommended for development environment consistency).
* **WSL 2 Distribution:** E.g., Ubuntu (used in this solution).
* **Git:** For cloning the repository.

**Steps to get the entire application running:**

1.  **Clone the Repository (This new challenge-specific repo):**
    ```bash
    git clone [https://github.com/SanjayGanapathy/wearable-data-pipeline-challenge.git](https://github.com/YOUR_GITHUB_USERNAME/wearable-data-pipeline-challenge.git)
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
    * Open the project in VS Code connected to WSL (`File > Open Folder...` and select your `~/wearable-data-pipeline-challenge` project root).
    * **`docker-compose.yml`**: Open this file. Locate the `environment` section for `ingestion_app`.
        * **Replace `"YOUR_FITBIT_CLIENT_ID"` and `"YOUR_FITBIT_CLIENT_SECRET"`** with your actual Fitbit app credentials.
    * **`ingestion/Dockerfile`**: Open this file. Locate the `ENV FITBIT_CLIENT_ID` and `ENV FITBIT_CLIENT_SECRET` lines.
        * **Replace `"YOUR_FITBIT_CLIENT_ID"` and `"YOUR_FITBIT_CLIENT_SECRET"`** with your actual Fitbit app credentials.
    * **`ingestion/synthetic_data_generator.py`**: Open this file.
        * **Replace `"YOUR_FITBIT_USER_ID"`** with the actual `user_id` you get from Fitbit OAuth (this is needed for consistency with synthetic data).
        * Adjust `SYNTHETIC_START_DATE_STR` and `SYNTHETIC_END_DATE_STR` if you want a different data generation range (default: June 2025).

5.  **Perform Initial Docker Build & Launch:**
    * Open your WSL terminal in VS Code (ensure you're in the project root: `~/wearable-data-pipeline-challenge$`).
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

6.  **Initialize Database Schema & Load Synthetic Data:**
    * Your database is initially empty.
    * **Connect to `psql` to create the `raw_data` table:**
        ```bash
        docker compose exec timescaledb psql -U user -d fitbit_data
        ```
        * At the `fitbit_data=#` prompt, paste these SQL commands:
            ```sql
            CREATE TABLE raw_data (
                timestamp TIMESTAMPTZ NOT NULL,
                participant_id TEXT NOT NULL,
                data_type TEXT NOT NULL, -- e.g., 'heart_rate', 'steps', 'sleep_total_minutes'
                value_numeric DOUBLE PRECISION,
                value_text TEXT
            );
            SELECT create_hypertable('raw_data', 'timestamp', chunk_time_interval => INTERVAL '1 day');
            ```
        * Type `\q` to exit `psql`.
    * **Generate and Load Synthetic Data (approx. 1 month):**
        * Open `ingestion/last_run.txt` in VS Code and clear its content (make it empty). Save it.
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
* **Docker Compose for Orchestration:** Manages `timescaledb` (database) and `ingestion_app` (script execution) services, ensuring portable and reproducible environment setup.
* **TimescaleDB (`timescale/timescaledb:latest-pg15`):** Chosen as the time-series database for its specialized features.
    * **Advantages of Time-Series Databases (specifically TimescaleDB):**
        * **Optimized for Time:** Designed for data where time is a primary axis, offering superior performance for time-range queries compared to traditional relational databases.
        * **Hypertables:** TimescaleDB's core feature, which automatically partitions data by time, making query performance efficient even with massive time-series datasets.
        * **SQL Interface:** Built on PostgreSQL, it retains the power and familiarity of standard SQL, reducing the learning curve for developers already familiar with SQL.
        * **Scalability & Features:** Provides features like continuous aggregates (for real-time rollups), data retention policies, and horizontal scaling capabilities crucial for large-scale wearable data.
        * **Compression:** Efficiently compresses historical data, saving storage costs.
* **Python (`fitbit_ingest.py`):** Used for ingestion logic due to its robust ecosystem for data processing and API interaction.
* **Cron Scheduler:** Configured within the `ingestion_app` Docker container (`0 1 * * *`) to ensure the ingestion script runs automatically once daily, as required.
* **Modularity & Extensibility (Schema):** The `raw_data` table schema (`timestamp`, `participant_id`, `data_type`, `value_numeric`, `value_text`) is designed to be flexible. It allows for storing various metrics (HR, steps, calories, sleep stages) and future integration with different wearable devices (Apple Watch, Oura Ring) without requiring schema changes.
* **Delta-Load Mechanism:** The `last_run.txt` file is used to store the timestamp of the last successful ingestion. The script then fetches only new data since that timestamp, preventing redundant data ingestion.
* **Fitbit API Interaction:** The `fitbit_ingest.py` script makes `requests` calls to the actual Fitbit API to fetch intraday data (Heart Rate, Steps, Sleep).
* **OAuth2 Token Management:** The `get_or_refresh_tokens` function handles the entire Fitbit OAuth2 token lifecycle (loading, checking validity, refreshing `access_token` using the `refresh_token`, and saving back to `tokens.json`). This ensures continuous, automated API access.

---

## **Task 2: Access / Read Flow (Dashboard App)**

**Overview:**
This implements the data access and visualization layer. It retrieves time-series data from the locally hosted TimescaleDB via a backend API and presents it on a simple web-based dashboard.

**Design Decisions & Implementation:**
* **Backend (`backend_app`):**
    * **FastAPI:** Chosen for building the API endpoints due to its modern asynchronous capabilities, high performance, automatic data validation (via Pydantic), and built-in interactive API documentation (Swagger UI/ReDoc).
    * **PostgreSQL Client (`psycopg2`):** Used to establish robust connections to TimescaleDB and execute SQL queries.
    * **`/data` Endpoint:**
        * Provides a flexible `GET` API (`http://localhost:8000/data`) for fetching time-series data.
        * Accepts `start_date`, `end_date`, `user_id`, and `metric` as query parameters.
        * Directly queries the `raw_data` hypertable in TimescaleDB.
        * Includes basic parameter validation and handles database query errors (returning HTTP 400/500 responses).
    * **CORS Middleware:** Essential `CORSMiddleware` is configured to allow the frontend application (running on a different port/origin, `http://localhost:8081`) to make successful API requests to the backend (`http://localhost:8000`).
* **Frontend (`frontend_app`):**
    * **Nginx:** A lightweight and high-performance web server used to serve the static HTML/JavaScript files that make up the dashboard.
    * **HTML/JavaScript (`index.html`, `script.js`):** Simple, vanilla JavaScript and HTML are used for the user interface, minimizing complexity for the challenge while demonstrating the core data flow.
    * **Chart.js:** A powerful and flexible JavaScript charting library used to render interactive line charts based on the fetched data.
    * **Data Flow:** The frontend allows user input for query parameters, constructs the API URL, uses the `fetch` API to retrieve data from the backend, and dynamically renders the line chart.

---

**Deliverables Checklist (as per challenge requirements):**

* **A working docker compose setup that runs an app that ingests data from the Fitbit API once daily (cron -> Python / Node.js -> Fitbit API -> TimescaleDB):** **YES.**
* **A working app launchable with a docker compose that serves data from the locally hosted TimescaleDB database:** **YES.**
* **README.md detailing configuration, schema, instructions:** **YES.** (This document itself).

---

## **Troubleshooting Notes (Key Issues Resolved During Development)**

This section outlines common pitfalls encountered during development and their solutions. This demonstrates robust problem-solving skills.

* **`ModuleNotFoundError` (e.g., `psycopg2`, `wearipedia`, `backend`):**
    * **Cause:** Python package not installed in the Docker container, or incorrect module path. `wearipedia` was a particularly stubborn case.
    * **Solution:** Ensure `poetry add` is run for all dependencies, `pyproject.toml`/`poetry.lock` are up-to-date, `docker compose build --no-cache --force-rm` is used for fresh builds, `WORKDIR` and `CMD` are correct in Dockerfiles. For `backend` module, ensure `backend/__init__.py` exists. For `wearipedia` specifically (when its code is part of the project), the issue was bypassed by using an independent synthetic data generator.
* **`Bind for 0.0.0.0:XXXX failed: port is already allocated`:**
    * **Cause:** Another application (or a previous Docker process) on the host machine is already using the required port (e.g., 5432 for DB, 8000 for backend, 80 for frontend).
    * **Solution:** Identify and stop the conflicting process (`netstat -ano`, `tasklist /svc`), or change the port mapping in `docker-compose.yml` (e.g., `5433:5432`, `8001:8000`, `8081:80`).
* **`400 Client Error: Bad Request` (from Fitbit API):**
    * **Cause:** Often caused by requesting an invalid `detail_level` for a specific Fitbit metric (e.g., `1sec` for steps, which might only be available at `1min`).
    * **Solution:** Adjust the requested `detail_level` in `fitbit_ingest.py` (e.