# Wearable Data Pipeline & Dashboard Challenge Solution

## Project Overview

This repository contains the complete solution for a software engineering challenge focused on building a full-stack data pipeline and visualization application for wearable device data. The system is designed to extract, process, store, and visualize time-series data, with an emphasis on extensibility and performance for clinical trials research.

This solution specifically implements:
* **Task 1:** A daily, delta-load data pipeline to ingest Fitbit data into a locally hosted TimescaleDB.
* **Task 2 & 3:** An access/read flow with a backend API, plus database-side optimizations (Continuous Aggregates, Compression) for handling large-scale queries.
* **Task 4:** A detailed **Grafana dashboard** for in-depth analysis, featuring an adherence overview, advanced data imputation, and a participant contact system.

---
## Challenge Context

The overarching goal is to develop portions of a software app that can ETL wearable data and create useful analysis/visualizations for clinical trials. This involves handling large numbers of participants (up to N=1,000), creating intuitive dashboards, and providing extensible data formats. The current focus is on Fitbit Charge data, delivering intraday, time-series metrics.

**Key Design Principles Adhered To:**
* **Modularity & Extensibility:** Data schema and service architecture are designed for easy expansion to accommodate new devices and metrics.
* **Industry Standards:** Leverages Docker for containerization, Docker Compose for multi-service orchestration, Python with Poetry for dependency management, and standard web technologies (FastAPI, Grafana).
* **Performance & Resource Efficiency:** Implements database-level optimizations and intelligent data imputation strategies.
* **Clean Code & Maintainability:** Code is structured logically and adheres to Python best practices.

---

## Local Setup & Launch Instructions

To run this application stack locally, you will need:

* **Docker Desktop:** Installed and running.
* **Python & Poetry:** For managing backend dependencies.
* **Git:** For cloning the repository.

**Steps to get the entire application running:**

1.  **Clone the Repository:**
    ```bash
    git clone <your-repo-url>
    cd wearable-data-pipeline-challenge
    ```

2.  **Update Backend Dependencies:** The new imputation methods require additional libraries.
    * Navigate to the `backend` directory.
    * Run `poetry lock` to ensure your `poetry.lock` file is up-to-date with the new `statsmodels` and `asyncpg` dependencies listed in `pyproject.toml`.
    * Return to the project root directory.

3.  **Perform Docker Build & Launch:**
    * Open your terminal in the project root.
    * Run the following commands to build the images and start the containers:
        ```bash
        docker compose build
        docker compose up -d
        ```
    * **Verification:** Run `docker compose ps`. You should see `timescaledb`, `ingestion_app`, `backend_app`, and `grafana` all listed as `Up`.

4.  **Initialize Database Schema:**
    * Connect to `psql` to create the necessary tables:
        ```bash
        docker compose exec timescaledb psql -U user -d fitbit_data
        ```
    * At the `fitbit_data=#` prompt, paste these SQL commands to create the `raw_data` and `imputed_data` tables:
        ```sql
        -- Create raw_data table
        CREATE TABLE raw_data (
            timestamp TIMESTAMPTZ NOT NULL,
            participant_id TEXT NOT NULL,
            data_type TEXT NOT NULL,
            value_numeric DOUBLE PRECISION,
            value_text TEXT
        );
        SELECT create_hypertable('raw_data', 'timestamp');

        -- Create imputed_data table
        CREATE TABLE imputed_data (
            "timestamp" TIMESTAMPTZ NOT NULL,
            participant_id TEXT,
            data_type TEXT,
            value_numeric DOUBLE PRECISION,
            value_text TEXT,
            is_imputed BOOLEAN DEFAULT TRUE
        );
        ```
    * Type `\q` to exit `psql`.

5.  **Generate and Load Synthetic Data:**
    * Run the synthetic data generator script:
        ```bash
        docker compose exec ingestion_app poetry run python /app/ingestion/synthetic_data_generator.py
        ```

6.  **Run the Imputation Process:**
    * This step is required to populate the `imputed_data` table. Run these commands in your terminal:
        ```bash
        # For heart rate (uses ARIMA model)
        curl -X POST "http://localhost:8001/data/run_imputation?user_id=test_participant_1&metric=heart_rate"

        # For steps (uses forward-fill)
        curl -X POST "http://localhost:8001/data/run_imputation?user_id=test_participant_1&metric=steps"
        ```

7.  **Access the Services:**
    * **Grafana Dashboard**: Open your browser and navigate to `http://localhost:3000`. The default login is `admin` / `password`.
    * **Contact Form**: Access the participant contact page at `http://localhost:8001/contact`.
    * **Backend API Docs**: The backend API documentation is available at `http://localhost:8001/docs`.

---
## **Task 4: Detailed Analysis Dashboard**

**Overview:**
This task builds upon the initial proof-of-concept to deliver a more detailed and powerful dashboard for in-depth analysis and visualization, leveraging Grafana for its robust time-series capabilities.

**Design Decisions & Implementation:**
* **Adherence Overview:** The dashboard features a top-level summary with key compliance metrics:
    * **Total Active Participants**: A count of all unique users who have submitted data.
    * **Inactive Participants**: A panel showing users who have not uploaded data in the last 48 hours.
    * **Low Sleep / Wear Time**: Panels that flag users who fall below predefined thresholds for sleep quality or overall wear time adherence.

* **Advanced Data Imputation:**
    * **Problem:** Simple imputation methods like mean/median are insufficient for clinical data. The initial KNN method proved too simplistic for large data gaps.
    * **Solution:** A more sophisticated, multi-strategy approach was implemented in the Python backend.
        * **ARIMA Model:** For continuous, dense data like `heart_rate`, an ARIMA time-series forecasting model is used to generate realistic, curved imputed values.
        * **Forward-Fill (`ffill`):** For sparse, cumulative data like `steps`, a logical forward-fill (and backward-fill for initial gaps) is used, which is more appropriate for that data type.
    * **Tracking Imputed Values:** The backend stores imputed data in a separate `imputed_data` table. Grafana queries both tables and displays the imputed data as a distinct, dashed line, making it easy for researchers to distinguish between real and imputed values.

* **Participant Interaction:**
    * **Clickable Participant List**: A master list of all participants is displayed on the dashboard. Clicking a participant's ID dynamically filters all dashboard panels to show data for only that user.
    * **Method to Contact Participants**: From the participant list, a user can click a link to open a dedicated contact page. This page, served by the FastAPI backend, allows for sending templated emails to participants based on their adherence status. This decouples the communication action from the dashboard itself while providing a seamless user workflow.