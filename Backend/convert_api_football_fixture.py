"""Pure, in-memory API-Football fixture conversion. No files, credentials or API calls."""

import re
from datetime import datetime, timedelta, timezone

from validate_match_schema import ValidationError, require_text, validate_match
from competition_mapping import resolve_competition
from validate_competition_schema import validate_catalog


# Same coarse statuses as the existing preview. Uncertain/unsupported codes are
# deliberately absent: do not silently classify abandoned or awarded results.
STATUS_MAP = {
    "NS": "scheduled", "1H": "live", "HT": "live", "2H": "live",
    "ET": "live", "BT": "live", "P": "live", "LIVE": "live",
    "FT": "finished", "AET": "finished", "PEN": "finished",
    "PST": "postponed", "CANC": "cancelled",
}
FINISH_TYPES = {"FT": "regularTime", "AET": "extraTime", "PEN": "penalties"}


class ReviewRequired(ValidationError):
    """Conversion cannot safely produce a complete schema-valid record."""

    def __init__(self, reason):
        super().__init__(f"REVIEW REQUIRED: {reason}")


def object_field(parent, key, path, optional=False):
    value = parent.get(key)
    if value is None and optional:
        return {}
    if not isinstance(value, dict):
        raise ReviewRequired(f"{path} must be an object" + (" or null." if optional else "."))
    return value


def positive_id(value, path):
    if type(value) is not int or value <= 0:
        raise ReviewRequired(f"{path} must be a positive numeric provider ID.")
    return value


def validate_team_mapping(mapping):
    # Verification is a caller responsibility; this function validates the
    # supplied registry's shape. It never discovers or guesses an association.
    if not isinstance(mapping, dict) or not mapping:
        raise ReviewRequired("Supply a nonempty dictionary of verified team mappings.")
    seen = set()
    for api_id, team_id in mapping.items():
        positive_id(api_id, "Verified mapping key")
        if not isinstance(team_id, str) or not re.fullmatch(r"wikidata_Q[1-9][0-9]*", team_id):
            raise ReviewRequired("Each verified mapping must contain a Wikidata-based team document ID.")
        if team_id in seen:
            raise ReviewRequired("The supplied registry maps multiple provider IDs to the same club.")
        seen.add(team_id)


def convert_kickoff(fixture, status):
    date = fixture.get("date")
    timestamp = fixture.get("timestamp")
    parsed_date = unix_date = None
    if date is not None:
        # Require an explicit timezone and avoid losing fractional precision.
        pattern = (r"[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}"
                   r"(?:\.[0-9]{1,6})?(?:Z|[+-][0-9]{2}:[0-9]{2})")
        try:
            if not isinstance(date, str) or not re.fullmatch(pattern, date):
                raise ValueError
            if not date.endswith("Z") and (int(date[-5:-3]) > 23 or int(date[-2:]) > 59):
                raise ValueError
            parsed_date = datetime.fromisoformat(date.replace("Z", "+00:00")).astimezone(timezone.utc)
            if parsed_date.microsecond:
                raise ValueError
        except (ValueError, OverflowError):
            raise ReviewRequired("fixture.date must identify a valid, whole-second instant with a timezone.") from None
    if timestamp is not None:
        try:
            if type(timestamp) is not int:
                raise ValueError
            # Epoch arithmetic also supports pre-1970 dates on Windows.
            unix_date = datetime(1970, 1, 1, tzinfo=timezone.utc) + timedelta(seconds=timestamp)
        except (ValueError, OverflowError):
            raise ReviewRequired("fixture.timestamp must be a valid integer Unix timestamp in seconds.") from None
    if parsed_date is not None and unix_date is not None and parsed_date != unix_date:
        raise ReviewRequired("fixture.date and fixture.timestamp disagree; neither value was guessed or corrected.")
    kickoff = parsed_date if parsed_date is not None else unix_date
    if kickoff is None:
        if status in {"postponed", "cancelled"}:
            return None
        raise ReviewRequired("A known kickoff date or Unix timestamp is required for this status.")
    return kickoff.isoformat(timespec="seconds").replace("+00:00", "Z")


