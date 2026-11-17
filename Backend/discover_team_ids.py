"""Discover club IDs conservatively. Run manually; no Firebase/API-Football use."""

import json
import re
import tempfile
import time
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from http.client import HTTPException
from math import ceil, isfinite
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen
from validate_match_schema import reject_duplicate_fields

# These existing modules use only the standard library and have main guards.
# Reuse their label, alias and statement extraction without making import-time requests.
from prepare_team_data import (
    ValidationError, english_aliases, english_description, english_label,
    normalize_name, valid_id,
)


BACKEND_DIR = Path(__file__).resolve().parent
INPUT_FILE = BACKEND_DIR / "input" / "teams_to_import.json"
OUTPUT_FILE = BACKEND_DIR / "output" / "teams_verified.json"
USER_AGENT = "MatchLensUniversityProject/1.0 (educational football club identity discovery)"
INPUT_FIELDS = ("expectedName", "expectedCountry", "shortName", "wikidataId")
STATUSES = ("SUCCESS", "NOT FOUND", "AMBIGUOUS", "REVIEW REQUIRED", "FAILED")
SEARCH_PAGE_SIZE = 50
MAX_SEARCH_PAGES = 10
# Conservative spacing for requests without an authenticated Wikimedia account.
REQUEST_INTERVAL_SECONDS = 7.0
MAX_REQUEST_ATTEMPTS = 3
MAX_RETRY_WAIT_SECONDS = 120
# These are geographic reference IDs, not guesses for the four missing club IDs.
COUNTRIES = {"Spain": "Q29", "England": "Q21", "Germany": "Q183"}
# https://www.wikidata.org/wiki/Q476028 -- association football club.
FOOTBALL_CLUB_CLASS = "Q476028"
UK_REGIONS = {"Q21", "Q22", "Q25", "Q26"}  # England, Scotland, Wales, Northern Ireland.


class Mismatch(ValidationError):
    """Enough evidence was available to reject this candidate."""


class ReviewRequired(ValidationError):
    """Essential evidence is missing or conflicting; do not guess a value."""


class RateLimited(ValidationError):
    """Stop this run's requests when Wikidata needs a longer cooling-off period."""


def retry_after_seconds(value):
    # Retry-After may contain either a number of seconds or an HTTP date.
    if not value:
        return None
    try:
        seconds = float(value)
        return max(0, ceil(seconds)) if isfinite(seconds) else None
    except ValueError:
        try:
            retry_time = parsedate_to_datetime(value)
            if retry_time.tzinfo is None:
                retry_time = retry_time.replace(tzinfo=timezone.utc)
            return max(0, ceil((retry_time - datetime.now(timezone.utc)).total_seconds()))
        except (ValueError, TypeError, OverflowError):
            return None


