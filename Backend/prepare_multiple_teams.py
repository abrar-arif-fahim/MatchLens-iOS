"""Prepare five verified team references as complete, local Firestore records."""

import json
import tempfile
from pathlib import Path
from validate_match_schema import reject_duplicate_fields

# Reuse the existing standard-library client: cached EntityData requests,
# descriptive User-Agent, timeouts, gentle pacing and bounded rate-limit retries.
# Its main guard makes this import safe. Never call its search/discover functions.
from discover_team_ids import (
    COUNTRIES, ValidationError, WikidataClient, club_name, english_aliases,
    english_description, english_label, other_section, valid_id,
)


BACKEND_DIR = Path(__file__).resolve().parent
INPUT_FILE = BACKEND_DIR / "output" / "teams_verified.json"
OUTPUT_FILE = BACKEND_DIR / "output" / "teams_prepared.json"
REFERENCE_FIELDS = {"expectedName", "expectedCountry", "shortName", "wikidataId"}
TEAM_COUNT = 5


def load_verified_teams():
    # Validate the whole input before making any requests.
    try:
        with INPUT_FILE.open(encoding="utf-8-sig") as input_file:
            data = json.load(input_file, object_pairs_hook=reject_duplicate_fields)
    except FileNotFoundError:
        raise ValidationError("Input file not found: Backend/output/teams_verified.json.") from None
    except (ValueError, UnicodeError):
        raise ValidationError("The verified input must contain valid UTF-8 JSON.") from None
    except OSError:
        raise ValidationError("Could not read the verified input. Check file permissions.") from None

    references = data.get("teams") if isinstance(data, dict) else None
    if not isinstance(references, list) or len(references) != TEAM_COUNT:
        raise ValidationError("The verified input must contain a teams array with exactly five clubs.")
    seen_ids, seen_names = set(), set()
    for index, reference in enumerate(references, start=1):
        if not isinstance(reference, dict) or set(reference) != REFERENCE_FIELDS:
            raise ValidationError(f"Club {index} must contain exactly the four verified-reference fields.")
        for field in REFERENCE_FIELDS:
            value = reference[field]
            if (not isinstance(value, str) or not value.strip()
                    or value.strip().casefold() in {"unknown", "n/a", "null", "none", "not available"}):
                raise ValidationError(f"Club {index}: {field} is missing or invalid.")
        entity_id = reference["wikidataId"]
        if not valid_id(entity_id):
            raise ValidationError(f"Club {index}: wikidataId must be a valid Q-number.")
        if entity_id in seen_ids:
            raise ValidationError(f"Club {index}: duplicate Wikidata ID {entity_id}.")
        name = club_name(reference["expectedName"])
        if not name or name in seen_names:
            raise ValidationError(f"Club {index}: empty or duplicate club identity.")
        if reference["expectedCountry"] not in COUNTRIES:
            raise ValidationError(f"Club {index}: application country is inconsistent with the verified format.")
        seen_ids.add(entity_id)
        seen_names.add(name)
    return references


def prepare_team(reference, client):
    entity_id = reference["wikidataId"]
    # One direct lookup of this club ID; no candidate search or country traversal.
    # The client rejects missing, redirected or inconsistent returned entity IDs.
    entity = client.get_entity(entity_id)
    name = english_label(entity)
    aliases = english_aliases(entity)
    expected_name = club_name(reference["expectedName"])
    if not any(club_name(value) == expected_name for value in [name] + aliases):
        raise ValidationError(
            f"Identity mismatch for {entity_id}: expected {reference['expectedName']!r}, "
            f"but the current English label is {name!r} and its aliases do not match."
        )
    if other_section(name) or other_section(english_description(entity), description=True):
        raise ValidationError(f"Identity mismatch for {entity_id}: another team or sporting section is identified.")

    # Preserve the already validated application country (including England),
    # and the application's shortName. Do not replace either with guessed values.
    return {
        "teamId": f"wikidata_{entity_id}",
        "wikidataId": entity_id,
        "name": name,
        "shortName": reference["shortName"],
        "country": reference["expectedCountry"],
        "source": "Wikidata",
    }


def save_teams(teams):
    # Replace the output only when every club is prepared. A temporary file
    # prevents a failed save from leaving partial JSON or truncating an older file.
    OUTPUT_FILE.parent.mkdir(parents=True, exist_ok=True)
    temporary_path = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w", encoding="utf-8", dir=OUTPUT_FILE.parent, suffix=".tmp", delete=False
        ) as temporary_file:
            temporary_path = Path(temporary_file.name)
            json.dump({"teams": teams}, temporary_file, ensure_ascii=False, indent=2)
            temporary_file.write("\n")
        temporary_path.replace(OUTPUT_FILE)
    finally:
        if temporary_path is not None:
            temporary_path.unlink(missing_ok=True)


def main():
    teams = []
    try:
        references = load_verified_teams()
        client = WikidataClient()
        print("Preparing verified clubs using direct Wikidata EntityData requests...")
        for index, reference in enumerate(references, start=1):
            print(f"[{index}/{TEAM_COUNT}] Retrieving {reference['expectedName']} ({reference['wikidataId']})...")
            team = prepare_team(reference, client)
            teams.append(team)
            print(
                f"  PREPARED: {team['name']} | {team['teamId']} | "
                f"{team['country']} | {team['shortName']}"
            )
        save_teams(teams)
    except ValidationError as error:
        print(f"FAILED: {error}")
    except OSError:
        print("FAILED: Could not save the prepared teams. Check output-folder permissions.")
    except (ValueError, TypeError, KeyError, AttributeError):
        print("FAILED: Unexpected or incomplete Wikidata data; preparation stopped.")
    except KeyboardInterrupt:
        print("\nCANCELLED: Team preparation interrupted.")
    else:
        print(f"\nSUCCESS: Prepared and saved {len(teams)} complete team records.")
        print(f"Saved to: {OUTPUT_FILE}")
        print("Application countries and shortName abbreviations were preserved from the verified input.")
        return 0

    print(f"Prepared before stopping: {len(teams)}/{TEAM_COUNT}. No new output was saved.")
    print("Any existing teams_prepared.json remains an older result, not a new successful preparation.")
    return 1


# Importing the script does not make requests. Run it manually to prepare teams.
if __name__ == "__main__":
    raise SystemExit(main())
