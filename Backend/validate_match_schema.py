"""Validate one local match example. No network, Firebase or file writes."""

import json
import re
from datetime import datetime
from pathlib import Path


INPUT_FILE = Path(__file__).resolve().parent / "input" / "match_schema_example.json"
FIELDS = {
    "matchId", "homeTeamId", "awayTeamId", "competitionId", "competition",
    "season", "kickoffUtc", "status", "homeScore", "awayScore", "isDemo",
    "source", "sourceMatchId",
    "sourceCompetitionId", "finishType", "regularTimeHomeScore", "regularTimeAwayScore",
    "extraTimeHomeScore", "extraTimeAwayScore", "penaltyHomeScore", "penaltyAwayScore",
}
STATUSES = {"scheduled", "live", "finished", "postponed", "cancelled"}
FINISH_TYPES = {"regularTime", "extraTime", "penalties"}
SLUG = r"[a-z0-9]+(?:_[a-z0-9]+)*"


class ValidationError(ValueError):
    """A readable explanation of an invalid match or input file."""


def reject_duplicate_fields(pairs):
    # json.load normally keeps the last duplicate key, hiding possible mistakes.
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValidationError("The JSON contains a duplicate field.")
        result[key] = value
    return result


def load_match(path=INPUT_FILE):
    try:
        with path.open(encoding="utf-8-sig") as input_file:
            return json.load(input_file, object_pairs_hook=reject_duplicate_fields)
    except ValidationError:
        raise
    except FileNotFoundError:
        raise ValidationError("Match input file was not found.") from None
    except (ValueError, UnicodeError, RecursionError):
        raise ValidationError("The input must contain valid UTF-8 JSON.") from None
    except OSError:
        raise ValidationError("Could not read the match input. Check file permissions.") from None


def require_text(value, field):
    # Reject mistakes rather than silently trimming or replacing prepared data.
    if (not isinstance(value, str) or not value.strip() or value != value.strip()
            or len(value) > 200 or any(ord(character) < 32 for character in value)
            or value.casefold() in {"unknown", "n/a", "null", "none"}):
        raise ValidationError(f"{field} must be a nonempty, trimmed public string.")


def validate_team_reference_data(document_id, team):
    """Shared local/Firestore identifier check; a name is not identity evidence."""
    if not isinstance(document_id, str) or not re.fullmatch(r"wikidata_Q[1-9][0-9]*", document_id):
        raise ValidationError("Team document ID must follow the wikidata_Q-number format.")
    if not isinstance(team, dict):
        raise ValidationError(f"teams/{document_id} contains unexpected document data.")
    if team.get("teamId") != document_id:
        raise ValidationError(f"teams/{document_id}: teamId is missing or inconsistent.")
    if team.get("wikidataId") != document_id.removeprefix("wikidata_"):
        raise ValidationError(f"teams/{document_id}: wikidataId is missing or inconsistent.")


def validate_kickoff(value, status):
    # A postponed/cancelled fixture may have no known kickoff. Never guess one.
    if value is None and status in {"postponed", "cancelled"}:
        return
    if not isinstance(value, str) or not re.fullmatch(
        r"[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}Z", value
    ):
        raise ValidationError("kickoffUtc must use YYYY-MM-DDTHH:MM:SSZ in UTC.")
    try:
        # The Z above explicitly means UTC; this check also rejects invalid dates.
        datetime.strptime(value, "%Y-%m-%dT%H:%M:%SZ")
    except ValueError:
        raise ValidationError("kickoffUtc contains an invalid calendar date or time.") from None


def validate_scores(home_score, away_score, status):
    scores = (home_score, away_score)
    for score in scores:
        # bool is a subclass of int in Python, so check the exact type.
        if score is not None and (type(score) is not int or score < 0):
            raise ValidationError("Scores must be nonnegative integers or null, never booleans.")
    if (home_score is None) != (away_score is None):
        raise ValidationError("Both scores must be known together, or both must be null.")
    if status in {"scheduled", "postponed", "cancelled"} and scores != (None, None):
        raise ValidationError("Scheduled, postponed and cancelled matches must have null scores.")
    if status == "finished" and home_score is None:
        raise ValidationError("A finished match must have both final scores.")
    # A live feed can have missing scores. null must not be invented as 0.


