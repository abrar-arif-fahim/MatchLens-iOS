"""Shared app-facing identities and projections. No credentials, I/O or writes."""

import copy
import re
import unicodedata
from datetime import datetime, timezone

from import_multiple_players import FIELDS as PLAYER_FIELDS, PreviewError as PlayerError, validate_player_records
from match_event_service import EVENT_FIELDS
from highlight_service import HIGHLIGHT_FIELDS
from match_service import TEAM_FIELDS, validate_document_path
from preview_multiple_teams import PreviewError as TeamError, validate_team_records
from validate_competition_schema import COMPETITION_FIELDS
from validate_match_schema import FIELDS as MATCH_FIELDS, SLUG, ValidationError, validate_match


PUBLIC_FIELDS = {"players": tuple(PLAYER_FIELDS), "teams": TEAM_FIELDS, "matches": tuple(sorted(MATCH_FIELDS)),
                 "competitions": tuple(sorted(COMPETITION_FIELDS)), "matchEvents": tuple(sorted(EVENT_FIELDS)),
                 "highlights": tuple(sorted(HIGHLIGHT_FIELDS))}
MAX_PAGE_SIZE = 50


class AccessError(ValidationError):
    """Authentication or ownership is missing; no private details are exposed."""


def require_uid(uid):
    if (not isinstance(uid, str) or not 1 <= len(uid) <= 128 or uid != uid.strip()
            or uid in {".", ".."} or "/" in uid or any(ord(char) < 33 for char in uid)):
        raise AccessError("A valid authenticated Firebase UID is required.")
    return uid


def require_owner(actor_uid, owner_uid):
    require_uid(actor_uid)
    require_uid(owner_uid)
    if actor_uid != owner_uid:
        raise AccessError("Access denied: private data belongs to a different authenticated user.")


def validate_public_path(collection, identifier):
    if not isinstance(collection, str):
        raise ValidationError("Invalid public collection.")
    if collection in ("teams", "competitions", "matches"):
        validate_document_path(collection, identifier)
        return
    if not isinstance(identifier, str) or len(identifier) > 200:
        raise ValidationError("Invalid public document identifier.")
    pattern = {"players": r"wikidata_Q[1-9][0-9]*",
               "matchEvents": r"(?:demo_)?event_" + SLUG + "__" + SLUG,
               "highlights": r"(?:demo_)?highlight_" + SLUG + "__" + SLUG}.get(collection)
    if pattern is None or not re.fullmatch(pattern, identifier):
        raise ValidationError("Invalid public collection or document identifier.")


def project(record, fields):
    if not isinstance(record, dict) or not set(fields).issubset(record):
        raise ValidationError("A stored document is missing required managed fields.")
    # Unrelated fields, provider-specific extras and credentials are never copied.
    return {field: copy.deepcopy(record[field]) for field in fields}


def utc_text(value, *, whole_seconds=False):
    """Serialize SDK Timestamps without losing nanoseconds or timezone meaning."""
    if isinstance(value, str):
        pattern = r"([0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2})(?:\.([0-9]{1,9}))?Z"
        match = re.fullmatch(pattern, value)
        if not match:
            raise ValidationError("A stored timestamp must be an aware Timestamp or UTC ISO string.")
        try:
            datetime.strptime(match[1], "%Y-%m-%dT%H:%M:%S")
        except ValueError:
            raise ValidationError("A stored timestamp contains an invalid date or time.") from None
        nano = int((match[2] or "").ljust(9, "0"))
        base = match[1]
    elif isinstance(value, datetime) and value.utcoffset() is not None:
        converted = value.astimezone(timezone.utc)
        base = converted.strftime("%Y-%m-%dT%H:%M:%S")
        nano = getattr(value, "nanosecond", converted.microsecond * 1000)
        if type(nano) is not int or not 0 <= nano < 1_000_000_000:
            raise ValidationError("A stored timestamp contains invalid fractional seconds.")
    else:
        raise ValidationError("A stored timestamp must include its timezone.")
    if whole_seconds:
        if nano:
            raise ValidationError("Match kickoff precision exceeds the current whole-second schema.")
        return base + "Z"
    return f"{base}.{nano:09d}Z"


def player_document(identifier, record):
    validate_public_path("players", identifier)
    data = project(record, PLAYER_FIELDS)
    try:
        validate_player_records({"players": [dict(data, documentId=identifier)]})
    except PlayerError as error:
        raise ValidationError(str(error)) from None
    return dict(data, playerId=identifier)


def team_document(identifier, record):
    validate_public_path("teams", identifier)
    data = project(record, TEAM_FIELDS)
    if data["teamId"] != identifier:
        raise ValidationError("The team document ID is inconsistent.")
    try:
        validate_team_records({"teams": [data]})
    except TeamError as error:
        raise ValidationError(str(error)) from None
    return data


def match_document(identifier, record):
    validate_public_path("matches", identifier)
    data = project(record, MATCH_FIELDS)
    if data["matchId"] != identifier:
        raise ValidationError("The match document ID is inconsistent.")
    if data["kickoffUtc"] is not None:
        data["kickoffUtc"] = utc_text(data["kickoffUtc"], whole_seconds=True)
    validate_match(data)
    return data


def search_text(value, *, max_length=100):
    if not isinstance(value, str) or len(value) > max_length or any(ord(char) < 32 for char in value):
        raise ValidationError("Search text must be a short single-line string.")
    decomposed = unicodedata.normalize("NFKD", value.casefold())
    return " ".join("".join(char for char in decomposed if not unicodedata.combining(char)).split())


def validate_page_size(value):
    if type(value) is not int or not 1 <= value <= MAX_PAGE_SIZE:
        raise ValidationError(f"Page size must be an integer between 1 and {MAX_PAGE_SIZE}.")
