"""Phase F: validate curated highlight metadata and build offline event timelines.

No video is downloaded, opened or uploaded. An authorized flag records the
caller's rights review; it does not independently establish a media licence.
"""

import copy
import math
import re
from urllib.parse import urlsplit

from match_event_service import (event_clock, prepare_event_bundles,
                                 validate_curated_provenance, validate_related_id)
from validate_match_schema import ValidationError, require_text


HIGHLIGHT_FIELDS = {"highlightId", "matchId", "title", "mediaType", "mediaReference",
                    "durationSeconds", "rightsStatus", "rightsEvidence", "markers", "isDemo", "source"}
MARKER_FIELDS = {"eventId", "videoSeconds"}


def validate_seconds(value, field, *, positive=False):
    # bool, NaN, infinity and enormous overflowing integers are not video times.
    valid = type(value) in (int, float)
    if valid:
        try:
            valid = math.isfinite(value) and (value > 0 if positive else value >= 0)
        except OverflowError:
            valid = False
    if not valid:
        raise ValidationError(f"{field} must be a finite {'positive' if positive else 'nonnegative'} number.")


def validate_media_reference(media_type, reference):
    require_text(reference, "Media reference")
    if media_type == "bundle":
        # A resource name for a future iOS app bundle, never a machine file path.
        if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_-]*\.(?:mp4|mov|m4v)", reference):
            raise ValidationError("Bundle media must be a simple mp4, mov or m4v resource filename.")
    elif media_type == "https":
        try:
            parsed = urlsplit(reference)
            port = parsed.port  # Validate malformed ports too, without making a request.
            valid = (parsed.scheme == "https" and bool(parsed.hostname)
                     and parsed.username is None and parsed.password is None
                     and not parsed.query and not parsed.fragment
                     and not any(character.isspace() for character in reference)
                     and "\\" not in reference and (port is None or 0 < port <= 65535))
        except ValueError:
            valid = False
        if not valid:
            raise ValidationError("HTTPS media must not contain credentials, query parameters or fragments.")
    else:
        raise ValidationError("Media type must be bundle or https when a reference is supplied.")


def validate_highlight(highlight, match, events):
    if not isinstance(highlight, dict) or set(highlight) != HIGHLIGHT_FIELDS:
        raise ValidationError("A highlight must contain exactly its eleven managed fields.")
    if highlight["matchId"] != match["matchId"]:
        raise ValidationError("The highlight references a different match.")
    validate_related_id(highlight["highlightId"], highlight["matchId"], "highlight")
    validate_curated_provenance(highlight, match)
    require_text(highlight["title"], "Highlight title")
    rights = highlight["rightsStatus"]
    if not isinstance(rights, str) or rights not in {"unconfirmed", "authorized"}:
        raise ValidationError("Highlight rightsStatus must be unconfirmed or authorized.")
    if rights == "unconfirmed":
        if any(highlight[field] is not None for field in ("mediaType", "mediaReference", "rightsEvidence")):
            raise ValidationError("REVIEW REQUIRED: Unconfirmed media must have null reference, type and rights evidence.")
    else:
        require_text(highlight["rightsEvidence"], "Public rights-review evidence")
        validate_media_reference(highlight["mediaType"], highlight["mediaReference"])

    duration = highlight["durationSeconds"]
    if duration is not None:
        validate_seconds(duration, "Video duration", positive=True)
    markers = highlight["markers"]
    if not isinstance(markers, list):
        raise ValidationError("Highlight markers must be an array, which may be empty.")
    if markers and duration is None:
        raise ValidationError("REVIEW REQUIRED: Marker bounds cannot be checked without a supplied video duration.")
    seen = set()
    for marker in markers:
        if not isinstance(marker, dict) or set(marker) != MARKER_FIELDS:
            raise ValidationError("A video marker must contain exactly eventId and videoSeconds.")
        event_id = marker["eventId"]
        if not isinstance(event_id, str) or event_id not in events:
            raise ValidationError("A video marker references an event absent from the validated event records.")
        if events[event_id]["matchId"] != match["matchId"]:
            raise ValidationError("A video marker cannot reference another match's event.")
        if event_id in seen:
            raise ValidationError("An event may appear only once in each highlight timeline.")
        seen.add(event_id)
        validate_seconds(marker["videoSeconds"], "Video marker")
        if marker["videoSeconds"] > duration:
            raise ValidationError("A video marker exceeds the supplied video duration.")


def build_timeline(highlight, events):
    """Read DTO: football clock and clip seconds are independent coordinates."""
    timeline = []
    for marker in sorted(highlight["markers"], key=lambda row: (row["videoSeconds"], row["eventId"])):
        event = events[marker["eventId"]]
        timeline.append({"eventId": event["eventId"], "videoSeconds": marker["videoSeconds"],
                         "matchClock": event_clock(event), "label": event["label"],
                         "eventType": event["eventType"], "teamId": event["teamId"], "playerId": event["playerId"]})
    return {"highlightId": highlight["highlightId"], "title": highlight["title"],
            "durationSeconds": highlight["durationSeconds"],
            "playbackEligible": highlight["rightsStatus"] == "authorized", "markers": timeline}


def prepare_highlight_bundles(matches, teams, players, catalog, events, highlights):
    """Validate every link before returning match, event and highlight read DTOs.

    Events/highlights remain separate records referencing matchId. Do not embed
    these growing lists or derived read DTOs into a Firestore match document.
    """
    prepared = prepare_event_bundles(matches, teams, players, catalog, events)
    match_index = {item["match"]["matchId"]: item for item in prepared}
    event_index = {event["eventId"]: event for item in prepared for event in item["events"]}
    if not isinstance(highlights, list):
        raise ValidationError("Highlights must be an array, which may be empty.")
    seen = set()
    for highlight in highlights:
        match_id = highlight.get("matchId") if isinstance(highlight, dict) else None
        if not isinstance(match_id, str) or match_id not in match_index:
            raise ValidationError("A highlight references a match absent from this batch.")
        validate_highlight(highlight, match_index[match_id]["match"], event_index)
        if highlight["highlightId"] in seen:
            raise ValidationError("Duplicate highlightId; the complete batch was stopped.")
        seen.add(highlight["highlightId"])
    for item in prepared:
        rows = [copy.deepcopy(row) for row in highlights if row["matchId"] == item["match"]["matchId"]]
        rows.sort(key=lambda row: row["highlightId"])
        item["highlights"] = rows
        item["highlightTimelines"] = [build_timeline(row, event_index) for row in rows]
    return prepared


def playback_target(prepared, highlight_id, event_id):
    """Return a future player's seek arguments from an already validated bundle.

    This only checks supplied rights metadata and marker bounds. Actual media
    availability, the rights claim and playback need separate verification.
    """
    for highlight in prepared["highlights"]:
        if highlight["highlightId"] == highlight_id:
            if highlight["rightsStatus"] != "authorized":
                raise ValidationError("REVIEW REQUIRED: Playback is unavailable until media rights are confirmed.")
            for marker in highlight["markers"]:
                if marker["eventId"] == event_id:
                    return {"matchId": highlight["matchId"], "highlightId": highlight_id, "eventId": event_id,
                            "mediaType": highlight["mediaType"], "mediaReference": highlight["mediaReference"],
                            "videoSeconds": marker["videoSeconds"]}
            raise ValidationError("The selected event has no supplied position in this highlight.")
    raise ValidationError("The selected highlight is absent from this match's prepared records.")
