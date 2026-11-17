"""Validate the schema's FC Barcelona entity and prepare one local team record."""

import json
import tempfile
from pathlib import Path
from validate_match_schema import reject_duplicate_fields

# These standard-library helpers use the same Request/urlopen pattern as
# wikidata_test.py, with a descriptive User-Agent, timeout and entity cache.
# This module has a main guard, so importing it does not make live requests.
from prepare_multiple_players import (
    ValidationError,
    claim_values,
    english_label,
    get_entity,
    normalize_name,
    valid_id,
)


BACKEND_DIR = Path(__file__).resolve().parent
INPUT_FILE = BACKEND_DIR / "input" / "team_schema_example.json"
OUTPUT_FILE = BACKEND_DIR / "output" / "team_barcelona.json"
BARCELONA_NAMES = {
    "fc barcelona", "f c barcelona", "futbol club barcelona", "football club barcelona"
}


def load_schema():
    with INPUT_FILE.open(encoding="utf-8-sig") as input_file:
        schema = json.load(input_file, object_pairs_hook=reject_duplicate_fields)
    if not isinstance(schema, dict):
        raise ValidationError("The team schema must contain one JSON object.")
    if not valid_id(schema.get("wikidataId")):
        raise ValidationError("The schema needs a valid wikidataId such as Q7156.")
    expected_name = schema.get("name")
    if not isinstance(expected_name, str) or normalize_name(expected_name) not in BARCELONA_NAMES:
        raise ValidationError("This script expects the local name FC Barcelona.")
    if schema.get("country") != "Spain":
        raise ValidationError("The local expected country must be Spain.")
    if schema.get("shortName") != "BAR":
        raise ValidationError("The schema must supply BAR as the app-defined shortName.")
    return schema


def english_description(entity):
    descriptions = entity.get("descriptions")
    description = descriptions.get("en") if isinstance(descriptions, dict) else None
    value = description.get("value") if isinstance(description, dict) else None
    return value.strip() if isinstance(value, str) else ""


def english_aliases(entity):
    aliases = entity.get("aliases")
    entries = aliases.get("en", []) if isinstance(aliases, dict) else []
    if not isinstance(entries, list):
        raise ValidationError("Wikidata returned an invalid English alias list.")
    return [entry["value"].strip() for entry in entries
            if isinstance(entry, dict) and isinstance(entry.get("value"), str)
            and entry["value"].strip()]


def property_ids(entity, property_id):
    entity_ids = set()
    for value in claim_values(entity, property_id):
        entity_id = value.get("id") if isinstance(value, dict) else None
        if not valid_id(entity_id):
            raise ValidationError(f"Invalid entity reference in {property_id}.")
        entity_ids.add(entity_id)
    return sorted(entity_ids)


def verify_name_and_description(name, description, aliases):
    normalized_label = normalize_name(name)
    alias_match = any(normalize_name(alias) in BARCELONA_NAMES for alias in aliases)
    # A generic Barcelona label needs an explicit full-club-name alias as well.
    if normalized_label not in BARCELONA_NAMES:
        if normalized_label != "barcelona" or not alias_match:
            raise ValidationError("Identity mismatch: the English label/aliases do not identify FC Barcelona.")

    words = normalize_name(description).split()
    if not words:
        raise ValidationError("Identity uncertain: the English description is missing.")
    if not ("football" in words and "club" in words
            and ("spanish" in words or "spain" in words)):
        raise ValidationError("Identity mismatch: the description does not identify a Spanish football club.")
    # Reject other sporting sections, reserve teams and youth/women's teams.
    other_teams = {"basketball", "handball", "futsal", "women", "female", "femeni", "reserve", "youth"}
    if other_teams.intersection(words) or "b team" in normalize_name(description):
        raise ValidationError("Identity mismatch: the description identifies a different team or section.")


