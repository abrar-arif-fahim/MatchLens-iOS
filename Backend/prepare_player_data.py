"""Prepare a local Messi record. Requests happen only when run directly."""

import json
import re
import unicodedata
from datetime import date
from http.client import HTTPException
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, build_opener

# These helpers are safe to import: their script has a __main__ guard.
from api_football_players import NoRedirects, find_messi, read_api_key
from prepare_multiple_players import ValidationError, birth_date


WIKIDATA_ID = "Q615"
OUTPUT_FILE = Path(__file__).resolve().parent / "output" / "player_messi.json"


class PlayerDataError(ValueError):
    """A fixed, safe message explaining why preparation cannot continue."""


def download_json(url, headers):
    request = Request(url, headers=headers)
    # Wikidata may redirect; requests carrying an API key must never do so.
    has_api_key = any(header.casefold() == "x-apisports-key" for header in headers)
    opener = build_opener(NoRedirects()) if has_api_key else build_opener()
    with opener.open(request, timeout=20) as response:
        return json.load(response)


def get_wikidata(entity_id):
    # Reuse the Wikidata EntityData request pattern.
    data = download_json(
        f"https://www.wikidata.org/wiki/Special:EntityData/{entity_id}.json",
        {"User-Agent": "MatchLensUniversityProject/1.0 (educational project)"},
    )
    entity = data["entities"][entity_id]
    if not isinstance(entity, dict) or entity.get("id") != entity_id:
        raise PlayerDataError("Unexpected Wikidata entity.")
    return entity


def claim_values(entity, property_id):
    # Ignore deprecated statements and use preferred statements when present.
    claims = [
        claim for claim in entity.get("claims", {}).get(property_id, [])
        if claim.get("rank") != "deprecated"
    ]
    preferred = [claim for claim in claims if claim.get("rank") == "preferred"]
    values = []
    for claim in preferred or claims:
        snak = claim.get("mainsnak", {})
        if snak.get("snaktype") == "value":
            values.append(snak.get("datavalue", {}).get("value"))
    return values


def clean_text(value):
    # Missing values stay None, which json.dumps writes as null.
    if not isinstance(value, str) or not value.strip():
        return None
    text = value.strip()
    if text.casefold() in {"not available", "unknown", "n/a"}:
        return None
    return text


def comparable_text(value):
    # Ignore accents, case and punctuation when comparing readable labels.
    text = unicodedata.normalize("NFKD", clean_text(value) or "")
    return " ".join(
        "".join(character if character.isalnum() else " "
                for character in text if not unicodedata.combining(character))
        .casefold().split()
    )


def valid_date(value):
    if not isinstance(value, str) or not re.fullmatch(r"[0-9]{4}-[0-9]{2}-[0-9]{2}", value):
        return None
    try:
        return date.fromisoformat(value).isoformat()
    except ValueError:
        return None


def wikidata_birth_date(entity):
    # Share the strict day/precision/calendar/uncertainty checks with the batch tool.
    try:
        return birth_date(entity)
    except ValidationError:
        raise PlayerDataError("Wikidata birth date is missing, uncertain or ambiguous; no merge.") from None


def get_api_profiles(api_key):
    # The secret is sent only in a header; never print requests or raw errors.
    query = urlencode({"search": "Messi"})
    data = download_json(
        f"https://v3.football.api-sports.io/players/profiles?{query}",
        {"x-apisports-key": api_key},
    )
    if (not isinstance(data, dict) or not isinstance(data.get("errors"), (dict, list))
            or data["errors"]):
        raise PlayerDataError("API-Football error; check key, plan access and quota.")
    profiles = data.get("response")
    results = data.get("results")
    if not isinstance(profiles, list) or type(results) is not int or results != len(profiles):
        raise PlayerDataError("Unexpected API-Football profile response.")
    paging = data.get("paging")
    if (not isinstance(paging, dict) or type(paging.get("current")) is not int
            or type(paging.get("total")) is not int
            or paging["current"] != 1 or paging["total"] != 1):
        raise PlayerDataError("Search is incomplete or paginated; identity cannot be confirmed.")
    return profiles


