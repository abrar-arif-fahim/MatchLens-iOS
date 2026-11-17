"""Verify one provider competition in memory. No mappings, files or Firebase writes."""

import argparse
import json
import re
import unicodedata
from datetime import datetime, timezone
from http.client import HTTPException
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, build_opener

from api_football_players import read_api_key
from preview_api_football_matches import display_provider_errors
from preview_api_football_team_ids import MappingError, NoRedirects, public_text
from validate_competition_schema import parse_date
from validate_match_schema import ValidationError


PREVIEW_MESSAGE = "PREVIEW ONLY - No provider data or mappings saved. No Firebase changes."
# These are expectations supplied for comparison, not a verified internal mapping.
LA_LIGA_EXPECTATIONS = {"id": 140, "name": "La Liga", "country": "Spain", "type": "League"}
# A conservative review heuristic, not a universal football competition rule.
MAX_SEASON_SPAN_DAYS = 2 * 366


def normalize_name(value):
    # Preserve all letters/numbers. Never strip women's/youth/division qualifiers
    # or accept a partial/fuzzy match merely because a name contains 'La Liga'.
    text = unicodedata.normalize("NFKD", value.casefold())
    return "".join(character for character in text if character.isalnum())


def safe_text(value, api_key):
    text = public_text(value)
    if text is None or (api_key and api_key in text):
        return None
    return text


def fetch_competition(provider_id, api_key):
    request = Request(
        "https://v3.football.api-sports.io/leagues?" + urlencode({"id": provider_id}),
        headers={"x-apisports-key": api_key,
                 "User-Agent": "MatchLensUniversityProject/1.0 (competition identity preview)"},
    )
    http_status = None
    try:
        # NoRedirects prevents another request and forwarding the secret header.
        with build_opener(NoRedirects()).open(request, timeout=20) as response:
            http_status = getattr(response, "status", None)
            print(f"HTTP status: {http_status if type(http_status) is int else 'unavailable'}")
            data = json.load(response)
            display_provider_errors(data, api_key)  # Existing filtered error display.
            for header in ("x-ratelimit-requests-remaining", "x-ratelimit-remaining"):
                if response.headers.get(header, "").strip() == "0":
                    print("Notice: Provider quota exhausted; this response can still be inspected. No retry will be made.")
    except HTTPError as error:
        print(f"HTTP status: {error.code}")
        try:
            display_provider_errors(json.load(error), api_key)
        except (ValueError, TypeError, OSError, HTTPException, RecursionError):
            print("Provider errors: unavailable (error body was not readable JSON).")
        finally:
            error.close()
        messages = {
            401: "Authentication failed. Check the existing API-Football key.",
            403: "Access denied. Review subscription, historical-season access, quota and IP restrictions.",
            404: "The leagues endpoint is unavailable for this request.",
            429: "Quota/rate limit reached. Check the dashboard before trying again manually.",
        }
        raise MappingError(messages.get(error.code, f"API-Football HTTP {error.code}; no retry was issued.")) from None
    except (URLError, OSError, HTTPException):
        if http_status is None:
            print("HTTP status: unavailable (no HTTP response received).")
        raise MappingError("API-Football connection failed or timed out. No retry was issued.") from None
    except (ValueError, UnicodeError, RecursionError):
        raise MappingError("API-Football returned invalid JSON.") from None
    return data


def read_records(data):
    if not isinstance(data, dict) or not isinstance(data.get("errors"), (dict, list)):
        raise MappingError("API-Football returned an unexpected response format.")
    if data["errors"]:
        error_text = json.dumps(data["errors"]).casefold()  # Inspect, never print raw errors.
        if any(word in error_text for word in ("quota", "limit", "requests")):
            raise MappingError("Provider reported exhausted quota or a rate limit. No retry was issued.")
        if any(word in error_text for word in ("plan", "subscription", "access", "free")):
            raise MappingError("Provider subscription/access restriction. Review leagues endpoint permissions.")
        raise MappingError("Provider reported an API error. Review the filtered message and existing configuration.")
    records = data.get("response")
    if (not isinstance(records, list) or type(data.get("results")) is not int
            or data["results"] != len(records)):
        raise MappingError("Provider competition results/counts are invalid.")
    paging = data.get("paging")
    complete = (isinstance(paging, dict) and type(paging.get("current")) is int
                and paging["current"] == 1 and type(paging.get("total")) is int and paging["total"] == 1)
    return records, complete


