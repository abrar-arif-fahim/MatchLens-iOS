"""Preview five Wikidata/API-Football club mappings in the terminal only."""

import argparse
import json
import re
import time
from http.client import HTTPException
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, build_opener

# All imported helpers have main guards; importing them makes no requests.
from api_football_players import NoRedirects, read_api_key
from prepare_multiple_teams import load_verified_teams
from discover_team_ids import ValidationError, club_name, normalize_name, other_section


EXPECTED_IDS = {"Q7156", "Q8682", "Q50602", "Q1130849", "Q15789"}
STATUSES = ("VERIFIED", "REVIEW REQUIRED", "NOT FOUND", "ERROR")
MAX_REQUESTS = 5
REQUEST_INTERVAL_SECONDS = 2
PREVIEW_MESSAGE = "PREVIEW ONLY - No provider responses or mappings saved. No Firebase changes."
BAYERN_WIKIDATA_ID = "Q15789"
# Documentation-provided lookup candidate; never an automatically accepted mapping.
BAYERN_API_FOOTBALL_ID = 157


class MappingError(ValueError):
    """A safe API error message that never includes headers or response bodies."""


def public_text(value):
    # Do not display URLs, control characters, credential-like content or tokens.
    if (not isinstance(value, str) or not value.strip() or len(value) > 100
            or any(ord(character) < 32 for character in value)
            or re.search(r"https?://|-----BEGIN|private[_ -]?key|api[_ -]?key|"
                         r"access[_ -]?token|password|client_secret|"
                         r"\b[A-Za-z0-9_-]{24,}\b", value, re.IGNORECASE)):
        return None
    return value.strip()


def parse_candidates(data):
    if not isinstance(data, dict) or not isinstance(data.get("errors"), (dict, list)):
        raise MappingError("API-Football returned an unexpected response format.")
    if data["errors"]:
        # Inspect for diagnosis without printing arbitrary provider error text.
        errors = json.dumps(data["errors"]).casefold()
        if any(word in errors for word in ("quota", "limit", "requests")):
            raise MappingError("API-Football reported a quota/rate limit. Check your dashboard before retrying.")
        raise MappingError("API-Football reported an error. Check the key, parameters and endpoint access in your plan.")
    records, paging = data.get("response"), data.get("paging")
    if (not isinstance(records, list) or type(data.get("results")) is not int
            or data["results"] != len(records) or not isinstance(paging, dict)
            or type(paging.get("current")) is not int or paging["current"] != 1
            or type(paging.get("total")) is not int or paging["total"] < 1):
        raise MappingError("API-Football returned invalid results or pagination information.")

    candidates, seen_ids = [], set()
    complete = paging["total"] == 1
    for record in records:
        team = record.get("team") if isinstance(record, dict) else None
        venue = record.get("venue") if isinstance(record, dict) else None
        team = team if isinstance(team, dict) else {}
        venue = venue if isinstance(venue, dict) else {}
        api_id = team.get("id")
        if type(api_id) is not int or api_id <= 0:
            api_id = None
        if api_id is None or api_id in seen_ids:
            complete = False  # Malformed/duplicate IDs prevent a unique mapping.
        seen_ids.add(api_id)
        founded = team.get("founded")
        # Extract only small public identity hints. Ignore logos, URLs and images.
        candidates.append({
            "apiFootballId": api_id,
            "name": public_text(team.get("name")),
            "country": public_text(team.get("country")),
            "national": team.get("national") if type(team.get("national")) is bool else None,
            "code": public_text(team.get("code")),
            "founded": founded if type(founded) is int and 0 < founded <= 9999 else None,
            "city": public_text(venue.get("city")),
        })
    return candidates, complete


def request_teams(parameters, api_key):
    # One GET only. The key is sent in the header, never in the URL or terminal.
    request = Request(
        "https://v3.football.api-sports.io/teams?" + urlencode(parameters),
        headers={"x-apisports-key": api_key, "User-Agent": "MatchLensUniversityProject/1.0 (club ID preview)"},
    )
    try:
        with build_opener(NoRedirects()).open(request, timeout=20) as response:
            data = json.load(response)
            stop_reason = None
            for header, label in (
                ("x-ratelimit-requests-remaining", "daily quota"),
                ("x-ratelimit-remaining", "per-minute limit"),
            ):
                remaining = response.headers.get(header)
                if remaining is not None and remaining.strip() == "0":
                    stop_reason = f"API-Football {label} reached; remaining clubs were not searched."
    except HTTPError as error:
        messages = {
            401: "Authentication failed. Check your existing API-Football key.",
            403: "Access denied. Check the key, subscription, quota and IP restrictions.",
            404: "The API-Football team endpoint is unavailable. Check the current API documentation.",
            429: "API-Football rate limit reached. No automatic retry; check your dashboard and retry later.",
            499: "API-Football timed out. No automatic retry was issued.",
        }
        raise MappingError(messages.get(error.code, f"API-Football HTTP {error.code}; remaining searches stopped.")) from None
    except (URLError, OSError, HTTPException):
        raise MappingError("API-Football connection failed or timed out. No automatic retry was issued.") from None
    except (ValueError, UnicodeError):
        raise MappingError("API-Football did not return valid JSON.") from None
    candidates, complete = parse_candidates(data)
    return candidates, complete, stop_reason


