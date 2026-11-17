"""Offline tests with fictional HTTP responses; no credentials or API calls."""

import copy
import io
import json
import unittest
from contextlib import redirect_stderr, redirect_stdout
from datetime import date
from unittest.mock import Mock, patch
from urllib.error import HTTPError, URLError
from urllib.parse import parse_qs, urlparse

import preview_api_football_competition as preview


TEST_KEY = "OFFLINE_SECRET_MARKER"


def fictional_record():
    # ID/name expectations are real lookup references. Season metadata and this
    # HTTP payload are entirely synthetic, never fetched or saved as real data.
    return {"league": {"id": 140, "name": "La Liga", "type": "League"},
            "country": {"name": "Spain"},
            "seasons": [{"year": 2030, "start": "2030-08-01", "end": "2031-05-31", "current": False},
                        {"year": 2032, "start": "2032-08-01", "end": "2033-05-31", "current": None}]}


def envelope(records):
    return {"errors": {}, "results": len(records), "response": records,
            "paging": {"current": 1, "total": 1}}


class CompetitionPreviewTests(unittest.TestCase):
    def setUp(self):
        for guard in (
            patch("urllib.request.OpenerDirector.open", side_effect=AssertionError("Network forbidden")),
            patch("api_football_players.read_api_key", side_effect=AssertionError("Real credentials forbidden")),
            patch.object(preview, "read_api_key", return_value=TEST_KEY),
            # Existing synthetic 2030-2033 seasons are historical at this fixed
            # test date. Dedicated tests below assess actual future-date logic.
            patch.object(preview, "utc_today", return_value=date(2035, 1, 1)),
        ):
            guard.start()
            self.addCleanup(guard.stop)

    def run_preview(self, data=None, argv=None, error=None, raw=None, headers=None):
        response = io.BytesIO(raw if raw is not None else json.dumps(data).encode("utf-8"))
        response.status, response.headers = 200, headers or {}
        opener = Mock()
        if error is None:
            opener.open.return_value = response
        else:
            opener.open.side_effect = error
        output = io.StringIO()
        with patch.object(preview, "build_opener", return_value=opener) as factory:
            with redirect_stdout(output):
                code = preview.main(["--competition-id", "140"] if argv is None else argv)
        self.assertNotIn(TEST_KEY, output.getvalue())
        self.assertIn(preview.PREVIEW_MESSAGE, output.getvalue())
        return code, output.getvalue(), opener, factory

    def test_one_get_checks_identity_and_keeps_season_boundaries_separate(self):
        data = envelope([fictional_record()])
        original = copy.deepcopy(data)
        code, output, opener, factory = self.run_preview(data)
        self.assertEqual(code, 0)
        self.assertEqual(data, original)
        self.assertIn("Identity: VERIFIED", output)
        self.assertIn('Name: "La Liga"', output)
        self.assertIn("2030 | 2030-08-01 | 2031-05-31 | false", output)
        self.assertIn("2032 | 2032-08-01 | 2033-05-31 | null", output)
        self.assertIn("No internal competition ID assigned", output)
        self.assertIn("No mapping created or saved", output)
        factory.assert_called_once()
        self.assertIsInstance(factory.call_args.args[0], preview.NoRedirects)
        opener.open.assert_called_once()
        request = opener.open.call_args.args[0]
        url = urlparse(request.full_url)
        self.assertEqual((url.scheme, url.netloc, url.path),
                         ("https", "v3.football.api-sports.io", "/leagues"))
        self.assertEqual(parse_qs(url.query), {"id": ["140"]})
        self.assertEqual(request.get_method(), "GET")
        self.assertEqual(request.get_header("X-apisports-key"), TEST_KEY)
        self.assertEqual(opener.open.call_args.kwargs, {"timeout": 20})

    def test_minor_formatting_variations_are_accepted(self):
        for name in ("LaLiga", "LA LIGA", "La-Liga", "La Líga"):
            record = fictional_record()
            record["league"]["name"] = name
            with self.subTest(name=name):
                code, output, opener, _ = self.run_preview(envelope([record]))
                self.assertEqual(code, 0)
                self.assertIn("Identity: VERIFIED", output)
                opener.open.assert_called_once()

    def test_other_divisions_categories_and_unreviewed_aliases_are_rejected(self):
        for name in ("La Liga 2", "La Liga Women", "La Liga U19", "LaLiga Hypermotion", "LaLiga EA Sports"):
            record = fictional_record()
            record["league"]["name"] = name
            code, output, opener, _ = self.run_preview(envelope([record]))
            self.assertEqual(code, 1)
            self.assertIn("Identity: REVIEW REQUIRED", output)
            self.assertIn("differs beyond minor formatting", output)
            self.assertNotIn("Identity: VERIFIED", output)
            opener.open.assert_called_once()

    def test_wrong_or_missing_identity_fields_require_review(self):
        for parent, field, value in (("league", "id", "140"), ("league", "id", 141),
                                      ("league", "id", True), ("league", "id", None),
                                      ("league", "name", None), ("league", "type", "Cup"),
                                      ("league", "type", []), ("country", "name", "England"),
                                      ("country", "name", None)):
            record = fictional_record()
            record[parent][field] = value
            with self.subTest(parent=parent, field=field, value=value):
                code, output, _, _ = self.run_preview(envelope([record]))
                self.assertEqual(code, 1)
                self.assertIn("Identity: REVIEW REQUIRED", output)
        code, output, _, _ = self.run_preview(envelope([None]))
        self.assertEqual(code, 1)
        self.assertIn("Identity: REVIEW REQUIRED", output)

    def test_empty_multiple_and_incomplete_results_are_not_selected(self):
        for records in ([], [fictional_record(), fictional_record()]):
            code, output, opener, _ = self.run_preview(envelope(records))
            self.assertEqual(code, 1)
            self.assertIn("Expected exactly one competition", output)
            self.assertNotIn("Identity: VERIFIED", output)
            opener.open.assert_called_once()
        data = envelope([fictional_record()])
        data["paging"]["total"] = 2
        code, output, opener, _ = self.run_preview(data)
        self.assertEqual(code, 1)
        self.assertIn("Identity: REVIEW REQUIRED", output)
        self.assertIn("Pagination metadata", output)
        opener.open.assert_called_once()

    def test_unavailable_seasons_do_not_invalidate_competition_identity(self):
        for seasons in (None, []):
            record = fictional_record()
            record["seasons"] = seasons
            code, output, _, _ = self.run_preview(envelope([record]))
            self.assertEqual(code, 1)  # Identity still passes; unavailable metadata needs review.
            self.assertIn("Identity: VERIFIED", output)
            self.assertIn("Season information unavailable", output)
            self.assertIn("Season REVIEW REQUIRED: Season metadata is unavailable", output)

    def test_invalid_season_metadata_is_reported_without_guessing(self):
        for changes in ({"year": None}, {"year": True}, {"start": "2030-02-30"},
                        {"start": "2031-08-01"}, {"end": "2029-01-01"}, {"current": "false"}):
            record = fictional_record()
            record["seasons"][0].update(changes)
            with self.subTest(changes=changes):
                code, output, _, _ = self.run_preview(envelope([record]))
                self.assertEqual(code, 1)
                self.assertIn("Identity: VERIFIED", output)  # Identity is a separate check.
                self.assertIn("Season REVIEW REQUIRED:", output)
        for seasons in ({}, [None], [fictional_record()["seasons"][0]] * 2):
            record = fictional_record()
            record["seasons"] = seasons
            code, output, _, _ = self.run_preview(envelope([record]))
            self.assertEqual(code, 1)
            self.assertIn("Season REVIEW REQUIRED:", output)

    def test_http_failures_and_redirects_are_filtered_and_not_retried(self):
        for status in (302, 401, 403, 404, 429, 503):
            body = {"errors": {"plan": "Access denied " + TEST_KEY, "api_key": "RAW_PRIVATE_MARKER"},
                    "account": "RAW_ACCOUNT_MARKER"}
            error = HTTPError("https://invalid.example", status, "RAW_HTTP_MARKER", {},
                              io.BytesIO(json.dumps(body).encode("utf-8")))
            code, output, opener, _ = self.run_preview(error=error)
            self.assertEqual(code, 1)
            self.assertIn(f"HTTP status: {status}", output)
            self.assertIn("ERROR:", output)
            for marker in ("RAW_PRIVATE_MARKER", "RAW_ACCOUNT_MARKER", "RAW_HTTP_MARKER"):
                self.assertNotIn(marker, output)
            opener.open.assert_called_once()

    def test_api_errors_dictionary_and_list_and_zero_quota_header(self):
        for errors in ({"plan": "Free subscription restriction " + TEST_KEY},
                       ["Requests quota limit reached " + TEST_KEY]):
            data = envelope([])
            data["errors"] = errors
            code, output, opener, _ = self.run_preview(data)
            self.assertEqual(code, 1)
            self.assertIn("Provider errors (filtered", output)
            self.assertIn("ERROR:", output)
            opener.open.assert_called_once()
        code, output, opener, _ = self.run_preview(envelope([fictional_record()]),
                                                  headers={"x-ratelimit-requests-remaining": "0"})
        self.assertEqual(code, 0)
        self.assertIn("quota exhausted", output)
        opener.open.assert_called_once()

    def test_invalid_json_envelopes_and_connection_failures_are_safe(self):
        code, output, opener, _ = self.run_preview(raw=b"not JSON")
        self.assertEqual(code, 1)
        self.assertIn("invalid JSON", output)
        opener.open.assert_called_once()
        for data in ([], {"errors": None}, dict(envelope([]), results=1)):
            code, output, opener, _ = self.run_preview(data)
            self.assertEqual(code, 1)
            self.assertIn("ERROR:", output)
            opener.open.assert_called_once()
        for error in (URLError("RAW_CONNECTION_MARKER"), TimeoutError("RAW_CONNECTION_MARKER")):
            code, output, opener, _ = self.run_preview(error=error)
            self.assertEqual(code, 1)
            self.assertIn("connection failed or timed out", output)
            self.assertNotIn("RAW_CONNECTION_MARKER", output)
            opener.open.assert_called_once()

    def test_credentials_missing_means_no_request(self):
        with patch.object(preview, "read_api_key", return_value=None):
            code, output, opener, _ = self.run_preview(envelope([]))
        self.assertEqual(code, 1)
        self.assertIn("credentials are unavailable", output)
        self.assertIn("API requests attempted: 0/1", output)
        opener.open.assert_not_called()

    def test_future_competition_can_only_be_checked_individually_with_expectations(self):
        record = fictional_record()
        record["league"].update(id=900001, name="Fictional Test League")
        record["country"]["name"] = "Fictional Country"
        argv = ["--competition-id", "900001", "--expected-name", "Fictional Test League",
                "--expected-country", "Fictional Country", "--expected-type", "League"]
        code, output, opener, _ = self.run_preview(envelope([record]), argv=argv)
        self.assertEqual(code, 0)
        self.assertIn("Identity: VERIFIED", output)
        opener.open.assert_called_once()
        self.assertEqual(parse_qs(urlparse(opener.open.call_args.args[0].full_url).query), {"id": ["900001"]})
        for argv in (["--competition-id", "900001"], ["--competition-id", "0"],
                     ["--competition-id", "140,143"], ["--competition-id", "140", "143"]):
            with patch.object(preview, "read_api_key") as key_reader, patch.object(preview, "build_opener") as factory:
                with redirect_stderr(io.StringIO()), self.assertRaises(SystemExit) as error:
                    preview.main(argv)
                self.assertEqual(error.exception.code, 2)
                key_reader.assert_not_called()
                factory.assert_not_called()

    def test_credentials_and_unmanaged_response_fields_are_not_displayed(self):
        record = fictional_record()
        record["league"].update(name=TEST_KEY, logo="https://invalid.example/RAW_LOGO_MARKER")
        record["seasons"][0]["coverage"] = {"private": "RAW_COVERAGE_MARKER"}
        data = envelope([record])
        data["account"] = "RAW_ACCOUNT_MARKER"
        code, output, _, _ = self.run_preview(data)
        self.assertEqual(code, 1)
        self.assertIn("redacted", output)
        for marker in ("RAW_LOGO_MARKER", "RAW_COVERAGE_MARKER", "RAW_ACCOUNT_MARKER"):
            self.assertNotIn(marker, output)
        # Even an accidental credential in a CLI expectation must stay hidden.
        code, output, _, _ = self.run_preview(data, argv=["--expected-name", TEST_KEY])
        self.assertEqual(code, 1)
        self.assertNotIn(TEST_KEY, output)

    def test_inspection_leaves_country_and_type_unconfirmed_with_one_request(self):
        record = fictional_record()
        record["league"].update(id=667, name="Friendlies Clubs", type="Fictional category")
        record["country"]["name"] = "Fictional scope"
        argv = ["--competition-id", "667", "--expected-name", "Friendlies Clubs", "--inspect"]
        expected = preview.parse_arguments(argv)
        self.assertEqual(expected, {"id": 667, "name": "Friendlies Clubs", "country": None, "type": None})
        code, output, opener, _ = self.run_preview(envelope([record]), argv=argv)
        self.assertEqual(code, 1)
        self.assertIn("Identity: REVIEW REQUIRED", output)
        self.assertNotIn("Identity: VERIFIED", output)
        self.assertIn('Country: "Fictional scope"', output)
        self.assertIn('Provider type: "Fictional category"', output)
        self.assertIn("Country requires independent confirmation", output)
        self.assertIn("Competition type requires independent confirmation", output)
        self.assertIn("2030 | 2030-08-01 | 2031-05-31", output)
        self.assertEqual(preview.parse_arguments(argv), expected)  # Provider values did not become expectations.
        opener.open.assert_called_once()
        request = opener.open.call_args.args[0]
        self.assertEqual(parse_qs(urlparse(request.full_url).query), {"id": ["667"]})

    def test_inspection_still_checks_known_id_and_name(self):
        argv = ["--competition-id", "667", "--expected-name", "Friendlies Clubs", "--inspect"]
        for returned_id, name in ((667, "Different fictional competition"), (900001, "Friendlies Clubs")):
            record = fictional_record()
            record["league"].update(id=returned_id, name=name)
            code, output, opener, _ = self.run_preview(envelope([record]), argv=argv)
            self.assertEqual(code, 1)
            self.assertIn("Identity: REVIEW REQUIRED", output)
            self.assertIn("differs beyond minor formatting" if returned_id == 667 else "differs from the requested provider ID", output)
            opener.open.assert_called_once()

    def test_inspection_only_verifies_when_all_expectations_are_supplied(self):
        # Synthetic metadata exercises explicit confirmation, not actual facts
        # about competition 667. No country/type assumptions become presets.
        record = fictional_record()
        record["league"].update(id=667, name="Friendlies Clubs")
        record["country"]["name"] = "Fictional scope"
        base = ["--competition-id", "667", "--expected-name", "Friendlies Clubs", "--inspect"]
        for supplied in (["--expected-country", "Fictional scope"], ["--expected-type", "League"]):
            code, output, _, _ = self.run_preview(envelope([record]), argv=base + supplied)
            self.assertEqual(code, 1)
            self.assertIn("Identity: REVIEW REQUIRED", output)
        code, output, _, _ = self.run_preview(envelope([record]), argv=base + [
            "--expected-country", "Fictional scope", "--expected-type", "League"])
        self.assertEqual(code, 0)
        self.assertIn("Identity: VERIFIED", output)
        # Inspection of the default ID must not fill unknowns from the La Liga preset either.
        expected = preview.parse_arguments(["--inspect"])
        self.assertEqual(expected["name"], "La Liga")
        self.assertIsNone(expected["country"])
        self.assertIsNone(expected["type"])

    def test_existing_copa_del_rey_command_remains_supported(self):
        record = fictional_record()
        record["league"].update(id=143, name="Copa del Rey", type="Cup")
        argv = ["--competition-id", "143", "--expected-name", "Copa del Rey",
                "--expected-country", "Spain", "--expected-type", "Cup"]
        code, output, opener, _ = self.run_preview(envelope([record]), argv=argv)
        self.assertEqual(code, 0)
        self.assertIn("Identity: VERIFIED", output)
        opener.open.assert_called_once()

    def test_unknown_competition_can_be_inspected_with_only_its_id(self):
        # No assumptions about the actual identity of 556: this payload is fictional.
        record = fictional_record()
        record["league"].update(id=556, name="Fictional unreviewed competition", type="Fictional category")
        record["country"]["name"] = "Fictional scope"
        argv = ["--competition-id", "556", "--inspect"]
        expected = {"id": 556, "name": None, "country": None, "type": None}
        self.assertEqual(preview.parse_arguments(argv), expected)
        code, output, opener, _ = self.run_preview(envelope([record]), argv=argv)
        self.assertEqual(code, 1)
        self.assertIn("Identity: REVIEW REQUIRED", output)
        self.assertNotIn("Identity: VERIFIED", output)
        for field in ("Name", "Country", "Competition type"):
            self.assertIn(f"{field} requires independent confirmation", output)
        self.assertIn('Name: "Fictional unreviewed competition"', output)
        self.assertIn('Country: "Fictional scope"', output)
        self.assertIn('Provider type: "Fictional category"', output)
        self.assertIn("2030 | 2030-08-01 | 2031-05-31", output)
        self.assertEqual(preview.parse_arguments(argv), expected)
        opener.open.assert_called_once()
        request = opener.open.call_args.args[0]
        self.assertEqual(urlparse(request.full_url).path, "/leagues")
        self.assertEqual(parse_qs(urlparse(request.full_url).query), {"id": ["556"]})

    def test_unknown_name_requires_review_even_if_other_expectations_are_supplied(self):
        record = fictional_record()
        record["league"].update(id=556, name="Fictional unreviewed competition")
        record["country"]["name"] = "Fictional scope"
        argv = ["--competition-id", "556", "--expected-country", "Fictional scope", "--expected-type", "League"]
        code, output, opener, _ = self.run_preview(envelope([record]), argv=argv + ["--inspect"])
        self.assertEqual(code, 1)
        self.assertIn("Name requires independent confirmation", output)
        self.assertNotIn("Identity: VERIFIED", output)
        opener.open.assert_called_once()
        with patch.object(preview, "read_api_key") as key_reader, patch.object(preview, "build_opener") as factory:
            with redirect_stderr(io.StringIO()), self.assertRaises(SystemExit) as error:
                preview.main(argv)  # Normal verification still requires a name.
            self.assertEqual(error.exception.code, 2)
            key_reader.assert_not_called()
            factory.assert_not_called()

    def test_id_only_inspection_handles_mismatches_empty_results_and_api_errors(self):
        argv = ["--competition-id", "556", "--inspect"]
        record = fictional_record()
        record["league"]["id"] = 900001
        data = envelope([])
        data["errors"] = ["Requests quota limit reached " + TEST_KEY]
        for payload, message in ((envelope([record]), "differs from the requested provider ID"),
                                 (envelope([]), "Expected exactly one competition"),
                                 (data, "ERROR: Provider reported exhausted quota")):
            code, output, opener, _ = self.run_preview(payload, argv=argv)
            self.assertEqual(code, 1)
            self.assertIn(message, output)
            self.assertNotIn("Identity: VERIFIED", output)
            opener.open.assert_called_once()

    def test_all_four_identity_checks_allow_following_calendar_year_seasons(self):
        # Identity expectations come from the project; this season payload is fictional.
        identities = ((140, "La Liga", "Spain", "League"), (143, "Copa del Rey", "Spain", "Cup"),
                      (667, "Friendlies Clubs", "World", "Cup"), (556, "Super Cup", "Spain", "Cup"))
        for provider_id, name, country, kind in identities:
            record = fictional_record()
            record["league"].update(id=provider_id, name=name, type=kind)
            record["country"]["name"] = country
            record["seasons"] = [{"year": 2024, "start": "2025-01-05", "end": "2025-01-09", "current": False}]
            argv = ["--competition-id", str(provider_id), "--expected-name", name,
                    "--expected-country", country, "--expected-type", kind]
            with self.subTest(provider_id=provider_id):
                code, output, opener, _ = self.run_preview(envelope([record]), argv=argv)
                self.assertEqual(code, 0)
                self.assertIn("Identity: VERIFIED", output)
                self.assertNotIn("Season REVIEW REQUIRED:", output)
                self.assertIn("2024 | 2025-01-05 | 2025-01-09", output)
                opener.open.assert_called_once()

    def test_future_season_schedule_does_not_reverse_verified_identity(self):
        record = fictional_record()
        record["league"].update(id=556, name="Super Cup", type="Cup")
        # Representative synthetic February dates, not captured provider data.
        record["seasons"] = [{"year": 2026, "start": "2027-02-10", "end": "2027-02-14", "current": False}]
        original = copy.deepcopy(record)
        argv = ["--competition-id", "556", "--expected-name", "Super Cup",
                "--expected-country", "Spain", "--expected-type", "Cup"]
        with patch.object(preview, "utc_today", return_value=date(2026, 11, 15)):
            code, output, opener, _ = self.run_preview(envelope([record]), argv=argv)
        self.assertEqual(code, 1)
        self.assertEqual(record, original)
        self.assertIn("Identity: VERIFIED", output)
        self.assertIn("Season REVIEW REQUIRED: Season row 1: future boundary dates", output)
        self.assertIn("unconfirmed provider schedule, not independently verified events", output)
        self.assertNotIn("start date disagrees", output)
        opener.open.assert_called_once()


