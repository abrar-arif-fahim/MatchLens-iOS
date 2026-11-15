"""Validate a local competition catalog. No network, credentials or file writes."""

import json
import re
from datetime import date
from pathlib import Path

from validate_match_schema import (
    SLUG, ValidationError, reject_duplicate_fields, require_text, validate_kickoff,
)


INPUT_FILE = Path(__file__).resolve().parent / "input" / "competition_schema_example.json"
CATALOG_FIELDS = {"competitions", "seasons", "providerMappings"}
COMPETITION_FIELDS = {"competitionId", "name", "competitionType", "country", "region", "isDemo", "source"}
SEASON_FIELDS = {"seasonId", "competitionId", "label", "startYear", "endYear", "startDate", "endDate", "isDemo", "source"}
MAPPING_FIELDS = {"provider", "providerCompetitionId", "competitionId", "status", "verificationEvidence", "verifiedAt"}
COMPETITION_TYPES = {"domesticLeague", "nationalCup", "internationalTournament", "friendly"}


def load_catalog(path=INPUT_FILE):
    try:
        with Path(path).open(encoding="utf-8-sig") as input_file:
            return json.load(input_file, object_pairs_hook=reject_duplicate_fields)
    except ValidationError:
        raise
    except FileNotFoundError:
        raise ValidationError("Competition input file was not found.") from None
    except (ValueError, UnicodeError, RecursionError):
        raise ValidationError("Competition input must contain valid UTF-8 JSON.") from None
    except OSError:
        raise ValidationError("Could not read competition input. Check file permissions.") from None


def require_fields(record, fields, label):
    if not isinstance(record, dict) or set(record) != fields:
        raise ValidationError(f"{label} must contain exactly its required schema fields.")


def validate_provenance(record):
    if type(record["isDemo"]) is not bool:
        raise ValidationError("isDemo must be a boolean.")
    require_text(record["source"], "source")
    if record["isDemo"] and record["source"] != "demo":
        raise ValidationError("Fictional records must use source demo.")
    if not record["isDemo"] and re.search(r"\bdemo\b", record["source"], re.IGNORECASE):
        raise ValidationError("Real-source records cannot claim a demo source.")


def validate_competition(record):
    require_fields(record, COMPETITION_FIELDS, "Competition")
    validate_provenance(record)
    require_text(record["competitionId"], "competitionId")
    prefix = "demo_competition_" if record["isDemo"] else "competition_"
    if not re.fullmatch(prefix + SLUG, record["competitionId"]):
        raise ValidationError("competitionId must use competition_<slug> or demo_competition_<slug> according to isDemo.")
    require_text(record["name"], "name")
    kind = record["competitionType"]
    if kind is not None and (not isinstance(kind, str) or kind not in COMPETITION_TYPES):
        raise ValidationError("competitionType must be domesticLeague, nationalCup, internationalTournament, friendly or null.")
    for field in ("country", "region"):
        if record[field] is not None:
            require_text(record[field], field)


def parse_date(value, field):
    if value is None:
        return None
    if not isinstance(value, str) or not re.fullmatch(r"[0-9]{4}-[0-9]{2}-[0-9]{2}", value):
        raise ValidationError(f"{field} must be YYYY-MM-DD or null.")
    try:
        return date.fromisoformat(value)
    except ValueError:
        raise ValidationError(f"{field} contains an invalid calendar date.") from None