def search_teams(query, api_key):
    # Preserve the normal five-club search and its existing request budget.
    return request_teams({"search": query}, api_key)


def check_candidate(reference, candidate):
    name, country = candidate["name"], candidate["country"]
    if candidate["national"] is True:
        return "NOT FOUND", "National team, not the requested club."
    if name is None or candidate["apiFootballId"] is None:
        return "REVIEW REQUIRED", "Candidate name or numeric provider ID is unavailable."
    if other_section(name):
        return "NOT FOUND", "Women's/reserve/youth team or another sporting section."
    if club_name(name) != club_name(reference["expectedName"]):
        return "NOT FOUND", "Distinctive name words do not match; no fuzzy/first-result selection."
    if country is None:
        return "REVIEW REQUIRED", "Country is unavailable."
    if (reference["expectedCountry"] == "England"
            and normalize_name(country) in {"united kingdom", "uk", "great britain"}):
        return "REVIEW REQUIRED", "United Kingdom alone does not establish England."
    if normalize_name(country) != normalize_name(reference["expectedCountry"]):
        return "NOT FOUND", "Country does not match the verified application country."
    if candidate["national"] is not False:
        return "REVIEW REQUIRED", "Club/national-team flag is missing or invalid."
    return "MATCH", "Normalized name, country and club flag match."


def review_candidates(reference, candidates, complete):
    reviews = [(candidate, *check_candidate(reference, candidate)) for candidate in candidates]
    matches = sum(decision == "MATCH" for _, decision, _ in reviews)
    uncertain = any(decision == "REVIEW REQUIRED" for _, decision, _ in reviews)
    if not complete or uncertain or matches > 1:
        status = "REVIEW REQUIRED"
        reason = "Incomplete/duplicate results, missing evidence or multiple plausible clubs; manual review required."
    elif matches == 1:
        status = "VERIFIED"
        reason = "Exactly one compatible club in the complete returned search."
    else:
        status = "NOT FOUND"
        reason = "No candidate passed the identity checks in the returned search."
    return {"reference": reference, "status": status, "reason": reason, "reviews": reviews}


def check_mapping_collisions(results):
    # A provider ID must not be assigned to two different Wikidata clubs.
    by_id = {}
    for result in results:
        if result["status"] == "VERIFIED":
            for candidate, decision, _ in result["reviews"]:
                if decision == "MATCH":
                    by_id.setdefault(candidate["apiFootballId"], []).append(result)
    for group in by_id.values():
        if len(group) > 1:
            for result in group:
                result["status"] = "REVIEW REQUIRED"
                result["reason"] = "The same API-Football ID was returned for different Wikidata clubs."


def display_results(results, requests_used):
    rows = [("Expected club", "Wikidata ID", "API-Football ID", "API-Football name", "Country", "Status")]
    totals = {status: 0 for status in STATUSES}
    for result in results:
        reference = result["reference"]
        totals[result["status"]] += 1
        for candidate, decision, _ in result["reviews"]:
            status = ("VERIFIED" if result["status"] == "VERIFIED" else "REVIEW REQUIRED") if decision == "MATCH" else decision
            rows.append((reference["expectedName"], reference["wikidataId"],
                         str(candidate["apiFootballId"]) if candidate["apiFootballId"] is not None else "-",
                         candidate["name"] or "-", candidate["country"] or "-", status))
        if not result["reviews"]:
            rows.append((reference["expectedName"], reference["wikidataId"], "-", "-", "-", result["status"]))
    widths = [max(len(row[column]) for row in rows) for column in range(len(rows[0]))]
    for index, row in enumerate(rows):
        print(" | ".join(value.ljust(width) for value, width in zip(row, widths)))
        if index == 0:
            print("-+-".join("-" * width for width in widths))
    for result in results:
        print(f"\n{result['reference']['expectedName']} - {result['status']}: {result['reason']}")
        for candidate, _, reason in result["reviews"]:
            hints = ", ".join(f"{field}={candidate[field]}" for field in ("code", "founded", "city") if candidate[field] is not None)
            print(f"  API-Football ID {candidate['apiFootballId'] or '-'}: {reason}" + (f" Provider hints: {hints}." if hints else ""))
    print("\nClub summary: " + " | ".join(f"{status} {totals[status]}" for status in STATUSES))
    print(f"API requests attempted: {requests_used}/{MAX_REQUESTS}. No retries or extra pages.")


def assess_bayern(candidates, complete, reference):
    if not complete or len(candidates) != 1:
        return "REVIEW REQUIRED", "The ID lookup must return exactly one complete, unambiguous team record."
    candidate = candidates[0]
    if candidate["apiFootballId"] != BAYERN_API_FOOTBALL_ID:
        return "REVIEW REQUIRED", "The returned numeric team ID does not match the requested ID 157."
    decision, reason = check_candidate(reference, candidate)
    if decision != "MATCH":
        return "REVIEW REQUIRED", reason
    return "VERIFIED", "Returned ID 157, Bayern club name, Germany and club flag all match."


