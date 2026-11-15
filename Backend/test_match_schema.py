"""Offline schema tests using fictional matches only; no API or Firebase access."""

import ast
import copy
import io
import json
import tempfile
import unittest
from contextlib import redirect_stdout
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

from validate_match_schema import (
    FIELDS, ValidationError, load_match, reject_duplicate_fields, validate_match,
)


BACKEND_DIR = Path(__file__).resolve().parent
CASE_FILE = BACKEND_DIR / "input" / "match_schema_test_cases.json"


class MatchSchemaTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        with CASE_FILE.open(encoding="utf-8") as case_file:
            data = json.load(case_file, object_pairs_hook=reject_duplicate_fields)
        cls.cases = {match["matchId"]: match for match in data["matches"]}
        if len(cls.cases) != len(data["matches"]):
            raise AssertionError("Demonstration case IDs must be unique.")

    def case(self, name):
        return copy.deepcopy(self.cases[f"demo_{name}_001"])

    def reject(self, match):
        with self.assertRaises(ValidationError):
            validate_match(match)

    def test_fictional_cases_are_valid_and_unchanged(self):
        self.assertEqual(len(self.cases), 7)
        for identifier, match in self.cases.items():
            with self.subTest(case=identifier):
                original = copy.deepcopy(match)
                self.assertIs(match["isDemo"], True)
                self.assertEqual(match["source"], "demo")
                self.assertIsNone(match["sourceMatchId"])
                self.assertIsNone(match["sourceCompetitionId"])
                validate_match(match)
                self.assertEqual(match, original)

    def test_default_example_remains_valid(self):
        validate_match(load_match())

    def test_extra_time_is_a_separate_period_not_an_extra_total(self):
        match = self.case("extra_time")
        validate_match(match)
        self.assertEqual((match["homeScore"], match["awayScore"]), (3, 2))
        self.assertEqual((match["regularTimeHomeScore"], match["regularTimeAwayScore"]), (2, 2))
        self.assertEqual((match["extraTimeHomeScore"], match["extraTimeAwayScore"]), (1, 0))
        # Accidentally storing cumulative 3-2 as the extra-time period is invalid.
        match["extraTimeHomeScore"], match["extraTimeAwayScore"] = 3, 2
        self.reject(match)

    def test_no_missing_scores_are_derived(self):
        match = self.case("extra_time")
        match["extraTimeHomeScore"] = match["extraTimeAwayScore"] = None
        validate_match(match)
        self.assertIsNone(match["extraTimeHomeScore"])
        self.assertEqual(match["homeScore"], 3)
        match["homeScore"] = match["awayScore"] = None
        self.reject(match)  # Finished totals are essential; do not infer them.
        self.assertIsNone(match["homeScore"])

    def test_regular_time_draw_is_a_valid_finished_result(self):
        match = self.case("regular")
        match["homeScore"] = match["awayScore"] = 0
        match["regularTimeHomeScore"] = match["regularTimeAwayScore"] = 0
        validate_match(match)

    def test_shootout_never_changes_match_goals(self):
        match = self.case("penalties")
        validate_match(match)
        self.assertEqual((match["homeScore"], match["awayScore"]), (1, 1))
        self.assertEqual((match["penaltyHomeScore"], match["penaltyAwayScore"]), (5, 4))
        match["homeScore"], match["awayScore"] = 6, 5
        self.reject(match)

    def test_direct_shootout_and_missing_tally(self):
        match = self.case("penalties")
        match["regularTimeHomeScore"] = match["regularTimeAwayScore"] = 1
        match["extraTimeHomeScore"] = match["extraTimeAwayScore"] = None
        validate_match(match)  # Do not claim extra time was played.
        match["penaltyHomeScore"] = match["penaltyAwayScore"] = None
        validate_match(match)  # Known finish method, unknown tally; invent no winner.

    def test_completed_shootout_cannot_be_tied(self):
        match = self.case("penalties")
        match["penaltyAwayScore"] = match["penaltyHomeScore"]
        self.reject(match)

    def test_live_penalty_tally_may_be_tied(self):
        match = self.case("penalties")
        match["status"], match["finishType"] = "live", None
        match["penaltyAwayScore"] = match["penaltyHomeScore"]
        validate_match(match)

    def test_two_leg_tie_does_not_require_a_drawn_single_match(self):
        match = self.case("penalties")
        match["homeScore"], match["awayScore"] = 2, 1
        match["regularTimeHomeScore"], match["regularTimeAwayScore"] = 1, 0
        validate_match(match)  # Aggregate scores/tie resolution are separate future work.

    def test_finish_type_rules(self):
        for status in ("scheduled", "live", "postponed", "cancelled"):
            match = self.case(status)
            match["finishType"] = "extraTime"
            with self.subTest(status=status):
                self.reject(match)
        for finish in (None, "AET", "regular", [], True):
            match = self.case("regular")
            match["finishType"] = finish
            with self.subTest(finish=finish):
                self.reject(match)

    def test_regular_finish_forbids_extra_time_and_shootout(self):
        for prefix in ("extraTime", "penalty"):
            match = self.case("regular")
            match[prefix + "HomeScore"] = match[prefix + "AwayScore"] = 0
            self.reject(match)  # Zero is known data, not the same as null.
        match = self.case("extra_time")
        match["penaltyHomeScore"], match["penaltyAwayScore"] = 5, 4
        self.reject(match)

    def test_unplayed_matches_have_no_score_values(self):
        for status in ("scheduled", "postponed", "cancelled"):
            for prefix in ("", "regularTime", "extraTime", "penalty"):
                match = self.case(status)
                home = prefix + "HomeScore" if prefix else "homeScore"
                away = prefix + "AwayScore" if prefix else "awayScore"
                match[home] = match[away] = 0
                with self.subTest(status=status, prefix=prefix):
                    self.reject(match)

    def test_invalid_score_values_and_partial_pairs(self):
        for prefix in ("", "regularTime", "extraTime", "penalty"):
            home = prefix + "HomeScore" if prefix else "homeScore"
            away = prefix + "AwayScore" if prefix else "awayScore"
            for value in (-1, True, 1.0, "1", [], {}):
                match = self.case("penalties")
                match[home], match[away] = value, 0
                with self.subTest(prefix=prefix, value=value):
                    self.reject(match)
            match = self.case("penalties")
            match[home] = None
            self.reject(match)

    def test_inconsistent_supplied_totals_are_rejected(self):
        for name, field, value in (("regular", "homeScore", 3),
                                   ("extra_time", "homeScore", 4),
                                   ("extra_time", "extraTimeHomeScore", 4)):
            match = self.case(name)
            match[field] = value
            self.reject(match)

    def test_live_unknown_totals_are_not_invented(self):
        match = self.case("live")
        match["homeScore"] = match["awayScore"] = None
        match["regularTimeHomeScore"], match["regularTimeAwayScore"] = 1, 0
        validate_match(match)
        self.assertIsNone(match["homeScore"])

    def test_provider_and_internal_competition_ids_stay_separate(self):
        match = self.case("regular")
        match.update(matchId="match_local_test", isDemo=False, source="Synthetic test source",
                     sourceMatchId="synthetic_fixture", sourceCompetitionId="synthetic_league", competitionId=None)
        validate_match(match)
        self.assertIsNone(match["competitionId"])
        for bad in (123, "synthetic_league", "wikidata_Q123", ""):
            candidate = copy.deepcopy(match)
            candidate["competitionId"] = bad
            self.reject(candidate)
        for bad in (123, "https://invalid.example/league", ""):
            candidate = copy.deepcopy(match)
            candidate["sourceCompetitionId"] = bad
            self.reject(candidate)

    def test_demo_markers_and_provider_ids(self):
        for changes in ({"sourceCompetitionId": "synthetic"}, {"sourceMatchId": "synthetic"},
                        {"source": "API-Football"}, {"isDemo": "true"}, {"matchId": "match_wrong"}):
            match = self.case("regular")
            match.update(changes)
            self.reject(match)

    def test_required_fields_extra_fields_and_legacy_record(self):
        for field in FIELDS:
            match = self.case("regular")
            del match[field]
            with self.subTest(field=field):
                self.reject(match)
        match = self.case("regular")
        match["apiFootballPhoto"] = "not allowed"
        self.reject(match)
        self.reject([])

    def test_team_ids_dates_and_status_still_validated(self):
        for changes in ({"awayTeamId": "wikidata_Q7156"}, {"homeTeamId": "529"},
                        {"homeTeamId": "wikidata_Q0"}, {"status": "AET"},
                        {"kickoffUtc": "2030-02-30T18:00:00Z"},
                        {"kickoffUtc": "2030-01-01T18:00:00+00:00"}):
            match = self.case("regular")
            match.update(changes)
            self.reject(match)

    def test_file_errors_are_readable(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "match.json"
            for text in ("{", '{"status":"live","status":"finished"}'):
                path.write_text(text, encoding="utf-8")
                with self.assertRaises(ValidationError):
                    load_match(path)
            path.write_bytes(b"\xff\xfe")
            with self.assertRaises(ValidationError):
                load_match(path)
            path.unlink()
            with self.assertRaises(ValidationError):
                load_match(path)

    def test_existing_firestore_preview_can_prepare_all_flat_fields(self):
        # Load only its pure preparation/comparison functions, without SDK imports
        # or its main entry point. No Firebase package/credentials are needed.
        path = BACKEND_DIR / "preview_match_import.py"
        tree = ast.parse(path.read_text(encoding="utf-8"))
        names = {"prepare_match_data", "values_match", "compare_match"}
        tree.body = [node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name in names]
        namespace = {"datetime": datetime, "timezone": timezone, "MATCH_FIELDS": tuple(sorted(FIELDS)),
                     "MISSING": object(), "ValidationError": ValidationError}
        exec(compile(tree, str(path), "exec"), namespace)
        for match in self.cases.values():
            data = namespace["prepare_match_data"](match)
            self.assertEqual(set(data), FIELDS)
            snapshot = type("Snapshot", (), {"exists": True, "id": match["matchId"], "to_dict": lambda self: data})()
            self.assertEqual(namespace["compare_match"](data, snapshot)[0], "NO CHANGE")

    def test_provider_preview_understands_finish_types_without_network(self):
        from preview_api_football_matches import inspect_fixture
        # Entirely synthetic provider-shaped data, not a saved API response.
        date = datetime(2020, 1, 1, tzinfo=timezone.utc)
        record = {
            "fixture": {"id": 900001, "date": "2020-01-01T00:00:00Z", "timestamp": int(date.timestamp()),
                        "status": {"short": "AET", "long": "Synthetic extra-time test"}},
            "league": {"id": 900002, "name": "Fictional Test Cup", "season": 2020},
            "teams": {"home": {"id": 529, "name": "Barcelona"}, "away": {"id": 541, "name": "Real Madrid"}},
            "goals": {"home": 3, "away": 2},
            "score": {"fulltime": {"home": 2, "away": 2}, "extratime": {"home": 1, "away": 0}},
        }
        mapping = {529: {"teamId": "wikidata_Q7156"}, 541: {"teamId": "wikidata_Q8682"}}
        with patch("urllib.request.OpenerDirector.open", side_effect=AssertionError("No network allowed")), redirect_stdout(io.StringIO()):
            for code, name in (("FT", "regular"), ("AET", "extra_time"), ("PEN", "penalties")):
                match = self.case(name)
                candidate = copy.deepcopy(record)
                candidate["fixture"]["status"]["short"] = code
                candidate["goals"] = {"home": match["homeScore"], "away": match["awayScore"]}
                candidate["score"] = {
                    period: {"home": match[prefix + "HomeScore"], "away": match[prefix + "AwayScore"]}
                    for period, prefix in (("fulltime", "regularTime"), ("extratime", "extraTime"), ("penalty", "penalty"))
                }
                original = copy.deepcopy(candidate)
                with self.subTest(provider_status=code):
                    issues = inspect_fixture(candidate, mapping, set(), datetime(2030, 1, 1, tzinfo=timezone.utc))
                    self.assertEqual(issues, [])
                    self.assertEqual(candidate, original)
            record["score"]["extratime"] = {"home": 3, "away": 2}
            issues = inspect_fixture(record, mapping, set(), datetime(2030, 1, 1, tzinfo=timezone.utc))
            self.assertTrue(any("Score details/schema" in issue for issue in issues))
            self.assertEqual(record["goals"], {"home": 3, "away": 2})


if __name__ == "__main__":
    unittest.main(verbosity=2)