class SeasonMetadataTests(unittest.TestCase):
    """Pure date checks: all season records are fictional and stay in memory."""

    def inspect(self, seasons, today=date(2026, 11, 15)):
        record = {"seasons": copy.deepcopy(seasons)}
        original = copy.deepcopy(record)
        output = io.StringIO()
        with redirect_stdout(output):
            issues = preview.display_seasons(record, today=today)
        self.assertEqual(record, original)
        return issues, output.getvalue()

    def test_provider_season_identifiers_allow_the_following_calendar_year(self):
        for identifier, calendar_year in ((2019, 2020), (2024, 2025), (2025, 2026)):
            with self.subTest(identifier=identifier):
                start, end = f"{calendar_year}-01-05", f"{calendar_year}-01-09"
                issues, output = self.inspect([{"year": identifier, "start": start, "end": end, "current": False}])
                self.assertEqual(issues, [])
                self.assertIn(f"{identifier} | {start} | {end}", output)

    def test_same_year_cross_year_and_leap_dates_remain_valid(self):
        for start, end in (("2024-02-29", "2024-03-02"), ("2024-08-01", "2025-05-31"),
                           ("2025-01-05", "2025-01-09")):
            issues, _ = self.inspect([{"year": 2024, "start": start, "end": end, "current": False}])
            self.assertEqual(issues, [])

    def test_future_boundaries_are_unconfirmed_schedules_without_changing_data(self):
        for start, end in (("2027-02-10", "2027-02-14"), ("2026-08-01", "2027-05-31")):
            seasons = [{"year": 2026, "start": start, "end": end, "current": False}]
            issues, _ = self.inspect(seasons)
            self.assertEqual(len(issues), 1)
            self.assertIn("future boundary dates", issues[0])
            self.assertIn("unconfirmed provider schedule", issues[0])
            # A later as-of date changes the schedule review, not the input data.
            issues, output = self.inspect(seasons, today=date(2028, 1, 1))
            self.assertEqual(issues, [])
            self.assertIn("Date checks do not independently verify events", output)
        issues, _ = self.inspect([{"year": 2026, "start": "2026-11-15", "end": "2026-11-15"}])
        self.assertEqual(issues, [])  # Today is not a future date.

    def test_missing_and_null_dates_stay_unknown_with_specific_review_reasons(self):
        for season in ({"year": 2024}, {"year": 2024, "start": None, "end": None},
                       {"year": 2024, "start": "2025-01-05"}, {"year": 2024, "end": "2025-01-09"}):
            issues, output = self.inspect([season])
            self.assertTrue(any("date is unavailable" in issue for issue in issues))
            self.assertIn("null", output)
            self.assertNotIn("<invalid>", output)  # Unknown is not a fabricated/invalid date.
        for seasons in (None, []):
            issues, output = self.inspect(seasons)
            self.assertIn("Season metadata is unavailable", issues[0])
            self.assertIn("no years or dates were invented", output)

    def test_invalid_formats_chronology_identifiers_and_duplicates_still_require_review(self):
        season = {"year": 2024, "start": "2025-01-05", "end": "2025-01-09", "current": False}
        for changes, reason in (({"start": "2025-02-30"}, "invalid calendar date"),
                                ({"start": "2025-1-05"}, "YYYY-MM-DD"),
                                ({"start": True}, "YYYY-MM-DD"),
                                ({"end": "2025-01-04"}, "end date precedes start date"),
                                ({"year": "2024"}, "provider year is missing/invalid"),
                                ({"current": "false"}, "current flag must be boolean")):
            issues, _ = self.inspect([dict(season, **changes)])
            self.assertTrue(any(reason in issue for issue in issues), issues)
        issues, _ = self.inspect([season, season])
        self.assertTrue(any("duplicate provider year" in issue for issue in issues))

    def test_unusually_long_date_ranges_require_competition_specific_review(self):
        issues, _ = self.inspect([{"year": 2019, "start": "2020-01-01", "end": "2023-01-01"}])
        self.assertEqual(len(issues), 1)
        self.assertIn("competition-specific review is needed, not automatic rejection", issues[0])
        issues, _ = self.inspect([{"year": 2019, "start": "2020-01-01", "end": "2022-01-01"}])
        self.assertEqual(issues, [])  # Two calendar years including a leap day.


if __name__ == "__main__":
    unittest.main(verbosity=2)
