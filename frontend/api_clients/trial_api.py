import os
import requests

# API URL (change via env var if needed)
API_BASE_URL = os.getenv("API_BASE_URL", "http://localhost:8000")

# Toggle debug logs (set DEBUG_API=1 in env if needed)
DEBUG = os.getenv("DEBUG_API", "0") == "1"

def log_debug(*args):
    if DEBUG:
        print("[TRIAL_API DEBUG]", *args)

def rank_trials(payload):
    """
    Send the payload to backend /rank endpoint and return parsed JSON on success.
    """
    url = f"{API_BASE_URL}/rank"

    try:
        log_debug("POST →", url)
        log_debug("Payload:", payload)

        response = requests.post(url, json=payload, timeout=15)

        # Raise for 4xx/5xx errors
        response.raise_for_status()

        # Try to parse response
        try:
            return response.json()
        except ValueError:
            print("Error: Backend did not return valid JSON.")
            print("Raw response:", response.text)
            return None

    except requests.Timeout:
        print("Error: Request to backend timed out.")
        return None

    except requests.ConnectionError:
        print(f"Error: Could not connect to backend at {url}.")
        print("Hint: Is the backend running? Did you expose port 8000?")
        return None

    except requests.HTTPError as e:
        print(f"HTTP error from backend: {e}")
        print("Status code:", response.status_code)
        print("Response text:", response.text)
        return None

    except requests.RequestException as e:
        print(f"Unexpected request error: {e}")
        return None
