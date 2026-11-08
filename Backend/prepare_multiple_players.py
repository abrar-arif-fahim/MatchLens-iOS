"""Prepare validated Wikidata players locally; no Firebase or API-Football access."""

import json
import re
import unicodedata
from datetime import date
from http.client import HTTPException
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


BACKEND_DIR = Path(__file__).resolve().parent
INPUT_FILE = BACKEND_DIR / "input" / "players_to_import.json"
OUTPUT_FILE = BACKEND_DIR / "output" / "players_prepared.json"
USER_AGENT = "MatchLensUniversityProject/1.0 (educational football data preparation)"


class ValidationError(ValueError):
    """A readable reason why one record cannot safely be prepared."""


def valid_id(value):
    return isinstance(value, str) and re.fullmatch(r"Q[1-9][0-9]*", value) is not None


def normalize_name(value):
    # Keep every word: do not use fuzzy matching, initials or surname-only checks.
    text = unicodedata.normalize("NFKD", value).casefold()
    text = "".join(character for character in text
                   if not unicodedata.combining(character))
    return " ".join(
        "".join(character if character.isalnum() else " " for character in text).split()
    )


def get_entity(entity_id, cache):
    if not valid_id(entity_id):
        raise ValidationError("Invalid Wikidata entity ID.")
    if entity_id in cache:
        # Remember failures too, so shared entities are not repeatedly requested.
        cached = cache[entity_id]
        if isinstance(cached, ValidationError):
            raise cached
        return cached

    # Reuse wikidata_test.py's Request + urlopen approach, without importing it:
    # that existing script makes live requests as soon as it is imported.
    request = Request(
        f"https://www.wikidata.org/wiki/Special:EntityData/{entity_id}.json",
        headers={"User-Agent": USER_AGENT},
    )
    try:
        with urlopen(request, timeout=20) as response:
            data = json.load(response)
    except HTTPError as error:
        failure = ValidationError(f"Wikidata HTTP {error.code} for {entity_id}.")
    except (URLError, OSError, HTTPException):
        failure = ValidationError(f"Network error or timeout retrieving {entity_id}.")
    except (ValueError, UnicodeError):
        failure = ValidationError(f"Invalid JSON returned for {entity_id}.")
    else:
        entities = data.get("entities") if isinstance(data, dict) else None
        entity = entities.get(entity_id) if isinstance(entities, dict) else None
        if isinstance(entity, dict) and entity.get("id") == entity_id and "missing" not in entity:
            cache[entity_id] = entity
            return entity
        # Reject redirects or a different returned ID; preserve the requested ID.
        failure = ValidationError(f"Missing or unexpected Wikidata entity {entity_id}.")

    cache[entity_id] = failure
    raise failure


def english_label(entity):
    labels = entity.get("labels")
    label = labels.get("en") if isinstance(labels, dict) else None
    value = label.get("value") if isinstance(label, dict) else None
    if not isinstance(value, str) or not value.strip():
        raise ValidationError("An essential English label is unavailable.")
    return value.strip()


def claim_values(entity, property_id):
    claims = entity.get("claims")
    statements = claims.get(property_id, []) if isinstance(claims, dict) else []
    if not isinstance(statements, list) or any(not isinstance(item, dict) for item in statements):
        raise ValidationError(f"Invalid claim structure for {property_id}.")
    statements = [item for item in statements if item.get("rank") != "deprecated"]
    preferred = [item for item in statements if item.get("rank") == "preferred"]
    values = []
    for statement in preferred or statements:
        snak = statement.get("mainsnak")
        if not isinstance(snak, dict) or snak.get("snaktype") != "value":
            raise ValidationError(f"Missing or uncertain value for {property_id}.")
        datavalue = snak.get("datavalue")
        if not isinstance(datavalue, dict) or "value" not in datavalue:
            raise ValidationError(f"Missing value for {property_id}.")
        values.append(datavalue["value"])
    if not values:
        raise ValidationError(f"Essential claim {property_id} is missing.")
    return values


