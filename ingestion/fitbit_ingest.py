import json
import os
from datetime import datetime, timedelta
import requests
import psycopg2  # For PostgreSQL connection
import time  # For sleep in retry logic
import base64  # For base64 encoding/decoding

# --- Configuration (from environment variables or config file) ---
FITBIT_CLIENT_ID = os.getenv("FITBIT_CLIENT_ID")
FITBIT_CLIENT_SECRET = os.getenv("FITBIT_CLIENT_SECRET")
FITBIT_REDIRECT_URI = (
    "http://localhost:8080/callback"  # Must match your Fitbit app config
)

DB_HOST = os.getenv(
    "DB_HOST", "timescaledb"
)  # 'timescaledb' as per docker-compose service name
DB_NAME = os.getenv("DB_NAME", "fitbit_data")
DB_USER = os.getenv("DB_USER", "user")
DB_PASSWORD = os.getenv("DB_PASSWORD", "password")

# IMPORTANT: These paths are absolute within the container's file system /app/ingestion/
# They should match the COPY . /app/ingestion/ in Dockerfile
TOKEN_FILE = "/app/ingestion/tokens.json"
LAST_RUN_FILE = "/app/ingestion/last_run.txt"
SCOPES = "activity heartrate sleep profile location settings"  # Ensure these match your Fitbit app permissions

# --- Helper Functions ---


def get_or_refresh_tokens(client_id, client_secret, redirect_uri, token_file):
    """
    Loads Fitbit OAuth2 tokens from file, refreshes them if expired, and saves them back.
    If no tokens exist or refresh fails, it guides the user on manual initial authorization.
    """
    tokens = {}
    # Attempt to load tokens from file
    if os.path.exists(token_file) and os.path.getsize(token_file) > 0:
        try:
            with open(token_file, "r") as f:
                tokens = json.load(f)
            print(f"Loaded tokens from {token_file}.")
        except json.JSONDecodeError:
            print(
                f"Warning: {token_file} is empty or invalid JSON. Discarding old tokens."
            )
            tokens = {}  # Discard invalid tokens

    # Proceed only if we successfully loaded tokens with access and refresh tokens
    if tokens and "access_token" in tokens and "refresh_token" in tokens:
        access_token_valid = False
        if "last_refreshed" in tokens and "expires_in" in tokens:
            try:
                last_refreshed_dt = datetime.fromisoformat(tokens["last_refreshed"])
                # Consider a buffer to refresh before it actually expires (5 minutes)
                expires_at = (
                    last_refreshed_dt
                    + timedelta(seconds=tokens["expires_in"])
                    - timedelta(minutes=5)
                )

                if expires_at < datetime.now():
                    print(
                        "Access token expired or near expiration. Attempting to refresh..."
                    )
                    # Fall through to refresh logic below
                else:
                    print("Access token is still valid.")
                    access_token_valid = True  # Mark as valid if not expired
            except ValueError:
                # If last_refreshed is malformed, treat token as expired and attempt refresh
                print(
                    f"Warning: 'last_refreshed' timestamp in {token_file} is malformed. Attempting token refresh as if expired."
                )
                # Fall through to refresh logic below
        else:
            # If last_refreshed or expires_in are missing, assume token is old/invalid and try to refresh
            print(
                f"Warning: 'last_refreshed' or 'expires_in' missing in {token_file}. Attempting token refresh."
            )
            # Fall through to refresh logic below

        # --- Token Refresh Logic ---
        if not access_token_valid:  # Only attempt refresh if not already valid
            try:
                auth_string = f"{client_id}:{client_secret}".encode()
                auth_header = base64.b64encode(auth_string).decode()

                refresh_data = {
                    "grant_type": "refresh_token",
                    "refresh_token": tokens["refresh_token"],
                    "client_id": client_id,
                    "redirect_uri": redirect_uri,
                }

                response = requests.post(
                    "https://api.fitbit.com/oauth2/token",
                    headers={
                        "Authorization": f"Basic {auth_header}",
                        "Content-Type": "application/x-www-form-urlencoded",
                    },
                    data=refresh_data,
                )
                response.raise_for_status()

                new_tokens = response.json()
                new_tokens["last_refreshed"] = (
                    datetime.now().isoformat()
                )  # Update timestamp

                tokens.update(new_tokens)  # Update existing tokens with new ones
                with open(token_file, "w") as f:  # Save to file
                    json.dump(tokens, f, indent=4)
                print("Tokens refreshed and saved successfully.")
                return tokens
            except requests.exceptions.RequestException as e:
                print(
                    f"Error refreshing token: {e}. Current refresh token might be invalid."
                )
                # If refresh fails, tokens are definitely not valid.
                pass  # Fall through to manual auth guidance
        else:
            # Token was already valid and no refresh was needed
            return tokens  # RETURN VALID TOKENS HERE if access_token_valid is True

    else:
        # If tokens file was empty or missing essential fields, fall through to manual auth guidance
        print("No essential tokens (access/refresh) found in file.")

    # --- Fallback to Manual Authorization Guidance (if refresh failed or no initial tokens) ---
    print("\n--- ATTENTION: MANUAL AUTHORIZATION REQUIRED ---")
    print("Please follow the steps below to get new tokens.")
    auth_url = (
        f"https://www.fitbit.com/oauth2/authorize?"
        f"response_type=code&client_id={client_id}&"
        f"scope={' '.join(SCOPES.split())}&redirect_uri={requests.utils.quote(redirect_uri, safe='')}"
    )
    print(f"\n1. Open this URL in your web browser: {auth_url}")
    print("2. Log in (if needed) and authorize the app.")
    print(
        "3. After redirection, copy the 'code' from the browser's URL bar (e.g., from 'http://localhost:8080/callback?code=YOUR_CODE_HERE#_=_')."
    )
    print(
        f"\n4. Then, in your WSL terminal, run the following curl command (REPLACE YOUR_AUTHORIZATION_CODE_HERE with the code you copied):"
    )
    print(
        f"""
    curl -X POST \\
         -H "Content-Type: application/x-www-form-urlencoded" \\
         -H "Authorization: Basic $(echo -n '{client_id}:{client_secret}' | base64)" \\
         -d "grant_type=authorization_code" \\
         -d "client_id={client_id}" \\
         -d "redirect_uri={redirect_uri}" \\
         -d "code=YOUR_AUTHORIZATION_CODE_HERE" \\
         "https://api.fitbit.com/oauth2/token"
    """
    )
    print("\n5. Copy the JSON response from the curl command.")
    print(
        f"6. Open '{token_file}' in VS Code and paste the JSON response into it. Add a '\"last_refreshed\": \"{datetime.now().isoformat()}\"' field."
    )
    print("7. Save the file and re-run this ingestion script.")
    return None  # Indicate that tokens are not available, script should exit or wait.


