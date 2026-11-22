"""Run the app's data workflows with fictional local snapshots only."""

import argparse
from datetime import datetime, timezone

from app_repository import MemoryRepository
from app_service import AppReadService
from auth_contracts import session_view
from import_multiple_players import PreviewError as PlayerError, load_players
from preview_match_analysis import load_demo_analysis
from preview_multiple_teams import PreviewError as TeamError
from user_data_service import UserDataService, simulate_user_plan
from validate_match_schema import ValidationError


DEMO_UID = "offline_demo_user"
MESSAGE = "OFFLINE ONLY - No Firebase Auth account, network request, Firestore write or media access."


def load_demo_repository():
    prepared, teams, catalog = load_demo_analysis()
    documents = {
        "players": {identifier: fields for identifier, fields in load_players()},
        "teams": {row["teamId"]: row for row in teams},
        "competitions": {row["competitionId"]: row for row in catalog["competitions"]},
        "matches": {prepared["match"]["matchId"]: prepared["firestoreData"]},
        "matchEvents": {row["eventId"]: row for row in prepared["events"]},
        "highlights": {row["highlightId"]: row for row in prepared["highlights"]},
    }
    return MemoryRepository(documents), catalog


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, allow_abbrev=False)
    parser.parse_args(argv)  # No live, apply, credential or output-file options.
    try:
        repository, catalog = load_demo_repository()
        app = AppReadService(repository, catalog, actor_uid=DEMO_UID, demo_mode=True)
        users = UserDataService(repository, app.resolve_reference, actor_uid=DEMO_UID)
        clock = datetime(2030, 1, 2, tzinfo=timezone.utc)  # Explicit fictional simulation clock.

        def simulate(plan):
            repository.documents = simulate_user_plan(plan, repository.documents, actor_uid=DEMO_UID,
                                                      server_time=clock, resolve_reference=app.resolve_reference)
            return plan["operation"]

        print("FICTIONAL OFFLINE APP WORKFLOW - Session UID is simulated; no actual login or registration.")
        identity = {"uid": DEMO_UID, "email": "offline@example.invalid", "emailVerified": False}
        print("Session contract before profile provisioning: " + session_view(identity, users.profile())["state"])
        print("Registration/profile contract: " + simulate(users.plan_profile("Offline MatchLens Fan")))
        print("Repeated profile provisioning: " + simulate(users.plan_profile("Offline MatchLens Fan")))
        print("Session contract after profile provisioning: " + session_view(identity, users.profile())["state"])
        feed = app.home_feed()
        player = app.search_players("messi")["items"][0]
        team = app.get_team("wikidata_Q7156")["team"]
        match_id = feed["matches"]["items"][0]["match"]["matchId"]
        detail = app.get_match_detail(match_id)
        highlight = detail["highlights"]["items"][0]
        print(f"Home feed: {len(feed['matches']['items'])} fictional match(s)")
        print(f"Player search/profile: {app.get_player(player['playerId'])['player']['name']}")
        print(f"Team information: {team['name']} | Roster: not collected")
        print(f"Match detail: {len(detail['events']['items'])} fictional events; "
              f"{len(detail['highlights']['items'])} metadata-only highlight(s)")
        for kind, identifier in (("player", player["playerId"]), ("team", team["teamId"]),
                                 ("match", match_id), ("highlight", highlight["highlightId"])):
            simulate(users.plan_favorite(kind, identifier))
        simulate(users.plan_watchlist(match_id))
        simulate(users.plan_settings({"appearance": "dark", "favoriteTeamId": team["teamId"]}))
        print(f"Favorites: {len(users.saved_items()['items'])} | Watchlist: {len(users.saved_items('watchlist')['items'])}")
        print("Settings: validated and simulated locally; no notifications are scheduled")
        print("Playback available: False | No video references are returned")
        print("Sign-out contract clears private state: " + session_view(None, users.profile())["state"])
        print("SUCCESS: Offline data workflows completed; live Firebase/iOS integration remains unverified.")
        return 0
    except (ValidationError, PlayerError, TeamError) as error:
        print(f"FAILED: {error}")
    except (OSError, ValueError, TypeError, KeyError, IndexError, AttributeError, RecursionError):
        print("FAILED: Invalid or unreadable local app data; raw details hidden.")
    finally:
        print(MESSAGE)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