class WikidataClient:
    def __init__(self):
        self.entities = {}
        self.last_request = 0.0
        self.stopped_reason = None

    def pause_or_stop(self, reason, retry_after, attempt):
        delay = retry_after_seconds(retry_after)
        if delay is None:
            delay = 30 * (2 ** attempt)
        if attempt + 1 >= MAX_REQUEST_ATTEMPTS or delay > MAX_RETRY_WAIT_SECONDS:
            self.stopped_reason = (
                f"{reason}. No more requests will be sent in this run. "
                f"Wait at least {delay} seconds before trying again."
            )
            raise RateLimited(self.stopped_reason)
        print(f"  {reason}; waiting {delay} seconds before retrying...")
        time.sleep(delay)

    def download(self, url):
        if self.stopped_reason:
            raise RateLimited(self.stopped_reason)
        request = Request(url, headers={"User-Agent": USER_AGENT})
        for attempt in range(MAX_REQUEST_ATTEMPTS):
            # Space every request, including retries; never send in parallel.
            delay = REQUEST_INTERVAL_SECONDS - (time.monotonic() - self.last_request)
            if delay > 0:
                time.sleep(delay)
            self.last_request = time.monotonic()
            try:
                with urlopen(request, timeout=20) as response:
                    retry_after = response.headers.get("Retry-After")
                    data = json.load(response)
            except HTTPError as error:
                if error.code in (429, 503):
                    retry_after = error.headers.get("Retry-After") if error.headers else None
                    self.pause_or_stop(f"Wikidata HTTP {error.code}", retry_after, attempt)
                    continue
                raise ValidationError(f"Wikidata HTTP {error.code}; retry this discovery later.") from None
            except (URLError, OSError, HTTPException):
                raise ValidationError("Wikidata network error or timeout; retry later.") from None
            except (ValueError, UnicodeError):
                raise ValidationError("Wikidata returned unreadable JSON.") from None
            if not isinstance(data, dict):
                raise ValidationError("Wikidata returned an unexpected response.")
            api_error = data.get("error")
            error_code = api_error.get("code") if isinstance(api_error, dict) else None
            if error_code in ("ratelimited", "maxlag"):
                self.pause_or_stop(f"Wikidata API {error_code}", retry_after, attempt)
                continue
            if api_error or data.get("errors"):
                raise ValidationError("Wikidata returned an API error.")
            return data

    def get_entity(self, entity_id):
        if not valid_id(entity_id):
            raise ValidationError("Invalid Wikidata entity reference.")
        if entity_id in self.entities:
            cached = self.entities[entity_id]
            if isinstance(cached, ValidationError):
                raise cached
            return cached
        try:
            data = self.download(
                f"https://www.wikidata.org/wiki/Special:EntityData/{entity_id}.json"
            )
            entities = data.get("entities")
            entity = entities.get(entity_id) if isinstance(entities, dict) else None
            if (data.get("redirects") or not isinstance(entity, dict)
                    or entity.get("id") != entity_id or entity.get("type") != "item"
                    or "missing" in entity or entity.get("redirect")):
                raise ValidationError(
                    f"{entity_id} is missing, redirected or unexpected; manual review required."
                )
        except ValidationError as error:
            self.entities[entity_id] = error
            raise
        self.entities[entity_id] = entity
        return entity

    def search(self, expected_name):
        candidate_ids = []
        continuation = None
        seen_pages = set()
        # Inspect multiple results and follow pagination. Never accept a truncated search.
        for _ in range(MAX_SEARCH_PAGES):
            parameters = {
                "action": "wbsearchentities", "search": expected_name,
                "language": "en", "uselang": "en", "type": "item",
                "format": "json", "limit": SEARCH_PAGE_SIZE,
            }
            if continuation is not None:
                parameters["continue"] = continuation
            data = self.download("https://www.wikidata.org/w/api.php?" + urlencode(parameters))
            results = data.get("search")
            if data.get("success") != 1 or data.get("warnings") or not isinstance(results, list):
                raise ValidationError("Incomplete Wikidata search response.")
            for result in results:
                entity_id = result.get("id") if isinstance(result, dict) else None
                if not valid_id(entity_id):
                    raise ValidationError("A search candidate is missing a valid entity ID.")
                if entity_id not in candidate_ids:
                    candidate_ids.append(entity_id)
            if "search-continue" not in data:
                return candidate_ids
            continuation = data["search-continue"]
            if type(continuation) is not int or continuation < 0 or continuation in seen_pages:
                raise ValidationError("Invalid or repeated search pagination; manual review required.")
            seen_pages.add(continuation)
        raise ValidationError(
            f"Search exceeded {MAX_SEARCH_PAGES} pages; results are incomplete. Review manually."
        )


def club_name(value):
    # Ignore accents, punctuation and common club designators, but retain every
    # distinctive name word. No fuzzy, substring or first-result matching.
    value = normalize_name(value.replace(".", ""))
    value = re.sub(r"\b(?:club de futbol|football club|futbol club|f c)\b", "fc", value)
    value = re.sub(r"\bc f\b", "cf", value)
    # These are spelling/translation variants, not fuzzy name matching.
    variants = {"munchen": "munich", "muenchen": "munich"}
    return " ".join(variants.get(word, word) for word in value.split()
                    if word not in {"fc", "cf"})


