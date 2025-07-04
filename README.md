# Wearable Data Pipeline, Dashboard & Monitoring

## Project Overview

This repository contains my complete solution for a software engineering challenge focused on building a full-stack data pipeline and visualization application for wearable device data. The system is designed to ingest, process, store, and visualize time-series data from Fitbit devices, with a professional-grade monitoring and alerting stack to ensure reliability.

In this project, I implemented:

- A daily data pipeline to ingest Fitbit data into a TimescaleDB database.
- A detailed Grafana dashboard for in-depth analysis, featuring an adherence overview and advanced data imputation.
- A complete monitoring and alerting stack using Prometheus, Grafana, and AlertManager to ensure pipeline observability.

---

## Key Features

- **Interactive Grafana Dashboard**: I built a powerful, interactive dashboard for deep analysis of time-series health metrics.
- **Adherence Overview**: I created at-a-glance panels that monitor participant compliance, including inactivity, low wear time, and poor sleep data quality.
- **Advanced Data Imputation**: I implemented a robust backend process that uses the appropriate model (ARIMA for continuous data, forward-fill for sparse data) to reliably fill gaps in the time-series data.
- **Participant Interaction**: I developed a clickable master list of participants to dynamically filter the dashboard, with integrated links to a separate contact form for researcher outreach.
- **Full Observability Stack**: I deployed a complete application monitoring stack using Prometheus, with pre-configured alerts for performance issues and dashboards to visualize container and host metrics.

---

## Technology Stack

- **Backend**: Python, FastAPI, Pandas, Statsmodels  
- **Database**: PostgreSQL with TimescaleDB extension  
- **Dashboard**: Grafana  
- **Monitoring**: Prometheus, AlertManager, cAdvisor, Node Exporter  
- **Containerization**: Docker & Docker Compose  

---

## Local Setup & Launch Instructions

To run this application stack locally, you will need **Docker Desktop** and **Git**.

### Step 1: Clone the Repository

```bash
git clone <your-repo-url>
cd wearable-data-pipeline-challenge
```

### Step 2: Configure Placeholders

You must update several placeholder values in the project files before launching the application.

**Fitbit API Credentials**  
File to edit: `docker-compose.yml`  
Placeholders:

- `YOUR_FITBIT_CLIENT_ID`
- `YOUR_FITBIT_CLIENT_SECRET`

**Fitbit User ID for Synthetic Data**  
File to edit: `ingestion/synthetic_data_generator.py`  
Placeholder:

- `YOUR_FITBIT_USER_ID`

**AlertManager Email Configuration**  
File to edit: `monitoring/alertmanager.yml`  
Placeholders:

- `your-email@gmail.com` (your sender email address)
- `YOUR_APP_PASSWORD` (use an app-specific password from your email provider for security)
- `admin@wearipedia.com` (the recipient email address)

### Step 3: Update Dependencies (If necessary)

If you have modified the backend dependencies in `pyproject.toml`, ensure the lock file is up to date.

```bash
# Navigate into the backend directory
cd backend

# Update the lock file
poetry lock

# Return to the project root
cd ..
```

### Step 4: Build and Launch the Stack

From the root directory of the project, run the following command to build all Docker images and start the services.

```bash
docker compose up -d --build
```

**Verification:**  
Run `docker compose ps`. You should see `timescaledb`, `ingestion_app`, `backend_app`, `grafana`, `prometheus`, `alertmanager`, `node_exporter`, and `cadvisor` all listed as **Up**.

### Step 5: Initialize the Database

The database is initially empty. You need to create the tables and load the initial data.

**Connect to the database:**

```bash
docker compose exec timescaledb psql -U user -d fitbit_data
```

**Paste these SQL commands at the `psql` prompt to create the tables:**

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

Exit the database shell by typing `\q`.

**Generate and load synthetic data:**

```bash
docker compose exec ingestion_app poetry run python /app/ingestion/synthetic_data_generator.py
```

---

## Using the Application

**Grafana Dashboard:**  
[http://localhost:3000](http://localhost:3000)  
Login with: `admin` / `password`

Add Prometheus as a data source (`http://prometheus:9090`).

Import dashboards using Grafana.com IDs:

- `1860` for Node Exporter
- `14282` for Docker Monitoring

**Participant Contact Form:**  
[http://localhost:8001/contact](http://localhost:8001/contact)

**Run Data Imputation** (Required to see imputed data in Grafana):

```bash
# For heart rate (uses ARIMA model)
curl -X POST "http://localhost:8001/data/run_imputation?user_id=test_participant_1&metric=heart_rate"

# For steps (uses forward-fill)
curl -X POST "http://localhost:8001/data/run_imputation?user_id=test_participant_1&metric=steps"
```

---

## Monitoring UIs

- **Prometheus**: [http://localhost:9090](http://localhost:9090)  
- **AlertManager**: [http://localhost:9093](http://localhost:9093)  
- **cAdvisor**: [http://localhost:8082](http://localhost:8082)  

---

## Troubleshooting & Development Journey

This section outlines key challenges I encountered during development and their solutions, demonstrating a robust and iterative problem-solving process.

### Initial Setup & Docker Networking

**Challenge:**  
Services failing to start due to `Bind for 0.0.0.0:XXXX failed: port is already allocated`.

**Solution:**  
I identified and resolved port conflicts by re-mapping host ports in `docker-compose.yml` (e.g., mapping cAdvisor to `8082:8080`). This highlighted the importance of isolating services and managing host resources.

### Backend Application & Dependencies

**Challenge:**  
The backend container repeatedly failed to start due to a variety of Python errors, including `SyntaxError`, `NameError`, and `ModuleNotFoundError`.

**Solution:**  
This required a multi-step debugging process. I used `docker compose logs backend_app` to identify the specific error, fixed typos and incorrect import statements in `app.py`, and updated the `backend/pyproject.toml` and `poetry.lock` files to include missing dependencies, followed by a full `docker compose build`.

### Data Imputation Logic

**Challenge:**  
The initial KNN imputation method produced unrealistic, flat-line data for large gaps. A subsequent ARIMA implementation failed for sparse data like steps and had runtime errors for heart_rate.

**Solution:**  
I developed a more sophisticated, multi-strategy imputation function. The final version uses the powerful ARIMA model for dense, continuous signals like `heart_rate` but intelligently switches to a more appropriate forward-fill (`ffill`) and backward-fill (`bfill`) strategy for sparse data like `steps`. This ensures the best model is used for each data type. I also addressed a `ValueError: cannot reindex on an axis with duplicate labels` by grouping raw data by timestamp and averaging the values before processing.

### Monitoring & Alerting Pipeline

**Challenge:**  
After setting up the full monitoring stack, alerts were not firing as expected.

**Solution:**  
I debugged the entire data flow, from metric generation to rule evaluation. I used the Prometheus UI to discover that the backend was DOWN due to an incorrect port in the scrape configuration (`8001` vs. the correct internal port `8000`). After fixing this, I tested the alert expression directly and found that the `rate()` function was not ideal for validation. The final solution was to implement a simpler and more reliable alert using the `increase()` function, which correctly triggered the alert pipeline.