def match_identity(entity, profiles):
    name = clean_text(entity.get("labels", {}).get("en", {}).get("value"))
    # Reuse the existing name check for both sources, checking every profile.
    if not name or find_messi([{"player": {"name": name}}]) is None:
        raise PlayerDataError("Wikidata name does not identify Lionel Messi; no merge.")
    birth_date = wikidata_birth_date(entity)
    matches = []
    for profile in profiles:
        player = find_messi([profile])
        if player is None:
            continue
        birth = player.get("birth")
        if not isinstance(birth, dict):
            continue
        if valid_date(birth.get("date")) == birth_date:
            matches.append(player)
    # Never pick the first result when multiple matching profiles exist.
    if len(matches) != 1:
        raise PlayerDataError("Name and birth date did not give one unique match; no merge.")
    player = matches[0]
    if type(player.get("id")) is not int or player["id"] <= 0:
        raise PlayerDataError("Matched API-Football profile has no valid numeric ID.")
    return name, birth_date, player


def wikidata_labels(entity, property_id, cache):
    labels = set()
    for value in claim_values(entity, property_id):
        entity_id = value.get("id") if isinstance(value, dict) else None
        if not entity_id:
            continue
        if entity_id not in cache:
            cache[entity_id] = get_wikidata(entity_id)
        label = clean_text(cache[entity_id].get("labels", {}).get("en", {}).get("value"))
        if label:
            labels.add(label)
    return labels


def normalize_position(value):
    # Map source labels to a few consistent football positions.
    positions = {
        "Forward": {"forward", "attacker", "striker", "centre forward",
                    "center forward", "second striker", "winger",
                    "left winger", "right winger", "forward association football"},
        "Midfielder": {"midfielder", "attacking midfielder", "central midfielder",
                       "defensive midfielder", "midfielder association football"},
        "Defender": {"defender", "centre back", "center back", "full back",
                     "left back", "right back", "defender association football"},
        "Goalkeeper": {"goalkeeper", "goalkeeper association football"},
    }
    text = comparable_text(value)
    for position, labels in positions.items():
        if text in labels:
            return position
    return None


def choose_field(wikidata_values, api_value):
    # Prefer a Wikidata value corroborated by the API. A single Wikidata value
    # also works when the API has no value. Conflicts/ambiguity become null.
    if not wikidata_values:
        return api_value
    if api_value:
        matches = [value for value in wikidata_values
                   if comparable_text(value) == comparable_text(api_value)]
        return matches[0] if len(matches) == 1 else None
    return next(iter(wikidata_values)) if len(wikidata_values) == 1 else None


def prepare_player(api_key):
    entity = get_wikidata(WIKIDATA_ID)
    name, birth_date, api_player = match_identity(entity, get_api_profiles(api_key))
    cache = {}
    countries = wikidata_labels(entity, "P27", cache)
    positions = {
        normalized for label in wikidata_labels(entity, "P413", cache)
        if (normalized := normalize_position(label)) is not None
    }
    # Explicitly allowlist stored fields: no photos, URLs or raw responses.
    return {
        "playerId": f"wikidata_{WIKIDATA_ID}",
        "wikidataId": WIKIDATA_ID,
        "apiFootballId": api_player["id"],
        "name": name,
        "dateOfBirth": birth_date,
        "nationality": choose_field(countries, clean_text(api_player.get("nationality"))),
        "position": choose_field(positions, normalize_position(api_player.get("position"))),
        # Both sources contribute stored IDs, even if public fields all use CC0.
        "sources": ["Wikidata", "API-Football"],
    }


def main():
    api_key = read_api_key()
    if not api_key:
        return 1
    try:
        player = prepare_player(api_key)
        output = json.dumps(player, ensure_ascii=False, indent=2)
        # Resolve the location relative to this script, regardless of cwd.
        OUTPUT_FILE.parent.mkdir(parents=True, exist_ok=True)
        OUTPUT_FILE.write_text(output + "\n", encoding="utf-8")
    except HTTPError as error:
        print(f"HTTP error {error.code}: check service access and request quota.")
        return 1
    except (URLError, OSError, HTTPException):
        print("Error: Could not reach a service or save the local output file.")
        return 1
    except PlayerDataError as error:
        # These messages are defined above, never copied from a service.
        print(f"Error: {error} No JSON saved.")
        return 1
    except (ValueError, KeyError, TypeError, AttributeError):
        # Do not print exception details: remote errors could contain secrets.
        print("Error: Data was missing, invalid, conflicting or ambiguous. No JSON saved.")
        return 1
    print(output)
    print(f"\nSaved to: {OUTPUT_FILE}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
