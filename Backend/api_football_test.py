
import json
from pathlib import Path
from urllib.request import Request, urlopen
from urllib.error import HTTPError, URLError

# Find the .env file in the project root
project_folder = Path(__file__).resolve().parent.parent
env_file = project_folder / ".env"

# Read the API key
api_key = None

if env_file.exists():
    for line in env_file.read_text(encoding="utf-8-sig").splitlines():
        line = line.strip()

        if line.startswith("API_FOOTBALL_KEY="):
            api_key = line.split("=", 1)[1].strip().strip('"').strip("'")
            break

if not api_key or api_key in (
    "PASTE_YOUR_API_KEY_HERE",
    "PASTE_YOUR_ACTUAL_API_KEY_HERE",
):
    print("Error: Valid API key not found in .env")
    raise SystemExit(1)

# API-Football account status endpoint
url = "https://v3.football.api-sports.io/status"

# Send the key securely in a request header
request = Request(
    url,
    headers={"x-apisports-key": api_key}
)

try:
    with urlopen(request, timeout=20) as response:
        data = json.load(response)

    # Check the API response
    if data.get("errors"):
        print("API returned an error. Check your account or API key.")
    else:
        account = data.get("response", {}).get("account", {})
        subscription = data.get("response", {}).get("subscription", {})
        requests = data.get("response", {}).get("requests", {})

        print("\n MATCHLENS API-FOOTBALL TEST ")
        print("Connection: Successful")
        print("Account:", account.get("firstname", "Available"))
        print("Plan:", subscription.get("plan", "Unknown"))
        print("Daily Request Limit:", requests.get("limit_day", "Unknown"))
        print("Requests Used:", requests.get("current", "Unknown"))

except HTTPError as error:
    print("HTTP Error:", error.code)
    print("Check your API key and account access.")

except URLError:
    print("Network Error: Could not connect to API-Football.")