def verify_bayern():
    requests_used = 0
    try:
        references = load_verified_teams()
        bayern = [team for team in references if team["wikidataId"] == BAYERN_WIKIDATA_ID]
        if (len(bayern) != 1 or public_text(bayern[0]["expectedName"]) is None
                or club_name(bayern[0]["expectedName"]) != "bayern munich"
                or bayern[0]["expectedCountry"] != "Germany"):
            raise ValidationError("The local Q15789 reference must identify Bayern Munich in Germany.")
        api_key = read_api_key()
        if not api_key:
            print("ERROR: The existing API-Football key is unavailable.")
            return 1

        print("Targeted check: Wikidata Q15789; API-Football lookup candidate 157.")
        requests_used = 1
        # One ID lookup only: never run name searches, retries or extra pages.
        candidates, complete, stop_reason = request_teams({"id": BAYERN_API_FOOTBALL_ID}, api_key)
        status, reason = assess_bayern(candidates, complete, bayern[0])
        print("Wikidata ID | API-Football ID | API-Football name | Country | Status")
        for candidate in candidates:
            print(f"{BAYERN_WIKIDATA_ID} | {candidate['apiFootballId'] or '-'} | "
                  f"{candidate['name'] or '-'} | {candidate['country'] or '-'} | {status}")
            hints = ", ".join(f"{field}={candidate[field]}" for field in ("code", "founded", "city")
                              if candidate[field] is not None)
            if hints:
                print(f"  Optional provider hints (not independently verified): {hints}")
        print(f"{status}: {reason}")
        if stop_reason:
            print(stop_reason)
        return 0 if status == "VERIFIED" else 1
    except (ValidationError, MappingError) as error:
        print(f"ERROR: {error}")
    except (OSError, ValueError, TypeError, KeyError, AttributeError):
        # Do not expose raw errors or private API configuration.
        print("ERROR: Invalid local configuration or unexpected provider data.")
    except KeyboardInterrupt:
        print("\nERROR: Targeted Bayern verification was cancelled.")
    finally:
        print(f"API requests attempted: {requests_used}/1. No retries, searches or extra pages.")
        print(f"\n{PREVIEW_MESSAGE}")
    return 1


def main():
    try:
        references = load_verified_teams()
        if {team["wikidataId"] for team in references} != EXPECTED_IDS:
            raise ValidationError("The input must contain the five expected verified Wikidata clubs.")
        for reference in references:
            if any(public_text(reference[field]) is None for field in ("expectedName", "expectedCountry", "shortName")):
                raise ValidationError("A local team reference contains invalid public text.")
            if len(club_name(reference["expectedName"])) < 3:
                raise ValidationError("A team search name is shorter than the API's three-character minimum.")
        api_key = read_api_key()
        if not api_key:
            return 1
        print("Wikidata IDs: existing local verified references. Candidate IDs/names/countries: API-Football.")
        print("VERIFIED means an identity match within this search, not permission to store or redistribute provider data.\n")
        results, cache = [], {}
        requests_used, stop_reason = 0, None
        for reference in references:
            query = club_name(reference["expectedName"])
            if stop_reason or requests_used >= MAX_REQUESTS:
                results.append({"reference": reference, "status": "ERROR", "reviews": [],
                                "reason": stop_reason or "Request budget reached; club was not searched."})
                continue
            try:
                if query not in cache:
                    if requests_used:
                        time.sleep(REQUEST_INTERVAL_SECONDS)
                    requests_used += 1
                    cache[query] = search_teams(query, api_key)
                candidates, complete, stop_reason = cache[query]
                results.append(review_candidates(reference, candidates, complete))
            except MappingError as error:
                # Stop all remaining calls after access, quota or network errors.
                stop_reason = str(error)
                results.append({"reference": reference, "status": "ERROR", "reviews": [], "reason": stop_reason})
        check_mapping_collisions(results)
        display_results(results, requests_used)
        return 0 if all(result["status"] == "VERIFIED" for result in results) else 1
    except ValidationError as error:
        print(f"Preview stopped: {error}")
    except OSError:
        print("Preview stopped: Could not read the local verified references or existing API configuration.")
    except (ValueError, TypeError, KeyError, AttributeError):
        print("Preview stopped: Invalid local configuration or unexpected provider data.")
    except KeyboardInterrupt:
        print("\nCANCELLED: Team mapping preview interrupted.")
    finally:
        print(f"\n{PREVIEW_MESSAGE}")
    return 1


def cli(argv=None):
    parser = argparse.ArgumentParser(
        description="Preview all five club mappings, or verify only Bayern using its documented API ID.",
        allow_abbrev=False,
    )
    parser.add_argument(
        "--verify-bayern", action="store_true",
        help="Check only Q15789 against GET /teams?id=157 using at most one API request.",
    )
    args = parser.parse_args(argv)
    return verify_bayern() if args.verify_bayern else main()


if __name__ == "__main__":
    raise SystemExit(cli())
