"""Offline tests with fictional API-style records; no output datasets are saved."""

import copy
import unittest
from datetime import datetime, timezone
from unittest.mock import patch

from convert_api_football_fixture import ReviewRequired, STATUS_MAP, convert_fixture
from validate_match_schema import FIELDS, validate_match


# These two associations were explicitly verified in the existing project.
VERIFIED_TEAMS = {529: "wikidata_Q7156", 541: "wikidata_Q8682"}


def fictional_fixture(code="FT"):
    """Build fresh synthetic data; none of these fixtures is a real result."""
    record = {
        "isDemo": True,  # Explicit test marker, not an official provider field.
        "fixture": {
            "id": 900001, "date": "2024-01-01T18:00:00+02:00",
            "timestamp": int(datetime(2024, 1, 1, 16, tzinfo=timezone.utc).timestamp()),
            "status": {"short": code, "long": "Fictional test status"},
        },
        "league": {"id": 900002, "name": "Fictional Conversion Test Cup", "season": 2024},
        "teams": {"home": {"id": 529, "name": "Barcelona"}, "away": {"id": 541, "name": "Real Madrid"}},
        "goals": {"home": 2, "away": 1},
        "score": {"fulltime": {"home": 2, "away": 1}, "extratime": {"home": None, "away": None},
                  "penalty": {"home": None, "away": None}},
    }
    if code == "AET":
        record["goals"] = {"home": 3, "away": 2}
        record["score"]["fulltime"] = {"home": 2, "away": 2}
        record["score"]["extratime"] = {"home": 1, "away": 0}
    elif code in ("PEN", "P"):
        record["goals"] = {"home": 1, "away": 1}
        record["score"]["fulltime"] = {"home": 1, "away": 1}
        record["score"]["penalty"] = {"home": 5, "away": 4} if code == "PEN" else {"home": 2, "away": 2}
    elif code not in ("FT",):
        record["goals"] = {"home": None, "away": None} if code in ("NS", "PST", "CANC") else {"home": 1, "away": 0}
        record["score"]["fulltime"] = {"home": None, "away": None}
    return record


