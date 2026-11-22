"""App contract and read workflows using fictional matches and local CC0 identities."""

import copy
import json
import unittest
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import Mock, patch

from app_contracts import (AccessError, match_document, player_document, require_owner, require_uid,
                           search_text, team_document, utc_text, validate_page_size, validate_public_path)
from app_repository import FirestoreReadRepository, MemoryRepository, RepositoryError
from app_service import AppReadService, NotFoundError, MEDIA_MESSAGE
from match_event_service import make_related_id
from preview_app_workflow import load_demo_repository
from validate_match_schema import ValidationError


class AppServicesTests(unittest.TestCase):
    def setUp(self):
        for guard in (
            patch("urllib.request.OpenerDirector.open", side_effect=AssertionError("No network allowed")),
            patch("firebase_admin.initialize_app", side_effect=AssertionError("No Auth/Admin setup allowed")),
            patch("firebase_admin.firestore.client", side_effect=AssertionError("No live client allowed")),
            patch("api_football_players.read_api_key", side_effect=AssertionError("No credentials allowed")),
        ):
            guard.start()
            self.addCleanup(guard.stop)
        self.repo, self.catalog = load_demo_repository()
        self.app = AppReadService(self.repo, self.catalog, actor_uid="test-alice", demo_mode=True)
        self.match_id = next(iter(self.repo.documents["matches"]))
        self.event_id = next(iter(self.repo.documents["matchEvents"]))
        self.highlight_id = next(iter(self.repo.documents["highlights"]))

    def test_uid_and_owner_checks_reject_missing_or_foreign_identity(self):
        for uid in (None, True, "", " ", "a/b", ".", "..", "a\nb", "a" * 129):
            with self.subTest(uid=uid), self.assertRaises(AccessError):
                require_uid(uid)
        self.assertEqual(require_uid("valid-custom.uid"), "valid-custom.uid")
        with self.assertRaises(AccessError):
            require_owner("test-alice", "test-bob")

    def test_public_path_rejects_cross_collection_paths_and_unverified_provider_ids(self):
        for collection, identifier in (("players", "529"), ("teams", "wikidata_Q01"), ("users", "test-alice"),
                                       ("players", "wikidata_Q1/other"), ("matches", "random"),
                                       ("highlights", "demo_highlight_parent__key__extra")):
            with self.subTest(collection=collection, identifier=identifier), self.assertRaises(ValidationError):
                validate_public_path(collection, identifier)

    def test_utc_conversion_accepts_aware_offsets_and_preserves_fractional_user_timestamps(self):
        value = datetime(2030, 1, 1, 18, tzinfo=timezone(timedelta(hours=2)))
        self.assertEqual(utc_text(value, whole_seconds=True), "2030-01-01T16:00:00Z")
        self.assertEqual(utc_text("2030-01-01T16:00:00.123456789Z"), "2030-01-01T16:00:00.123456789Z")
        self.assertEqual(utc_text(value), "2030-01-01T16:00:00.000000000Z")

    def test_invalid_or_naive_timestamps_are_not_invented(self):
        for value in (None, datetime(2030, 1, 1), "2030-02-30T00:00:00Z", "2030-01-01T00:00:00+01:00",
                      "2030-01-01", True, "2030-01-01T00:00:00.1234567890Z"):
            with self.subTest(value=value), self.assertRaises(ValidationError):
                utc_text(value)
        with self.assertRaises(ValidationError):
            utc_text("2030-01-01T00:00:00.001Z", whole_seconds=True)

    def test_sdk_nanoseconds_are_not_discarded(self):
        from google.api_core.datetime_helpers import DatetimeWithNanoseconds
        timestamp = DatetimeWithNanoseconds(2030, 1, 1, nanosecond=123456789, tzinfo=timezone.utc)
        self.assertEqual(utc_text(timestamp), "2030-01-01T00:00:00.123456789Z")
        with self.assertRaises(ValidationError):
            utc_text(timestamp, whole_seconds=True)

    def test_managed_projections_hide_provider_extras_and_keep_ids_separate(self):
        data = dict(self.repo.documents["players"]["wikidata_Q615"], apiFootballId=900001, photo="excluded", privateKey="excluded")
        player = player_document("wikidata_Q615", data)
        self.assertEqual(player["playerId"], "wikidata_Q615")
        self.assertNotIn("apiFootballId", player)
        self.assertNotIn("photo", player)
        self.assertNotIn("privateKey", player)
        self.assertEqual(set(player), {"playerId", "wikidataId", "name", "dateOfBirth", "nationality", "position", "source"})

    def test_identity_and_missing_public_fields_fail(self):
        team = self.repo.documents["teams"]["wikidata_Q7156"]
        for data in (dict(team, teamId="wikidata_Q8682"), {key: value for key, value in team.items() if key != "country"}):
            with self.subTest(data=data), self.assertRaises(ValidationError):
                team_document("wikidata_Q7156", data)
        player = dict(self.repo.documents["players"]["wikidata_Q615"], dateOfBirth="not-a-date")
        with self.assertRaises(ValidationError):
            player_document("wikidata_Q615", player)

    def test_match_document_converts_native_timestamp_but_not_invalid_identity(self):
        raw = self.repo.documents["matches"][self.match_id]
        result = match_document(self.match_id, raw)
        self.assertEqual(result["kickoffUtc"], "2030-01-01T18:00:00Z")
        with self.assertRaises(ValidationError):
            match_document("demo_other", raw)
        json.dumps(result)  # JSON read DTO, no response or file is saved.

    def test_search_normalization_and_page_sizes_are_explicit(self):
        self.assertEqual(search_text("  MBAPPÉ  "), "mbappe")
        for value in (None, "a\nb", "x" * 101):
            with self.subTest(value=value), self.assertRaises(ValidationError):
                search_text(value)
        for value in (True, 0, -1, 51, "20"):
            with self.subTest(value=value), self.assertRaises(ValidationError):
                validate_page_size(value)

    def test_service_requires_session_and_explicit_demo_boolean(self):
        for uid, demo in ((None, False), ("test-alice", 1)):
            with self.subTest(uid=uid), self.assertRaises(ValidationError):
                AppReadService(self.repo, self.catalog, actor_uid=uid, demo_mode=demo)

    def test_default_real_feed_hides_demo_records_and_direct_demo_lookup(self):
        production = AppReadService(self.repo, self.catalog, actor_uid="test-alice")
        feed = production.home_feed()
        self.assertFalse(feed["isDemo"])
        self.assertEqual(feed["matches"]["items"], [])
        with self.assertRaises(NotFoundError):
            production.get_match_detail(self.match_id)

    def test_home_feed_is_joined_without_fictional_trending_or_media_claims(self):
        result = self.app.home_feed()
        card = result["matches"]["items"][0]
        self.assertEqual(card["homeTeam"]["teamId"], card["match"]["homeTeamId"])
        self.assertEqual(card["competition"]["competitionId"], card["match"]["competitionId"])
        self.assertIn("Fictional", result["dataLabel"])
        self.assertEqual(result["featuredHighlights"], [])
        self.assertIn("unavailable", result["mediaMessage"])
        json.dumps(result)

    def test_player_search_handles_accents_and_profile_does_not_invent_rosters(self):
        result = self.app.search_players("MBAPPE")["items"]
        self.assertEqual([row["playerId"] for row in result], ["wikidata_Q21621995"])
        profile = self.app.get_player(result[0]["playerId"])
        self.assertIsNone(profile["team"])
        self.assertIsNone(profile["statistics"])
        self.assertEqual(profile["rosterStatus"], "notCollected")

    def test_team_search_abbreviation_and_profile(self):
        self.assertEqual(self.app.search_teams("BAR")["items"][0]["teamId"], "wikidata_Q7156")
        self.assertIsNone(self.app.get_team("wikidata_Q7156")["players"])
        matches = self.app.team_matches("wikidata_Q7156")
        self.assertEqual(len(matches["home"]["items"]), 1)
        self.assertEqual(matches["away"]["items"], [])

    def test_catalog_search_pagination_does_not_drop_matching_rows(self):
        identifiers, cursor = [], None
        while True:
            page = self.app.search_players("", page_size=1, cursor=cursor)
            identifiers.extend(row["playerId"] for row in page["items"])
            self.assertEqual(page["searchScope"], "boundedCatalogPage")
            if not page["hasMore"]:
                break
            cursor = page["nextCursor"]
        self.assertEqual(len(identifiers), 5)
        self.assertEqual(len(set(identifiers)), 5)

    def test_empty_search_page_can_still_offer_more_catalog_pages(self):
        prototype = next(iter(self.repo.documents["players"].values()))
        self.repo.documents["players"] = {
            f"wikidata_Q{index:05d}": dict(prototype, wikidataId=f"Q{index:05d}", name="Fictional Player")
            for index in range(90001, 90052)
        }
        last_id = sorted(self.repo.documents["players"])[-1]
        self.repo.documents["players"][last_id]["name"] = "Unique Fictional Match"
        first = self.app.search_players("unique")
        self.assertEqual(first["items"], [])
        self.assertTrue(first["hasMore"])
        second = self.app.search_players("unique", cursor=first["nextCursor"])
        self.assertEqual([row["playerId"] for row in second["items"]], [last_id])

    def test_long_valid_names_are_searchable_without_relaxing_user_input_limit(self):
        self.repo.documents["players"]["wikidata_Q615"]["name"] = ("Alexandria " * 15).strip()
        self.assertEqual(self.app.search_players("alexandria")["items"][0]["playerId"], "wikidata_Q615")

    def test_bad_catalog_record_reports_issue_without_leaking_extra_fields(self):
        self.repo.documents["players"]["wikidata_Q615"]["source"] = "unreviewed"
        result = self.app.search_players("")
        self.assertEqual(len(result["items"]), 4)
        self.assertEqual(result["issues"][0]["documentId"], "wikidata_Q615")
        self.assertNotIn("unreviewed", json.dumps(result["issues"]))

    def test_missing_public_records_are_not_empty_successful_profiles(self):
        with self.assertRaises(NotFoundError):
            self.app.get_player("wikidata_Q999999")

    def test_missing_competition_is_a_feed_issue_and_detail_failure(self):
        self.repo.documents["competitions"] = {}
        result = self.app.home_feed()["matches"]
        self.assertEqual(result["items"], [])
        self.assertEqual(len(result["issues"]), 1)
        with self.assertRaises(NotFoundError):
            self.app.get_match_detail(self.match_id)

    def test_connectivity_failure_stops_feed_instead_of_hiding_it_as_empty(self):
        with patch.object(self.repo, "get", side_effect=RepositoryError("Storage unavailable")):
            with self.assertRaises(RepositoryError):
                self.app.home_feed()

    def test_details_integrate_events_players_timelines_and_nullable_unknowns(self):
        result = self.app.get_match_detail(self.match_id)
        self.assertEqual(len(result["events"]["items"]), 2)
        self.assertEqual(len(result["highlights"]["items"]), 1)
        self.assertEqual(len(result["eventPlayers"]), 1)
        self.assertIsNone(result["lineups"])
        self.assertIsNone(result["statistics"])
        self.assertFalse(result["highlights"]["items"][0]["playbackAvailable"])
        self.assertNotIn("mediaReference", result["highlights"]["items"][0])
        self.assertIn(None, [row["matchClock"] for row in result["highlightTimelines"][0]["markers"]])
        self.assertNotIn("firestoreData", result)
        json.dumps(result)

    def test_marker_events_outside_first_event_page_are_still_resolved(self):
        result = self.app.get_match_detail(self.match_id, page_size=1)
        self.assertEqual(len(result["events"]["items"]), 1)
        self.assertTrue(result["events"]["hasMore"])
        self.assertEqual(len(result["highlightTimelines"][0]["markers"]), 2)
        second = self.app.get_match_detail(self.match_id, page_size=1, event_cursor=result["events"]["nextCursor"])
        ids = [row["eventId"] for row in result["events"]["items"] + second["events"]["items"]]
        self.assertEqual(len(set(ids)), 2)

    def test_media_with_only_claimed_authorization_is_hidden_and_not_returned(self):
        self.repo.documents["highlights"][self.highlight_id].update(
            rightsStatus="authorized", rightsEvidence="Synthetic claim only", mediaType="bundle",
            mediaReference="fictional_nonexistent_clip.mp4")
        self.assertEqual(self.app.get_match_detail(self.match_id)["highlights"]["items"], [])
        with self.assertRaisesRegex(ValidationError, "Playback unavailable"):
            self.app.resolve_reference("highlight", self.highlight_id)

    def test_cross_match_events_and_provenance_mismatch_fail_analysis(self):
        original = copy.deepcopy(self.repo.documents["matchEvents"][self.event_id])
        for changes in ({"isDemo": False}, {"eventId": make_related_id("demo_wrong", "event", "one")},
                        {"teamId": "wikidata_Q15789"}):
            self.repo.documents["matchEvents"][self.event_id] = dict(original, **changes)
            with self.subTest(changes=changes), self.assertRaises(ValidationError):
                self.app.get_match_detail(self.match_id)

    def test_missing_marker_event_is_not_invented(self):
        del self.repo.documents["matchEvents"][self.event_id]
        with self.assertRaises(NotFoundError):
            self.app.get_match_detail(self.match_id)

    def test_analysis_link_budget_stops_before_fetching_unknown_events(self):
        highlight = self.repo.documents["highlights"][self.highlight_id]
        highlight["markers"] = [{"eventId": make_related_id(self.match_id, "event", f"item_{index}"), "videoSeconds": 1}
                                for index in range(101)]
        with self.assertRaisesRegex(ValidationError, "budget"):
            self.app.get_match_detail(self.match_id)

    def test_reference_resolver_supports_all_saved_types_and_no_provider_id_shortcuts(self):
        for kind, identifier in (("player", "wikidata_Q615"), ("team", "wikidata_Q7156"),
                                 ("match", self.match_id), ("highlight", self.highlight_id)):
            self.assertIsInstance(self.app.resolve_reference(kind, identifier), dict)
        for kind, identifier in (("team", "529"), ("unsupported", "wikidata_Q615")):
            with self.subTest(kind=kind), self.assertRaises(ValidationError):
                self.app.resolve_reference(kind, identifier)

    def test_match_pagination_is_stable_when_kickoff_times_tie(self):
        template = self.repo.documents["matches"][self.match_id]
        for suffix in ("a", "b", "c"):
            self.repo.documents["matches"]["demo_" + suffix] = dict(template, matchId="demo_" + suffix)
        seen, cursor = [], None
        while True:
            page = self.app.list_matches(page_size=1, cursor=cursor)
            seen.extend(row["match"]["matchId"] for row in page["items"])
            if not page["hasMore"]:
                break
            cursor = page["nextCursor"]
        self.assertEqual(len(seen), 4)
        self.assertEqual(len(set(seen)), 4)
        self.assertEqual(seen, sorted(seen, reverse=True))

    def test_cursor_must_belong_to_the_same_query(self):
        with self.assertRaises(ValidationError):
            self.app.list_matches(status="scheduled", cursor=self.match_id)
        with self.assertRaises(ValidationError):
            self.app.list_matches(status="unsupported")

    def test_empty_catalog_collections_have_honest_empty_states(self):
        self.repo.documents["players"] = {}
        self.repo.documents["matches"] = {}
        self.assertEqual(self.app.search_players()["items"], [])
        self.assertEqual(self.app.home_feed()["matches"]["items"], [])

    def test_memory_repository_copies_data_and_rejects_private_cross_user_reads(self):
        documents = {"players": copy.deepcopy(self.repo.documents["players"])}
        memory = MemoryRepository(documents)
        result = memory.get("players", "wikidata_Q615")
        result["name"] = "Local edit"
        self.assertNotEqual(memory.get("players", "wikidata_Q615")["name"], "Local edit")
        self.assertEqual(documents["players"], memory.documents["players"])
        with self.assertRaises(AccessError):
            memory.private_page("test-bob", "test-alice", "favorites")

    def test_bad_queries_are_rejected_before_sdk_access(self):
        db = Mock()
        repository = FirestoreReadRepository(db)
        for kwargs in ({"page_size": True}, {"page_size": 51}, {"filters": [("credentials", "anything")]},
                       {"filters": [([], None)]}, {"order_by": "password"}, {"after_id": "../private"}):
            with self.subTest(kwargs=kwargs), self.assertRaises(ValidationError):
                repository.page("players", **kwargs)
        with self.assertRaises(AccessError):
            repository.get("users", "test-alice")
        db.collection.assert_not_called()

    def test_invalid_detail_and_team_page_inputs_do_not_read_storage(self):
        with patch.object(self.repo, "get") as get:
            for operation in (lambda: self.app.get_match_detail(self.match_id, page_size=True),
                              lambda: self.app.get_match_detail(self.match_id, event_cursor="../secret"),
                              lambda: self.app.team_matches("wikidata_Q7156", page_size=1000)):
                with self.assertRaises(ValidationError):
                    operation()
            get.assert_not_called()

    def test_cancelled_match_retains_null_kickoff_and_scores_in_details_and_feed(self):
        raw = self.repo.documents["matches"][self.match_id]
        raw.update(status="cancelled", kickoffUtc=None, finishType=None, homeScore=None, awayScore=None,
                   regularTimeHomeScore=None, regularTimeAwayScore=None)
        self.repo.documents["matchEvents"] = {}
        self.repo.documents["highlights"] = {}
        detail = self.app.get_match_detail(self.match_id)
        self.assertIsNone(detail["match"]["kickoffUtc"])
        self.assertIsNone(detail["match"]["homeScore"])
        self.assertEqual(detail["events"]["items"], [])
        self.assertIsNone(self.app.home_feed()["matches"]["items"][0]["match"]["kickoffUtc"])

    def test_sdk_read_projection_timeout_and_no_writes(self):
        db = Mock()
        reference = db.collection.return_value.document.return_value
        reference.get.return_value = SimpleNamespace(id="wikidata_Q615", exists=True,
            to_dict=lambda: copy.deepcopy(self.repo.documents["players"]["wikidata_Q615"]))
        repository = FirestoreReadRepository(db)
        self.assertEqual(repository.get("players", "wikidata_Q615")["name"], "Lionel Messi")
        self.assertEqual(reference.get.call_args.kwargs["timeout"], 20)
        self.assertIsNone(reference.get.call_args.kwargs["retry"])
        for operation in ("set", "update", "create", "delete"):
            getattr(reference, operation).assert_not_called()
        db.transaction.assert_not_called()
        db.batch.assert_not_called()

    def test_sdk_query_is_bounded_cursor_checked_and_never_writes(self):
        db, query = Mock(), Mock()
        reference = db.collection.return_value
        reference.select.return_value = query
        for method in ("where", "order_by", "start_after", "limit"):
            getattr(query, method).return_value = query
        raw = copy.deepcopy(self.repo.documents["matches"][self.match_id])
        snapshot = SimpleNamespace(id=self.match_id, exists=True, to_dict=lambda: raw)
        reference.document.return_value.get.return_value = snapshot
        query.stream.return_value = [snapshot]
        repository = FirestoreReadRepository(db)
        result = repository.page("matches", filters=(("isDemo", True),), order_by="kickoffUtc",
                                 page_size=2, after_id=self.match_id)
        self.assertEqual(result["items"][0][0], self.match_id)
        query.limit.assert_called_once_with(3)
        query.start_after.assert_called_once_with(snapshot)
        query.stream.assert_called_once_with(timeout=20, retry=None)
        db.batch.assert_not_called()
        db.transaction.assert_not_called()

    def test_sdk_errors_are_sanitized_and_not_successful_empty_results(self):
        db = Mock()
        db.collection.side_effect = RuntimeError("SENSITIVE_CONFIGURATION_MARKER")
        repository = FirestoreReadRepository(db)
        for method in (lambda: repository.get("players", "wikidata_Q615"), lambda: repository.page("players")):
            with self.assertRaises(RepositoryError) as caught:
                method()
            self.assertNotIn("SENSITIVE_CONFIGURATION_MARKER", str(caught.exception))


if __name__ == "__main__":
    unittest.main()
