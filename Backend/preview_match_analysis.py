"""Preview fictional match events and highlight timelines entirely offline."""

import argparse
import copy
import json
from pathlib import Path

from competition_mapping import load_verified_catalog
from highlight_service import prepare_highlight_bundles
from import_multiple_players import PreviewError as PlayerPreviewError, load_players
from match_event_service import make_related_id, preview_curated_records
from match_service import local_document_reader, preview_matches, summarize_plan
from preview_multiple_teams import PreviewError as TeamPreviewError, load_teams
from validate_competition_schema import INPUT_FILE as DEMO_CATALOG_FILE
from validate_match_schema import ValidationError, reject_duplicate_fields


DEMO_MATCH_FILE = Path(__file__).resolve().parent / "input" / "match_schema_test_cases.json"
MESSAGE = "OFFLINE DRY RUN ONLY - No external requests, media access or database changes; no provider data saved."


def load_demo_analysis():
    with DEMO_MATCH_FILE.open(encoding="utf-8-sig") as handle:
        data = json.load(handle, object_pairs_hook=reject_duplicate_fields)
    matches = data.get("matches") if isinstance(data, dict) else None
    if not isinstance(matches, list):
        raise ValidationError("The fictional match cases must contain a matches array.")
    selected = [row for row in matches if isinstance(row, dict) and row.get("matchId") == "demo_regular_001"]
    if len(selected) != 1 or selected[0].get("isDemo") is not True:
        raise ValidationError("Exactly one explicitly fictional regular-finish example is required.")
    match = copy.deepcopy(selected[0])
    # This association belongs only to the local demonstration, not a real competition.
    match["competitionId"] = "demo_competition_001"
    teams = load_teams()
    players = [dict(player, documentId=identifier) for identifier, player in load_players()]
    if not players:
        raise ValidationError("The demo needs at least one validated local player reference.")
    catalog = load_verified_catalog(DEMO_CATALOG_FILE)
    # Real identity references may appear in fictional events. This does not
    # establish actual participation, club membership or an actual goal/save.
    events = [
        {"eventId": make_related_id(match["matchId"], "event", "goal_1"),
         "matchId": match["matchId"], "teamId": match["homeTeamId"],
         "playerId": players[0]["documentId"], "eventType": "goal", "matchMinute": 45,
         "addedTime": 2, "label": "Fictional goal", "isDemo": True, "source": "demo"},
        {"eventId": make_related_id(match["matchId"], "event", "save_1"),
         "matchId": match["matchId"], "teamId": match["awayTeamId"], "playerId": None,
         "eventType": "save", "matchMinute": None, "addedTime": None,
         "label": "Fictional save with unknown match minute", "isDemo": True, "source": "demo"},
    ]
    highlights = [{
        "highlightId": make_related_id(match["matchId"], "highlight", "clip_1"),
        "matchId": match["matchId"], "title": "Fictional virtual timeline - no video",
        "mediaType": None, "mediaReference": None, "durationSeconds": 120,
        "rightsStatus": "unconfirmed", "rightsEvidence": None,
        "markers": [{"eventId": events[0]["eventId"], "videoSeconds": 30},
                    {"eventId": events[1]["eventId"], "videoSeconds": 75}],
        "isDemo": True, "source": "demo",
    }]
    return prepare_highlight_bundles([match], teams, players, catalog, events, highlights)[0], teams, catalog


def simulate_analysis(prepared, teams, catalog, operation):
    """Compare a validated bundle with isolated fictional document states."""
    if operation not in ("CREATE", "UPDATE", "NO CHANGE"):
        raise ValidationError("Choose a supported offline preview operation.")
    match = prepared["match"]
    documents = {"teams": {team["teamId"]: team for team in teams},
                 "competitions": {row["competitionId"]: row for row in catalog["competitions"]}, "matches": {}}
    if operation != "CREATE":
        documents["matches"][match["matchId"]] = dict(prepared["firestoreData"], unrelated="Preserved")
        if operation == "UPDATE":
            documents["matches"][match["matchId"]]["season"] = "Earlier fictional season"
    plans = {"matches": preview_matches([match], teams, catalog, local_document_reader(documents))}
    for collection, field, changed_field in (("events", "eventId", "label"),
                                              ("highlights", "highlightId", "title")):
        existing = {}
        if operation != "CREATE":
            existing = {row[field]: dict(copy.deepcopy(row), unrelated="Preserved") for row in prepared[collection]}
            if operation == "UPDATE":
                for row in existing.values():
                    row[changed_field] = "Earlier fictional text"
        plans[collection] = preview_curated_records(prepared[collection], existing, field)
    return plans


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, allow_abbrev=False)
    parser.parse_args(argv)  # No live mode, write flag, output files or media URLs.
    try:
        prepared, teams, catalog = load_demo_analysis()
        print("FICTIONAL DEMONSTRATION - not real match results or actual video positions.")
        print("Player references verify identity only; demo participation is fictional.")
        print(f"Match: {prepared['match']['matchId']}")
        for timeline in prepared["highlightTimelines"]:
            print(f"Highlight: {timeline['highlightId']} | Playback eligible: {timeline['playbackEligible']}")
            for marker in timeline["markers"]:
                print(f"  {marker['eventId']} | Match clock: {marker['matchClock'] or 'unknown'}"
                      f" | Fictional video seconds: {marker['videoSeconds']}")
        for operation in ("CREATE", "UPDATE", "NO CHANGE"):
            plans = simulate_analysis(prepared, teams, catalog, operation)
            print(f"\nSimulated {operation}:")
            for collection, plan in plans.items():
                counts = summarize_plan(plan)
                print(f"  {collection}: " + " | ".join(f"{key} {value}" for key, value in counts.items()))
        return 0
    except (ValidationError, PlayerPreviewError, TeamPreviewError) as error:
        print(f"FAILED: {error}")
    except (OSError, ValueError, TypeError, KeyError, AttributeError, RecursionError):
        print("FAILED: Invalid or unreadable local input; raw details hidden.")
    finally:
        print(MESSAGE)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
