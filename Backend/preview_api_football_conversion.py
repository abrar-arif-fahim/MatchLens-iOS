"""Convert one season's head-to-head response in memory; never save or import."""

import argparse
from collections import Counter
from pathlib import Path

from competition_mapping import load_verified_catalog, resolve_competition

from convert_api_football_fixture import (
    ReviewRequired, convert_fixture, convert_kickoff, validate_team_mapping,
)
from preview_api_football_matches import (
    MappingError, fetch_head_to_head, head_to_head_query, load_team_mapping,
    read_api_key, read_fixture_records,
)
from validate_match_schema import ValidationError, validate_match


SEASON = 2024
PREVIEW_MESSAGE = "PREVIEW ONLY - No provider data saved. No Firebase changes."


def fixture_id(record):
    """Only return an ID that is safe to compare/display; never print raw input."""
    fixture = record.get("fixture") if isinstance(record, dict) else None
    value = fixture.get("id") if isinstance(fixture, dict) else None
    return value if type(value) is int and value > 0 else None


def validate_conversion(record, match, mapping, competition_catalog=None):
    # Recheck the schema independently, then check the conversion contract.
    validate_match(match)
    provider_id = record["fixture"]["id"]
    if (match["matchId"] != f"match_api_football_fixture_{provider_id}"
            or match["sourceMatchId"] != str(provider_id)):
        raise ValidationError("Converted internal/provider fixture IDs are inconsistent.")
    for side in ("home", "away"):
        api_id = record["teams"][side]["id"]
        if match[f"{side}TeamId"] != mapping[api_id]:
            raise ValidationError("Converted team references disagree with the verified mapping.")
    if match["kickoffUtc"] != convert_kickoff(record["fixture"], match["status"]):
        raise ValidationError("Converted kickoff does not preserve the provider's UTC instant.")
    competition_id = (resolve_competition(competition_catalog, record["league"]["id"])["competitionId"]
                      if competition_catalog is not None else None)
    if (match["sourceCompetitionId"] != str(record["league"]["id"])
            or match["competitionId"] != competition_id):
        raise ValidationError("Provider/internal competition identifiers were not kept separate.")
    if match["isDemo"] is not False or match["source"] != "API-Football":
        raise ValidationError("Converted source metadata is inconsistent with real-source mode.")
    if record["league"]["season"] != SEASON:
        raise ReviewRequired("Returned league.season differs from the requested 2024 season.")


def score_pair(match, home_field, away_field):
    # Preserve unknown scores in the display instead of replacing them with 0.
    home, away = match[home_field], match[away_field]
    return f"{'null' if home is None else home} / {'null' if away is None else away}"


def display_match(match):
    # Print only validated IDs, timestamps, enums and scores. Raw names, headers,
    # provider objects and arbitrary error text are deliberately not displayed.
    print(f"  Internal match ID: {match['matchId']}")
    print(f"  Home -> {match['homeTeamId']} | Away -> {match['awayTeamId']}")
    print(f"  Kickoff UTC: {match['kickoffUtc'] or 'null'}")
    print(f"  Status: {match['status']} | Finish: {match['finishType'] or 'null'}")
    print("  Goals (home / away): " + score_pair(match, "homeScore", "awayScore"))
    print("  Regular time: " + score_pair(match, "regularTimeHomeScore", "regularTimeAwayScore"))
    print("  Extra-time period: " + score_pair(match, "extraTimeHomeScore", "extraTimeAwayScore"))
    print("  Shootout: " + score_pair(match, "penaltyHomeScore", "penaltyAwayScore"))
    print(f"  Provider competition ID: {match['sourceCompetitionId']} | Season: {match['season']}")
    if match["competitionId"] is None:
        print("  Internal competition ID: null (mapping not verified)")
    else:
        print(f"  Internal competition ID: {match['competitionId']}")


