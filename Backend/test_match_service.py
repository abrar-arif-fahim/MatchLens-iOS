"""Complete offline workflows with synthetic results and isolated document readers."""

import copy
import io
import json
import unittest
from contextlib import redirect_stdout
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import Mock, patch

import match_service as service
import preview_backend_pipeline as command
from competition_mapping import load_verified_catalog
from convert_api_football_fixture import ReviewRequired
from preview_match_import import MISSING
from test_competition_mapping import synthetic_catalog
from test_convert_api_football_fixture import VERIFIED_TEAMS, fictional_fixture
from test_preview_api_football_conversion import provider_record
from validate_competition_schema import load_catalog
from validate_match_schema import FIELDS, ValidationError, load_match, validate_match


def local_teams():
    return [
        {"teamId": "wikidata_Q7156", "wikidataId": "Q7156", "name": "FC Barcelona",
         "shortName": "BAR", "country": "Spain", "source": "Wikidata"},
        {"teamId": "wikidata_Q8682", "wikidataId": "Q8682", "name": "Real Madrid CF",
         "shortName": "RMA", "country": "Spain", "source": "Wikidata"},
    ]


class MatchServiceTests(unittest.TestCase):
    def setUp(self):
        for guard in (
            patch("urllib.request.OpenerDirector.open", side_effect=AssertionError("No network allowed")),
            patch("firebase_admin.initialize_app", side_effect=AssertionError("No credentials allowed")),
            patch("firebase_admin.firestore.client", side_effect=AssertionError("No real client allowed")),
        ):
            guard.start()
            self.addCleanup(guard.stop)
        self.catalog = synthetic_catalog()
        self.teams = local_teams()

    def prepared(self, code="FT"):
        # These synthetic inputs exercise real-source metadata, never real results.
        return service.prepare_fixture(provider_record(code), VERIFIED_TEAMS, self.teams, self.catalog, is_demo=False)

    def documents(self):
        return {"teams": {item["teamId"]: copy.deepcopy(item) for item in self.teams},
                "competitions": {item["competitionId"]: copy.deepcopy(item) for item in self.catalog["competitions"]},
                "matches": {}}

    def preview(self, matches, documents=None):
        reader = Mock(wraps=service.local_document_reader(self.documents() if documents is None else documents))
        plan = service.preview_matches(matches, self.teams, self.catalog, reader)
        return plan, reader

    def assert_all_preview_operations(self, prepared, catalog):
        """Carry one converted record through all three isolated store states."""
        match = prepared["match"]
        validate_match(match)  # Check the final internal record independently.
        self.assertEqual(set(match), FIELDS)
        self.assertEqual(set(prepared["firestoreData"]), FIELDS)
        data = prepared["firestoreData"]
        for expected, existing in (
            ("CREATE", None),
            ("UPDATE", dict(data, season="Earlier fictional edition")),
            ("NO CHANGE", dict(data, unrelatedField="Preserve this local value")),
        ):
            with self.subTest(operation=expected):
                documents = {
                    "teams": {team["teamId"]: copy.deepcopy(team) for team in self.teams},
                    "competitions": {row["competitionId"]: copy.deepcopy(row) for row in catalog["competitions"]},
                    "matches": {} if existing is None else {match["matchId"]: existing},
                }
                original = copy.deepcopy(documents)
                reader = Mock(wraps=service.local_document_reader(documents))
                plan = service.preview_matches([match], self.teams, catalog, reader)
                self.assertEqual(plan[0]["operation"], expected)
                self.assertEqual(service.summarize_plan(plan),
                                 {operation: int(operation == expected)
                                  for operation in ("CREATE", "UPDATE", "NO CHANGE")})
                if expected == "UPDATE":
                    self.assertEqual(plan[0]["differences"], [("season", "Earlier fictional edition", match["season"])])
                else:
                    self.assertEqual(plan[0]["differences"], [])
                self.assertEqual(reader.call_count, 4)
                self.assertEqual(plan[0]["prepared"]["match"], match)
                self.assertEqual(documents, original)  # A preview must never update the store.

    def test_json_fixture_to_reviewed_mapping_to_all_preview_operations(self):
        # Fictional results exercise the real-source ID contract in memory only.
        # No JSON fixture/converted record is saved or presented as a real match.
        catalog = load_verified_catalog()
        bindings = {140: "competition_la_liga", 143: "competition_copa_del_rey",
                    667: "competition_friendlies_clubs", 556: "competition_spain_super_cup"}
        for provider_id, internal_id in bindings.items():
            for index, code in enumerate(("FT", "AET", "PEN", "NS", "1H", "PST", "CANC")):
                with self.subTest(provider_id=provider_id, status=code):
                    fixture = provider_record(code, 900001 + index)
                    fixture["league"]["id"] = provider_id
                    fixture["league"]["name"] = next(row["name"] for row in catalog["competitions"]
                                                       if row["competitionId"] == internal_id)
                    record = json.load(io.StringIO(json.dumps(fixture)))
                    original = copy.deepcopy(record)
                    prepared = service.prepare_fixture(record, VERIFIED_TEAMS, self.teams, catalog, is_demo=False)
                    match = prepared["match"]
                    self.assertEqual(match["competitionId"], internal_id)
                    self.assertEqual(match["sourceCompetitionId"], str(provider_id))
                    self.assertEqual(match["matchId"], f"match_api_football_fixture_{fixture['fixture']['id']}")
                    self.assertEqual(match["sourceMatchId"], str(fixture["fixture"]["id"]))
                    self.assertEqual(match["homeTeamId"], VERIFIED_TEAMS[record["teams"]["home"]["id"]])
                    self.assertEqual(match["awayTeamId"], VERIFIED_TEAMS[record["teams"]["away"]["id"]])
                    self.assertEqual(match["kickoffUtc"], "2024-01-01T16:00:00Z")
                    self.assertEqual(match["homeScore"], record["goals"]["home"])
                    self.assertEqual(match["awayScore"], record["goals"]["away"])
                    for period, prefix in (("fulltime", "regularTime"), ("extratime", "extraTime"),
                                           ("penalty", "penalty")):
                        for side in ("Home", "Away"):
                            self.assertEqual(match[prefix + side + "Score"],
                                             record["score"][period][side.lower()])
                    self.assertEqual(record, original)
                    self.assert_all_preview_operations(prepared, catalog)

    def test_explicit_demo_json_stays_fictional_through_all_preview_operations(self):
        catalog = load_catalog()
        for code in ("FT", "AET", "PEN", "NS", "1H", "PST", "CANC"):
            with self.subTest(status=code):
                record = json.load(io.StringIO(json.dumps(fictional_fixture(code))))
                prepared = service.prepare_fixture(record, VERIFIED_TEAMS, self.teams, catalog,
                                                    is_demo=True, demo_competition_id="demo_competition_001")
                match = prepared["match"]
                self.assertTrue(match["isDemo"])
                self.assertEqual(match["source"], "demo")
                self.assertTrue(match["matchId"].startswith("demo_"))
                self.assertIsNone(match["sourceMatchId"])
                self.assertIsNone(match["sourceCompetitionId"])
                self.assert_all_preview_operations(prepared, catalog)

    def test_complete_preview_through_mocked_firestore_adapter_never_writes(self):
        prepared = self.prepared("AET")
        match = prepared["match"]
        for expected in ("CREATE", "UPDATE", "NO CHANGE"):
            with self.subTest(operation=expected):
                documents = self.documents()
                if expected != "CREATE":
                    documents["matches"][match["matchId"]] = dict(prepared["firestoreData"])
                if expected == "UPDATE":
                    documents["matches"][match["matchId"]]["season"] = "Earlier fictional edition"
                snapshot_reader = service.local_document_reader(documents)
                references = {}
                collections = []

                def collection(name):
                    result = Mock()
                    collections.append(result)
                    def document(identifier):
                        reference = Mock()
                        reference.get.return_value = snapshot_reader(name, identifier)
                        references[name, identifier] = reference
                        return reference
                    result.document.side_effect = document
                    return result

                db = Mock()
                db.collection.side_effect = collection
                plan = service.preview_matches([match], self.teams, self.catalog,
                                               service.firestore_document_reader(db))
                self.assertEqual(plan[0]["operation"], expected)
                self.assertEqual({call.args[0] for call in db.collection.call_args_list},
                                 {"teams", "competitions", "matches"})
                self.assertEqual(len(references), 4)
                for (name, _), reference in references.items():
                    reference.get.assert_called_once_with(field_paths=service.READ_FIELDS[name], timeout=20, retry=None)
                    for operation in ("set", "update", "create", "delete"):
                        getattr(reference, operation).assert_not_called()
                for result in collections:
                    result.add.assert_not_called()
                db.batch.assert_not_called()
                db.transaction.assert_not_called()

    def test_end_to_end_conversion_reference_validation_and_create_preview(self):
        for code in ("FT", "AET", "PEN", "NS", "1H", "PST", "CANC"):
            with self.subTest(code=code):
                prepared = self.prepared(code)
                plan, reader = self.preview([prepared["match"]])
                self.assertEqual(plan[0]["operation"], "CREATE")
                self.assertEqual(service.summarize_plan(plan), {"CREATE": 1, "UPDATE": 0, "NO CHANGE": 0})
                self.assertEqual(reader.call_count, 4)  # Two teams, one competition, one match.
                self.assertEqual(prepared["match"]["competitionId"], "competition_synthetic_001")
                self.assertEqual(prepared["competitionSeasons"], [])
                self.assertEqual(prepared["firestoreData"]["kickoffUtc"], datetime(2024, 1, 1, 16, tzinfo=timezone.utc))

    def test_extra_time_and_shootout_periods_survive_full_preparation(self):
        extra = self.prepared("AET")["firestoreData"]
        self.assertEqual((extra["homeScore"], extra["regularTimeHomeScore"], extra["extraTimeHomeScore"]), (3, 2, 1))
        penalty = self.prepared("PEN")["firestoreData"]
        self.assertEqual((penalty["homeScore"], penalty["awayScore"], penalty["penaltyHomeScore"], penalty["penaltyAwayScore"]), (1, 1, 5, 4))
        scheduled = self.prepared("NS")["firestoreData"]
        self.assertIsNone(scheduled["homeScore"])
        self.assertIsNone(scheduled["regularTimeHomeScore"])

    def test_no_change_and_unrelated_existing_fields_are_preserved_in_preview(self):
        prepared = self.prepared()
        documents = self.documents()
        documents["matches"][prepared["match"]["matchId"]] = dict(prepared["firestoreData"], unrelated="keep me")
        original = copy.deepcopy(documents)
        plan, _ = self.preview([prepared["match"]], documents)
        self.assertEqual(plan[0]["operation"], "NO CHANGE")
        self.assertEqual(plan[0]["differences"], [])
        self.assertEqual(documents, original)
        self.assertNotIn("unrelated", plan[0]["prepared"]["firestoreData"])

    def test_update_detects_missing_null_boolean_float_and_date_string_differences(self):
        prepared = self.prepared()
        for field, old in (("homeScore", True), ("homeScore", 2.0), ("homeScore", None),
                           ("kickoffUtc", prepared["match"]["kickoffUtc"])):
            documents = self.documents()
            documents["matches"][prepared["match"]["matchId"]] = dict(prepared["firestoreData"], **{field: old})
            with self.subTest(field=field, old=old):
                plan, _ = self.preview([prepared["match"]], documents)
                self.assertEqual(plan[0]["operation"], "UPDATE")
                self.assertEqual([row[0] for row in plan[0]["differences"]], [field])
        del documents["matches"][prepared["match"]["matchId"]]["finishType"]
        plan, _ = self.preview([prepared["match"]], documents)
        difference = next(row for row in plan[0]["differences"] if row[0] == "finishType")
        self.assertIs(difference[1], MISSING)

    def test_duplicate_or_invalid_later_matches_stop_before_any_read(self):
        good = self.prepared()["match"]
        for bad in (dict(good), dict(good, matchId="match_other", status="unsupported")):
            reader = Mock()
            with self.subTest(bad=bad["matchId"]), self.assertRaises(ValidationError):
                service.preview_matches([good, bad], self.teams, self.catalog, reader)
            reader.assert_not_called()

    def test_unresolved_competition_or_missing_local_team_stop_before_any_read(self):
        good = self.prepared()["match"]
        for change in ({"competitionId": None}, {"competitionId": "competition_missing"},
                       {"homeTeamId": "wikidata_Q900999"}):
            reader = Mock()
            with self.subTest(change=change), self.assertRaises(ValidationError):
                service.preview_matches([dict(good, **change)], self.teams, self.catalog, reader)
            reader.assert_not_called()

    def test_duplicate_malformed_or_inconsistent_local_teams_are_rejected(self):
        good = self.prepared()["match"]
        cases = [[], [self.teams[0], self.teams[0]], [dict(self.teams[0], wikidataId="Q8682")],
                 [dict(self.teams[0], teamId="wikidata_Q0")], [None]]
        for teams in cases:
            reader = Mock()
            with self.subTest(teams=teams), self.assertRaises(ValidationError):
                service.preview_matches([good], teams, self.catalog, reader)
            reader.assert_not_called()

    def test_local_team_schema_reuses_required_fields_and_provider_field_exclusion(self):
        match = self.prepared()["match"]
        missing = dict(self.teams[0])
        del missing["name"]
        for bad in (missing, dict(self.teams[0], source="API-Football"),
                    dict(self.teams[0], apiFootballId=529), dict(self.teams[0], name="")):
            reader = Mock()
            with self.subTest(bad=bad), self.assertRaises(ValidationError):
                service.preview_matches([match], [bad, self.teams[1]], self.catalog, reader)
            reader.assert_not_called()

    def test_missing_remote_team_or_competition_prevents_a_complete_plan(self):
        match = self.prepared()["match"]
        for collection, identifier in (("teams", "wikidata_Q7156"), ("competitions", "competition_synthetic_001")):
            documents = self.documents()
            del documents[collection][identifier]
            with self.subTest(collection=collection), self.assertRaisesRegex(ValidationError, "does not exist"):
                self.preview([match], documents)

    def test_remote_identifier_or_reviewed_identity_conflicts_are_rejected(self):
        match = self.prepared()["match"]
        for collection, identifier, changes in (
            ("teams", "wikidata_Q7156", {"wikidataId": "Q8682"}),
            ("competitions", "competition_synthetic_001", {"name": "A different competition"}),
            ("competitions", "competition_synthetic_001", {"isDemo": True}),
        ):
            documents = self.documents()
            documents[collection][identifier].update(changes)
            with self.subTest(collection=collection, changes=changes), self.assertRaises(ValidationError):
                self.preview([match], documents)

    def test_wrong_snapshot_id_and_reader_failures_are_sanitized(self):
        match = self.prepared()["match"]
        reader = Mock(return_value=SimpleNamespace(id="wrong", exists=True))
        with self.assertRaisesRegex(ValidationError, "inconsistent"):
            service.preview_matches([match], self.teams, self.catalog, reader)
        reader = Mock(side_effect=RuntimeError("PRIVATE_CONFIGURATION_MARKER"))
        with self.assertRaises(ValidationError) as error:
            service.preview_matches([match], self.teams, self.catalog, reader)
        self.assertNotIn("PRIVATE_CONFIGURATION_MARKER", str(error.exception))

    def test_invalid_snapshot_existence_or_missing_dictionary_method_is_rejected(self):
        match = self.prepared()["match"]
        for snapshot in (SimpleNamespace(id="wikidata_Q7156", exists=True),
                         SimpleNamespace(id="wikidata_Q7156", exists=1, to_dict=lambda: self.teams[0])):
            with self.subTest(snapshot=snapshot), self.assertRaises(ValidationError):
                service.preview_matches([match], self.teams, self.catalog, Mock(return_value=snapshot))

    def test_shared_remote_references_are_read_once_per_preview(self):
        first, second = self.prepared()["match"], self.prepared("NS")["match"]
        second.update(matchId="match_api_football_fixture_900003", sourceMatchId="900003")
        plan, reader = self.preview([first, second])
        self.assertEqual(len(plan), 2)
        self.assertEqual(reader.call_count, 5)

    def test_input_and_reader_snapshot_mutations_cannot_change_other_callers(self):
        record = provider_record()
        original_record, original_teams, original_catalog = copy.deepcopy((record, self.teams, self.catalog))
        prepared = service.prepare_fixture(record, VERIFIED_TEAMS, self.teams, self.catalog, is_demo=False)
        prepared["match"]["competition"] = "Changed copy"
        prepared["homeTeam"]["name"] = "Changed copy"
        prepared["competition"]["name"] = "Changed copy"
        self.assertEqual((record, self.teams, self.catalog), (original_record, original_teams, original_catalog))
        documents = self.documents()
        reader = service.local_document_reader(documents)
        documents["teams"]["wikidata_Q7156"]["name"] = "Changed outside the store"
        snapshot = reader("teams", "wikidata_Q7156")
        data = snapshot.to_dict()
        data["name"] = "Changed snapshot copy"
        self.assertEqual(snapshot.to_dict()["name"], "FC Barcelona")

    def test_fictional_converter_uses_only_an_explicit_demo_competition(self):
        catalog = load_catalog()
        prepared = service.prepare_fixture(fictional_fixture(), VERIFIED_TEAMS, self.teams, catalog,
                                            is_demo=True, demo_competition_id="demo_competition_001")
        self.assertIs(prepared["match"]["isDemo"], True)
        self.assertTrue(prepared["match"]["matchId"].startswith("demo_"))
        self.assertIsNone(prepared["match"]["sourceMatchId"])
        self.assertIsNone(prepared["match"]["sourceCompetitionId"])
        self.assertEqual(prepared["competition"]["competitionId"], "demo_competition_001")
        with self.assertRaises(ValidationError):
            service.prepare_fixture(fictional_fixture(), VERIFIED_TEAMS, self.teams, catalog, is_demo=True)
        with self.assertRaises(ValidationError):
            service.prepare_fixture(provider_record(), VERIFIED_TEAMS, self.teams, self.catalog,
                                    is_demo=False, demo_competition_id="demo_competition_001")

    def test_unknown_teams_competitions_and_unsupported_statuses_require_review(self):
        for change in ("team", "competition", "status"):
            record = provider_record()
            if change == "team":
                record["teams"]["away"]["id"] = 900999
            elif change == "competition":
                record["league"]["id"] = 900999
            else:
                record["fixture"]["status"]["short"] = "ABD"
            with self.subTest(change=change), self.assertRaises(ReviewRequired):
                service.prepare_fixture(record, VERIFIED_TEAMS, self.teams, self.catalog, is_demo=False)

    def test_firestore_adapter_only_reads_selected_fields_without_retries(self):
        db = Mock()
        reader = service.firestore_document_reader(db)
        db.collection.assert_not_called()
        reader("teams", "wikidata_Q7156")
        db.collection.assert_called_once_with("teams")
        reference = db.collection.return_value.document.return_value
        reference.get.assert_called_once_with(field_paths=service.TEAM_FIELDS, timeout=20, retry=None)
        for operation in ("set", "update", "create", "delete"):
            getattr(reference, operation).assert_not_called()
        db.batch.assert_not_called()
        db.transaction.assert_not_called()

    def test_firestore_adapter_rejects_unsafe_paths_before_any_call(self):
        db = Mock()
        reader = service.firestore_document_reader(db)
        for collection, identifier in (("users", "abc"), ("teams", "../private"), ("teams", "wikidata_Q0"),
                                       ([], "abc"), ("matches", None), ("competitions", "140")):
            with self.subTest(collection=collection, identifier=identifier), self.assertRaises(ValidationError):
                reader(collection, identifier)
        db.collection.assert_not_called()

    def test_firestore_adapter_hides_sdk_errors(self):
        db = Mock()
        db.collection.side_effect = RuntimeError("PRIVATE_CONFIGURATION_MARKER")
        with self.assertRaises(ValidationError) as error:
            service.firestore_document_reader(db)("teams", "wikidata_Q7156")
        self.assertNotIn("PRIVATE_CONFIGURATION_MARKER", str(error.exception))
        self.assertIn("permissions", str(error.exception))

    def test_new_command_runs_only_a_local_fictional_preview(self):
        output = io.StringIO()
        with redirect_stdout(output):
            self.assertEqual(command.main([]), 0)
        self.assertIn("FICTIONAL DEMONSTRATION", output.getvalue())
        self.assertIn("Simulated summary: CREATE 1 | UPDATE 0 | NO CHANGE 0", output.getvalue())
        self.assertIn(command.MESSAGE, output.getvalue())

    def test_command_rejects_real_source_input_and_write_or_live_flags(self):
        with patch.object(command, "load_match", return_value=self.prepared()["match"]), redirect_stdout(io.StringIO()):
            self.assertEqual(command.main([]), 1)
        for flag in ("--apply", "--firestore", "--output"):
            with self.subTest(flag=flag), redirect_stdout(io.StringIO()), patch("sys.stderr", io.StringIO()):
                with self.assertRaises(SystemExit) as error:
                    command.main([flag])
                self.assertEqual(error.exception.code, 2)


if __name__ == "__main__":
    unittest.main()