def verify_club_type(entity, cache):
    # P31 = instance of; P279 = subclass of. Follow a short, bounded hierarchy
    # in case Wikidata uses a more specific class than association football club.
    pending = [(entity_id, 0) for entity_id in property_ids(entity, "P31")]
    visited = set()
    while pending:
        entity_id, depth = pending.pop(0)
        if entity_id in visited:
            continue
        if len(visited) >= 30:
            raise ValidationError("Club classification is too broad; manual review is required.")
        visited.add(entity_id)
        club_type = get_entity(entity_id, cache)
        if normalize_name(english_label(club_type)) == "association football club":
            return
        claims = club_type.get("claims")
        if depth < 3 and isinstance(claims, dict) and claims.get("P279"):
            pending.extend((parent, depth + 1) for parent in property_ids(club_type, "P279"))
    raise ValidationError("Identity mismatch: P31/P279 does not establish an association football club.")


def prepare_team(schema):
    cache = {}
    entity_id = schema["wikidataId"]
    # Use the exact supplied ID. The request helper also rejects redirected IDs.
    entity = get_entity(entity_id, cache)
    name = english_label(entity)
    description = english_description(entity)
    aliases = english_aliases(entity)
    print(f"Requested Wikidata ID: {entity_id}")
    print(f"English name: {name}")
    print(f"English description: {description or '(not available)'}")
    print("English aliases:", "; ".join(aliases) if aliases else "(not available)")
    verify_name_and_description(name, description, aliases)

    # P17 = country. Never replace missing claims with the schema's expectation.
    country_ids = property_ids(entity, "P17")
    countries = [english_label(get_entity(country_id, cache)) for country_id in country_ids]
    print("Country from Wikidata:", "; ".join(countries))
    if country_ids != ["Q29"] or countries != ["Spain"]:
        raise ValidationError("Identity mismatch: country claims do not unambiguously identify Spain.")
    verify_club_type(entity, cache)
    print("Classification: association football club (verified through P31/P279)")
    print("shortName: BAR (application-defined, not verified as a Wikidata value)")
    return {
        "teamId": f"wikidata_{entity_id}",
        "wikidataId": entity_id,
        "name": name,
        "shortName": schema["shortName"],
        "country": countries[0],
        # Attribution applies to Wikidata facts; shortName is the local app code.
        "source": "Wikidata",
    }


def save_team(team):
    # Save only after validation. Replace the output atomically so a failed save
    # cannot leave an older output truncated or a partially written new record.
    OUTPUT_FILE.parent.mkdir(parents=True, exist_ok=True)
    temporary_path = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w", encoding="utf-8", dir=OUTPUT_FILE.parent, suffix=".tmp", delete=False
        ) as temporary_file:
            temporary_path = Path(temporary_file.name)
            json.dump(team, temporary_file, ensure_ascii=False, indent=2)
            temporary_file.write("\n")
        temporary_path.replace(OUTPUT_FILE)
    finally:
        if temporary_path is not None:
            temporary_path.unlink(missing_ok=True)


def report_existing_output():
    try:
        if OUTPUT_FILE.exists():
            print(f"Existing output: {OUTPUT_FILE}")
            print("That file was not updated or validated by this failed run; do not treat it as a new result.")
        else:
            print("No team output file was created.")
    except OSError:
        print("Could not check whether an older output exists; this run produced no validated result.")


def main():
    try:
        schema = load_schema()
        print("Validating the supplied Wikidata entity for FC Barcelona...")
        team = prepare_team(schema)
        save_team(team)
    except ValidationError as error:
        print(f"FAILED: {error}")
    except FileNotFoundError:
        print("FAILED: Input file not found: Backend/input/team_schema_example.json.")
    except (ValueError, UnicodeError):
        print("FAILED: Invalid JSON, text encoding or incomplete Wikidata data.")
    except OSError:
        print("FAILED: Could not read the schema or save the output. Check file access.")
    except (KeyError, TypeError, AttributeError):
        print("FAILED: Unexpected or incomplete Wikidata data; manual review is required.")
    else:
        print("\nSUCCESS: FC Barcelona identity and essential Wikidata fields validated.")
        print(json.dumps(team, ensure_ascii=False, indent=2))
        print(f"Saved to: {OUTPUT_FILE}")
        return 0
    report_existing_output()
    return 1


# Importing this file never sends requests. Run it manually to start validation.
if __name__ == "__main__":
    raise SystemExit(main())
