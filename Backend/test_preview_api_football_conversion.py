"""Offline integration tests. All fixtures and HTTP responses here are fictional."""

import copy
import io
import json
import unittest
from contextlib import redirect_stdout
from unittest.mock import Mock, patch
from urllib.error import HTTPError, URLError
from urllib.parse import parse_qs, urlparse

import preview_api_football_conversion as preview
import preview_api_football_matches as api_preview
from convert_api_football_fixture import convert_fixture
from test_convert_api_football_fixture import VERIFIED_TEAMS, fictional_fixture


TEST_KEY = "OFFLINE_CREDENTIAL_MARKER"
LOCAL_TEAMS = {
    api_id: {"teamId": team_id, "name": "Verified local test name"}
    for api_id, team_id in VERIFIED_TEAMS.items()
}


def provider_record(code="FT", identifier=900001):
    # Exercise real-source mode synthetically, in captured memory only. Never
    # save/display these test records as historical fixtures or output datasets.
    record = fictional_fixture(code)
    del record["isDemo"]
    record["fixture"]["id"] = identifier
    return record


def envelope(records):
    return {"errors": {}, "results": len(records), "response": records,
            "paging": {"current": 1, "total": 1}}


class ConversionPreviewTests(unittest.TestCase):
    def setUp(self):
        # A missed mock must fail, never access the network or the real .env.
        guards = [
            patch("urllib.request.OpenerDirector.open", side_effect=AssertionError("Network forbidden")),
            patch("api_football_players.read_api_key", side_effect=AssertionError("Real credentials forbidden")),
            patch.object(preview, "read_api_key", return_value=TEST_KEY),
            patch.object(preview, "load_team_mapping", return_value=copy.deepcopy(LOCAL_TEAMS)),
        ]
        for guard in guards:
            guard.start()
            self.addCleanup(guard.stop)

    def run_preview(self, data=None, error=None, raw=None, headers=None):
        response = io.BytesIO(raw if raw is not None else json.dumps(data).encode("utf-8"))
        response.status = 200
        response.headers = headers or {}
        opener = Mock()
        if error is not None:
            opener.open.side_effect = error
        else:
            opener.open.return_value = response
        output = io.StringIO()
        with patch.object(api_preview, "build_opener", return_value=opener) as factory:
            with redirect_stdout(output):
                exit_code = preview.main([])
        self.assertNotIn(TEST_KEY, output.getvalue())
        self.assertIn(preview.PREVIEW_MESSAGE, output.getvalue())
        return exit_code, output.getvalue(), opener, factory

    def test_one_get_converts_all_records_and_preserves_periods(self):
        records = [provider_record(code, 900001 + index)
                   for index, code in enumerate(("FT", "AET", "PEN", "NS", "1H"))]
        original = copy.deepcopy(records)
        with patch.object(preview, "validate_match", wraps=preview.validate_match) as validator:
            code, output, opener, factory = self.run_preview(envelope(records))
        self.assertEqual(code, 0)
        self.assertEqual(records, original)
        self.assertEqual(validator.call_count, 5)  # Explicit schema recheck per conversion.
        self.assertIn("fixtures returned 5 | PASSED 5 | REVIEW REQUIRED 0 | FAILED 0", output)
        self.assertIn("Finish: extraTime", output)
        self.assertIn("Goals (home / away): 3 / 2", output)
        self.assertIn("Regular time: 2 / 2", output)
        self.assertIn("Extra-time period: 1 / 0", output)
        self.assertIn("Finish: penalties", output)
        self.assertIn("Shootout: 5 / 4", output)
        self.assertIn("Goals (home / away): null / null", output)
        self.assertIn("Internal competition ID: null (mapping not verified)", output)
        self.assertIn("match_api_football_fixture_900001", output)
        self.assertIn("2024-01-01T16:00:00Z", output)
        factory.assert_called_once()
        self.assertIsInstance(factory.call_args.args[0], api_preview.NoRedirects)
        opener.open.assert_called_once()
        request = opener.open.call_args.args[0]
        parsed = urlparse(request.full_url)
        self.assertEqual((parsed.scheme, parsed.netloc, parsed.path),
                         ("https", "v3.football.api-sports.io", "/fixtures/headtohead"))
        self.assertEqual(parse_qs(parsed.query), {"h2h": ["529-541"], "season": ["2024"]})
        self.assertEqual(request.get_method(), "GET")
        self.assertEqual(request.get_header("X-apisports-key"), TEST_KEY)
        self.assertEqual(opener.open.call_args.kwargs, {"timeout": 20})

    def test_review_and_failure_records_do_not_stop_other_conversions(self):
        unknown = provider_record(identifier=900002)
        unknown["teams"]["home"]["id"] = 999999
        unsupported = provider_record("TBD", 900003)
        code, output, opener, _ = self.run_preview(envelope([provider_record(), unknown, unsupported, None, {}]))
        self.assertEqual(code, 1)
        self.assertIn("PASSED 1 | REVIEW REQUIRED 3 | FAILED 1", output)
        self.assertIn("no supplied verified mapping", output)
        self.assertIn("unsupported or uncertain", output)
        self.assertIn("fixture must be an object", output)
        self.assertIn("returned fixture record is not an object", output)
        opener.open.assert_called_once()

    def test_duplicate_fixture_ids_require_review_for_every_occurrence(self):
        code, output, opener, _ = self.run_preview(envelope([provider_record(), provider_record()]))
        self.assertEqual(code, 1)
        self.assertIn("PASSED 0 | REVIEW REQUIRED 2 | FAILED 0", output)
        self.assertIn("Duplicate fixture ID", output)
        opener.open.assert_called_once()

    def test_wrong_season_and_conflicting_timestamps_are_not_corrected(self):
        wrong_season = provider_record()
        wrong_season["league"]["season"] = 2023
        bad_time = provider_record(identifier=900002)
        bad_time["fixture"]["timestamp"] += 60
        code, output, _, _ = self.run_preview(envelope([wrong_season, bad_time]))
        self.assertEqual(code, 1)
        self.assertIn("PASSED 0 | REVIEW REQUIRED 2 | FAILED 0", output)
        self.assertIn("differs from the requested 2024 season", output)
        self.assertIn("fixture.date and fixture.timestamp disagree", output)

    def test_conversion_contract_detects_valid_but_incorrect_output(self):
        record = provider_record()
        match = convert_fixture(record, VERIFIED_TEAMS, is_demo=False)
        corruptions = {"matchId": "match_api_football_fixture_900999", "sourceMatchId": "900999",
                       "homeTeamId": "wikidata_Q11571", "kickoffUtc": "2024-01-01T17:00:00Z",
                       "sourceCompetitionId": "900999", "competitionId": "competition_unverified",
                       "source": "Different provider"}
        for field, value in corruptions.items():
            broken = dict(match, **{field: value})
            with self.subTest(field=field), patch.object(preview, "convert_fixture", return_value=broken):
                code, output, _, _ = self.run_preview(envelope([record]))
                self.assertEqual(code, 1)
                self.assertIn("PASSED 0 | REVIEW REQUIRED 0 | FAILED 1", output)

    def test_missing_scores_stay_unknown_and_fictional_marker_is_rejected(self):
        scheduled = provider_record("NS")
        del scheduled["goals"]
        del scheduled["score"]
        aet = provider_record("AET", 900002)
        del aet["score"]["extratime"]
        fictional = fictional_fixture()
        fictional["fixture"]["id"] = 900003
        code, output, _, _ = self.run_preview(envelope([scheduled, aet, fictional]))
        self.assertEqual(code, 1)
        self.assertIn("PASSED 2 | REVIEW REQUIRED 1 | FAILED 0", output)
        self.assertIn("Extra-time period: null / null", output)
        self.assertIn("marked as fictional cannot be converted as real-source", output)

    def test_empty_response_and_additional_pages_do_not_trigger_requests(self):
        code, output, opener, _ = self.run_preview(envelope([]))
        self.assertEqual(code, 1)
        self.assertIn("No fixtures returned", output)
        self.assertIn("fixtures returned 0 | PASSED 0", output)
        opener.open.assert_called_once()
        data = envelope([provider_record()])
        data["paging"]["total"] = 2
        code, output, opener, _ = self.run_preview(data)
        self.assertEqual(code, 1)
        self.assertIn("Response REVIEW REQUIRED: Additional pages", output)
        opener.open.assert_called_once()

    def test_http_errors_are_filtered_and_never_retried(self):
        for status in (302, 401, 403, 429, 503):
            body = {"errors": {"plan": "Access denied " + TEST_KEY, "private_key": "PRIVATE_BODY_MARKER"},
                    "account": "PRIVATE_ACCOUNT_MARKER"}
            error = HTTPError("https://invalid.example", status, "PRIVATE_HTTP_MESSAGE", {},
                              io.BytesIO(json.dumps(body).encode("utf-8")))
            with self.subTest(status=status):
                code, output, opener, _ = self.run_preview(error=error)
                self.assertEqual(code, 1)
                self.assertIn(f"HTTP status: {status}", output)
                self.assertIn("Preview incomplete", output)
                for marker in ("PRIVATE_BODY_MARKER", "PRIVATE_ACCOUNT_MARKER", "PRIVATE_HTTP_MESSAGE"):
                    self.assertNotIn(marker, output)
                opener.open.assert_called_once()

    def test_provider_errors_dictionary_and_list_and_exhausted_quota(self):
        for errors in ({"plan": "Free plan subscription restriction " + TEST_KEY},
                       ["Requests quota limit reached " + TEST_KEY]):
            data = envelope([])
            data["errors"] = errors
            with self.subTest(errors_type=type(errors).__name__):
                code, output, opener, _ = self.run_preview(data)
                self.assertEqual(code, 1)
                self.assertIn("Provider errors (filtered", output)
                self.assertIn("fixtures returned unknown", output)
                opener.open.assert_called_once()
        code, output, opener, _ = self.run_preview(envelope([provider_record()]),
                                                  headers={"x-ratelimit-requests-remaining": "0"})
        self.assertEqual(code, 0)  # Current response is valid; quota only blocks later calls.
        self.assertIn("Daily quota exhausted", output)
        opener.open.assert_called_once()

    def test_invalid_json_envelope_and_connectivity_errors_stop_safely(self):
        code, output, opener, _ = self.run_preview(raw=b"not valid JSON")
        self.assertEqual(code, 1)
        self.assertIn("invalid JSON", output)
        opener.open.assert_called_once()
        data = envelope([provider_record()])
        data["results"] = 2
        code, output, opener, _ = self.run_preview(data)
        self.assertEqual(code, 1)
        self.assertIn("invalid fixture results/counts", output)
        opener.open.assert_called_once()
        for error in (URLError("PRIVATE_CONNECTION_MARKER"), TimeoutError("PRIVATE_CONNECTION_MARKER")):
            code, output, opener, _ = self.run_preview(error=error)
            self.assertEqual(code, 1)
            self.assertIn("connection failed or timed out", output)
            self.assertNotIn("PRIVATE_CONNECTION_MARKER", output)
            opener.open.assert_called_once()

    def test_missing_credentials_or_invalid_local_mapping_make_no_request(self):
        with patch.object(preview, "read_api_key", return_value=None):
            code, output, opener, _ = self.run_preview(envelope([]))
            self.assertEqual(code, 1)
            self.assertIn("credentials are unavailable", output)
            self.assertIn("API requests attempted: 0/1", output)
            opener.open.assert_not_called()
        with patch.object(preview, "load_team_mapping", return_value={}):
            code, output, opener, _ = self.run_preview(envelope([]))
            self.assertEqual(code, 1)
            self.assertIn("verified team mappings", output)
            opener.open.assert_not_called()

    def test_raw_responses_names_and_unmanaged_fields_are_never_displayed(self):
        record = provider_record()
        record["league"]["name"] = "RAW_NAME_MARKER"
        record["teams"]["home"]["name"] = "RAW_NAME_MARKER"
        record["headers"] = {"api-key": TEST_KEY}
        record["events"] = [{"secret": "RAW_BODY_MARKER"}]
        data = envelope([record])
        data["account"] = "RAW_ACCOUNT_MARKER"
        code, output, _, _ = self.run_preview(data)
        self.assertEqual(code, 0)
        for marker in ("RAW_NAME_MARKER", "RAW_BODY_MARKER", "RAW_ACCOUNT_MARKER"):
            self.assertNotIn(marker, output)


if __name__ == "__main__":
    unittest.main(verbosity=2)