def birth_date(entity):
    dates = set()
    for value in claim_values(entity, "P569"):
        if not isinstance(value, dict):
            raise ValidationError("Invalid birth-date claim.")
        precision = value.get("precision")
        calendar = value.get("calendarmodel")
        raw_date = value.get("time")
        if (type(precision) is not int or precision < 11
                or calendar != "http://www.wikidata.org/entity/Q1985727"
                or value.get("before", 0) != 0 or value.get("after", 0) != 0):
            raise ValidationError("Birth date is uncertain or is not an exact Gregorian day.")
        if not isinstance(raw_date, str) or not re.fullmatch(
            r"\+[0-9]{4}-[0-9]{2}-[0-9]{2}T00:00:00Z", raw_date
        ):
            raise ValidationError("Birth date is not a supported YYYY-MM-DD date.")
        try:
            parsed_date = date.fromisoformat(raw_date[1:11])
        except ValueError:
            raise ValidationError("Birth date is not a real calendar date.") from None
        if parsed_date > date.today():
            raise ValidationError("Birth date cannot be in the future.")
        dates.add(parsed_date.isoformat())
    if len(dates) != 1:
        raise ValidationError("Conflicting birth-date claims require manual review.")
    return next(iter(dates))


def readable_claims(entity, property_id, cache):
    labels = set()
    for value in claim_values(entity, property_id):
        entity_id = value.get("id") if isinstance(value, dict) else None
        if not valid_id(entity_id):
            raise ValidationError(f"Invalid entity reference in {property_id}.")
        labels.add(english_label(get_entity(entity_id, cache)))
    # Multiple citizenships/positions are valid. Keep every label in stable order
    # in the requested string field, instead of claiming one is the primary value.
    return "; ".join(sorted(labels, key=str.casefold))


def prepare_player(reference, cache, seen_ids):
    if not isinstance(reference, dict):
        raise ValidationError("Each input player must be a JSON object.")
    entity_id = reference.get("wikidataId")
    expected_name = reference.get("expectedName")
    if not valid_id(entity_id):
        raise ValidationError("Input wikidataId must be a valid ID such as Q615.")
    if not isinstance(expected_name, str) or not normalize_name(expected_name):
        raise ValidationError("Input expectedName is missing or invalid.")
    if entity_id in seen_ids:
        raise ValidationError("Duplicate player ID in the input list.")
    seen_ids.add(entity_id)

    entity = get_entity(entity_id, cache)
    name = english_label(entity)
    if normalize_name(name) != normalize_name(expected_name):
        raise ValidationError(
            f"Identity mismatch: Wikidata English name is {name!r}; manual review required."
        )
    # Only validated Wikidata values enter the output. No photos or provider IDs.
    return {
        "documentId": f"wikidata_{entity_id}",
        "wikidataId": entity_id,
        "name": name,
        "dateOfBirth": birth_date(entity),
        "nationality": readable_claims(entity, "P27", cache),
        "position": readable_claims(entity, "P413", cache),
        "source": "Wikidata",
    }


def main():
    try:
        with INPUT_FILE.open(encoding="utf-8-sig") as input_file:
            data = json.load(input_file)
    except FileNotFoundError:
        print("Input file not found: Backend/input/players_to_import.json.")
        return 1
    except (ValueError, UnicodeError):
        print("Input file must contain valid UTF-8 JSON.")
        return 1
    except OSError:
        print("Could not read the input file. Check file permissions.")
        return 1
    references = data.get("players") if isinstance(data, dict) else None
    if not isinstance(references, list) or not references:
        print("Input must contain a nonempty players array.")
        return 1

    cache = {}
    seen_ids = set()
    players = []
    failures = []
    print("Retrieving and validating Wikidata players...")
    for index, reference in enumerate(references, start=1):
        try:
            player = prepare_player(reference, cache, seen_ids)
        except ValidationError as error:
            name = reference.get("expectedName", "Unknown name") if isinstance(reference, dict) else "Unknown name"
            entity_id = reference.get("wikidataId", "Unknown ID") if isinstance(reference, dict) else "Unknown ID"
            failures.append(f"{name} ({entity_id}): {error}")
            print(f"[{index}/{len(references)}] FAILED: {name} ({entity_id})")
        else:
            players.append(player)
            print(f"[{index}/{len(references)}] VALIDATED: {player['name']} ({player['wikidataId']})")

    if failures:
        print("\nValidation failures (excluded from output):")
        for failure in failures:
            print(f"  - {failure}")
    print(f"\nSuccessful: {len(players)} | Failed: {len(failures)}")
    try:
        OUTPUT_FILE.parent.mkdir(parents=True, exist_ok=True)
        OUTPUT_FILE.write_text(
            json.dumps({"players": players}, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
    except OSError:
        print("Could not save the prepared JSON. Check output-folder permissions.")
        return 1
    print(f"Saved {len(players)} validated records to: {OUTPUT_FILE}")
    # Nonzero means at least one input needs attention, even if others succeeded.
    return 1 if failures else 0


# No live requests happen when this module is imported.
if __name__ == "__main__":
    raise SystemExit(main())