def inspect_identity(record, expected, api_key):
    league = record.get("league") if isinstance(record, dict) else None
    country = record.get("country") if isinstance(record, dict) else None
    league = league if isinstance(league, dict) else {}
    country = country if isinstance(country, dict) else {}
    provider_id = league.get("id")
    name = safe_text(league.get("name"), api_key)
    country_name = safe_text(country.get("name"), api_key)
    kind = safe_text(league.get("type"), api_key)
    valid_id = type(provider_id) is int and provider_id > 0
    print("\nCompetition identity (source: API-Football):")
    print(f"  Provider competition ID: {provider_id if valid_id else '<invalid>'}")
    for label, value in (("Name", name), ("Country", country_name), ("Provider type", kind)):
        print(f"  {label}: {json.dumps(value, ensure_ascii=True) if value is not None else '<missing/invalid/redacted>'}")
    issues = []
    if not valid_id or provider_id != expected["id"]:
        issues.append("Returned league.id is missing, invalid or differs from the requested provider ID.")
    if expected["name"] is None:
        issues.append("Name requires independent confirmation; the returned provider value has not been accepted.")
    elif not name or normalize_name(name) != normalize_name(expected["name"]):
        issues.append("Name is missing or differs beyond minor formatting; no alias or sponsor name was guessed.")
    if expected["country"] is None:
        issues.append("Country requires independent confirmation; the returned provider value has not been accepted.")
    elif not country_name or country_name.casefold() != expected["country"].casefold():
        issues.append("Country is missing or does not match the expected country.")
    if expected["type"] is None:
        issues.append("Competition type requires independent confirmation; the returned provider value has not been accepted.")
    elif not kind or kind.casefold() != expected["type"].casefold():
        issues.append("Competition type is missing or does not match the expected provider type.")
    return issues


def utc_today():
    return datetime.now(timezone.utc).date()


def display_seasons(record, today=None):
    # An injectable date keeps offline tests deterministic. Manual runs use UTC.
    today = utc_today() if today is None else today
    print("\nSeasons (provider metadata, separate from competition identity):")
    print("Provider year is a season identifier; it does not require matching calendar years.")
    print("Date checks do not independently verify events. Future dates are unconfirmed provider schedules.")
    seasons = record.get("seasons") if isinstance(record, dict) else None
    if seasons is None or seasons == []:
        print("Season information unavailable; no years or dates were invented.")
        return ["Season metadata is unavailable; no season date range can be assessed."]
    if not isinstance(seasons, list):
        return ["The seasons field must be an array or null."]
    print("Provider year | Start date | End date | Current")
    issues, seen_years = [], set()
    for index, season in enumerate(seasons, start=1):
        if not isinstance(season, dict):
            issues.append(f"Season row {index} is not an object.")
            continue
        year = season.get("year")
        valid_year = type(year) is int and 1000 <= year <= 9999
        if not valid_year:
            issues.append(f"Season row {index}: provider year is missing/invalid; it was not inferred from dates.")
        elif year in seen_years:
            issues.append(f"Season row {index}: duplicate provider year requires edition review.")
        if valid_year:
            seen_years.add(year)
        dates, displayed_dates = [], []
        for field in ("start", "end"):
            try:
                value = parse_date(season.get(field), f"Season {field}")
                displayed_dates.append(value.isoformat() if value is not None else "null")
                if value is None:
                    issues.append(f"Season row {index}: {field} date is unavailable; the date range cannot be fully assessed.")
            except ValidationError as error:
                issues.append(f"Season row {index}: {error}")
                value = None
                displayed_dates.append("<invalid>")
            dates.append(value)
        if all(value is not None for value in dates) and dates[1] < dates[0]:
            issues.append(f"Season row {index}: end date precedes start date.")
        elif all(value is not None for value in dates) and (dates[1] - dates[0]).days > MAX_SEASON_SPAN_DAYS:
            issues.append(f"Season row {index}: date range exceeds {MAX_SEASON_SPAN_DAYS} days; competition-specific review is needed, not automatic rejection.")
        if any(value is not None and value > today for value in dates):
            issues.append(f"Season row {index}: future boundary dates are an unconfirmed provider schedule, not independently verified events.")
        current = season.get("current")
        if current is not None and type(current) is not bool:
            issues.append(f"Season row {index}: current flag must be boolean or null.")
        current_text = "null" if current is None else str(current).lower() if type(current) is bool else "<invalid>"
        print(f"{year if valid_year else '<missing/invalid>'} | {displayed_dates[0]} | {displayed_dates[1]} | {current_text}")
    return issues


