"""Fictional event/player workflows. No network, credentials or database access."""

import copy
import json
import unittest
from pathlib import Path
from unittest.mock import patch

import match_event_service as service
from import_multiple_players import PreviewError, validate_player_records
from match_service import summarize_plan
from test_match_service import local_teams
from validate_competition_schema import load_catalog
from validate_match_schema import ValidationError


def demo_match():
    path = Path(__file__).resolve().parent / "input" / "match_schema_test_cases.json"
    with path.open(encoding="utf-8-sig") as handle:
        match = json.load(handle)["matches"][0]
    match["competitionId"] = "demo_competition_001"
    return match


def fictional_players():
    # These are synthetic identity shapes, not fetched or verified Wikidata data.
    return [{"documentId": "wikidata_Q900001", "wikidataId": "Q900001",
             "name": "Fictional Player", "dateOfBirth": "1995-01-01",
             "nationality": "Fictional country", "position": "forward", "source": "Wikidata"}]


def fictional_event(match, key="goal_1", **changes):
    event = {"eventId": service.make_related_id(match["matchId"], "event", key),
             "matchId": match["matchId"], "teamId": match["homeTeamId"],
             "playerId": "wikidata_Q900001", "eventType": "goal", "matchMinute": 45,
             "addedTime": 2, "label": "Fictional goal", "isDemo": match["isDemo"],
             "source": "demo" if match["isDemo"] else "manual"}
    event.update(changes)
    return event


