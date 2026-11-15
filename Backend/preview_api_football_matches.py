"""Inspect up to three real head-to-head fixtures in memory; never import/save."""

import argparse
import json
import math
import re
from datetime import datetime, timezone
from http.client import HTTPException
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, build_opener

# These existing modules have main guards; importing them makes no live requests.
from api_football_players import read_api_key
from prepare_multiple_teams import load_verified_teams
from preview_api_football_team_ids import MappingError, NoRedirects, public_text
from validate_match_schema import ValidationError, validate_kickoff, validate_scores, validate_score_details


# Supplied and confirmed by the project team in Step 28F.5.4. Separate ID systems.
TEAM_IDS = {529: "Q7156", 541: "Q8682"}
MAX_MATCHES = 3
MISSING = object()
STATUS_MAP = {
    "NS": "scheduled", "1H": "live", "HT": "live", "2H": "live",
    "ET": "live", "BT": "live", "P": "live", "LIVE": "live",
    "FT": "finished", "AET": "finished", "PEN": "finished",
    "PST": "postponed", "CANC": "cancelled",
}
PREVIEW_MESSAGE = "PREVIEW ONLY - No response data saved. No Firebase changes."


def display_value(value):
    if value is MISSING:
        return "<missing>"
    if value is None:
        return "null"
    if isinstance(value, str):
        text = public_text(value)
        return json.dumps(text, ensure_ascii=False) if text is not None else "<invalid/redacted text>"
    if type(value) in (int, float, bool):
        if type(value) is float and not math.isfinite(value):
            return "<invalid number>"
        return json.dumps(value)
    return "<unexpected value hidden>"


def load_team_mapping():
    # Use existing local club identities. Do not reconnect to Firebase/Wikidata.
    references = {team["wikidataId"]: team for team in load_verified_teams()}
    mapping = {}
    for api_id, wikidata_id in TEAM_IDS.items():
        reference = references.get(wikidata_id)
        if reference is None or public_text(reference["expectedName"]) is None:
            raise ValidationError("An expected local Wikidata club reference is missing or invalid.")
        mapping[api_id] = {
            "teamId": f"wikidata_{wikidata_id}", "name": reference["expectedName"],
        }
    return mapping


def head_to_head_query(season=None):
    parameters = {"h2h": "529-541"}
    if season is None:
        parameters["last"] = MAX_MATCHES
    else:
        parameters["season"] = season  # Do not also send the restricted last filter.
    return urlencode(parameters)


def redact_provider_errors(value, api_key, depth=0):
    # Filter ONLY the errors field, never headers, account data or the full body.
    private_fields = (r"key|token|secret|password|authorization|header|credential|account|"
                      r"email|client|user|customer|session|cookie|response|data|subscription[_ -]?(?:id|number)")
    if depth > 2:
        return "<nested details omitted>"
    if isinstance(value, dict):
        filtered = {}
        for field, detail in list(value.items())[:10]:
            if not isinstance(field, str) or re.search(private_fields, field, re.IGNORECASE):
                filtered["<private field omitted>"] = "<redacted>"
                continue
            label = public_text(field.replace(api_key, "<redacted>") if api_key else field)
            if label is not None and not re.fullmatch(r"[A-Za-z][A-Za-z0-9 _-]{0,59}", label):
                label = None  # Error labels must not expose email addresses/URLs.
            filtered[label or "<field omitted>"] = redact_provider_errors(detail, api_key, depth + 1)
        return filtered
    if isinstance(value, list):
        return [redact_provider_errors(item, api_key, depth + 1) for item in value[:10]]
    if not isinstance(value, str):
        return "<non-text details omitted>"
    text = value.replace(api_key, "<redacted>") if api_key else value
    if (len(text) > 500 or re.search(
            r"-----BEGIN|private[_ -]?key|secret|password|authorization|header|credential|"
            r"account|customer|session|cookie|client[_ -]?(?:id|email)|subscription[_ -]?(?:id|number)|"
            r"[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}", text, re.IGNORECASE)):
        return "<private or oversized message omitted>"
    text = re.sub(r"\b(?:Bearer|Basic)\s+\S+", "<authorization value redacted>", text, flags=re.IGNORECASE)
    text = re.sub(r"https?://\S+", "<URL omitted>", text, flags=re.IGNORECASE)
    return re.sub(r"\b[A-Za-z0-9_./+=-]{24,}\b", "<token redacted>", text)