def other_section(value, description=False):
    words = normalize_name(value).split()
    blocked = {"women", "womens", "female", "femeni", "femenino", "ladies",
               "reserve", "reserves", "youth", "junior", "juniors", "academy",
               "basketball", "handball", "futsal", "stadium", "arena", "defunct", "dissolved"}
    if description:
        # A club description can legitimately mention its stadium.
        blocked.difference_update({"stadium", "arena"})
    return (bool(blocked.intersection(words)) or "b team" in " ".join(words)
            or (bool(words) and words[-1] in {"b", "ii"})
            or any(re.fullmatch(r"u[0-9]{2}|under[0-9]{2}", word) for word in words))


def qualifier_boundary(statement, property_id):
    """Read temporal qualifiers without guessing dates in the current year."""
    qualifiers = statement.get("qualifiers", {})
    entries = qualifiers.get(property_id, []) if isinstance(qualifiers, dict) else []
    boundaries = []
    for entry in entries if isinstance(entries, list) else []:
        datavalue = entry.get("datavalue") if isinstance(entry, dict) else None
        value = datavalue.get("value", {}) if isinstance(datavalue, dict) else {}
        raw_time = value.get("time", "") if isinstance(value, dict) else ""
        if not isinstance(raw_time, str) or not re.match(r"\+[0-9]{4}-[0-9]{2}-[0-9]{2}T", raw_time):
            continue
        try:
            boundaries.append(datetime.strptime(raw_time[1:11], "%Y-%m-%d").date())
        except ValueError:
            # Bounds for imprecise years are used only to exclude claims that
            # definitely ended in a past year or start in a future year.
            year = int(raw_time[1:5])
            today = datetime.now(timezone.utc).date()
            if 1 <= year < today.year:
                boundaries.append(today.replace(year=year, month=12, day=31))
            elif today.year < year <= 9999:
                boundaries.append(today.replace(year=year, month=1, day=1))
    return boundaries


def statement_ids(entity, property_id, classification=False):
    # For classification, inspect ALL non-deprecated ranks. A normal club claim
    # remains valid even alongside an unrelated preferred classification.
    claims = entity.get("claims")
    if not isinstance(claims, dict):
        raise ReviewRequired(f"Statements are missing while checking {property_id}.")
    statements = claims.get(property_id, [])
    if not isinstance(statements, list):
        raise ReviewRequired(f"Invalid statement list for {property_id}.")
    active = []
    today = datetime.now(timezone.utc).date()
    for statement in statements:
        if not isinstance(statement, dict) or statement.get("rank") == "deprecated":
            continue
        if not classification:
            if any(end < today for end in qualifier_boundary(statement, "P582")):
                continue
            if any(start > today for start in qualifier_boundary(statement, "P580")):
                continue
        active.append(statement)
    if not classification:
        preferred = [statement for statement in active if statement.get("rank") == "preferred"]
        active = preferred or active
    ids = set()
    for statement in active:
        snak = statement.get("mainsnak", {})
        datavalue = snak.get("datavalue", {}) if isinstance(snak, dict) else {}
        value = datavalue.get("value", {}) if isinstance(datavalue, dict) else {}
        entity_id = value.get("id") if isinstance(value, dict) else None
        if isinstance(snak, dict) and snak.get("snaktype") == "value" and valid_id(entity_id):
            ids.add(entity_id)
        elif not classification:
            raise ReviewRequired(f"Unknown or invalid country/location value in {property_id}.")
    return sorted(ids)


def verify_classification(entity, client):
    pending = statement_ids(entity, "P31", classification=True)
    # Decisive direct evidence: no requests for unrelated class branches.
    if FOOTBALL_CLUB_CLASS in pending:
        return
    if not pending:
        raise ReviewRequired("Classification validation: no usable non-deprecated P31 statement.")
    visited = set()
    incomplete = []
    for _ in range(4):
        parents = set()
        for entity_id in pending:
            if entity_id in visited:
                continue
            if len(visited) >= 30:
                raise ReviewRequired("Classification validation: hierarchy exceeded 30 entities.")
            visited.add(entity_id)
            try:
                classification = client.get_entity(entity_id)
                ancestors = statement_ids(classification, "P279", classification=True)
            except RateLimited:
                raise
            except ValidationError as error:
                incomplete.append(f"{entity_id}: {error}")
                continue
            if FOOTBALL_CLUB_CLASS in ancestors:
                return
            parents.update(ancestors)
        pending = sorted(parents)
        if not pending:
            if incomplete:
                raise ReviewRequired("Classification validation incomplete: " + "; ".join(incomplete))
            raise Mismatch("Classification validation failed: no P31/P279 path to association football club Q476028.")
    raise ReviewRequired("Classification validation: subclass hierarchy exceeded the depth limit.")