class MatchEventServiceTests(unittest.TestCase):
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

    def prepare(self, events=None):
        return service.prepare_event_bundles([self.match], self.teams, self.players, self.catalog,
                                             events if events is not None else [fictional_event(self.match)])

    def test_match_team_competition_player_event_join_is_isolated(self):
        event = fictional_event(self.match)
        original = copy.deepcopy((self.match, self.teams, self.players, self.catalog, event))
        result = self.prepare([event])[0]
        self.assertEqual(result["match"], self.match)
        self.assertEqual(result["homeTeam"]["teamId"], event["teamId"])
        self.assertEqual(result["competition"]["competitionId"], self.match["competitionId"])
        self.assertEqual(result["eventPlayers"][event["playerId"]]["name"], "Fictional Player")
        self.assertNotIn("events", result["firestoreData"])
        result["events"][0]["label"] = "Local edit"
        result["eventPlayers"][event["playerId"]]["name"] = "Local edit"
        self.assertEqual((self.match, self.teams, self.players, self.catalog, event), original)

    def test_ids_are_stable_parent_scoped_and_unambiguous(self):
        first = service.make_related_id("demo_a_b", "event", "c")
        second = service.make_related_id("demo_a", "event", "b_c")
        self.assertNotEqual(first, second)
        self.assertEqual(first, service.make_related_id("demo_a_b", "event", "c"))
        self.assertEqual(service.make_related_id("match_example", "event", "goal_1"),
                         "event_example__goal_1")
        for invalid in ("", " ../x", "UPPER", "a__b", None):
            with self.subTest(key=invalid), self.assertRaises(ValidationError):
                service.make_related_id(self.match["matchId"], "event", invalid)

    def test_wrong_parent_kind_or_noncanonical_match_id_is_rejected(self):
        for parent, kind in (("../match_example", "event"), ("demo_example", "player")):
            with self.subTest(parent=parent, kind=kind), self.assertRaises(ValidationError):
                service.make_related_id(parent, kind, "one")
        event = fictional_event(self.match, eventId="demo_event_other_match__goal_1")
        with self.assertRaisesRegex(ValidationError, "parent match"):
            self.prepare([event])

    def test_unknown_event_match_or_team_or_player_is_rejected(self):
        for changes in ({"matchId": "demo_missing"}, {"teamId": "wikidata_Q123"},
                        {"playerId": "wikidata_Q123"}, {"playerId": []}):
            with self.subTest(changes=changes), self.assertRaises(ValidationError):
                self.prepare([fictional_event(self.match, **changes)])

    def test_required_team_and_player_context_are_checked(self):
        for changes in ({"teamId": None}, {"eventType": "other", "teamId": None}):
            with self.subTest(changes=changes), self.assertRaises(ValidationError):
                self.prepare([fictional_event(self.match, **changes)])
        result = self.prepare([fictional_event(self.match, eventType="other", teamId=None, playerId=None)])[0]
        self.assertEqual(result["eventPlayers"], {})

    def test_null_clock_and_unknown_player_are_preserved(self):
        result = self.prepare([fictional_event(self.match, matchMinute=None, addedTime=None, playerId=None)])[0]
        event = result["events"][0]
        self.assertIsNone(service.event_clock(event))
        self.assertIsNone(event["playerId"])
        self.assertEqual(result["match"]["homeScore"], 2)
        # A partial event list is never used to recalculate the final score.

    def test_event_clock_and_sorting_keep_added_time_separate(self):
        events = [fictional_event(self.match, "later", matchMinute=46, addedTime=0),
                  fictional_event(self.match, "unknown_clock", matchMinute=None, addedTime=None),
                  fictional_event(self.match, "stoppage", matchMinute=45, addedTime=10)]
        result = self.prepare(events)[0]["events"]
        self.assertEqual([service.event_clock(row) for row in result], ["45+10", "46", None])

    def test_invalid_clock_values_are_rejected(self):
        for changes in ({"matchMinute": True}, {"matchMinute": -1}, {"matchMinute": 2.5},
                        {"addedTime": False}, {"addedTime": "2"}, {"addedTime": -1},
                        {"matchMinute": None, "addedTime": 1}):
            with self.subTest(changes=changes), self.assertRaises(ValidationError):
                self.prepare([fictional_event(self.match, **changes)])

    def test_all_curated_event_types_validate(self):
        events = [fictional_event(self.match, kind.lower(), eventType=kind) for kind in service.EVENT_TYPES]
        self.assertEqual(len(self.prepare(events)[0]["events"]), len(service.EVENT_TYPES))

    def test_missing_extra_or_unsupported_event_data_is_rejected(self):
        valid = fictional_event(self.match)
        missing = dict(valid)
        del missing["label"]
        for event in (missing, dict(valid, photo="excluded"), dict(valid, sourcePlayerId=1),
                      dict(valid, label="  "), dict(valid, eventType="unreviewed"), dict(valid, eventType=[])):
            with self.subTest(event=event), self.assertRaises(ValidationError):
                self.prepare([event])

    def test_event_provenance_cannot_be_relabelled(self):
        for changes in ({"isDemo": False}, {"isDemo": 1}, {"source": "api-football"}, {"source": "manual"}):
            with self.subTest(changes=changes), self.assertRaises(ValidationError):
                self.prepare([fictional_event(self.match, **changes)])

    def test_duplicate_events_or_malformed_arrays_stop_complete_batch(self):
        valid = fictional_event(self.match)
        for events in ([valid, copy.deepcopy(valid)], [valid, None], {}, "events"):
            with self.subTest(events=events), self.assertRaises(ValidationError):
                self.prepare(events)

    def test_no_events_is_a_valid_incomplete_analysis(self):
        self.assertEqual(self.prepare([])[0]["events"], [])

    def test_scheduled_match_cannot_contain_occurred_events(self):
        for status in ("scheduled", "postponed", "cancelled"):
            with self.subTest(status=status):
                self.match.update(status=status, finishType=None, homeScore=None, awayScore=None,
                                  regularTimeHomeScore=None, regularTimeAwayScore=None)
                with self.assertRaisesRegex(ValidationError, "occurred events"):
                    self.prepare()
                self.assertEqual(self.prepare([])[0]["events"], [])

    def test_live_match_can_have_curated_events(self):
        self.match.update(status="live", finishType=None)
        self.assertEqual(len(self.prepare()[0]["events"]), 1)

    def test_invalid_or_duplicate_players_are_not_accepted(self):
        original = self.players
        for players in ([dict(original[0], dateOfBirth="1995-02-30")],
                        [dict(original[0], documentId="wikidata_Q2")],
                        original + original, "players"):
            with self.subTest(players=players), self.assertRaises(ValidationError):
                service.index_players(players)

    def test_player_public_allowlist_omits_provider_extras(self):
        player = dict(self.players[0], apiFootballId=123, photo="excluded")
        indexed = service.index_players([player])[player["documentId"]]
        self.assertEqual(set(indexed), {"wikidataId", "name", "dateOfBirth", "nationality", "position", "source"})

    def test_read_service_does_not_expand_five_player_import_limit(self):
        players = [dict(self.players[0], documentId=f"wikidata_Q{index}", wikidataId=f"Q{index}")
                   for index in range(900001, 900007)]
        self.assertEqual(len(service.index_players(players)), 6)
        with self.assertRaises(PreviewError):
            validate_player_records({"players": players})
        for limit in (-1, True, "5"):
            with self.subTest(limit=limit), self.assertRaises(PreviewError):
                validate_player_records({"players": []}, max_records=limit)

    def test_all_three_local_preview_states_preserve_unrelated_fields(self):
        record = self.prepare()[0]["events"][0]
        identifier = record["eventId"]
        for action, documents in (("CREATE", {}), ("UPDATE", {identifier: dict(record, label="Earlier demo label")}),
                                  ("NO CHANGE", {identifier: dict(record, unrelated="kept")})):
            original = copy.deepcopy(documents)
            plan = service.preview_curated_records([record], documents, "eventId")
            self.assertEqual(plan[0]["operation"], action)
            self.assertEqual(summarize_plan(plan)[action], 1)
            self.assertEqual(documents, original)
            if action == "UPDATE":
                self.assertEqual(plan[0]["differences"], [("label", "Earlier demo label", record["label"])])

    def test_nested_comparison_is_type_strict(self):
        self.assertFalse(service.managed_values_equal({"time": [True]}, {"time": [1]}))
        self.assertFalse(service.managed_values_equal([1], [1.0]))
        self.assertTrue(service.managed_values_equal({"time": [1, None]}, {"time": [1, None]}))

    def test_invalid_preview_snapshots_or_duplicate_ids_fail(self):
        event = fictional_event(self.match)
        for records, documents, field in (([event, event], {}, "eventId"), ([event], [], "eventId"),
                                           ([event], {event["eventId"]: None}, "eventId"),
                                           ([], {}, "matchId"), ([None], {}, "eventId")):
            with self.subTest(field=field, records=records), self.assertRaises(ValidationError):
                service.preview_curated_records(records, documents, field)


if __name__ == "__main__":
    unittest.main()
