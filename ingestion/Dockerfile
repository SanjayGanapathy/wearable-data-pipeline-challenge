# Use an official Python runtime as a parent image
FROM python:3.10-slim-bullseye

# Set the working directory in the container
WORKDIR /app # This will now be your project root (due to docker-compose volume mount)

# Install necessary system libraries for psycopg2-binary, plus cron
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    libpq-dev \
    cron \
    && rm -rf /var/lib/apt/lists/*

# TEMPORARY: This line helps force cache rebuild on every build (remove later for clean builds)
RUN echo "FORCE_INGESTION_BUILD_$(date +%s)"

# Copy pyproject.toml and poetry.lock for Poetry to use during the build process
# These files are in the build context root (which is /app due to WORKDIR)
COPY pyproject.toml poetry.lock ./

# Install poetry and your project's dependencies
RUN pip install poetry
RUN poetry install --no-root # Install production dependencies only

# ALL PREVIOUS COPY INSTRUCTIONS FOR PROJECT-SPECIFIC FILES (wearipedia/, ingestion/) ARE REMOVED
# because they are now available via the volume mount from docker-compose.yml.

# Set environment variables for database connection and Fitbit API credentials
ENV DB_HOST=timescaledb
ENV DB_NAME=fitbit_data
ENV DB_USER=user
ENV DB_PASSWORD=password
ENV FITBIT_CLIENT_ID="23QGKQ" 
ENV FITBIT_CLIENT_SECRET="7fd7962cda03f1f8e833ebd4d5cd2db4" 

# Create the cron job
# The script path is now relative to WORKDIR /app
RUN echo "0 1 * * * /usr/local/bin/poetry run python /app/ingestion/fitbit_ingest.py >> /var/log/cron.log 2>&1" | crontab -

# Give execution rights on the cron file
RUN chmod 0644 /var/spool/cron/crontabs/root

# Run the command to start cron in the foreground
CMD ["cron", "-f"]