def location_countries(location_id, client):
    """Collect explicit geographic IDs from P17 and administrative P131 links."""
    pending = [(location_id, 0)]
    visited = set()
    evidence = set()
    while pending:
        entity_id, depth = pending.pop(0)
        if entity_id in visited:
            continue
        if len(visited) >= 40:
            raise ReviewRequired("Country validation: location hierarchy exceeded 40 entities.")
        visited.add(entity_id)
        if entity_id in set(COUNTRIES.values()) | UK_REGIONS | {"Q145"}:
            evidence.add(entity_id)
            continue
        location = client.get_entity(entity_id)
        countries = statement_ids(location, "P17")
        evidence.update(countries)
        # A UK sovereign-state claim still needs an England/Scotland/etc. branch.
        if countries and "Q145" not in countries:
            continue
        parents = statement_ids(location, "P131")
        if parents and depth >= 7:
            raise ReviewRequired("Country validation: location hierarchy exceeded the depth limit.")
        pending.extend((parent, depth + 1) for parent in parents)
    return evidence


def verify_country(entity, expected_country, client):
    countries = set(statement_ids(entity, "P17"))
    expected_id = COUNTRIES[expected_country]
    compatible = {expected_id, "Q145"} if expected_country == "England" else {expected_id}
    contradictory = countries - compatible
    if contradictory:
        details = ", ".join(sorted(countries))
        if len(countries) > 1:
            raise ReviewRequired(f"Country validation: conflicting current P17 values ({details}).")
        raise Mismatch(f"Country validation failed: P17 is {details}; expected {expected_country} ({expected_id}).")
    if expected_id in countries:
        return expected_country
    # Rule: P17 describes a sovereign state. UK does NOT mean England. Require
    # direct England evidence or a geographic chain to England. Prefer the club's
    # P131 administrative location, then P159 headquarters, then P115 home venue.
    # A positive chain is enough; unknown optional branches do not negate it.
    notes = []
    for property_id in ("P131", "P159", "P115"):
        locations = statement_ids(entity, property_id)
        evidence = set()
        for location_id in locations:
            try:
                evidence.update(location_countries(location_id, client))
            except RateLimited:
                raise
            except ValidationError as error:
                notes.append(f"{property_id}/{location_id}: {error}")
        conflicts = evidence - compatible
        if conflicts:
            raise ReviewRequired(
                f"Country validation: {property_id} provides conflicting geographic evidence "
                + ", ".join(sorted(evidence)) + "."
            )
        if expected_id in evidence:
            return expected_country
    detail = "; ".join(notes) if notes else "no usable P131, P159 or P115 chain to " + expected_country
    raise ReviewRequired(f"Country validation: P17 alone is insufficient; {detail}.")


def verify_candidate(entity_id, team, client):
    try:
        entity = client.get_entity(entity_id)
    except RateLimited:
        raise
    except ValidationError as error:
        raise ValidationError(f"Entity retrieval failed for {entity_id}: {error}") from None
    try:
        label = english_label(entity)
        aliases = english_aliases(entity)
    except ValidationError as error:
        raise ReviewRequired(f"Name validation could not be completed: {error}") from None
    description = english_description(entity)
    if not any(club_name(name) == club_name(team["expectedName"]) for name in [label] + aliases):
        raise Mismatch(
            f"Name validation failed: expected {team['expectedName']!r}; "
            f"English label is {label!r}; aliases are {aliases!r}."
        )
    if other_section(label) or other_section(description, description=True):
        raise Mismatch("Name/description validation failed: another team, venue or sporting section is identified.")
    # Descriptions may say "multisport organisation" or "football team".
    # P31, rather than a required description phrase, proves the club type.
    verify_classification(entity, client)
    try:
        country = verify_country(entity, team["expectedCountry"], client)
    except RateLimited:
        raise
    except ReviewRequired as error:
        raise ReviewRequired(f"Country check: {error}") from None
    except Mismatch:
        raise
    except ValidationError as error:
        raise ValidationError(f"Country validation could not be completed: {error}") from None
    return label, country