def display_provider_errors(data, api_key):
    errors = data.get("errors") if isinstance(data, dict) else None
    if not isinstance(errors, (dict, list)):
        print("Provider errors: unavailable (missing or invalid errors field).")
        return
    filtered = redact_provider_errors(errors, api_key)
    # JSON escaping prevents terminal control characters from being interpreted.
    print("Provider errors (filtered, up to 10 entries per level): " + json.dumps(filtered, ensure_ascii=True))


def fetch_head_to_head(api_key, season=None):
    query = head_to_head_query(season)
    request = Request(
        "https://v3.football.api-sports.io/fixtures/headtohead?" + query,
        headers={"x-apisports-key": api_key, "User-Agent": "MatchLensUniversityProject/1.0 (fixture preview)"},
    )
    notices = []
    http_status = None
    try:
        # Redirects are blocked: at most one GET, with no forwarded secret header.
        with build_opener(NoRedirects()).open(request, timeout=20) as response:
            http_status = getattr(response, "status", None)
            print(f"HTTP status: {http_status if type(http_status) is int else 'unavailable'}")
            data = json.load(response)
            display_provider_errors(data, api_key)
            for header, label in (("x-ratelimit-requests-remaining", "Daily quota"),
                                  ("x-ratelimit-remaining", "Per-minute quota")):
                remaining = response.headers.get(header)
                if remaining is not None and remaining.strip() == "0":
                    notices.append(f"{label} exhausted after this response; no further requests will be made.")
    except HTTPError as error:
        print(f"HTTP status: {error.code}")
        try:
            display_provider_errors(json.load(error), api_key)
        except (ValueError, TypeError, OSError, HTTPException, RecursionError):
            print("Provider errors: unavailable (HTTP error body was not readable JSON).")
        finally:
            error.close()
        messages = {
            401: "Authentication failed. Check the existing API-Football key.",
            403: "Access denied. Check subscription, historical-data access, quota and IP restrictions.",
            404: "The head-to-head endpoint is unavailable. Check the API documentation.",
            429: "API-Football quota/rate limit reached. Check the dashboard and retry manually later.",
            499: "API-Football timed out. No automatic retry was issued.",
        }
        raise MappingError(messages.get(error.code, f"API-Football HTTP {error.code}. No retry was issued.")) from None
    except (URLError, OSError, HTTPException):
        if http_status is None:
            print("HTTP status: unavailable (no HTTP response received).")
        raise MappingError("API-Football connection failed or timed out. No retry was issued.") from None
    except (ValueError, UnicodeError, RecursionError):
        print("Provider errors: unavailable (invalid JSON).")
        raise MappingError("API-Football returned invalid JSON.") from None
    return data, notices


def read_fixture_records(data):
    if not isinstance(data, dict) or not isinstance(data.get("errors"), (dict, list)):
        raise MappingError("API-Football returned an unexpected response format.")
    if data["errors"]:
        # Diagnose without exposing raw error bodies, which can echo secrets.
        errors = json.dumps(data["errors"]).casefold()
        if any(word in errors for word in ("plan", "subscription", "access", "free")):
            raise MappingError("Subscription/parameter restriction. Check access to head-to-head, last and historical seasons; no fallback request was made.")
        if any(word in errors for word in ("quota", "limit", "requests")):
            raise MappingError("API-Football reported exhausted quota or a rate limit. No retry was issued.")
        raise MappingError("API-Football reported an error. Check endpoint access, parameters and credentials.")
    records = data.get("response")
    if (not isinstance(records, list) or type(data.get("results")) is not int
            or data["results"] != len(records)):
        raise MappingError("API-Football returned invalid fixture results/counts.")
    paging = data.get("paging")
    issues = []
    if (not isinstance(paging, dict) or type(paging.get("current")) is not int
            or paging["current"] != 1 or type(paging.get("total")) is not int
            or paging["total"] < 1):
        issues.append("Pagination metadata is missing or invalid; completeness cannot be confirmed.")
    elif paging["total"] != 1:
        issues.append("Additional pages were reported. No additional page was requested.")
    return records, issues


