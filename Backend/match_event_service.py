"""Phase E: curate and validate match/player event links without I/O or writes."""

import copy
import re

from import_multiple_players import PreviewError, validate_player_records
from match_service import prepare_matches, validate_document_path
from preview_match_import import MISSING, values_match
from validate_match_schema import SLUG, ValidationError, require_text


EVENT_FIELDS = {"eventId", "matchId", "teamId", "playerId", "eventType", "matchMinute",
                "addedTime", "label", "isDemo", "source"}
EVENT_TYPES = {"goal", "yellowCard", "redCard", "save", "substitution", "other"}


def related_prefix(match_id, kind):
    validate_document_path("matches", match_id)
    if kind not in ("event", "highlight"):
        raise ValidationError("Only event and highlight child identifiers are supported.")
    prefix = "demo_" if match_id.startswith("demo_") else ""
    # Double underscore separates two slugs unambiguously; neither slug can
    # contain it. This avoids collisions such as parent a_b/key c vs a/key b_c.
    return f"{prefix}{kind}_{match_id.split('_', 1)[1]}__"


def make_related_id(match_id, kind, stable_key):
    require_text(stable_key, "Stable child key")
    if not re.fullmatch(SLUG, stable_key):
        raise ValidationError("Stable child keys must use lowercase words/numbers separated by underscores.")
    identifier = related_prefix(match_id, kind) + stable_key
    require_text(identifier, "Child document ID")
    return identifier


def validate_related_id(identifier, match_id, kind):
    require_text(identifier, "Child document ID")
    prefix = related_prefix(match_id, kind)
    if not identifier.startswith(prefix) or not re.fullmatch(SLUG, identifier[len(prefix):]):
        raise ValidationError("The child document ID does not match its parent match or record type.")


def validate_curated_provenance(record, match):
    if type(record["isDemo"]) is not bool or record["isDemo"] != match["isDemo"]:
        raise ValidationError("Curated data and its match must have the same boolean isDemo value.")
    expected = "demo" if match["isDemo"] else "manual"
    if record["source"] != expected:
        raise ValidationError("Curated records must use demo or manual provenance appropriate to their match.")


def index_players(players):
    try:
        validated = validate_player_records({"players": players}, max_records=None)
    except PreviewError as error:
        raise ValidationError(str(error)) from None
    return {identifier: dict(data) for identifier, data in validated}


def validate_event(event, match, players):
    if not isinstance(event, dict) or set(event) != EVENT_FIELDS:
        raise ValidationError("An event must contain exactly its ten managed fields.")
    if event["matchId"] != match["matchId"]:
        raise ValidationError("The event references a different match.")
    validate_related_id(event["eventId"], event["matchId"], "event")
    validate_curated_provenance(event, match)
    kind = event["eventType"]
    if not isinstance(kind, str) or kind not in EVENT_TYPES:
        raise ValidationError("Unsupported match event type; manual review is required.")
    require_text(event["label"], "Event label")
    if match["status"] not in {"live", "finished"}:
        raise ValidationError("Unplayed, postponed or cancelled matches cannot contain occurred events.")
    team_id, player_id = event["teamId"], event["playerId"]
    if team_id is not None and team_id not in (match["homeTeamId"], match["awayTeamId"]):
        raise ValidationError("The event team does not participate in this match.")
    if kind != "other" and team_id is None:
        raise ValidationError("This event type requires a known participating team.")
    if player_id is not None:
        if not isinstance(player_id, str) or player_id not in players:
            raise ValidationError("The event player is absent from the validated player records.")
        if team_id is None:
            raise ValidationError("An event naming a player must also identify its team.")
    for field in ("matchMinute", "addedTime"):
        value = event[field]
        if value is not None and (type(value) is not int or value < 0):
            raise ValidationError("Match minute and added time must be nonnegative integers or null.")
    if event["matchMinute"] is None and event["addedTime"] is not None:
        raise ValidationError("Added time cannot be supplied without a known match minute.")


def event_clock(event):
    minute, added = event["matchMinute"], event["addedTime"]
    if minute is None:
        return None
    return f"{minute}+{added}" if added else str(minute)


def prepare_event_bundles(matches, teams, players, catalog, events):
    """Join existing match preparation to validated curated events and players.

    These are read DTOs, not growing arrays to embed in the match document.
    Identity existence does not prove roster membership or real event occurrence.
    Event lists may be incomplete; never recalculate match scores from them.
    """
    prepared = prepare_matches(matches, teams, catalog)
    player_index = index_players(players)
    match_index = {item["match"]["matchId"]: item for item in prepared}
    if not isinstance(events, list):
        raise ValidationError("Events must be an array, which may be empty.")
    seen = set()
    for event in events:
        match_id = event.get("matchId") if isinstance(event, dict) else None
        if not isinstance(match_id, str) or match_id not in match_index:
            raise ValidationError("An event references a match absent from this batch.")
        validate_event(event, match_index[match_id]["match"], player_index)
        if event["eventId"] in seen:
            raise ValidationError("Duplicate eventId; the complete event batch was stopped.")
        seen.add(event["eventId"])
    for item in prepared:
        rows = [copy.deepcopy(row) for row in events if row["matchId"] == item["match"]["matchId"]]
        # 45+10 precedes 46; added time is not added to the next period's clock.
        rows.sort(key=lambda row: (row["matchMinute"] is None, row["matchMinute"] or 0,
                                   row["addedTime"] or 0, row["eventId"]))
        item["events"] = rows
        item["eventPlayers"] = {row["playerId"]: dict(player_index[row["playerId"]])
                                for row in rows if row["playerId"] is not None}
    return prepared


def managed_values_equal(existing, proposed):
    # Preserve typed comparison inside nested future highlight-marker arrays.
    if isinstance(proposed, dict):
        return (type(existing) is dict and set(existing) == set(proposed)
                and all(managed_values_equal(existing[key], value) for key, value in proposed.items()))
    if isinstance(proposed, list):
        return (type(existing) is list and len(existing) == len(proposed)
                and all(managed_values_equal(old, new) for old, new in zip(existing, proposed)))
    return values_match(existing, proposed)


def preview_curated_records(records, existing_documents, id_field):
    """Compare already validated event/highlight records locally. Never write."""
    if id_field not in ("eventId", "highlightId") or not isinstance(existing_documents, dict):
        raise ValidationError("Supply a local document dictionary and a curated record ID field.")
    if not isinstance(records, list):
        raise ValidationError("Prepared records must be an array.")
    plan, seen = [], set()
    for record in records:
        identifier = record.get(id_field) if isinstance(record, dict) else None
        require_text(identifier, id_field)
        if identifier in seen:
            raise ValidationError("Duplicate curated document ID; preview stopped.")
        seen.add(identifier)
        if identifier not in existing_documents:
            action, differences = "CREATE", []
        else:
            current = existing_documents[identifier]
            if not isinstance(current, dict):
                raise ValidationError("An existing curated document must be an object.")
            differences = [(key, current.get(key, MISSING), copy.deepcopy(value))
                           for key, value in record.items()
                           if not managed_values_equal(current.get(key, MISSING), value)]
            action = "UPDATE" if differences else "NO CHANGE"
        plan.append({"documentId": identifier, "operation": action, "differences": differences})
    return plan
