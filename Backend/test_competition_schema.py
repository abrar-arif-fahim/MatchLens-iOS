"""Offline competition tests. Examples and mapping references are fictional."""

import copy
import io
import unittest
from contextlib import redirect_stdout
from unittest.mock import patch

import validate_competition_schema as schema
from validate_match_schema import ValidationError, load_match, validate_match


class CompetitionSchemaTests(unittest.TestCase):
    def setUp(self):
        self.data = schema.load_catalog()
        guard = patch("urllib.request.OpenerDirector.open", side_effect=AssertionError("Network forbidden"))
        guard.start()
        self.addCleanup(guard.stop)

    def reject(self, data):
        original = copy.deepcopy(data)
        with self.assertRaises(ValidationError):
            schema.validate_catalog(data)
        self.assertEqual(data, original)

    def real_source_contract(self):
        # Exercise non-demo validation with synthetic values in memory only.
        # This is not an assertion that any actual competition was verified.
        data = copy.deepcopy(self.data)
        competition = data["competitions"][0]
        competition.update(competitionId="competition_synthetic_001", isDemo=False, source="manual")
        season = data["seasons"][0]
        season.update(competitionId=competition["competitionId"],
                      seasonId="competition_synthetic_001_season_001", isDemo=False, source="manual")
        return data

    def mapping(self, verified=False):
        return {
            "provider": "API-Football", "providerCompetitionId": "900001",
            "competitionId": "competition_synthetic_001" if verified else None,
            "status": "verified" if verified else "pending",
            "verificationEvidence": "Fictional test evidence; not a real verification." if verified else None,
            "verifiedAt": "2030-01-02T12:00:00Z" if verified else None,
        }

    def test_default_example_is_fictional_valid_and_unchanged(self):
        original = copy.deepcopy(self.data)
        schema.validate_catalog(self.data)
        self.assertEqual(self.data, original)
        self.assertTrue(self.data["competitions"][0]["isDemo"])
        self.assertTrue(self.data["seasons"][0]["isDemo"])
        self.assertEqual(self.data["providerMappings"], [])

    def test_all_four_competition_types_are_supported(self):
        for kind in ("domesticLeague", "nationalCup", "internationalTournament", "friendly"):
            with self.subTest(kind=kind):
                data = copy.deepcopy(self.data)
                data["competitions"][0]["competitionType"] = kind
                schema.validate_catalog(data)

    def test_unknown_details_and_unavailable_seasons_are_not_invented(self):
        competition = self.data["competitions"][0]
        competition.update(competitionType=None, country=None, region=None)
        self.data["seasons"] = []  # No verified edition information yet.
        schema.validate_catalog(self.data)
        for field in ("competitionType", "country", "region"):
            self.assertIsNone(competition[field])

    def test_country_and_region_are_independent_optional_strings(self):
        self.data["competitions"][0].update(country="Fictional country", region="Fictional region")
        schema.validate_catalog(self.data)
        for field in ("country", "region"):
            for invalid in (False, 12, [], {}, "", "unknown"):
                data = copy.deepcopy(self.data)
                data["competitions"][0][field] = invalid
                self.reject(data)

    def test_invalid_identifiers_are_rejected(self):
        for identifier in (None, 140, True, "140", "wikidata_Q1", "competition_", "competition_upperCase",
                           "demo_competition_", "demo_competition_a/b", " demo_competition_001"):
            data = copy.deepcopy(self.data)
            data["competitions"][0]["competitionId"] = identifier
            with self.subTest(identifier=identifier):
                self.reject(data)

    def test_missing_fields_and_unexpected_provider_fields_are_rejected(self):
        for field in schema.COMPETITION_FIELDS:
            data = copy.deepcopy(self.data)
            del data["competitions"][0][field]
            self.reject(data)
        for field in ("providerCompetitionId", "season", "matchId", "logo"):
            data = copy.deepcopy(self.data)
            data["competitions"][0][field] = "not part of competition identity"
            self.reject(data)

    def test_invalid_names_types_and_catalog_shapes_are_rejected(self):
        for value in (None, "", "  ", " unknown ", "unknown", " Cup", "Cup\n", True, []):
            data = copy.deepcopy(self.data)
            data["competitions"][0]["name"] = value
            self.reject(data)
        for value in ("league", True, [], {}, 1):
            data = copy.deepcopy(self.data)
            data["competitions"][0]["competitionType"] = value
            self.reject(data)
        for value in (None, [], {}, {"competitions": [], "seasons": [], "providerMappings": []}):
            self.reject(value)
        for field in schema.CATALOG_FIELDS:
            data = copy.deepcopy(self.data)
            data[field] = {}
            self.reject(data)

    def test_duplicate_competition_ids_are_rejected(self):
        self.data["competitions"].append(copy.deepcopy(self.data["competitions"][0]))
        self.reject(self.data)

    def test_demo_and_source_markers_must_be_consistent(self):
        for changes in ({"isDemo": 1}, {"source": "Wikidata"}, {"source": None}, {"isDemo": False}):
            data = copy.deepcopy(self.data)
            data["competitions"][0].update(changes)
            self.reject(data)
        real = self.real_source_contract()
        schema.validate_catalog(real)
        real["competitions"][0]["source"] = "demo"
        self.reject(real)

    def test_cross_year_season_is_separate_from_competition_identity(self):
        original_competition = copy.deepcopy(self.data["competitions"][0])
        season = self.data["seasons"][0]
        season.update(startDate="2030-08-01", endDate="2031-05-31")
        schema.validate_catalog(self.data)
        self.assertEqual(self.data["competitions"][0], original_competition)
        self.assertNotEqual(season["seasonId"], season["competitionId"])

    def test_single_year_season_and_leap_day(self):
        self.data["seasons"][0].update(label="2032 (fictional)", startYear=2032, endYear=2032,
                                      startDate="2032-02-29", endDate="2032-12-01")
        schema.validate_catalog(self.data)

    def test_missing_dates_stay_null_and_one_known_boundary_is_allowed(self):
        season = self.data["seasons"][0]
        season["endDate"] = "2031-05-31"
        schema.validate_catalog(self.data)
        self.assertIsNone(season["startDate"])
        self.assertEqual(season["startYear"], 2030)

    def test_invalid_years_dates_and_reversed_ranges_are_rejected(self):
        for changes in ({"startYear": True}, {"endYear": "2031"}, {"endYear": None},
                        {"startYear": 999}, {"endYear": 10000}, {"startYear": 2032},
                        {"startDate": "2030-02-30"}, {"startDate": "2030-8-01"},
                        {"endDate": 20310531}, {"endDate": "2032-01-01"},
                        {"endYear": 2030, "startDate": "2030-09-01", "endDate": "2030-01-01"}):
            data = copy.deepcopy(self.data)
            data["seasons"][0].update(changes)
            with self.subTest(changes=changes):
                self.reject(data)

    def test_season_fields_identifiers_and_parent_must_be_consistent(self):
        for field in schema.SEASON_FIELDS:
            data = copy.deepcopy(self.data)
            del data["seasons"][0][field]
            self.reject(data)
        for changes in ({"competitionId": "demo_competition_missing"}, {"competitionId": []},
                        {"seasonId": "demo_competition_other_season_001"}, {"seasonId": "2030/31"},
                        {"label": None}, {"isDemo": False, "source": "manual"}):
            data = copy.deepcopy(self.data)
            data["seasons"][0].update(changes)
            self.reject(data)

    def test_season_ids_are_unique_stable_and_allow_multiple_editions(self):
        first = self.data["seasons"][0]
        self.data["seasons"].append(copy.deepcopy(first))
        self.reject(self.data)
        self.data["seasons"][1].update(seasonId="demo_competition_001_season_002", label="Another fictional edition")
        schema.validate_catalog(self.data)
        original_id = first["seasonId"]
        first["label"] = "A corrected fictional display label"
        schema.validate_catalog(self.data)
        self.assertEqual(first["seasonId"], original_id)

    def test_pending_mapping_has_no_internal_association(self):
        self.data["providerMappings"] = [self.mapping()]
        schema.validate_catalog(self.data)
        self.assertIsNone(self.data["providerMappings"][0]["competitionId"])
        for field in ("competitionId", "verifiedAt", "verificationEvidence"):
            data = copy.deepcopy(self.data)
            data["providerMappings"][0][field] = "unreviewed association"
            self.reject(data)

    def test_verified_mapping_contract_only_in_synthetic_memory(self):
        data = self.real_source_contract()
        data["providerMappings"] = [self.mapping(verified=True)]
        original = copy.deepcopy(data)
        schema.validate_catalog(data)
        self.assertEqual(data, original)
        self.assertNotEqual(data["providerMappings"][0]["providerCompetitionId"],
                            data["competitions"][0]["competitionId"])

    def test_duplicate_and_conflicting_external_mappings_are_rejected(self):
        data = self.real_source_contract()
        first = self.mapping(verified=True)
        data["providerMappings"] = [first, copy.deepcopy(first)]
        self.reject(data)
        other = dict(data["competitions"][0], competitionId="competition_synthetic_002")
        data["competitions"].append(other)
        data["providerMappings"][1]["competitionId"] = other["competitionId"]
        self.reject(data)  # Same provider ID, different internal targets.

    def test_multiple_provider_ids_cannot_silently_alias_one_competition(self):
        data = self.real_source_contract()
        data["providerMappings"] = [self.mapping(verified=True),
                                    dict(self.mapping(verified=True), providerCompetitionId="900002")]
        self.reject(data)

    def test_mapping_requires_evidence_timestamp_and_non_demo_target(self):
        for changes in ({"competitionId": None}, {"competitionId": "competition_missing"},
                        {"verificationEvidence": None}, {"verificationEvidence": ""},
                        {"verifiedAt": None}, {"verifiedAt": "2030-01-02T12:00:00+00:00"},
                        {"verifiedAt": "2030-02-30T12:00:00Z"}):
            data = self.real_source_contract()
            data["providerMappings"] = [dict(self.mapping(verified=True), **changes)]
            self.reject(data)
        self.data["providerMappings"] = [dict(self.mapping(verified=True), competitionId="demo_competition_001")]
        self.reject(self.data)

    def test_mapping_shape_provider_ids_and_status_are_validated(self):
        for changes in ({"provider": "api-football"}, {"providerCompetitionId": 900001},
                        {"providerCompetitionId": True}, {"providerCompetitionId": "0900001"},
                        {"providerCompetitionId": "0"}, {"providerCompetitionId": "https://invalid.example"},
                        {"status": "assumed"}, {"status": []}):
            data = copy.deepcopy(self.data)
            data["providerMappings"] = [dict(self.mapping(), **changes)]
            self.reject(data)
        for field in schema.MAPPING_FIELDS:
            data = copy.deepcopy(self.data)
            mapping = self.mapping()
            del mapping[field]
            data["providerMappings"] = [mapping]
            self.reject(data)

    def test_existing_match_reference_and_schema_remain_compatible(self):
        match = load_match()
        validate_match(match)
        competition = self.data["competitions"][0]
        self.assertEqual(match["competitionId"], competition["competitionId"])
        self.assertEqual(match["isDemo"], competition["isDemo"])
        self.assertEqual(match["competition"], competition["name"])

    def test_file_errors_and_main_messages_are_safe(self):
        with patch.object(schema.Path, "open", side_effect=FileNotFoundError):
            with self.assertRaisesRegex(ValidationError, "not found"):
                schema.load_catalog()
        for raw in ('not JSON', '{"competitions": [], "competitions": []}'):
            with patch.object(schema.Path, "open", return_value=io.StringIO(raw)):
                with self.assertRaises(ValidationError):
                    schema.load_catalog()
        with patch.object(schema.Path, "open", side_effect=PermissionError):
            with self.assertRaisesRegex(ValidationError, "permissions"):
                schema.load_catalog()
        output = io.StringIO()
        with redirect_stdout(output):
            code = schema.main()
        self.assertEqual(code, 0)
        self.assertIn("DEMO ONLY", output.getvalue())
        self.assertIn("No external requests or database changes", output.getvalue())
        bad = copy.deepcopy(self.data)
        bad["competitions"][0]["competitionId"] = "PRIVATE_INPUT_MARKER"
        with patch.object(schema, "load_catalog", return_value=bad), redirect_stdout(output):
            code = schema.main()
        self.assertEqual(code, 1)
        self.assertNotIn("PRIVATE_INPUT_MARKER", output.getvalue())


if __name__ == "__main__":
    unittest.main(verbosity=2)
