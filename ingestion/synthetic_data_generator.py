import json
import os
from datetime import datetime, timedelta
import random
import numpy as np
import pandas as pd
import psycopg2

print("SYNTHETIC DATA GENERATOR SCRIPT HAS STARTED!")  # <-- Debug print

# --- Configuration (from environment variables) ---
DB_HOST = os.getenv("DB_HOST", "timescaledb")
DB_NAME = os.getenv("DB_NAME", "fitbit_data")
DB_USER = os.getenv("DB_USER", "user")
DB_PASSWORD = os.getenv("DB_PASSWORD", "password")

# Define the date range for synthetic data generation
# Task 2 requires ~1 month of data.
# Set these to generate data for a month in the recent past (e.g., June 2025)
SYNTHETIC_START_DATE_STR = "2025-06-01"
SYNTHETIC_END_DATE_STR = "2025-06-30"


# --- Database Insertion Function ---
def insert_record_into_db(
    cursor, participant_id, timestamp, data_type, value_numeric, value_text
):
    insert_sql = """
    INSERT INTO raw_data (timestamp, participant_id, data_type, value_numeric, value_text)
    VALUES (%s, %s, %s, %s, %s);
    """
    try:
        cursor.execute(
            insert_sql,
            (timestamp, participant_id, data_type, value_numeric, value_text),
        )
        return True
    except (psycopg2.Error, ValueError) as e:
        print(f"Error inserting record ({data_type} at {timestamp}): {e}")
        return False


# --- Synthetic Data Generation Logic (Independent of Wearipedia) ---
def generate_synthetic_fitbit_data(participant_id, start_date_str, end_date_str, conn):
    cursor = conn.cursor()
    records_inserted_count = 0

    start_date_dt = datetime.strptime(start_date_str, "%Y-%m-%d").date()
    end_date_dt = datetime.strptime(end_date_str, "%Y-%m-%d").date()

    current_date = start_date_dt
    while current_date <= end_date_dt:
        print(
            f"Generating synthetic data for {participant_id} on {current_date.strftime('%Y-%m-%d')}..."
        )

        daily_records_inserted = 0  # Initialize counter for this specific day

        # Simulate data for each hour of the day (e.g., 24 data points per day per metric)
        for hour in range(24):
            # Generate a base timestamp for this hour (e.g., 2025-06-01 10:00:00)
            timestamp_base_hour = datetime(
                current_date.year, current_date.month, current_date.day, hour, 0, 0
            )

            # --- Heart Rate (simulated BPM) ---
            # Add unique random seconds offset within the hour for uniqueness
            hr_timestamp = timestamp_base_hour + timedelta(
                seconds=random.randint(0, 19)
            )
            hr_value = random.randint(60, 100) + random.random()  # 60-100 BPM
            if insert_record_into_db(
                cursor, participant_id, hr_timestamp, "heart_rate", hr_value, None
            ):
                records_inserted_count += 1
                daily_records_inserted += 1

            # --- Steps (simulated steps per hour) ---
            # Add unique random seconds offset (different range than HR)
            steps_timestamp = timestamp_base_hour + timedelta(
                seconds=random.randint(20, 39)
            )
            steps_value = random.randint(0, 500)  # 0-500 steps
            if insert_record_into_db(
                cursor, participant_id, steps_timestamp, "steps", steps_value, None
            ):
                records_inserted_count += 1
                daily_records_inserted += 1

            # --- Calories (simulated calories burned per hour) ---
            # Add unique random seconds offset (different range than HR/Steps)
            calories_timestamp = timestamp_base_hour + timedelta(
                seconds=random.randint(40, 59)
            )
            calories_value = random.randint(50, 200)  # 50-200 calories
            if insert_record_into_db(
                cursor,
                participant_id,
                calories_timestamp,
                "calories",
                calories_value,
                None,
            ):
                records_inserted_count += 1
                daily_records_inserted += 1

        # --- Sleep Data (once per day/night for simplicity) ---
        # Sleep timestamp should ideally be unique per day for sleep records
        sleep_start_timestamp = datetime(
            current_date.year,
            current_date.month,
            current_date.day,
            22,
            random.randint(0, 59),
            random.randint(0, 59),
        )

        # Total minutes asleep
        total_minutes_asleep = random.randint(300, 500)  # 5-8 hours
        if insert_record_into_db(
            cursor,
            participant_id,
            sleep_start_timestamp,
            "sleep_total_minutes",
            total_minutes_asleep,
            None,
        ):
            records_inserted_count += 1
            daily_records_inserted += 1

        # Sleep stages (example breakdown)
        sleep_stages = {"deep": 0.2, "light": 0.5, "rem": 0.2, "wake": 0.1}
        for stage, proportion in sleep_stages.items():
            minutes_in_stage = total_minutes_asleep * proportion + random.randint(
                -10, 10
            )
            minutes_in_stage = max(0, minutes_in_stage)  # Ensure not negative
            if insert_record_into_db(
                cursor,
                participant_id,
                sleep_start_timestamp,
                f"sleep_{stage}_minutes",
                minutes_in_stage,
                None,
            ):
                records_inserted_count += 1
                daily_records_inserted += 1

        conn.commit()  # Commit changes for each day
        # --- CORRECTED PRINT STATEMENT ---
        print(
            f"Completed synthetic data for {current_date.strftime('%Y-%m-%d')}. Records inserted this day: {daily_records_inserted}. Total records so far: {records_inserted_count}"
        )

        current_date += timedelta(days=1)

    print(
        f"Finished generating and inserting synthetic data for {participant_id}. Total records: {records_inserted_count}"
    )


if __name__ == "__main__":
    conn = None
    try:
        conn = psycopg2.connect(
            host=DB_HOST, database=DB_NAME, user=DB_USER, password=DB_PASSWORD
        )

        participant_id_to_generate = os.getenv(
            "FITBIT_USER_ID", "test_participant_1"
        )  # Use env var or default

        # Example: Generate 1 month of data
        generate_synthetic_fitbit_data(
            conn=conn,
            participant_id=participant_id_to_generate,
            start_date_str=SYNTHETIC_START_DATE_STR,
            end_date_str=SYNTHETIC_END_DATE_STR,
        )

    except Exception as e:
        print(f"An error occurred during synthetic data generation: {e}")
        import traceback

        traceback.print_exc()
    finally:
        if conn:
            conn.close()
            print("Database connection closed.")
