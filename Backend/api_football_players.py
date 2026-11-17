import json
from http.client import HTTPException
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import HTTPRedirectHandler, Request, build_opener


class NoRedirects(HTTPRedirectHandler):
    # Do not forward the private API header to a redirected URL.
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def read_api_key():
    # Locate .env from this file, so the current working folder does not matter.
    env_file = Path(__file__).resolve().parent.parent / ".env"

    try:
        lines = env_file.read_text(encoding="utf-8-sig").splitlines()
    except (OSError, UnicodeError):
        print("Error: Could not read the project root .env file.")
        return None

    for line in lines:
        line = line.strip()
        if line.startswith("API_FOOTBALL_KEY="):
            key = line.split("=", 1)[1].strip().strip('"').strip("'")
            if key and key.upper() not in (
                "PASTE_YOUR_API_KEY_HERE",
                "PASTE_YOUR_ACTUAL_API_KEY_HERE",
                "YOUR_API_KEY_HERE",
                "YOUR_API_FOOTBALL_KEY_HERE",
            ) and not any(character.isspace() or ord(character) < 32 for character in key):
                return key
            break
    print("Error: Valid API_FOOTBALL_KEY not found in .env.")
    return None


def find_messi(profiles):
    # Check every returned profile instead of assuming the first is Lionel.
    matches = []
    for profile in profiles:
        if not isinstance(profile, dict):
            continue
        player = profile.get("player")
        if not isinstance(player, dict):
            continue

        first = str(player.get("firstname") or "").casefold().split()
        last = str(player.get("lastname") or "").casefold().split()
        name = str(player.get("name") or "").casefold().split()

        matches_parts = bool(first) and first[0] == "lionel" and "messi" in last
        matches_name = bool(name) and name[0] == "lionel" and "messi" in name[1:]
        if matches_parts or matches_name:
            matches.append(player)

    # A name alone must not select one of several matching people.
    return matches[0] if len(matches) == 1 else None


def display_player(player):
    # Build the full name from the returned first/last names when both exist.
    first = player.get("firstname")
    last = player.get("lastname")
    full_name = f"{first} {last}" if first and last else player.get("name")
    birth = player.get("birth")
    if not isinstance(birth, dict):
        birth = {}

    fields = (
        ("API-Football Player ID", player.get("id")),
        ("Full name", full_name),
        ("First name", first),
        ("Last name", last),
        ("Date of birth", birth.get("date")),
        ("Nationality", player.get("nationality")),
        ("Height", player.get("height")),
        ("Weight", player.get("weight")),
        ("Playing position", player.get("position")),
        ("Photo URL", player.get("photo")),
    )

    print("\nMATCHLENS PLAYER PROFILE")
    for label, value in fields:
        print(f"{label}: {value if value is not None and value != '' else 'Not available'}")


def main():
    api_key = read_api_key()
    if not api_key:
        return 1

    # Make just one request. The key goes in the header, never in the URL.
    query = urlencode({"search": "Messi"})
    url = f"https://v3.football.api-sports.io/players/profiles?{query}"

    try:
        request = Request(url, headers={"x-apisports-key": api_key})
        with build_opener(NoRedirects()).open(request, timeout=20) as response:
            data = json.load(response)
    except HTTPError as error:
        print(f"HTTP error: {error.code}. Check your API access and request quota.")
        return 1
    except (URLError, OSError, HTTPException):
        print("Network error: Could not retrieve profiles. Check your connection.")
        return 1
    except (ValueError, UnicodeError):
        print("Error: Invalid API key format or unreadable JSON response.")
        return 1

    if not isinstance(data, dict) or any(
        field not in data for field in ("errors", "results", "response")
    ):
        print("Error: API-Football returned an unexpected response format.")
        return 1

    # Do not print raw errors or response bodies, which may contain private data.
    if not isinstance(data["errors"], (dict, list)) or data["errors"]:
        print("API-Football returned an error. Check your key, plan access, and quota.")
        return 1

    results = data["results"]
    profiles = data["response"]
    if type(results) is not int or not isinstance(profiles, list) or results != len(profiles):
        print("Error: API-Football returned unexpected results or profile data.")
        return 1
    if results == 0 or not profiles:
        print("No player profiles returned for the search 'Messi'.")
        return 1

    paging = data.get("paging")
    if (not isinstance(paging, dict) or type(paging.get("current")) is not int
            or type(paging.get("total")) is not int
            or paging["current"] != 1 or paging["total"] != 1):
        print("Search is incomplete or paginated. A unique identity cannot be confirmed.")
        return 1

    player = find_messi(profiles)
    if player is None:
        print("Lionel Messi was not uniquely identified among the returned profiles.")
        return 1
    if type(player.get("id")) is not int or player["id"] <= 0:
        print("The matching player has no valid provider ID.")
        return 1

    display_player(player)
    return 0


# Importing this file does not send a request; running it directly does.
if __name__ == "__main__":
    raise SystemExit(main())
