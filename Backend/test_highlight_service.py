"""Offline highlight validation using fictional times, events and rights claims."""

import copy
import unittest
from unittest.mock import patch

import highlight_service as service
from match_event_service import make_related_id, preview_curated_records
from match_service import prepare_fixture, summarize_plan
from test_competition_mapping import synthetic_catalog
from test_convert_api_football_fixture import VERIFIED_TEAMS, fictional_fixture
from test_match_event_service import demo_match, fictional_event, fictional_players
from test_match_service import local_teams
from test_preview_api_football_conversion import provider_record
from validate_competition_schema import load_catalog
from validate_match_schema import ValidationError, validate_match


def fictional_highlight(match, event, key="clip_1", **changes):
    # A virtual timeline: no media exists and these are not real video positions.
    highlight = {"highlightId": make_related_id(match["matchId"], "highlight", key),
                 "matchId": match["matchId"], "title": "Fictional highlight",
                 "mediaType": None, "mediaReference": None, "durationSeconds": 120,
                 "rightsStatus": "unconfirmed", "rightsEvidence": None,
                 "markers": [{"eventId": event["eventId"], "videoSeconds": 30}],
                 "isDemo": match["isDemo"], "source": "demo" if match["isDemo"] else "manual"}
    highlight.update(changes)
    return highlight