def get_last_run_timestamp(file_path):
    """Reads the last successful ingestion timestamp."""
    if os.path.exists(file_path) and os.path.getsize(file_path) > 0:
        with open(file_path, "r") as f:
            content = f.read().strip()
            if content:
                try:
                    return datetime.fromisoformat(content)
                except ValueError:
                    print(
                        f"Warning: Invalid timestamp in {file_path}. Starting from default."
                    )
    # Default to 7 days ago if no last run recorded
    return datetime.now() - timedelta(days=7)


def save_last_run_timestamp(file_path, timestamp):
    """Saves the current ingestion timestamp."""
    # Ensure directory exists within the container's /app/ingestion
    os.makedirs(os.path.dirname(file_path), exist_ok=True)
    with open(file_path, "w") as f:
        f.write(timestamp.isoformat())


def fetch_fitbit_intraday_data(access_token, user_id, date_str, detail_level="1sec"):
    """Fetches intraday data for a given date and detail level."""
    headers = {"Authorization": f"Bearer {access_token}"}
    base_url = f"https://api.fitbit.com/1/user/{user_id}/activities"
    base_sleep_url = f"https://api.fitbit.com/1.2/user/{user_id}/sleep"

    fetched_data = {}

    # --- Fetch Heart Rate ---
    try:
        hr_url = f"{base_url}/heart/date/{date_str}/1d/{detail_level}.json"
        hr_response = requests.get(hr_url, headers=headers)
        hr_response.raise_for_status()
        fetched_data["heart_rate"] = hr_response.json()
        print(f"Fetched Heart Rate data for {date_str}.")
    except requests.exceptions.RequestException as e:
        print(f"Error fetching Heart Rate for {date_str}: {e}")
        fetched_data["heart_rate"] = {}  # Store empty if error

    # --- Fetch Steps ---
    try:
        steps_url = f"{base_url}/steps/date/{date_str}/1d/1min.json"
        steps_response = requests.get(steps_url, headers=headers)
        steps_response.raise_for_status()
        fetched_data["steps"] = steps_response.json()
        print(f"Fetched Steps data for {date_str}.")
    except requests.exceptions.RequestException as e:
        print(f"Error fetching Steps for {date_str}: {e}")
        fetched_data["steps"] = {}

    # --- Fetch Sleep (Note: different API version and structure) ---
    try:
        sleep_url = f"{base_sleep_url}/date/{date_str}.json"
        sleep_response = requests.get(sleep_url, headers=headers)
        sleep_response.raise_for_status()
        fetched_data["sleep"] = sleep_response.json()
        print(f"Fetched Sleep data for {date_str}.")
    except requests.exceptions.RequestException as e:
        print(f"Error fetching Sleep for {date_str}: {e}")
        fetched_data["sleep"] = {}

    # You can add more data types (calories, distance, etc.) here

    return fetched_data


