import json
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen


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
            if key and key not in (
                "PASTE_YOUR_API_KEY_HERE",
                "PASTE_YOUR_ACTUAL_API_KEY_HERE",
                "YOUR_API_KEY_HERE",
            ):
                return key
            break

    print("Error: Valid API_FOOTBALL_KEY not found in .env.")
    return None


def find_messi(profiles):
    # Check every returned profile instead of assuming the first is Lionel.
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
            return player

    return None


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
        return

    # Make just one request. The key goes in the header, never in the URL.
    query = urlencode({"search": "Messi"})
    url = f"https://v3.football.api-sports.io/players/profiles?{query}"

    try:
        request = Request(url, headers={"x-apisports-key": api_key})
        with urlopen(request, timeout=20) as response:
            data = json.load(response)
    except HTTPError as error:
        print(f"HTTP error: {error.code}. Check your API access and request quota.")
        return
    except (URLError, OSError):
        print("Network error: Could not retrieve profiles. Check your connection.")
        return
    except (ValueError, UnicodeError):
        print("Error: Invalid API key format or unreadable JSON response.")
        return

    if not isinstance(data, dict) or any(
        field not in data for field in ("errors", "results", "response")
    ):
        print("Error: API-Football returned an unexpected response format.")
        return

    # Do not print raw errors or response bodies, which may contain private data.
    if data["errors"]:
        print("API-Football returned an error. Check your key, plan access, and quota.")
        return

    results = data["results"]
    profiles = data["response"]
    if not isinstance(results, int) or results < 0 or not isinstance(profiles, list):
        print("Error: API-Football returned unexpected results or profile data.")
        return
    if results == 0 or not profiles:
        print("No player profiles returned for the search 'Messi'.")
        return

    player = find_messi(profiles)
    if player is None:
        print("Lionel Messi was not found among the returned player profiles.")
        return

    display_player(player)


# Importing this file does not send a request; running it directly does.
if __name__ == "__main__":
    main()