def validate_score_details(status, finish_type, home_score, away_score,
                           regular_time, extra_time, penalties):
    """Check supplied totals/periods without calculating or replacing any field."""
    if not isinstance(status, str) or status not in STATUSES:
        raise ValidationError("Score details require an allowed match status.")
    validate_scores(home_score, away_score, status)
    for label, pair in (("regular-time", regular_time), ("extra-time", extra_time), ("penalty", penalties)):
        if not isinstance(pair, (tuple, list)) or len(pair) != 2:
            raise ValidationError(f"The {label} score must be a home/away pair.")
        try:
            validate_scores(pair[0], pair[1], "live")  # Unknown pairs may stay null.
        except ValidationError as error:
            raise ValidationError(f"{label} score: {error}") from None

    if status == "finished":
        if not isinstance(finish_type, str) or finish_type not in FINISH_TYPES:
            raise ValidationError("A finished match requires regularTime, extraTime or penalties as finishType.")
    elif finish_type is not None:
        raise ValidationError("finishType must be null until a match is finished.")

    if status in {"scheduled", "postponed", "cancelled"}:
        if any(value is not None for pair in (regular_time, extra_time, penalties) for value in pair):
            raise ValidationError("Unplayed/postponed/cancelled matches must have null period scores.")
        return

    if finish_type == "regularTime" and any(value is not None for pair in (extra_time, penalties) for value in pair):
        raise ValidationError("A regular-time finish cannot contain extra-time or shootout scores.")
    if finish_type == "extraTime" and any(value is not None for value in penalties):
        raise ValidationError("An extra-time finish cannot contain shootout scores.")
    if finish_type == "penalties" and penalties[0] is not None and penalties[0] == penalties[1]:
        raise ValidationError("A completed penalty shootout cannot have a tied tally.")

    for side, total in enumerate((home_score, away_score)):
        regular, extra = regular_time[side], extra_time[side]
        if total is None:
            continue  # Never derive an unknown total from available periods.
        if ((regular is not None and regular > total)
                or (extra is not None and extra > total)):
            raise ValidationError("A period's goals cannot exceed the supplied match total.")
        if finish_type == "regularTime" and regular is not None and regular != total:
            raise ValidationError("Regular-time and final scores disagree for a regular-time finish.")
        if regular is not None and extra is not None and regular + extra != total:
            raise ValidationError("Supplied regular-time plus extra-time-period goals disagree with final/current goals.")
    # Shootout tallies are never added to goals. Do not require a drawn match:
    # a two-leg tie may lead to penalties despite a non-drawn second-leg score.


def validate_match(match):
    if not isinstance(match, dict) or set(match) != FIELDS:
        raise ValidationError(f"A match must contain exactly the {len(FIELDS)} current schema fields.")
    for field in (
        "matchId", "homeTeamId", "awayTeamId", "competition",
        "season", "status", "source",
    ):
        require_text(match[field], field)

    for field in ("homeTeamId", "awayTeamId"):
        if not re.fullmatch(r"wikidata_Q[1-9][0-9]*", match[field]):
            raise ValidationError(f"{field} must follow the wikidata_Q-number format.")
    if match["homeTeamId"] == match["awayTeamId"]:
        raise ValidationError("Home and away team IDs must be different.")
    if match["status"] not in STATUSES:
        raise ValidationError("status must be scheduled, live, finished, postponed or cancelled.")
    if type(match["isDemo"]) is not bool:
        raise ValidationError("isDemo must be a JSON boolean.")

    # Internal match IDs stay separate from the original provider's match ID.
    match_prefix = "demo_" if match["isDemo"] else "match_"
    competition_prefix = "demo_competition_" if match["isDemo"] else "competition_"
    if not re.fullmatch(match_prefix + SLUG, match["matchId"]):
        raise ValidationError("matchId must use demo_<slug> or match_<slug> according to isDemo.")
    if match["competitionId"] is not None:
        require_text(match["competitionId"], "competitionId")
        if not re.fullmatch(competition_prefix + SLUG, match["competitionId"]):
            raise ValidationError("competitionId must be null or use the internal prefix appropriate to isDemo.")
    if match["sourceCompetitionId"] is not None:
        require_text(match["sourceCompetitionId"], "sourceCompetitionId")
        if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_-]{0,99}", match["sourceCompetitionId"]):
            raise ValidationError("sourceCompetitionId must be a public provider ID, not a URL.")

    if match["isDemo"]:
        if (match["source"] != "demo" or match["sourceMatchId"] is not None
                or match["sourceCompetitionId"] is not None):
            raise ValidationError("Demo matches require source demo and null provider match/competition IDs.")
    else:
        if re.search(r"\bdemo\b", match["source"], flags=re.IGNORECASE):
            raise ValidationError("A real match cannot identify a demo source.")
        require_text(match["sourceMatchId"], "sourceMatchId")
        if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_-]{0,99}", match["sourceMatchId"]):
            raise ValidationError("sourceMatchId must be a public source ID, not a URL or credentials.")

    validate_kickoff(match["kickoffUtc"], match["status"])
    validate_score_details(
        match["status"], match["finishType"], match["homeScore"], match["awayScore"],
        (match["regularTimeHomeScore"], match["regularTimeAwayScore"]),
        (match["extraTimeHomeScore"], match["extraTimeAwayScore"]),
        (match["penaltyHomeScore"], match["penaltyAwayScore"]),
    )


def main():
    try:
        match = load_match()
        validate_match(match)
    except ValidationError as error:
        # Only print our own explanations, never arbitrary input or raw errors.
        print(f"FAILED: {error}")
        return 1

    print("SUCCESS: Match schema passed local structure and value validation.")
    if match["isDemo"]:
        print("DEMO ONLY: The fixture and kickoff are fictional, not verified football information.")
    else:
        print("Structure only: real-match facts and source reuse permissions were not verified.")
    print("Team ID formats checked locally; Firestore document existence was not checked.")
    print("LOCAL VALIDATION ONLY - No external requests or database changes.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
