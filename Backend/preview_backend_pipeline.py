"""Run the integrated pipeline on existing fictional match data, entirely locally."""

import argparse

from competition_mapping import load_verified_catalog
from match_service import local_document_reader, preview_matches, summarize_plan
from preview_match_import import display_match_value
from preview_multiple_teams import PreviewError, load_teams
from validate_competition_schema import INPUT_FILE as DEMO_CATALOG_FILE
from validate_match_schema import ValidationError, load_match, validate_match


MESSAGE = "OFFLINE DRY RUN ONLY - No external requests or database changes; no provider data saved."


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, allow_abbrev=False)
    parser.parse_args(argv)  # No live mode, output path, write flag or credential options.
    try:
        match = load_match()
        validate_match(match)
        if not match["isDemo"]:
            raise ValidationError("This offline demonstration accepts only explicitly fictional match data.")
        teams = load_teams()
        catalog = load_verified_catalog(DEMO_CATALOG_FILE)
        documents = {"teams": {team["teamId"]: team for team in teams},
                     "competitions": {item["competitionId"]: item for item in catalog["competitions"]},
                     "matches": {}}
        plan = preview_matches([match], teams, catalog, local_document_reader(documents))
        print("FICTIONAL DEMONSTRATION - Local snapshots, not a Firestore query.")
        for entry in plan:
            prepared = entry["prepared"]
            print(f"{entry['matchId']} | {entry['operation']}")
            print(f"  Home: {prepared['homeTeam']['teamId']} | Away: {prepared['awayTeam']['teamId']}")
            print(f"  Competition: {prepared['competition']['competitionId']}")
            print(f"  UTC kickoff: {prepared['match']['kickoffUtc'] or 'null'}")
            for field, old, new in entry["differences"]:
                print(f"  {field}: {display_match_value(old)} -> {display_match_value(new)}")
        counts = summarize_plan(plan)
        print("Simulated summary: " + " | ".join(f"{key} {value}" for key, value in counts.items()))
        return 0
    except (ValidationError, PreviewError) as error:
        print(f"FAILED: {error}")
    except (OSError, ValueError, TypeError, KeyError, AttributeError):
        print("FAILED: Invalid local data or unreadable input; raw details hidden.")
    finally:
        print(MESSAGE)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
