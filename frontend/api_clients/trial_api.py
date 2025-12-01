import os
import requests

API_BASE_URL = os.getenv("API_BASE_URL", "http://localhost:8000")
DEBUG = os.getenv("DEBUG_API", "0") == "1"

def log_debug(*args):
    if DEBUG:
        print("[TRIAL_API DEBUG]", *args)

def rank_trials(payload):

    url = f"{API_BASE_URL}/rank"

    try:
        log_debug("POST →", url)
        log_debug("Payload:", payload)

        response = requests.post(url, json=payload, timeout=15)

        response.raise_for_status()

        try:
            return response.json()
        except ValueError:
            print("Error: Backend returned non-JSON.")
            print("Raw:", response.text)
            return None

    except requests.Timeout:
        print("Error: Backend timed out.")
        return None

    except requests.ConnectionError:
        print(f"Error: Could not connect to backend at {url}. Is it running?")
        return None

    except requests.HTTPError as e:
        print(f"Backend error: {e}")
        print("Status:", response.status_code)
        print("Response:", response.text)
        return None

    except requests.RequestException as e:
        print(f"Unexpected request error: {e}")
        return None