def object_field(parent, field, issues):
    value = parent.get(field)
    if not isinstance(value, dict):
        issues.append(f"The {field} object is missing or invalid.")
        return {}
    return value


def inspect_kickoff(fixture, issues, now):
    utc_date = None
    date = fixture.get("date")
    pattern = (r"[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}"
               r"(?:\.[0-9]{1,6})?(?:Z|[+-][0-9]{2}:[0-9]{2})")
    try:
        if not isinstance(date, str) or not re.fullmatch(pattern, date):
            raise ValueError
        if not date.endswith("Z") and (int(date[-5:-3]) > 23 or int(date[-2:]) > 59):
            raise ValueError
        utc_date = datetime.fromisoformat(date.replace("Z", "+00:00")).astimezone(timezone.utc)
    except (ValueError, OverflowError):
        issues.append("fixture.date is missing/invalid or lacks an explicit timezone.")
    timestamp = fixture.get("timestamp", MISSING)
    if timestamp is not MISSING and timestamp is not None:
        try:
            if type(timestamp) is not int:
                raise ValueError
            unix_date = datetime.fromtimestamp(timestamp, timezone.utc)
            if utc_date is not None and unix_date != utc_date:
                issues.append("fixture.date and the Unix timestamp disagree; manual review required.")
            elif utc_date is None:
                utc_date = unix_date
                issues.append("UTC display uses the provided Unix timestamp because fixture.date was unavailable.")
        except (ValueError, OverflowError, OSError):
            issues.append("The provided Unix kickoff timestamp is invalid.")
    kickoff = utc_date.isoformat().replace("+00:00", "Z") if utc_date is not None else None
    try:
        validate_kickoff(kickoff, "finished")  # Historical games need a known UTC kickoff.
    except ValidationError as error:
        issues.append(f"Kickoff/schema: {error}")
    if utc_date is not None and utc_date > now:
        issues.append("Kickoff is in the future; this is not a previous match.")
    return kickoff


