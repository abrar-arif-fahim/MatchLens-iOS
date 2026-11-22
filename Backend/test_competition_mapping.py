"""Offline lookup/conversion tests. All fixture results are fictional and in memory."""

import copy
import io
import json
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest.mock import patch

import competition_mapping as registry
import preview_api_football_conversion as preview
from convert_api_football_fixture import ReviewRequired, convert_fixture
from test_convert_api_football_fixture import VERIFIED_TEAMS, fictional_fixture
from test_preview_api_football_conversion import envelope, provider_record
from validate_match_schema import ValidationError, validate_match


def synthetic_catalog():
    return {
        "competitions": [{
            "competitionId": "competition_synthetic_001", "name": "Synthetic Test Cup",
            "competitionType": "nationalCup", "country": None, "region": None,
            "isDemo": False, "source": "manual",
        }],
        "seasons": [],
        "providerMappings": [{
            "provider": "API-Football", "providerCompetitionId": "900002",
            "competitionId": "competition_synthetic_001", "status": "verified",
            "verificationEvidence": "Synthetic test evidence, not an actual competition verification.",
            "verifiedAt": "2020-01-01T00:00:00Z",
        }],
    }


class CompetitionMappingTests(unittest.TestCase):
    def setUp(self):
        guard = patch("urllib.request.OpenerDirector.open", side_effect=AssertionError("No network allowed"))
        guard.start()
        self.addCleanup(guard.stop)
        self.catalog = synthetic_catalog()

    def test_checked_in_configuration_contains_only_confirmed_reference_mappings(self):
        catalog = registry.load_verified_catalog()
        expected = {140: "competition_la_liga", 143: "competition_copa_del_rey",
                    667: "competition_friendlies_clubs", 556: "competition_spain_super_cup"}
        self.assertEqual(len(catalog["competitions"]), 4)
        self.assertEqual(catalog["seasons"], [])
        for external, internal in expected.items():
            competition = registry.resolve_competition(catalog, external)
            self.assertEqual(competition["competitionId"], internal)
            self.assertEqual(competition["source"], "manual")
        friendly = registry.resolve_competition(catalog, 667)
        self.assertIsNone(friendly["country"])
        self.assertEqual(friendly["region"], "World")

    def test_lookup_accepts_integer_or_canonical_string_without_mutating_catalog(self):
        original = copy.deepcopy(self.catalog)
        for identifier in (900002, "900002"):
            result = registry.resolve_competition(self.catalog, identifier)
            self.assertEqual(result["competitionId"], "competition_synthetic_001")
            result["name"] = "Caller changed this copy"
        self.assertEqual(self.catalog, original)

    def test_lookup_rejects_malformed_identifiers_and_other_namespaces(self):
        for value in (True, False, 0, -1, 900002.0, "0900002", " 900002", "", None, [], {}):
            with self.subTest(value=value), self.assertRaises(ValidationError):
                registry.resolve_competition(self.catalog, value)
        with self.assertRaises(ValidationError):
            registry.resolve_competition(self.catalog, 900002, provider="another-provider")

    def test_unknown_and_pending_ids_require_review(self):
        with self.assertRaisesRegex(ValidationError, "No verified competition mapping"):
            registry.resolve_competition(self.catalog, 900999)
        self.catalog["providerMappings"][0].update(
            status="pending", competitionId=None, verificationEvidence=None, verifiedAt=None
        )
        with self.assertRaisesRegex(ValidationError, "pending"):
            registry.resolve_competition(self.catalog, 900002)

    def test_conflicts_anywhere_in_catalog_prevent_lookup(self):
        self.catalog["providerMappings"].append(copy.deepcopy(self.catalog["providerMappings"][0]))
        with self.assertRaisesRegex(ValidationError, "Duplicate provider"):
            registry.resolve_competition(self.catalog, 900002)
        self.catalog = synthetic_catalog()
        self.catalog["providerMappings"][0]["competitionId"] = "competition_missing"
        with self.assertRaises(ValidationError):
            registry.resolve_competition(self.catalog, 900002)

    def test_invalid_unrelated_mapping_is_not_hidden_by_successful_lookup(self):
        self.catalog["providerMappings"].append(dict(self.catalog["providerMappings"][0],
                                                    providerCompetitionId="900003", status="unreviewed"))
        with self.assertRaises(ValidationError):
            registry.resolve_competition(self.catalog, 900002)

    def test_internal_ids_are_not_regenerated_from_names_or_provider_ids(self):
        self.catalog["competitions"][0]["name"] = "Synthetic Renamed Cup"
        self.assertEqual(registry.resolve_competition(self.catalog, 900002)["competitionId"],
                         "competition_synthetic_001")
        for value in (None, [], "900002", "competition_missing"):
            with self.subTest(value=value), self.assertRaises(ValidationError):
                registry.get_competition(self.catalog, value)

    def test_catalog_file_errors_do_not_expose_input_contents(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "catalog.json"
            for raw in ("{", '{"competitions":[],"competitions":[]}'):
                path.write_text(raw, encoding="utf-8")
                with self.assertRaises(ValidationError):
                    registry.load_verified_catalog(path)
            path.unlink()
            output = io.StringIO()
            with redirect_stdout(output):
                self.assertEqual(registry.main(["--catalog", str(path)]), 1)
            self.assertIn("LOCAL ONLY", output.getvalue())

    def test_seasons_remain_separate_and_follow_actual_calendar_boundaries(self):
        self.assertEqual(registry.get_competition_seasons(self.catalog, "competition_synthetic_001"), [])
        self.catalog["seasons"].append({
            "seasonId": "competition_synthetic_001_season_edition_one",
            "competitionId": "competition_synthetic_001", "label": "Synthetic edition",
            "startYear": 2025, "endYear": 2025, "startDate": "2025-01-01", "endDate": "2025-01-02",
            "isDemo": False, "source": "manual",
        })
        result = registry.get_competition_seasons(self.catalog, "competition_synthetic_001")
        result[0]["label"] = "Changed copy"
        self.assertEqual(self.catalog["seasons"][0]["label"], "Synthetic edition")

    def test_all_supported_fixture_states_convert_with_verified_competition(self):
        for code in ("FT", "AET", "PEN", "NS", "1H", "PST", "CANC"):
            record = provider_record(code)
            original = copy.deepcopy(record)
            with self.subTest(code=code):
                match = convert_fixture(record, VERIFIED_TEAMS, is_demo=False, competition_catalog=self.catalog)
                validate_match(match)
                self.assertEqual(match["competitionId"], "competition_synthetic_001")
                self.assertEqual(match["sourceCompetitionId"], "900002")
                self.assertEqual(match["season"], "2024")
                self.assertEqual(record, original)
                registry.validate_match_competition(match, self.catalog)

    def test_scores_are_preserved_without_adding_shootout_to_goals(self):
        extra = convert_fixture(provider_record("AET"), VERIFIED_TEAMS, is_demo=False,
                                competition_catalog=self.catalog)
        self.assertEqual((extra["homeScore"], extra["awayScore"]), (3, 2))
        self.assertEqual((extra["regularTimeHomeScore"], extra["regularTimeAwayScore"]), (2, 2))
        self.assertEqual((extra["extraTimeHomeScore"], extra["extraTimeAwayScore"]), (1, 0))
        shootout = convert_fixture(provider_record("PEN"), VERIFIED_TEAMS, is_demo=False,
                                   competition_catalog=self.catalog)
        self.assertEqual((shootout["homeScore"], shootout["awayScore"]), (1, 1))
        self.assertEqual((shootout["penaltyHomeScore"], shootout["penaltyAwayScore"]), (5, 4))

    def test_legacy_null_mapping_and_fictional_provenance_are_preserved(self):
        match = convert_fixture(provider_record(), VERIFIED_TEAMS, is_demo=False)
        self.assertIsNone(match["competitionId"])
        demo = convert_fixture(fictional_fixture(), VERIFIED_TEAMS, is_demo=True, competition_catalog=self.catalog)
        self.assertIsNone(demo["competitionId"])
        self.assertIsNone(demo["sourceCompetitionId"])
        self.assertIs(demo["isDemo"], True)

    def test_explicit_catalog_does_not_silently_accept_unknown_competition(self):
        record = provider_record()
        record["league"]["id"] = 900999
        with self.assertRaisesRegex(ReviewRequired, "No verified competition mapping"):
            convert_fixture(record, VERIFIED_TEAMS, is_demo=False, competition_catalog=self.catalog)

    def test_malformed_demo_markers_cannot_silently_be_converted_as_real(self):
        for marker in ("true", 1, None, True):
            record = provider_record()
            record["isDemo"] = marker
            with self.subTest(marker=marker), self.assertRaises(ReviewRequired):
                convert_fixture(record, VERIFIED_TEAMS, is_demo=False, competition_catalog=self.catalog)

    def test_match_link_conflicts_and_unresolved_ids_are_rejected(self):
        match = convert_fixture(provider_record(), VERIFIED_TEAMS, is_demo=False, competition_catalog=self.catalog)
        for target in (None, "competition_missing"):
            with self.subTest(target=target), self.assertRaises(ValidationError):
                registry.validate_match_competition(dict(match, competitionId=target), self.catalog)
        self.catalog["competitions"].append(dict(self.catalog["competitions"][0],
                                               competitionId="competition_synthetic_002"))
        with self.assertRaisesRegex(ValidationError, "conflicts"):
            registry.validate_match_competition(dict(match, competitionId="competition_synthetic_002"), self.catalog)

    def test_provider_year_does_not_generate_season_dates_or_association(self):
        record = provider_record()
        record["fixture"]["date"] = "2025-01-01T12:00:00Z"
        record["fixture"]["timestamp"] = None
        match = convert_fixture(record, VERIFIED_TEAMS, is_demo=False, competition_catalog=self.catalog)
        self.assertEqual(match["season"], "2024")
        self.assertEqual(self.catalog["seasons"], [])
        self.assertNotIn("competitionSeasonId", match)

    def test_mapped_in_memory_preview_reports_passed_and_review_separately(self):
        good, unknown = provider_record("AET"), provider_record("FT", 900003)
        unknown["league"]["id"] = 900999
        output = io.StringIO()
        with redirect_stdout(output):
            counts = preview.preview_records([good, unknown], VERIFIED_TEAMS, self.catalog)
        self.assertEqual(counts, {"PASSED": 1, "REVIEW REQUIRED": 1, "FAILED": 0})
        self.assertIn("Internal competition ID: competition_synthetic_001", output.getvalue())

    def test_invalid_catalog_stops_manual_preview_before_credentials_or_request(self):
        with patch.object(preview, "load_team_mapping", return_value={k: {"teamId": v} for k, v in VERIFIED_TEAMS.items()}), \
             patch.object(preview, "load_verified_catalog", side_effect=ValidationError("Invalid catalog")), \
             patch.object(preview, "read_api_key") as key, patch.object(preview, "fetch_head_to_head") as fetch, \
             redirect_stdout(io.StringIO()):
            self.assertEqual(preview.main(["--competition-catalog", "unused.json"]), 1)
        key.assert_not_called()
        fetch.assert_not_called()

    def test_catalog_flag_still_uses_only_one_mocked_fixture_request(self):
        with patch.object(preview, "load_team_mapping", return_value={k: {"teamId": v} for k, v in VERIFIED_TEAMS.items()}), \
             patch.object(preview, "load_verified_catalog", return_value=self.catalog), \
             patch.object(preview, "read_api_key", return_value="fictional-test-key"), \
             patch.object(preview, "fetch_head_to_head", return_value=(envelope([provider_record()]), [])) as fetch, \
             redirect_stdout(io.StringIO()):
            self.assertEqual(preview.main(["--competition-catalog", "unused.json"]), 0)
        fetch.assert_called_once_with("fictional-test-key", season=2024)


if __name__ == "__main__":
    unittest.main()