def write_data_to_timescaledb(data, conn, participant_id, date_str):
    """
    Writes fetched Fitbit data into the raw_data hypertable.
    Parses different data types (heart rate, steps, sleep) from Fitbit API response.
    """
    cursor = conn.cursor()
    insert_sql = """
    INSERT INTO raw_data (timestamp, participant_id, data_type, value_numeric, value_text)
    VALUES (%s, %s, %s, %s, %s);
    """
    records_inserted = 0

    try:
        # --- Handle Heart Rate Data ---
        # The API response for intraday heart rate is typically under 'activities-heart-intraday' -> 'dataset'
        if "heart_rate" in data and "activities-heart-intraday" in data["heart_rate"]:
            hr_dataset = data["heart_rate"]["activities-heart-intraday"].get(
                "dataset", []
            )
            for entry in hr_dataset:
                try:
                    full_timestamp_str = f"{date_str}T{entry['time']}"
                    timestamp = datetime.fromisoformat(full_timestamp_str)
                    value = entry["value"]
                    cursor.execute(
                        insert_sql,
                        (timestamp, participant_id, "heart_rate", value, None),
                    )
                    records_inserted += 1
                except (KeyError, ValueError, psycopg2.Error) as e:
                    print(f"Skipping HR entry due to error: {e} - Data: {entry}")

        # --- Handle Steps Data ---
        # The API response for intraday steps is typically under 'activities-steps-intraday' -> 'dataset'
        if "steps" in data and "activities-steps-intraday" in data["steps"]:
            steps_dataset = data["steps"]["activities-steps-intraday"].get(
                "dataset", []
            )
            for entry in steps_dataset:
                try:
                    full_timestamp_str = f"{date_str}T{entry['time']}"
                    timestamp = datetime.fromisoformat(full_timestamp_str)
                    value = entry["value"]
                    cursor.execute(
                        insert_sql, (timestamp, participant_id, "steps", value, None)
                    )
                    records_inserted += 1
                except (KeyError, ValueError, psycopg2.Error) as e:
                    print(f"Skipping Steps entry due to error: {e} - Data: {entry}")

        # --- Handle Sleep Data ---
        # Sleep data is usually structured differently, often a list of sleep records for the day.
        # We'll extract total minutes asleep, and basic sleep stage minutes.
        if "sleep" in data and "sleep" in data["sleep"]:
            sleep_records = data["sleep"].get(
                "sleep", []
            )  # 'sleep' key holds a list of sleep objects
            for sleep_entry in sleep_records:
                try:
                    sleep_date_str = sleep_entry.get("dateOfSleep")
                    sleep_start_time_str = sleep_entry.get("startTime")
                    sleep_timestamp = datetime.fromisoformat(
                        f"{sleep_date_str}T{sleep_start_time_str}"
                    )

                    # Total minutes asleep
                    cursor.execute(
                        insert_sql,
                        (
                            sleep_timestamp,
                            participant_id,
                            "sleep_total_minutes",
                            sleep_entry.get("minutesAsleep"),
                            None,
                        ),
                    )
                    records_inserted += 1

                    # Basic sleep stages (example: deep, light, rem, wake)
                    levels_summary = sleep_entry.get("levels", {}).get("summary", {})
                    for (
                        level_data
                    ) in (
                        levels_summary.values()
                    ):  # Iterate over values of the summary dict
                        level_name = level_data.get("level")
                        minutes = level_data.get("minutes")
                        if level_name and minutes is not None:
                            cursor.execute(
                                insert_sql,
                                (
                                    sleep_timestamp,
                                    participant_id,
                                    f"sleep_{level_name}_minutes",
                                    minutes,
                                    None,
                                ),
                            )
                            records_inserted += 1
                except (KeyError, ValueError, psycopg2.Error) as e:
                    print(
                        f"Skipping Sleep entry due to error: {e} - Data: {sleep_entry}"
                    )

        # --- Add more elif blocks for other data_type_keys (e.g., 'calories', 'distance') ---
        # Remember to consult Fitbit API docs for their specific JSON structure
        # and adapt parsing accordingly.

        conn.commit()  # Commit all changes if no exceptions occurred
        print(
            f"Successfully wrote {records_inserted} records for participant {participant_id} on {date_str}."
        )

    except Exception as e:
        print(
            f"Critical error during data write transaction for {participant_id} on {date_str}: {e}"
        )
        conn.rollback()  # Rollback all changes if a critical error occurs
        raise  # Re-raise to ensure the main script loop catches it and logs it.

    finally:
        cursor.close()