def inspect_fixture(record, mapping, seen_ids, now, requested_season=None):
    issues = []
    if not isinstance(record, dict):
        issues.append("The fixture record is not an object.")
        record = {}
    fixture = object_field(record, "fixture", issues)
    league = object_field(record, "league", issues)
    teams = object_field(record, "teams", issues)
    goals = object_field(record, "goals", issues)
    status = object_field(fixture, "status", issues)
    home = object_field(teams, "home", issues)
    away = object_field(teams, "away", issues)
    fixture_id = fixture.get("id", MISSING)
    if type(fixture_id) is not int or fixture_id <= 0:
        issues.append("The numeric API-Football fixture ID is missing or invalid.")
    elif fixture_id in seen_ids:
        issues.append("Duplicate fixture ID in this response.")
    else:
        seen_ids.add(fixture_id)

    home_id, away_id = home.get("id"), away.get("id")
    if (type(home_id) is not int or type(away_id) is not int
            or {home_id, away_id} != set(TEAM_IDS)):
        issues.append("Participating team IDs must be exactly 529 and 541, in either home/away order.")
    for label, team in (("Home", home), ("Away", away)):
        if public_text(team.get("name")) is None:
            issues.append(f"{label} team name is missing or unsafe to display.")
    if public_text(league.get("name")) is None:
        issues.append("Competition name is missing or invalid.")
    if type(league.get("id")) is not int or league["id"] <= 0:
        issues.append("Provider competition ID is missing or invalid.")
    season = league.get("season")
    if type(season) is not int or not 1000 <= season <= 9999:
        issues.append("Provider season must be a four-digit integer; do not invent a missing season.")
    if requested_season is not None and season != requested_season:
        issues.append("Provider season does not match the requested season.")

    short = status.get("short")
    mapped_status = STATUS_MAP.get(short) if isinstance(short, str) else None
    if mapped_status is None:
        issues.append("Provider status needs an explicit schema decision (for example TBD, SUSP, INT, ABD, AWD or WO).")
    if short not in ("FT", "AET", "PEN"):
        issues.append("The returned status does not confirm a completed previous match.")
    home_score, away_score = goals.get("home", MISSING), goals.get("away", MISSING)
    try:
        # Validate values without replacing null/missing scores or changing them.
        validate_scores(home_score, away_score, mapped_status or "live")
    except ValidationError as error:
        issues.append(f"Score/schema: {error}")
    score = record.get("score")
    if score is not None:
        if not isinstance(score, dict):
            issues.append("The optional period-score breakdown is invalid.")
        else:
            for period in ("halftime", "fulltime", "extratime", "penalty"):
                pair = score.get(period)
                if pair is None:
                    continue  # An unavailable period is not an invented zero.
                if not isinstance(pair, dict):
                    issues.append(f"The {period} score object is invalid.")
                    continue
                try:
                    validate_scores(pair.get("home", MISSING), pair.get("away", MISSING), "live")
                except ValidationError as error:
                    issues.append(f"{period} score: {error}")
                else:
                    if (short == "FT" and period == "fulltime" and pair.get("home") is not None
                            and (pair["home"], pair["away"]) != (home_score, away_score)):
                        issues.append("FT goals disagree with the full-time score breakdown.")
                    if short == "FT" and period in ("extratime", "penalty") and pair.get("home") is not None:
                        issues.append("An FT fixture contains extra-time/shootout scores; review the finish type.")
    if mapped_status is not None:
        # Compare supplied provider periods with the local schema, without
        # preparing/persisting a match or deriving totals from period scores.
        pairs = []
        for period in ("fulltime", "extratime", "penalty"):
            pair = score.get(period) if isinstance(score, dict) else None
            pairs.append((pair.get("home", MISSING), pair.get("away", MISSING))
                         if isinstance(pair, dict) else (None, None))
        finish_type = {"FT": "regularTime", "AET": "extraTime", "PEN": "penalties"}.get(short)
        try:
            validate_score_details(mapped_status, finish_type, home_score, away_score, *pairs)
        except ValidationError as error:
            issues.append(f"Score details/schema: {error}")
    kickoff = inspect_kickoff(fixture, issues, now)

    print(f"\nAPI-Football fixture ID: {display_value(fixture_id)}")
    print(f"Competition: {display_value(league.get('name', MISSING))} | Provider league ID: {display_value(league.get('id', MISSING))}")
    print(f"Season (provider): {display_value(league.get('season', MISSING))}")
    for label, team in (("Home", home), ("Away", away)):
        api_id = team.get("id", MISSING)
        internal = mapping.get(api_id) if type(api_id) is int else None
        target = f"teams/{internal['teamId']}" if internal else "<unmapped>"
        print(f"{label}: {display_value(team.get('name', MISSING))} | API-Football {display_value(api_id)} -> {target}")
    print(f"Kickoff UTC: {display_value(kickoff)}")
    print(f"Status (provider): {display_value(status.get('short', MISSING))} / {display_value(status.get('long', MISSING))}")
    print(f"Status (schema comparison only): {mapped_status or '<review required>'}")
    print(f"Goals (provider): home={display_value(home_score)}, away={display_value(away_score)}")
    if isinstance(score, dict):
        for period in ("halftime", "fulltime", "extratime", "penalty"):
            pair = score.get(period)
            if isinstance(pair, dict):
                print(f"  {period}: home={display_value(pair.get('home', MISSING))}, away={display_value(pair.get('away', MISSING))}")
    print("Validation: " + ("REVIEW REQUIRED" if issues else "Basic checks passed"))
    for issue in issues:
        print(f"  - {issue}")
    return issues


