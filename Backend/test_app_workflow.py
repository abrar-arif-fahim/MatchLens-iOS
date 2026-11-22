"""Complete offline app workflows; authentication remains a simulated boundary."""

import copy
import io
import unittest
from contextlib import redirect_stdout, redirect_stderr
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

import preview_app_workflow as command
from app_repository import MemoryRepository
from app_service import AppReadService
from convert_api_football_fixture import convert_fixture
from test_competition_mapping import synthetic_catalog
from test_convert_api_football_fixture import VERIFIED_TEAMS
from test_match_event_service import fictional_event
from test_highlight_service import fictional_highlight
from test_preview_api_football_conversion import provider_record
from user_data_service import UserDataService, simulate_user_plan
from validate_match_schema import ValidationError


class AppWorkflowTests(unittest.TestCase):
    def setUp(self):
        for guard in (
            patch("urllib.request.OpenerDirector.open", side_effect=AssertionError("No network allowed")),
            patch("firebase_admin.initialize_app", side_effect=AssertionError("No live authentication allowed")),
            patch("firebase_admin.firestore.client", side_effect=AssertionError("No database allowed")),
            patch("api_football_players.read_api_key", side_effect=AssertionError("No credentials allowed")),
        ):
            guard.start()
            self.addCleanup(guard.stop)

    def test_complete_command_runs_all_screen_data_workflows_without_writes(self):
        original_open = Path.open
        def read_only_open(path, mode="r", *args, **kwargs):
            self.assertFalse(any(flag in mode for flag in "wax+"))
            return original_open(path, mode, *args, **kwargs)
        output = io.StringIO()
        with patch.object(Path, "open", read_only_open), patch.dict("os.environ", {}, clear=True), redirect_stdout(output):
            self.assertEqual(command.main([]), 0)
        text = output.getvalue()
        for expected in ("Session UID is simulated", "Repeated profile provisioning: NO CHANGE",
                         "Home feed: 1 fictional", "Player search/profile:", "Team information:",
                         "Match detail: 2 fictional", "Favorites: 4 | Watchlist: 1",
                         "Playback available: False", "SUCCESS: Offline", command.MESSAGE):
            self.assertIn(expected, text)

    def test_two_user_lifecycle_from_registration_recovery_to_saved_detail_and_settings(self):
        repo, catalog = command.load_demo_repository()
        original = copy.deepcopy(repo.documents)
        app = AppReadService(repo, catalog, actor_uid="test-alice", demo_mode=True)
        users = UserDataService(repo, app.resolve_reference, actor_uid="test-alice")
        clock = datetime(2030, 1, 2, tzinfo=timezone.utc)
        def apply(plan):
            repo.documents = simulate_user_plan(plan, repo.documents, actor_uid="test-alice",
                                                server_time=clock, resolve_reference=app.resolve_reference)
        self.assertIsNone(users.profile())
        apply(users.plan_profile("Fictional fan"))
        player = app.search_players("messi")["items"][0]
        card = app.home_feed()["matches"]["items"][0]
        detail = app.get_match_detail(card["match"]["matchId"])
        self.assertEqual(detail["match"], card["match"])
        apply(users.plan_favorite("player", player["playerId"]))
        apply(users.plan_favorite("highlight", detail["highlights"]["items"][0]["highlightId"]))
        apply(users.plan_watchlist(card["match"]["matchId"]))
        apply(users.plan_settings({"favoriteTeamId": card["homeTeam"]["teamId"], "appearance": "dark"}))
        self.assertEqual(len(users.saved_items()["items"]), 2)
        self.assertEqual(users.saved_items("watchlist")["items"][0]["target"]["matchId"], card["match"]["matchId"])
        self.assertEqual(users.settings()["values"]["appearance"], "dark")
        bob = UserDataService(repo, app.resolve_reference, actor_uid="test-bob")
        self.assertIsNone(bob.profile())
        self.assertEqual(bob.saved_items()["items"], [])
        for collection in ("players", "teams", "competitions", "matches", "matchEvents", "highlights"):
            self.assertEqual(repo.documents[collection], original[collection])

    def test_conversion_mapping_period_scores_analysis_and_user_reference_in_real_source_contract(self):
        # Fictional results exercise the real-source wire contract only in memory.
        base, _ = command.load_demo_repository()
        catalog = synthetic_catalog()
        for status in ("FT", "AET", "PEN", "NS", "1H"):
            with self.subTest(status=status):
                fixture = provider_record(status)
                match = convert_fixture(fixture, VERIFIED_TEAMS, is_demo=False, competition_catalog=catalog)
                documents = copy.deepcopy(base.documents)
                documents["competitions"] = {row["competitionId"]: row for row in catalog["competitions"]}
                documents["matches"] = {match["matchId"]: match}
                event = fictional_event(match, playerId="wikidata_Q615")
                highlight = fictional_highlight(match, event)
                documents["matchEvents"] = {} if status == "NS" else {event["eventId"]: event}
                documents["highlights"] = {} if status == "NS" else {highlight["highlightId"]: highlight}
                repository = MemoryRepository(documents)
                app = AppReadService(repository, catalog, actor_uid="test-alice")
                detail = app.get_match_detail(match["matchId"])
                self.assertFalse(detail["isDemo"])
                self.assertEqual(detail["match"]["sourceCompetitionId"], str(fixture["league"]["id"]))
                self.assertEqual(detail["match"]["sourceMatchId"], str(fixture["fixture"]["id"]))
                self.assertEqual(detail["match"]["homeScore"], fixture["goals"]["home"])
                self.assertEqual(detail["match"]["extraTimeHomeScore"], fixture["score"]["extratime"]["home"])
                self.assertEqual(detail["match"]["penaltyHomeScore"], fixture["score"]["penalty"]["home"])
                users = UserDataService(repository, app.resolve_reference, actor_uid="test-alice")
                self.assertEqual(users.plan_watchlist(match["matchId"])["operation"], "CREATE")

    def test_offline_cli_has_no_live_apply_or_output_flags(self):
        for args in (["--apply"], ["--live"], ["--output", "forbidden.json"]):
            with self.subTest(args=args), redirect_stderr(io.StringIO()), self.assertRaises(SystemExit) as caught:
                command.main(args)
            self.assertEqual(caught.exception.code, 2)

    def test_command_failure_is_explicit_and_keeps_offline_notice(self):
        for error in (FileNotFoundError(), ValidationError("Invalid local contract.")):
            output = io.StringIO()
            with self.subTest(error=type(error).__name__), patch.object(command, "load_demo_repository", side_effect=error), \
                 redirect_stdout(output):
                self.assertEqual(command.main([]), 1)
            self.assertIn("FAILED:", output.getvalue())
            self.assertIn(command.MESSAGE, output.getvalue())


if __name__ == "__main__":
    unittest.main()
