# Use an official Python runtime as a parent image
FROM python:3.10-slim-bullseye

# Set the working directory in the container
WORKDIR /app # This will now be your project root (due to docker-compose volume mount)

# Install necessary system libraries for psycopg2-binary
RUN apt-get update && apt-get install -y --no-install-recommends \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

# TEMPORARY: This line helps force cache rebuild on every build (remove later)
RUN echo "FORCE_BACKEND_BUILD_$(date +%s)"

# Copy pyproject.toml and poetry.lock from the build context root
COPY pyproject.toml poetry.lock ./

# Install poetry and backend dependencies (FastAPI, uvicorn, psycopg2-binary, pandas, numpy etc.)
# Poetry will see pyproject.toml and poetry.lock from /app
RUN pip install poetry
RUN poetry install --no-root # Install production dependencies only

# Explicitly set PYTHONPATH to ensure Python finds modules in /app and its subdirectories
ENV PYTHONPATH=/app

# Expose the port FastAPI will run on
EXPOSE 8000

# Command to run the FastAPI application
# app:app refers to 'app.py' file which is in 'backend/' subfolder of the mounted /app
# --host 0.0.0.0 makes it accessible from outside the container
CMD ["/usr/local/bin/poetry", "run", "uvicorn", "backend.app:app", "--host", "0.0.0.0", "--port", "8000"]