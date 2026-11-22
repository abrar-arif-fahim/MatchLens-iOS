"""Resolve reviewed competition references locally. No API, Firebase or writes."""

import argparse
import re
from pathlib import Path

from validate_competition_schema import load_catalog, validate_catalog
from validate_match_schema import SLUG, ValidationError, require_text, validate_match


CATALOG_FILE = Path(__file__).resolve().parent / "input" / "competition_mappings.json"


def load_verified_catalog(path=CATALOG_FILE):
    catalog = load_catalog(path)
    validate_catalog(catalog)
    return catalog


def provider_id_text(value):
    # Accept the numeric API field or our catalog's canonical string, never bool.
    if type(value) is int and value > 0:
        return str(value)
    if isinstance(value, str) and re.fullmatch(r"[1-9][0-9]*", value):
        return value
    raise ValidationError("Provider competition ID must be a canonical positive integer.")


def get_competition(catalog, competition_id):
    validate_catalog(catalog)
    require_text(competition_id, "competitionId")
    if not re.fullmatch(r"(?:demo_)?competition_" + SLUG, competition_id):
        raise ValidationError("Invalid internal competition ID.")
    for competition in catalog["competitions"]:
        if competition["competitionId"] == competition_id:
            return dict(competition)
    raise ValidationError("The internal competition is absent from the catalog.")


def resolve_competition(catalog, provider_id, provider="API-Football"):
    # Validate the WHOLE catalog: a lookup must not conceal duplicate/conflicting IDs.
    validate_catalog(catalog)
    if provider != "API-Football":
        raise ValidationError("Unsupported competition provider namespace.")
    external_id = provider_id_text(provider_id)
    for mapping in catalog["providerMappings"]:
        if mapping["provider"] == provider and mapping["providerCompetitionId"] == external_id:
            if mapping["status"] != "verified":
                raise ValidationError("Competition mapping is pending; manual review is required.")
            return get_competition(catalog, mapping["competitionId"])
    raise ValidationError("No verified competition mapping exists for this provider ID.")


def validate_match_competition(match, catalog):
    """Check a match's internal link and provider association without changing it."""
    validate_match(match)
    if match["competitionId"] is None:
        raise ValidationError("Match competitionId is unresolved; manual review is required.")
    competition = get_competition(catalog, match["competitionId"])
    if competition["isDemo"] != match["isDemo"]:
        raise ValidationError("Match and competition demonstration markers disagree.")
    if not match["isDemo"] and match["source"] == "API-Football":
        expected = resolve_competition(catalog, match["sourceCompetitionId"])
        if expected["competitionId"] != match["competitionId"]:
            raise ValidationError("Match competitionId conflicts with its verified provider mapping.")
    return competition


def get_competition_seasons(catalog, competition_id):
    # No season is selected by a fixture's provider year or guessed calendar dates.
    get_competition(catalog, competition_id)
    return [dict(season) for season in catalog["seasons"]
            if season["competitionId"] == competition_id]


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, allow_abbrev=False)
    parser.add_argument("--catalog", type=Path, default=CATALOG_FILE)
    args = parser.parse_args(argv)
    try:
        catalog = load_verified_catalog(args.catalog)
        print("LOCAL COMPETITION MAPPING VALIDATION")
        for mapping in catalog["providerMappings"]:
            target = mapping["competitionId"] or "unresolved"
            print(f"{mapping['provider']} {mapping['providerCompetitionId']} -> {target} | {mapping['status']}")
        print(f"Competitions: {len(catalog['competitions'])} | Seasons: {len(catalog['seasons'])}")
        print("Identity review metadata only; no provider storage/reuse permission is implied.")
        return 0
    except ValidationError as error:
        print(f"FAILED: {error}")
        return 1
    finally:
        print("LOCAL ONLY - No external requests, files written or Firebase changes.")


if __name__ == "__main__":
    raise SystemExit(main())