def load_teams():
    with INPUT_FILE.open(encoding="utf-8-sig") as input_file:
        data = json.load(input_file, object_pairs_hook=reject_duplicate_fields)
    teams = data.get("teams") if isinstance(data, dict) else None
    if not isinstance(teams, list) or not 1 <= len(teams) <= 5:
        raise ValidationError("Input must contain a teams array with one to five records.")
    names, known_ids = set(), set()
    for index, team in enumerate(teams, start=1):
        if not isinstance(team, dict) or set(team) != set(INPUT_FIELDS):
            raise ValidationError(f"Team {index} must contain exactly the four expected input fields.")
        for field in INPUT_FIELDS[:3]:
            if not isinstance(team[field], str) or not team[field].strip():
                raise ValidationError(f"Team {index}: {field} must be a nonempty string.")
        if not club_name(team["expectedName"]) or club_name(team["expectedName"]) in names:
            raise ValidationError("Empty or duplicate expected club name.")
        names.add(club_name(team["expectedName"]))
        if team["expectedCountry"] not in COUNTRIES:
            raise ValidationError("This initial discovery supports Spain, England and Germany.")
        entity_id = team["wikidataId"]
        if entity_id is not None:
            if not valid_id(entity_id) or entity_id in known_ids:
                raise ValidationError("Invalid or duplicate supplied Wikidata ID.")
            known_ids.add(entity_id)
        if club_name(team["expectedName"]) == "barcelona" and (
            entity_id != "Q7156" or team["expectedCountry"] != "Spain"
        ):
            raise ValidationError("FC Barcelona must retain its verified Q7156 / Spain reference.")
    return teams


def discover(team, client):
    result = {"team": team, "status": "FAILED", "matches": [], "notes": []}
    supplied_id = team["wikidataId"]
    if supplied_id is not None:
        # This path never searches, paginates or tries a replacement club ID,
        # whether validation succeeds or fails. Geography lookups may be needed.
        print(f"  Validating supplied ID {supplied_id} directly; no name search.")
        try:
            label, country = verify_candidate(supplied_id, team, client)
        except ReviewRequired as error:
            result["status"] = "REVIEW REQUIRED"
            result["notes"].append(f"{supplied_id}: {error}")
        except ValidationError as error:
            result["notes"].append(f"{supplied_id}: {error}")
        else:
            result["status"] = "SUCCESS"
            result["matches"].append((supplied_id, label, country))
        return result

    try:
        candidates = client.search(team["expectedName"])
    except ValidationError as error:
        result["notes"].append(str(error))
        return result
    incomplete = False
    needs_review = False
    if candidates:
        print(f"  Inspecting {len(candidates)} candidates with paced requests; this can take several minutes.")
    for index, candidate_id in enumerate(candidates, start=1):
        print(f"  Candidate {index}/{len(candidates)}: {candidate_id}")
        try:
            label, country = verify_candidate(candidate_id, team, client)
        except RateLimited as error:
            incomplete = True
            result["notes"].append(str(error))
            break
        except Mismatch as error:
            result["notes"].append(f"{candidate_id}: rejected — {error}")
        except ReviewRequired as error:
            needs_review = True
            result["notes"].append(f"{candidate_id}: review required — {error}")
        except ValidationError as error:
            incomplete = True
            result["notes"].append(f"{candidate_id}: could not fully check — {error}")
        else:
            result["matches"].append((candidate_id, label, country))
    # Even one unchecked candidate prevents claiming that a match is unique.
    if len(result["matches"]) > 1:
        result["status"] = "AMBIGUOUS"
    elif incomplete:
        result["status"] = "FAILED"
    elif needs_review:
        result["status"] = "REVIEW REQUIRED"
    elif len(result["matches"]) == 1:
        result["status"] = "SUCCESS"
    else:
        result["status"] = "NOT FOUND"
        if not candidates:
            result["notes"].append("Search returned no candidates.")
    return result