def convert_fixture(record, verified_team_mapping, *, is_demo=None, competition_catalog=None):
    """Return one 21-field match or raise ReviewRequired; never mutate the input.

    verified_team_mapping is {numeric_api_id: 'wikidata_Q...'}, supplied only
    after identity verification. is_demo must be explicitly True or False.
    Fictional records get demo IDs/source and null external source IDs, in line
    with the existing schema. Real-source mode preserves external IDs as strings.
    An optional reviewed competition catalog enables strict competition mapping.
    Without it the legacy null competitionId behavior is preserved. Demo data
    never acquires a real competition association from provider IDs.
    """
    if not isinstance(record, dict):
        raise ReviewRequired("One provider fixture object is required, not an API response envelope or array.")
    if type(is_demo) is not bool:
        raise ReviewRequired("Explicitly choose is_demo=True for fictional data or is_demo=False for real-source data.")
    if "isDemo" in record and type(record["isDemo"]) is not bool:
        raise ReviewRequired("An input demonstration marker must be a boolean; uncertain provenance requires review.")
    if record.get("isDemo") is True and not is_demo:
        raise ReviewRequired("Input marked as fictional cannot be converted as real-source data.")
    validate_team_mapping(verified_team_mapping)
    competition_id = None
    if competition_catalog is not None:
        try:
            validate_catalog(competition_catalog)
        except ValidationError as error:
            raise ReviewRequired(f"Competition catalog: {error}") from None

    fixture = object_field(record, "fixture", "fixture")
    league = object_field(record, "league", "league")
    teams = object_field(record, "teams", "teams")
    status_data = object_field(fixture, "status", "fixture.status")
    fixture_id = positive_id(fixture.get("id"), "fixture.id")
    league_id = positive_id(league.get("id"), "league.id")
    if competition_catalog is not None and not is_demo:
        try:
            competition_id = resolve_competition(competition_catalog, league_id)["competitionId"]
        except ValidationError as error:
            raise ReviewRequired(f"Competition mapping: {error}") from None
    team_ids = []
    for side in ("home", "away"):
        team = object_field(teams, side, f"teams.{side}")
        api_id = positive_id(team.get("id"), f"teams.{side}.id")
        if api_id not in verified_team_mapping:
            raise ReviewRequired(f"teams.{side}.id has no supplied verified mapping; no name-based guess was made.")
        team_ids.append(verified_team_mapping[api_id])
    if team_ids[0] == team_ids[1]:
        raise ReviewRequired("Home and away must identify different verified clubs.")

    short = status_data.get("short")
    if not isinstance(short, str) or short not in STATUS_MAP:
        raise ReviewRequired("fixture.status.short is unsupported or uncertain; TBD/SUSP/INT/ABD/AWD/WO require a schema decision.")
    status = STATUS_MAP[short]
    season = league.get("season")
    if type(season) is not int or not 1000 <= season <= 9999:
        raise ReviewRequired("league.season must be a four-digit integer.")
    try:
        require_text(league.get("name"), "league.name")
    except ValidationError as error:
        raise ReviewRequired(str(error)) from None

    goals = object_field(record, "goals", "goals", optional=True)
    score = object_field(record, "score", "score", optional=True)
    periods = {}
    for period in ("fulltime", "extratime", "penalty"):
        pair = object_field(score, period, f"score.{period}", optional=True)
        # Missing or explicit-null scores stay unknown. Never infer totals,
        # subtract periods, replace missing data with zero or add a shootout.
        periods[period] = (pair.get("home"), pair.get("away"))

    match = {
        "matchId": f"{'demo' if is_demo else 'match'}_api_football_fixture_{fixture_id}",
        "homeTeamId": team_ids[0], "awayTeamId": team_ids[1],
        "competitionId": competition_id,
        "sourceCompetitionId": None if is_demo else str(league_id),
        "competition": league["name"], "season": str(season),
        "kickoffUtc": convert_kickoff(fixture, status),
        "status": status, "finishType": FINISH_TYPES.get(short),
        "homeScore": goals.get("home"), "awayScore": goals.get("away"),
        "regularTimeHomeScore": periods["fulltime"][0], "regularTimeAwayScore": periods["fulltime"][1],
        "extraTimeHomeScore": periods["extratime"][0], "extraTimeAwayScore": periods["extratime"][1],
        "penaltyHomeScore": periods["penalty"][0], "penaltyAwayScore": periods["penalty"][1],
        "isDemo": is_demo, "source": "demo" if is_demo else "API-Football",
        "sourceMatchId": None if is_demo else str(fixture_id),
    }
    try:
        validate_match(match)
    except ValidationError as error:
        raise ReviewRequired(f"Converted values are incompatible with the current schema: {error}") from None
    return match