def preview_records(records, mapping, competition_catalog=None):
    """Convert all records independently; retain only summary counts afterward."""
    counts = {"PASSED": 0, "REVIEW REQUIRED": 0, "FAILED": 0}
    occurrences = Counter(fixture_id(record) for record in records if fixture_id(record) is not None)
    for index, record in enumerate(records, start=1):
        provider_id = fixture_id(record)
        label = f"Record {index} | API-Football fixture {provider_id if provider_id is not None else '<invalid>'}"
        try:
            if not isinstance(record, dict):
                raise ValidationError("The returned fixture record is not an object.")
            if provider_id is not None and occurrences[provider_id] > 1:
                raise ReviewRequired("Duplicate fixture ID in this response; records cannot be treated as separate matches.")
            match = convert_fixture(record, mapping, is_demo=False, competition_catalog=competition_catalog)
            validate_conversion(record, match, mapping, competition_catalog)
        except ReviewRequired as error:
            counts["REVIEW REQUIRED"] += 1
            print(f"\n{label} | {error}")
        except ValidationError as error:
            counts["FAILED"] += 1
            print(f"\n{label} | FAILED: {error}")
        except (ValueError, TypeError, KeyError, AttributeError, OverflowError):
            counts["FAILED"] += 1
            print(f"\n{label} | FAILED: Unexpected conversion structure or value; raw details hidden.")
        else:
            counts["PASSED"] += 1
            print(f"\n{label} | PASSED")
            display_match(match)
    return counts


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, allow_abbrev=False)
    parser.add_argument("--competition-catalog", type=Path,
                        help="Use a locally reviewed catalog for strict internal competition mapping.")
    args = parser.parse_args(argv)  # No endpoint overrides, retries or write flags.
    requests_used = 0
    total = None
    counts = {"PASSED": 0, "REVIEW REQUIRED": 0, "FAILED": 0}
    completed = False
    try:
        # Reuse the existing local references and already verified 529/541 IDs.
        mapping = {api_id: team["teamId"] for api_id, team in load_team_mapping().items()}
        validate_team_mapping(mapping)
        catalog = load_verified_catalog(args.competition_catalog) if args.competition_catalog else None
        api_key = read_api_key()
        if not api_key:
            print("ERROR: API-Football credentials are unavailable in the existing .env configuration.")
            return 1
        print("Real-source conversion preview - API-Football, isDemo=false.")
        print("GET /fixtures/headtohead?" + head_to_head_query(SEASON))
        for api_id, team_id in mapping.items():
            print(f"Verified mapping: API-Football {api_id} -> teams/{team_id}")
        if catalog is None:
            print("No competition catalog selected; competitionId stays null.")
        else:
            print("Strict local competition mapping enabled. Unknown/pending IDs require review.")
        requests_used = 1
        # This existing helper makes one GET, with redirects blocked and no retry.
        data, notices = fetch_head_to_head(api_key, season=SEASON)
        for notice in notices:
            print(f"Notice: {notice}")
        records, response_issues = read_fixture_records(data)
        total = len(records)
        print(f"Fixtures returned: {total}. Processing all returned records in memory.")
        counts = preview_records(records, mapping, catalog)
        if not records:
            print("No fixtures returned; no conversion success is claimed and no fallback was requested.")
        for issue in response_issues:
            print(f"Response REVIEW REQUIRED: {issue}")
        completed = True
        return 1 if (not records or counts["REVIEW REQUIRED"] or counts["FAILED"] or response_issues) else 0
    except (ValidationError, MappingError) as error:
        print(f"ERROR: {error}")  # Only our own safe messages, not raw responses.
    except OSError:
        print("ERROR: Could not read existing local references or API configuration.")
    except (ValueError, TypeError, KeyError, AttributeError, OverflowError):
        print("ERROR: Unexpected response or configuration; raw details hidden. No retry was issued.")
    except KeyboardInterrupt:
        print("\nCANCELLED: Conversion preview interrupted.")
    finally:
        print(f"\nSummary: fixtures returned {total if total is not None else 'unknown'} | "
              f"PASSED {counts['PASSED']} | REVIEW REQUIRED {counts['REVIEW REQUIRED']} | FAILED {counts['FAILED']}")
        if not completed:
            print("Preview incomplete; request/configuration failure is not a fixture conversion result.")
        print(f"API requests attempted: {requests_used}/1. No retries, redirects or additional pages.")
        print("Successful conversion does not grant permission to store or redistribute provider data.")
        print(PREVIEW_MESSAGE)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