def positive_id(value):
    if not re.fullmatch(r"[1-9][0-9]{0,8}", value):
        raise argparse.ArgumentTypeError("Competition ID must be a positive integer of at most nine digits.")
    return int(value)


def parse_arguments(argv):
    parser = argparse.ArgumentParser(description=__doc__, allow_abbrev=False)
    parser.add_argument("--competition-id", type=positive_id, default=140, help="One provider ID only; defaults to 140.")
    parser.add_argument("--expected-name", help="Required for IDs other than 140 unless inspecting.")
    parser.add_argument("--expected-country", help="Required for IDs other than 140 unless inspecting.")
    parser.add_argument("--expected-type", choices=("League", "Cup"), help="Provider category, not our internal competitionType.")
    parser.add_argument("--inspect", action="store_true",
                        help="Allow unknown expected name/country/type; unconfirmed fields keep the result under review.")
    args = parser.parse_args(argv)
    defaults = LA_LIGA_EXPECTATIONS if args.competition_id == 140 else {}
    expected = {"id": args.competition_id, "name": args.expected_name, "country": args.expected_country,
                "type": args.expected_type}
    for field in ("name", "country", "type"):
        # Preserve the known La Liga name default. Other missing inspection
        # expectations stay unknown; returned provider values never fill them.
        if expected[field] is None and (not args.inspect or field == "name"):
            expected[field] = defaults.get(field)
        if args.inspect and expected[field] is None:
            continue
        if public_text(expected[field]) != expected[field] or not expected[field]:
            parser.error("Supply nonempty public expected name, country and type for the single requested competition.")
    if expected["name"] is not None and not normalize_name(expected["name"]):
        parser.error("Expected name must contain letters or numbers.")
    return expected


def main(argv=None):
    expected = parse_arguments(argv)
    requests_used = 0
    try:
        api_key = read_api_key()
        if not api_key:
            print("ERROR: Existing .env API-Football credentials are unavailable.")
            return 1
        print("GET /leagues?" + urlencode({"id": expected["id"]}))
        displayed_expected = {field: value if field == "id" else safe_text(value, api_key)
                              for field, value in expected.items()}
        print("Expected identity: " + json.dumps(displayed_expected, ensure_ascii=True))
        if any(expected[field] is None for field in ("name", "country", "type")):
            print("INSPECTION: Null expectations are unconfirmed. Returned name/country/type values will not fill them automatically.")
        requests_used = 1
        records, complete = read_records(fetch_competition(expected["id"], api_key))
        print(f"Competition records returned: {len(records)}")
        if len(records) != 1:
            print("REVIEW REQUIRED: Expected exactly one competition; no candidate was selected.")
            return 1
        issues = inspect_identity(records[0], expected, api_key)
        if not complete:
            issues.append("Pagination metadata is incomplete or indicates more pages; no additional request was made.")
        print("\nIdentity: " + ("REVIEW REQUIRED" if issues else "VERIFIED"))
        if not issues:
            print("Requested provider ID, name, country and type match the expected competition.")
        for issue in issues:
            print(f"  - {issue}")
        season_issues = display_seasons(records[0])
        for issue in season_issues:
            print(f"Season REVIEW REQUIRED: {issue}")
        return 1 if issues or season_issues else 0
    except MappingError as error:
        print(f"ERROR: {error}")  # Our messages only; never raw exception/response text.
    except (OSError, ValueError, TypeError, KeyError, AttributeError, OverflowError):
        print("ERROR: Invalid configuration or unexpected provider data. Raw details hidden; no retry was made.")
    except KeyboardInterrupt:
        print("\nERROR: Preview interrupted; no verification result is claimed.")
    finally:
        print(f"\nAPI requests attempted: {requests_used}/1. No retries, redirects, extra endpoints or pages.")
        print("No internal competition ID assigned. No mapping created or saved.")
        print("Identity verification does not grant data storage or redistribution rights.")
        print(PREVIEW_MESSAGE)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