def display_schema_notes():
    print("\nSchema comparison - no import-ready record is created:")
    print("  fixture.id (provider integer) -> sourceMatchId (string); separate stable match_<slug> ID still needed.")
    print("  league.id -> sourceCompetitionId (string); competitionId stays null until its internal mapping is verified.")
    print("  league.season is an integer; the local schema expects a string.")
    print("  fixture.date includes an offset; display converts it to UTC Z. A future importer would use a Firestore Timestamp.")
    print("  Provider codes map to scheduled/live/finished/postponed/cancelled; unsupported/uncertain states require review.")
    print("  goals.home/away stay unchanged, including null. Missing differs from null; period/shootout scores stay separate.")
    print("  FT/AET/PEN distinguish regularTime/extraTime/penalties finishType. Extra-time scores describe only that period, not cumulative goals.")
    print("  Real-data provenance would be source=API-Football and isDemo=false, subject to reuse permission review.")
    print("  Existing Wikidata team IDs are referenced; no team/player documents are updated or rechecked here.")


def season_argument(value):
    if not re.fullmatch(r"[1-9][0-9]{3}", value):
        raise argparse.ArgumentTypeError("Season must be a four-digit year, such as 2024.")
    return int(value)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, allow_abbrev=False)
    parser.add_argument("--season", type=season_argument, help="Filter by a season instead of sending last=3.")
    args = parser.parse_args(argv)
    requests_used = 0
    completed = False
    try:
        mapping = load_team_mapping()
        api_key = read_api_key()
        if not api_key:
            return 1
        print("Real-data inspection only - source: API-Football. No demonstration result is substituted.")
        print("GET /fixtures/headtohead?" + head_to_head_query(args.season))
        for api_id, team in mapping.items():
            print(f"Known team mapping: API-Football {api_id} -> teams/{team['teamId']} ({team['name']})")
        requests_used = 1
        data, notices = fetch_head_to_head(api_key, args.season)
        records, response_issues = read_fixture_records(data)
        for notice in notices:
            print(f"Notice: {notice}")
        seen_ids, issues_per_match = set(), []
        now = datetime.now(timezone.utc)
        displayed = records[:MAX_MATCHES]
        print(f"Received {len(records)} fixtures; displaying {len(displayed)} in provider order (maximum {MAX_MATCHES}).")
        for record in displayed:
            issues_per_match.append(inspect_fixture(record, mapping, seen_ids, now, args.season))
        if not records:
            print("No matches returned. Check provider coverage and your plan; no fallback request was made.")
        display_schema_notes()
        for issue in response_issues:
            print(f"Response issue: {issue}")
        failed = sum(bool(issues) for issues in issues_per_match)
        issue_count = sum(len(issues) for issues in issues_per_match) + len(response_issues)
        print(f"\nSummary: retrieved {len(records)} | displayed {len(displayed)} | basic checks passed {len(displayed) - failed} | require review {failed} | validation issues {issue_count}")
        print("No internal match/competition IDs were assigned; this is not approval to import or republish.")
        completed = True
        return 1 if issue_count else 0
    except (ValidationError, MappingError) as error:
        print(f"ERROR: {error}")
    except OSError:
        print("ERROR: Could not read the local team references or existing API configuration.")
    except (ValueError, TypeError, KeyError, AttributeError, OverflowError):
        print("ERROR: Invalid local configuration or unexpected provider data. Raw errors are not displayed.")
    except KeyboardInterrupt:
        print("\nCANCELLED: Fixture preview interrupted.")
    finally:
        if not completed:
            print("Summary: preview incomplete; no fixture validation result is claimed.")
        print(f"API requests attempted: {requests_used}/1. No retries, redirects or additional pages.")
        print(f"\n{PREVIEW_MESSAGE}")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