class HighlightServiceTests(unittest.TestCase):
    def setUp(self):
        for guard in (
            patch("urllib.request.OpenerDirector.open", side_effect=AssertionError("No network allowed")),
            patch("firebase_admin.initialize_app", side_effect=AssertionError("No credentials allowed")),
            patch("firebase_admin.firestore.client", side_effect=AssertionError("No database allowed")),
        ):
            guard.start()
            self.addCleanup(guard.stop)
        self.match, self.teams = demo_match(), local_teams()
        self.players, self.catalog = fictional_players(), load_catalog()
        self.event = fictional_event(self.match)
        self.highlight = fictional_highlight(self.match, self.event)

    def prepare(self, highlights=None, events=None):
        return service.prepare_highlight_bundles(
            [self.match], self.teams, self.players, self.catalog,
            [self.event] if events is None else events,
            [self.highlight] if highlights is None else highlights)[0]

    def authorize(self, **changes):
        # Tests exercise the metadata gate; no real media licence or file is claimed.
        self.highlight.update(rightsStatus="authorized", rightsEvidence="Fictional test approval only",
                              mediaType="bundle", mediaReference="fictional_clip.mp4")
        self.highlight.update(changes)

    def test_virtual_timeline_joins_player_team_and_match_without_mutation(self):
        original = copy.deepcopy((self.match, self.event, self.highlight))
        prepared = self.prepare()
        marker = prepared["highlightTimelines"][0]["markers"][0]
        self.assertEqual(marker["playerId"], self.players[0]["documentId"])
        self.assertEqual(marker["teamId"], self.match["homeTeamId"])
        self.assertEqual(marker["matchClock"], "45+2")
        self.assertEqual(marker["videoSeconds"], 30)
        self.assertFalse(prepared["highlightTimelines"][0]["playbackEligible"])
        self.assertIsNone(prepared["highlights"][0]["mediaReference"])
        self.assertNotIn("highlights", prepared["firestoreData"])
        prepared["highlights"][0]["markers"][0]["videoSeconds"] = 100
        prepared["highlightTimelines"][0]["markers"][0]["label"] = "Local edit"
        self.assertEqual((self.match, self.event, self.highlight), original)

    def test_unconfirmed_media_cannot_produce_a_playback_target(self):
        with self.assertRaisesRegex(ValidationError, "rights are confirmed"):
            service.playback_target(self.prepare(), self.highlight["highlightId"], self.event["eventId"])

    def test_authorized_bundle_yields_seek_arguments_without_accessing_media(self):
        self.authorize()
        prepared = self.prepare()
        self.assertTrue(prepared["highlightTimelines"][0]["playbackEligible"])
        target = service.playback_target(prepared, self.highlight["highlightId"], self.event["eventId"])
        self.assertEqual(target, {"matchId": self.match["matchId"], "highlightId": self.highlight["highlightId"],
                                  "eventId": self.event["eventId"], "mediaType": "bundle",
                                  "mediaReference": "fictional_clip.mp4", "videoSeconds": 30})

    def test_authorized_https_is_only_a_reference_not_a_download(self):
        self.authorize(mediaType="https", mediaReference="https://example.invalid/fictional_clip.mp4")
        self.assertEqual(self.prepare()["highlights"][0]["mediaType"], "https")

    def test_unconfirmed_rights_cannot_include_media_or_evidence(self):
        for change in ({"mediaReference": "fictional_clip.mp4"}, {"mediaType": "bundle"},
                       {"rightsEvidence": "Unreviewed assertion"}):
            with self.subTest(change=change), self.assertRaisesRegex(ValidationError, "REVIEW REQUIRED"):
                self.prepare([dict(self.highlight, **change)])

    def test_invalid_rights_or_missing_evidence_are_rejected(self):
        for rights in (None, True, [], "assumed", "Authorized"):
            with self.subTest(rights=rights), self.assertRaises(ValidationError):
                self.prepare([dict(self.highlight, rightsStatus=rights)])
        self.authorize(rightsEvidence=None)
        with self.assertRaises(ValidationError):
            self.prepare()

    def test_private_or_invalid_media_locations_are_rejected(self):
        for media_type, reference in (
            ("bundle", "../clip.mp4"), ("bundle", "C:\\private\\clip.mp4"), ("bundle", "clip.txt"),
            ("https", "http://example.invalid/clip.mp4"), ("https", "https://user:secret@example.invalid/a"),
            ("https", "https://example.invalid/a?token=fictional"), ("https", "https://example.invalid/a#secret"),
            ("https", "https://example.invalid:invalid/a"), ("https", "https://example.invalid/a b"),
            ("https", "https://example.invalid\\a"), ("file", "clip.mp4"), (None, None),
        ):
            with self.subTest(media_type=media_type, reference=reference), self.assertRaises(ValidationError):
                self.authorize(mediaType=media_type, mediaReference=reference)
                self.prepare()

    def test_missing_or_extra_fields_are_rejected(self):
        missing = dict(self.highlight)
        del missing["durationSeconds"]
        for highlight in (missing, dict(self.highlight, providerVideoId=123), dict(self.highlight, title=" ")):
            with self.subTest(highlight=highlight), self.assertRaises(ValidationError):
                self.prepare([highlight])

    def test_invalid_duration_values_are_rejected(self):
        for value in (True, 0, -1, "120", float("nan"), float("inf"), 10 ** 400):
            with self.subTest(value=type(value).__name__), self.assertRaises(ValidationError):
                self.prepare([dict(self.highlight, durationSeconds=value)])

    def test_null_duration_is_preserved_without_markers(self):
        prepared = self.prepare([dict(self.highlight, durationSeconds=None, markers=[])])
        self.assertIsNone(prepared["highlights"][0]["durationSeconds"])
        self.assertEqual(prepared["highlightTimelines"][0]["markers"], [])

    def test_marker_requires_a_known_duration(self):
        with self.assertRaisesRegex(ValidationError, "bounds"):
            self.prepare([dict(self.highlight, durationSeconds=None)])

    def test_zero_and_exact_end_positions_are_allowed(self):
        for position in (0, 120, 0.5):
            with self.subTest(position=position):
                highlight = dict(self.highlight, markers=[{"eventId": self.event["eventId"], "videoSeconds": position}])
                self.assertEqual(self.prepare([highlight])["highlightTimelines"][0]["markers"][0]["videoSeconds"],
                                 position)

    def test_marker_out_of_bounds_or_nonfinite_is_rejected(self):
        for position in (-1, 120.1, True, "30", None, float("nan"), float("inf"), 10 ** 400):
            with self.subTest(position=type(position).__name__), self.assertRaises(ValidationError):
                self.prepare([dict(self.highlight, markers=[{"eventId": self.event["eventId"],
                                                            "videoSeconds": position}])])

    def test_unknown_or_duplicate_marker_events_are_rejected(self):
        markers = self.highlight["markers"]
        for bad in (markers + markers, [{"eventId": "demo_event_absent__one", "videoSeconds": 1}],
                    [{"eventId": [], "videoSeconds": 1}], [{"eventId": self.event["eventId"]}],
                    [dict(markers[0], unwanted="excluded")], [None], "markers"):
            with self.subTest(markers=bad), self.assertRaises(ValidationError):
                self.prepare([dict(self.highlight, markers=bad)])

    def test_cross_match_marker_is_rejected_even_when_event_exists(self):
        other_match = dict(self.match, matchId="demo_other_001")
        other_event = fictional_event(other_match)
        self.highlight["markers"] = [{"eventId": other_event["eventId"], "videoSeconds": 1}]
        with self.assertRaisesRegex(ValidationError, "another match"):
            service.prepare_highlight_bundles([self.match, other_match], self.teams, self.players,
                                              self.catalog, [self.event, other_event], [self.highlight])

    def test_match_and_child_id_must_agree(self):
        for change in ({"matchId": "demo_missing"}, {"highlightId": "demo_highlight_other__one"},
                       {"highlightId": self.event["eventId"]}):
            with self.subTest(change=change), self.assertRaises(ValidationError):
                self.prepare([dict(self.highlight, **change)])

    def test_highlight_provenance_must_match(self):
        for change in ({"isDemo": False}, {"isDemo": 1}, {"source": "api-football"}):
            with self.subTest(change=change), self.assertRaises(ValidationError):
                self.prepare([dict(self.highlight, **change)])

    def test_duplicate_or_malformed_highlight_batch_is_rejected(self):
        for highlights in ([self.highlight, self.highlight], [self.highlight, None], {}, "highlights"):
            with self.subTest(highlights=highlights), self.assertRaises(ValidationError):
                self.prepare(highlights)

    def test_no_highlights_is_valid(self):
        self.assertEqual(self.prepare([])["highlightTimelines"], [])

    def test_video_order_is_independent_of_football_clock(self):
        later = fictional_event(self.match, "later", matchMinute=80)
        unknown = fictional_event(self.match, "unknown_clock", matchMinute=None, addedTime=None)
        self.highlight["markers"] = [{"eventId": self.event["eventId"], "videoSeconds": 100},
                                     {"eventId": later["eventId"], "videoSeconds": 5},
                                     {"eventId": unknown["eventId"], "videoSeconds": 50}]
        timeline = self.prepare(events=[self.event, later, unknown])["highlightTimelines"][0]
        self.assertEqual([row["videoSeconds"] for row in timeline["markers"]], [5, 50, 100])
        self.assertEqual([row["matchClock"] for row in timeline["markers"]], ["80+2", None, "45+2"])

    def test_seek_rejects_absent_event_or_highlight_without_guessing(self):
        self.authorize()
        prepared = self.prepare()
        for highlight_id, event_id in ((self.highlight["highlightId"], "demo_event_absent__one"),
                                       ("demo_highlight_absent__one", self.event["eventId"])):
            with self.subTest(highlight=highlight_id), self.assertRaises(ValidationError):
                service.playback_target(prepared, highlight_id, event_id)

    def test_nested_marker_difference_is_included_in_local_update(self):
        record = self.prepare()["highlights"][0]
        identifier = record["highlightId"]
        old = copy.deepcopy(record)
        old["markers"][0]["videoSeconds"] = 30.0
        for action, documents in (("CREATE", {}), ("UPDATE", {identifier: old}),
                                  ("NO CHANGE", {identifier: dict(record, unrelated="kept")})):
            original = copy.deepcopy(documents)
            plan = preview_curated_records([record], documents, "highlightId")
            self.assertEqual(summarize_plan(plan)[action], 1)
            self.assertEqual(documents, original)
            if action == "UPDATE":
                self.assertEqual([row[0] for row in plan[0]["differences"]], ["markers"])

    def test_fixture_conversion_through_analysis_for_regular_extra_time_penalties_and_live(self):
        # Start with explicitly fictional API-shaped input, never an actual response.
        for code in ("FT", "AET", "PEN", "1H"):
            with self.subTest(code=code):
                fixture = fictional_fixture(code)
                match = prepare_fixture(fixture, VERIFIED_TEAMS, self.teams, self.catalog,
                                        is_demo=True, demo_competition_id="demo_competition_001")["match"]
                event = fictional_event(match)
                highlight = fictional_highlight(match, event)
                prepared = service.prepare_highlight_bundles([match], self.teams, self.players,
                                                             self.catalog, [event], [highlight])[0]
                validate_match(prepared["match"])
                self.assertTrue(prepared["match"]["isDemo"])
                self.assertIsNone(prepared["match"]["sourceMatchId"])
                self.assertEqual(prepared["highlightTimelines"][0]["markers"][0]["eventId"], event["eventId"])
                self.assertEqual(prepared["match"]["homeScore"], fixture["goals"]["home"])

    def test_manual_curated_records_keep_real_source_contract_separate_from_demo(self):
        # Exercise the real-source branch synthetically in memory, not real facts.
        catalog = synthetic_catalog()
        match = prepare_fixture(provider_record("AET"), VERIFIED_TEAMS, self.teams, catalog,
                                is_demo=False)["match"]
        event = fictional_event(match)
        highlight = fictional_highlight(match, event)
        prepared = service.prepare_highlight_bundles([match], self.teams, self.players, catalog,
                                                     [event], [highlight])[0]
        self.assertEqual(prepared["match"]["source"], "API-Football")
        self.assertEqual(prepared["events"][0]["source"], "manual")
        self.assertEqual(prepared["highlights"][0]["source"], "manual")
        self.assertFalse(prepared["highlights"][0]["isDemo"])
        self.assertTrue(prepared["events"][0]["eventId"].startswith("event_"))
        self.assertTrue(prepared["highlights"][0]["highlightId"].startswith("highlight_"))
        for field, value in (("source", "demo"), ("isDemo", True)):
            with self.subTest(field=field), self.assertRaises(ValidationError):
                service.prepare_highlight_bundles([match], self.teams, self.players, catalog,
                                                  [event], [dict(highlight, **{field: value})])

    def test_multiple_matches_keep_highlights_and_players_in_their_own_bundles(self):
        other_match = dict(self.match, matchId="demo_other_001")
        other_event = fictional_event(other_match, playerId=None)
        other_highlight = fictional_highlight(other_match, other_event)
        prepared = service.prepare_highlight_bundles([self.match, other_match], self.teams, self.players,
                                                     self.catalog, [self.event, other_event],
                                                     [other_highlight, self.highlight])
        self.assertEqual([row["highlights"][0]["matchId"] for row in prepared],
                         [self.match["matchId"], other_match["matchId"]])
        self.assertEqual(prepared[1]["eventPlayers"], {})
        for row in prepared:
            self.assertEqual(row["events"][0]["matchId"], row["match"]["matchId"])


if __name__ == "__main__":
    unittest.main()