def display_results(results):
    rows = [("Expected team", "Wikidata ID", "Verified Wikidata label", "Country", "Status")]
    for result in results:
        matches = result["matches"]
        rows.append((result["team"]["expectedName"],
                     ", ".join(match[0] for match in matches) or result["team"]["wikidataId"] or "-",
                     "; ".join(match[1] for match in matches) or "-",
                     "; ".join(sorted({match[2] for match in matches})) or "-",
                     result["status"]))
    widths = [max(len(row[column]) for row in rows) for column in range(5)]
    print()
    for index, row in enumerate(rows):
        print(" | ".join(value.ljust(width) for value, width in zip(row, widths)))
        if index == 0:
            print("-+-".join("-" * width for width in widths))
    if any(result["matches"] and result["status"] != "SUCCESS" for result in results):
        print("\nIDs in non-SUCCESS rows are candidate evidence only; they are not saved.")
    for result in results:
        if result["notes"]:
            print(f"\n{result['team']['expectedName']} — candidate review:")
            for note in result["notes"]:
                print("  " + note)
    totals = {status: sum(result["status"] == status for result in results) for status in STATUSES}
    print("\nSummary: " + " | ".join(f"{status}: {totals[status]}" for status in STATUSES))


def save_verified(results):
    teams = []
    for result in results:
        if result["status"] == "SUCCESS":
            team = {field: result["team"][field] for field in INPUT_FIELDS}
            team["wikidataId"] = result["matches"][0][0]
            teams.append(team)
    OUTPUT_FILE.parent.mkdir(parents=True, exist_ok=True)
    temporary_path = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w", encoding="utf-8", dir=OUTPUT_FILE.parent, suffix=".tmp", delete=False
        ) as temporary_file:
            temporary_path = Path(temporary_file.name)
            json.dump({"teams": teams}, temporary_file, ensure_ascii=False, indent=2)
            temporary_file.write("\n")
        temporary_path.replace(OUTPUT_FILE)
    finally:
        if temporary_path is not None:
            temporary_path.unlink(missing_ok=True)
    print(f"\nSaved {len(teams)} fully verified teams to: {OUTPUT_FILE}")
    print("shortName values are application-defined abbreviations, not Wikidata facts.")


def main():
    try:
        teams = load_teams()
        supplied = sum(team["wikidataId"] is not None for team in teams)
        print(f"Supplied IDs: {supplied} (direct validation); null IDs: {len(teams) - supplied} (search discovery).")
        client = WikidataClient()
        results = []
        for team in teams:
            print(f"Checking {team['expectedName']}...")
            results.append(discover(team, client))
        # Prevent two input names from being assigned the same verified club ID.
        for result in results:
            if result["status"] == "SUCCESS":
                entity_id = result["matches"][0][0]
                duplicates = [other for other in results if any(
                    match[0] == entity_id for match in other["matches"]
                )]
                if len(duplicates) > 1:
                    result["status"] = "AMBIGUOUS"
                    result["notes"].append("This entity also matched another input team; review manually.")
        display_results(results)
        save_verified(results)
        return 0 if all(result["status"] == "SUCCESS" for result in results) else 1
    except FileNotFoundError:
        print("FAILED: Input file not found: Backend/input/teams_to_import.json.")
    except ValidationError as error:
        print(f"FAILED: {error}")
    except (ValueError, UnicodeError):
        print("FAILED: Input must contain valid UTF-8 JSON.")
    except OSError:
        print("FAILED: Could not read the input or save the verified output. Check file access.")
    print("No new output was saved; any previous teams_verified.json is not a result of this run.")
    return 1


# Importing this file does not contact Wikidata. Run it yourself to start requests.
if __name__ == "__main__":
    raise SystemExit(main())