class FixtureConversionTests(unittest.TestCase):
    def setUp(self):
        # Any unexpected network or credential access would fail a test.
        guard = patch("urllib.request.OpenerDirector.open", side_effect=AssertionError("No network allowed"))
        guard.start()
        self.addCleanup(guard.stop)
        guard = patch("api_football_players.read_api_key", side_effect=AssertionError("No credentials needed"))
        guard.start()
        self.addCleanup(guard.stop)

    def convert(self, record, mapping=None):
        original, original_mapping = copy.deepcopy(record), copy.deepcopy(VERIFIED_TEAMS if mapping is None else mapping)
        chosen_mapping = VERIFIED_TEAMS if mapping is None else mapping
        result = convert_fixture(record, chosen_mapping, is_demo=True)
        validate_match(result)
        self.assertEqual(set(result), FIELDS)
        self.assertEqual(record, original)
        self.assertEqual(chosen_mapping, original_mapping)
        return result

    def reject(self, record, mapping=None):
        original = copy.deepcopy(record)
        with self.assertRaisesRegex(ReviewRequired, "REVIEW REQUIRED:"):
            convert_fixture(record, VERIFIED_TEAMS if mapping is None else mapping, is_demo=True)
        self.assertEqual(record, original)

    def test_regular_time_finish(self):
        match = self.convert(fictional_fixture())
        self.assertEqual((match["status"], match["finishType"]), ("finished", "regularTime"))
        self.assertEqual((match["homeScore"], match["awayScore"]), (2, 1))
        self.assertEqual((match["regularTimeHomeScore"], match["regularTimeAwayScore"]), (2, 1))

    def test_extra_time_preserves_the_three_two_total(self):
        match = self.convert(fictional_fixture("AET"))
        self.assertEqual(match["finishType"], "extraTime")
        self.assertEqual((match["homeScore"], match["awayScore"]), (3, 2))
        self.assertEqual((match["regularTimeHomeScore"], match["regularTimeAwayScore"]), (2, 2))
        self.assertEqual((match["extraTimeHomeScore"], match["extraTimeAwayScore"]), (1, 0))

    def test_shootout_is_separate_from_final_goals(self):
        match = self.convert(fictional_fixture("PEN"))
        self.assertEqual(match["finishType"], "penalties")
        self.assertEqual((match["homeScore"], match["awayScore"]), (1, 1))
        self.assertEqual((match["penaltyHomeScore"], match["penaltyAwayScore"]), (5, 4))
        self.assertIsNone(match["extraTimeHomeScore"])  # No invented extra-time 0.

    def test_scheduled_match_has_null_scores(self):
        match = self.convert(fictional_fixture("NS"))
        self.assertEqual(match["status"], "scheduled")
        self.assertIsNone(match["finishType"])
        for field in FIELDS:
            if field.endswith("Score"):
                self.assertIsNone(match[field])

    def test_live_statuses_and_live_shootout(self):
        for code in ("1H", "HT", "2H", "ET", "BT", "P", "LIVE"):
            with self.subTest(code=code):
                match = self.convert(fictional_fixture(code))
                self.assertEqual(match["status"], "live")
                self.assertIsNone(match["finishType"])
        self.assertEqual(self.convert(fictional_fixture("P"))["penaltyHomeScore"], 2)

    def test_postponed_and_cancelled_allow_an_unknown_kickoff(self):
        for code, status in (("PST", "postponed"), ("CANC", "cancelled")):
            record = fictional_fixture(code)
            del record["fixture"]["date"]
            record["fixture"]["timestamp"] = None
            match = self.convert(record)
            self.assertEqual(match["status"], status)
            self.assertIsNone(match["kickoffUtc"])

    def test_mapping_agrees_with_existing_preview(self):
        from preview_api_football_matches import TEAM_IDS, STATUS_MAP as PREVIEW_STATUSES
        self.assertEqual(VERIFIED_TEAMS, {api_id: f"wikidata_{wikidata_id}" for api_id, wikidata_id in TEAM_IDS.items()})
        self.assertEqual(STATUS_MAP, PREVIEW_STATUSES)

    def test_reverse_home_away_order_is_supported(self):
        record = fictional_fixture()
        record["teams"]["home"], record["teams"]["away"] = record["teams"]["away"], record["teams"]["home"]
        match = self.convert(record)
        self.assertEqual(match["homeTeamId"], "wikidata_Q8682")
        self.assertEqual(match["awayTeamId"], "wikidata_Q7156")

    def test_unknown_team_is_never_guessed_by_name(self):
        record = fictional_fixture()
        record["teams"]["home"]["id"] = 999999
        self.reject(record)

    def test_invalid_or_ambiguous_mapping_is_rejected(self):
        for mapping in ({}, None, {"529": "wikidata_Q7156"}, {True: "wikidata_Q7156"},
                        {529: "Q7156", 541: "wikidata_Q8682"},
                        {529: "wikidata_Q7156", 541: "wikidata_Q7156"},
                        {529: "teams/wikidata_Q7156", 541: "wikidata_Q8682"}):
            with self.subTest(mapping=mapping):
                with self.assertRaises(ReviewRequired):
                    convert_fixture(fictional_fixture(), mapping, is_demo=True)
        record = fictional_fixture()
        record["teams"]["away"]["id"] = 529
        self.reject(record)

    def test_unsupported_and_uncertain_statuses_require_review(self):
        for code in ("TBD", "SUSP", "INT", "ABD", "AWD", "WO", "NEW", None, [], True):
            record = fictional_fixture()
            record["fixture"]["status"]["short"] = code
            with self.subTest(code=code):
                self.reject(record)

    def test_required_information_and_provider_types(self):
        for parent, key in (("fixture", "id"), ("fixture", "status"), ("league", "id"),
                            ("league", "name"), ("league", "season"), ("teams", "home")):
            record = fictional_fixture()
            del record[parent][key]
            with self.subTest(parent=parent, key=key):
                self.reject(record)
        for value in (True, 0, -1, "900001", 1.0, None):
            record = fictional_fixture()
            record["fixture"]["id"] = value
            self.reject(record)
        for value in (True, "2024", 24, None):
            record = fictional_fixture()
            record["league"]["season"] = value
            self.reject(record)
        for value in (None, [], {}, "invalid"):
            self.reject(value)

    def test_utc_conversion_and_matching_unix_timestamp(self):
        match = self.convert(fictional_fixture())
        self.assertEqual(match["kickoffUtc"], "2024-01-01T16:00:00Z")
        record = fictional_fixture()
        record["fixture"]["date"] = "2024-01-01T16:00:00.000Z"
        self.assertEqual(self.convert(record)["kickoffUtc"], match["kickoffUtc"])

    def test_unix_only_and_iso_only_preserve_known_times(self):
        for field in ("date", "timestamp"):
            record = fictional_fixture()
            del record["fixture"][field]
            self.assertEqual(self.convert(record)["kickoffUtc"], "2024-01-01T16:00:00Z")
        record = fictional_fixture()
        record["fixture"].update(date=None, timestamp=0)
        self.assertEqual(self.convert(record)["kickoffUtc"], "1970-01-01T00:00:00Z")

    def test_no_silent_timestamp_correction_or_truncation(self):
        for value in ("2024-01-01T16:00:00", "2024-02-30T16:00:00Z",
                      "2024-01-01T16:00:00+00:99", "2024-01-01T16:00:00.123456Z"):
            record = fictional_fixture()
            record["fixture"]["date"] = value
            self.reject(record)
        record = fictional_fixture()
        record["fixture"]["timestamp"] += 3600
        self.reject(record)
        for value in (True, "1704124800", 1.5, 10 ** 100):
            record = fictional_fixture()
            record["fixture"]["timestamp"] = value
            self.reject(record)

    def test_essential_unknown_kickoff_cannot_be_invented(self):
        for code in ("FT", "NS", "1H"):
            record = fictional_fixture(code)
            record["fixture"].pop("date")
            record["fixture"].pop("timestamp")
            self.reject(record)

    def test_null_missing_and_partial_scores(self):
        record = fictional_fixture("NS")
        del record["goals"]
        del record["score"]
        match = self.convert(record)
        self.assertIsNone(match["homeScore"])
        self.assertIsNone(match["regularTimeHomeScore"])
        record = fictional_fixture("AET")
        del record["score"]["extratime"]
        match = self.convert(record)
        self.assertIsNone(match["extraTimeHomeScore"])
        self.assertEqual(match["homeScore"], 3)
        record = fictional_fixture()
        del record["goals"]["away"]
        self.reject(record)
        record = fictional_fixture()
        del record["goals"]
        self.reject(record)  # Never derive finished totals from fulltime.

    def test_bad_or_cumulative_period_scores_are_not_reinterpreted(self):
        for period, value in (("fulltime", []), ("extratime", {"home": 3, "away": 2}),
                              ("extratime", {"home": True, "away": 0}),
                              ("extratime", {"home": 1.0, "away": 0}),
                              ("extratime", {"home": 1, "away": None})):
            record = fictional_fixture("AET")
            record["score"][period] = value
            self.reject(record)
        record = fictional_fixture("PEN")
        record["score"]["penalty"] = {"home": 4, "away": 4}
        self.reject(record)

    def test_match_ids_are_stable_namespaced_and_not_date_based(self):
        record = fictional_fixture()
        first = self.convert(record)
        record["fixture"]["date"] = "2025-02-03T16:00:00Z"
        record["fixture"]["timestamp"] = None
        record["fixture"]["status"]["short"] = "AET"
        self.assertEqual(self.convert(record)["matchId"], first["matchId"])
        record["fixture"]["id"] += 1
        self.assertNotEqual(self.convert(record)["matchId"], first["matchId"])

    def test_demo_mode_keeps_fictional_records_out_of_real_namespace(self):
        match = self.convert(fictional_fixture())
        self.assertTrue(match["matchId"].startswith("demo_api_football_fixture_"))
        self.assertIs(match["isDemo"], True)
        self.assertEqual(match["source"], "demo")
        self.assertIsNone(match["sourceMatchId"])
        self.assertIsNone(match["sourceCompetitionId"])
        self.assertIsNone(match["competitionId"])

    def test_provenance_must_be_explicit_and_not_contradictory(self):
        for choice in (None, "false", 0):
            with self.assertRaises(ReviewRequired):
                convert_fixture(fictional_fixture(), VERIFIED_TEAMS, is_demo=choice)
        with self.assertRaises(ReviewRequired):
            convert_fixture(fictional_fixture(), VERIFIED_TEAMS)
        with self.assertRaises(ReviewRequired):
            convert_fixture(fictional_fixture(), VERIFIED_TEAMS, is_demo=False)

    def test_real_source_metadata_contract_in_memory_only(self):
        # Synthetic input exercises the real-source branch only. This object is
        # never displayed or saved as an actual fixture or an output dataset.
        record = fictional_fixture()
        del record["isDemo"]
        match = convert_fixture(record, VERIFIED_TEAMS, is_demo=False)
        validate_match(match)
        self.assertEqual(match["matchId"], "match_api_football_fixture_900001")
        self.assertEqual(match["sourceMatchId"], "900001")
        self.assertEqual(match["sourceCompetitionId"], "900002")
        self.assertIsNone(match["competitionId"])
        self.assertEqual(match["source"], "API-Football")
        self.assertIs(match["isDemo"], False)

    def test_nonmanaged_fields_and_private_material_are_not_copied(self):
        record = fictional_fixture()
        record["headers"] = {"api-key": "PRIVATE_MARKER"}
        record["teams"]["home"]["logo"] = "https://invalid.example/image"
        record["events"] = [{"unexpected": "PRIVATE_MARKER"}]
        match = self.convert(record)
        self.assertNotIn("PRIVATE_MARKER", repr(match))
        self.assertNotIn("https://", repr(match))


if __name__ == "__main__":
    unittest.main(verbosity=2)