# --- Main Ingestion Logic ---
def main_ingestion_loop():
    print("Starting Fitbit data ingestion...")

    # IMPORTANT: These paths are absolute within the container's file system /app/ingestion/
    # They should match the COPY . /app/ingestion/ in Dockerfile
    tokens_file_path = TOKEN_FILE
    last_run_file_path = LAST_RUN_FILE

    # Dummy user ID for initial testing (replace with actual user ID from OAuth)
    # This will be replaced by user_id from tokens if available
    fitbit_user_id = "YOUR_FITBIT_USER_ID"  # <<< GET A REAL ONE!

    tokens = get_or_refresh_tokens(
        FITBIT_CLIENT_ID, FITBIT_CLIENT_SECRET, FITBIT_REDIRECT_URI, tokens_file_path
    )
    if not tokens or "access_token" not in tokens:
        print(
            "Failed to get/refresh Fitbit tokens or access_token missing. Ingestion aborted."
        )
        return

    # Use the user ID from tokens if available, otherwise fallback to placeholder
    fitbit_user_id = tokens.get("user_id", fitbit_user_id)

    last_run_dt = get_last_run_timestamp(last_run_file_path)
    today = datetime.now().date()
    # Ingest data from the day *after* last_run_dt up to yesterday
    current_date = last_run_dt.date() + timedelta(days=1)

    conn = None
    try:
        conn = psycopg2.connect(
            host=DB_HOST, database=DB_NAME, user=DB_USER, password=DB_PASSWORD
        )

        # Loop through each day from the day after last run up to yesterday
        while current_date < today:
            date_str = current_date.strftime("%Y-%m-%d")
            print(f"Processing data for date: {date_str}")

            # Fetch data for the specific user and date
            intraday_data = fetch_fitbit_intraday_data(
                tokens["access_token"], fitbit_user_id, date_str
            )

            # Write fetched data to TimescaleDB
            write_data_to_timescaledb(intraday_data, conn, fitbit_user_id, date_str)

            # Move to the next day
            current_date += timedelta(days=1)
            # Update last run after each successful day's ingestion
            save_last_run_timestamp(last_run_file_path, datetime.now())

        print("Fitbit data ingestion loop complete.")

    except Exception as e:
        print(f"An error occurred during ingestion loop: {e}")
        import traceback

        traceback.print_exc()  # Print full traceback for debugging
    finally:
        if conn:
            conn.close()
            print("Database connection closed.")


if __name__ == "__main__":
    print(f"Ingestion script started at: {datetime.now()}")
    main_ingestion_loop()
    print(f"Ingestion script finished at: {datetime.now()}")