def validate_season(record, competitions):
    require_fields(record, SEASON_FIELDS, "Season")
    validate_provenance(record)
    require_text(record["competitionId"], "Season competitionId")
    competition = competitions.get(record["competitionId"])
    if competition is None:
        raise ValidationError("Season references a competition absent from this catalog.")
    if record["isDemo"] != competition["isDemo"]:
        raise ValidationError("Season and competition demo markers must agree.")
    require_text(record["seasonId"], "seasonId")
    if not re.fullmatch(re.escape(record["competitionId"]) + "_season_" + SLUG, record["seasonId"]):
        raise ValidationError("seasonId must use its competitionId followed by _season_<slug>.")
    require_text(record["label"], "Season label")
    for field in ("startYear", "endYear"):
        if type(record[field]) is not int or not 1000 <= record[field] <= 9999:
            raise ValidationError(f"{field} must be a four-digit integer; omit an unverified season record rather than guess years.")
    if record["startYear"] > record["endYear"]:
        raise ValidationError("A season cannot end before its startYear.")
    start = parse_date(record["startDate"], "startDate")
    end = parse_date(record["endDate"], "endDate")
    if ((start is not None and start.year != record["startYear"])
            or (end is not None and end.year != record["endYear"])):
        raise ValidationError("Season dates must agree with their supplied startYear/endYear.")
    if start is not None and end is not None and end < start:
        raise ValidationError("A season endDate cannot precede its startDate.")


def validate_mappings(records, competitions):
    # Structural checks do not perform identity verification or grant data rights.
    seen_external, seen_internal = set(), set()
    for record in records:
        require_fields(record, MAPPING_FIELDS, "Provider mapping")
        if record["provider"] != "API-Football":
            raise ValidationError("Only the exact provider namespace API-Football is supported initially.")
        external_id = record["providerCompetitionId"]
        require_text(external_id, "providerCompetitionId")
        if not re.fullmatch(r"[1-9][0-9]*", external_id):
            raise ValidationError("API-Football competition IDs must be canonical positive integer strings.")
        external_key = (record["provider"], external_id)
        if external_key in seen_external:
            raise ValidationError("Duplicate provider competition ID; repeated or conflicting mappings require review.")
        seen_external.add(external_key)
        if record["status"] == "pending":
            if any(record[field] is not None for field in ("competitionId", "verificationEvidence", "verifiedAt")):
                raise ValidationError("Pending mappings must have null target and verification metadata.")
            continue
        if record["status"] != "verified":
            raise ValidationError("Mapping status must be pending or verified.")
        require_text(record["competitionId"], "Mapping competitionId")
        competition = competitions.get(record["competitionId"])
        if competition is None or competition["isDemo"]:
            raise ValidationError("Verified provider mappings must reference an existing non-demo competition in this catalog.")
        internal_key = (record["provider"], record["competitionId"])
        if internal_key in seen_internal:
            raise ValidationError("Multiple IDs from one provider target the same competition; manual review is required.")
        seen_internal.add(internal_key)
        require_text(record["verificationEvidence"], "verificationEvidence")
        validate_kickoff(record["verifiedAt"], "finished")  # Reuse exact UTC-Z validation.


def validate_catalog(data):
    require_fields(data, CATALOG_FIELDS, "Competition catalog")
    for field in CATALOG_FIELDS:
        if not isinstance(data[field], list):
            raise ValidationError("competitions, seasons and providerMappings must be arrays.")
    if not data["competitions"]:
        raise ValidationError("At least one competition is required.")
    competitions = {}
    for record in data["competitions"]:
        validate_competition(record)
        competition_id = record["competitionId"]
        if competition_id in competitions:
            raise ValidationError("Duplicate competitionId in this catalog.")
        competitions[competition_id] = record
    seen_seasons = set()
    for record in data["seasons"]:
        validate_season(record, competitions)
        if record["seasonId"] in seen_seasons:
            raise ValidationError("Duplicate seasonId in this catalog.")
        seen_seasons.add(record["seasonId"])
    validate_mappings(data["providerMappings"], competitions)


def main():
    try:
        data = load_catalog()
        validate_catalog(data)
    except ValidationError as error:
        print(f"FAILED: {error}")  # Own explanations only; never dump arbitrary input.
        return 1
    print("SUCCESS: Competition schema passed local structure and value validation.")
    print(f"Records: competitions {len(data['competitions'])} | seasons {len(data['seasons'])} | mappings {len(data['providerMappings'])}")
    if any(record["isDemo"] for record in data["competitions"]):
        print("DEMO ONLY: Demo competitions and seasons are fictional, not verified football information.")
    print("Structure only: competition facts, mapping evidence and data reuse permissions were not independently verified.")
    print("LOCAL VALIDATION ONLY - No external requests or database changes.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
