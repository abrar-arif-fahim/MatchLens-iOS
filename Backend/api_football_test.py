
"""Test the API-Football connection only when this file is run directly."""

import json
from http.client import HTTPException
from urllib.error import HTTPError, URLError
from urllib.request import Request, build_opener

from api_football_players import NoRedirects, read_api_key


def main():
    api_key = read_api_key()
    if not api_key:
        return 1
    request = Request(
        "https://v3.football.api-sports.io/status",
        headers={"x-apisports-key": api_key},
    )
    try:
        # One request; never forward credentials through an HTTP redirect.
        with build_opener(NoRedirects()).open(request, timeout=20) as response:
            data = json.load(response)
        if not isinstance(data, dict) or not isinstance(data.get("errors"), (dict, list)):
            print("API-Football returned an unexpected response format.")
            return 1
        if data["errors"]:
            print("API returned an error. Check your key, account access and quota.")
            return 1
        status = data.get("response")
        if not isinstance(status, dict):
            print("API-Football returned an unexpected status response.")
            return 1
        subscription = status.get("subscription")
        quota = status.get("requests")
        if not isinstance(subscription, dict) or not isinstance(quota, dict):
            print("API-Football returned incomplete subscription or quota information.")
            return 1
        print("\nMATCHLENS API-FOOTBALL TEST")
        print("Connection: Successful")
        # Show only the expected public plan names and numeric quota values.
        plan = subscription.get("plan")
        print("Plan:", plan if plan in ("Free", "Pro", "Ultra", "Mega") else "Available")
        for label, field in (("Daily Request Limit", "limit_day"), ("Requests Used", "current")):
            value = quota.get(field)
            print(f"{label}:", value if type(value) is int and value >= 0 else "Unknown")
        return 0
    except HTTPError as error:
        print(f"HTTP error {error.code}. Check API access and quota.")
    except (URLError, OSError, HTTPException):
        print("Network error: Could not connect to API-Football.")
    except (ValueError, UnicodeError):
        print("Invalid configuration or unreadable JSON response.")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
