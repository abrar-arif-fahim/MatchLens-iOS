"""Read-only Firestore import preview for the local MatchLens match example."""

import json
import math
from datetime import datetime, timezone

from firebase_admin.exceptions import FirebaseError
from google.api_core.exceptions import GoogleAPICallError, PermissionDenied, Unauthenticated
from google.auth.exceptions import GoogleAuthError

# These helpers have main guards. Importing them makes no database/API requests.
from validate_match_schema import FIELDS, ValidationError, load_match, validate_match
from validate_match_team_references import read_team_reference
from preview_multiple_teams import (
    DRY_RUN_MESSAGE, MISSING, PreviewError, display_value, get_firestore_client,
)


MATCH_FIELDS = tuple(sorted(FIELDS))


def prepare_match_data(match):
    # The schema has already validated the entire input. Copy only managed fields.
    data = {field: match[field] for field in MATCH_FIELDS}
    if data["kickoffUtc"] is not None:
        # A future Firestore document should use a Timestamp, not a date string.
        data["kickoffUtc"] = datetime.strptime(
            data["kickoffUtc"], "%Y-%m-%dT%H:%M:%SZ"
        ).replace(tzinfo=timezone.utc)
    return data


def values_match(existing, proposed):
    if isinstance(proposed, datetime):
        # Firestore returns a datetime subclass. Compare instants, preserving any
        # extra nanoseconds, rather than rejecting it for having a different type.
        return (
            isinstance(existing, datetime) and existing == proposed
            and getattr(existing, "nanosecond", existing.microsecond * 1000)
            == proposed.microsecond * 1000
        )
    # Python considers True == 1 and 1.0 == 1; those are different schema types.
    return type(existing) is type(proposed) and existing == proposed


def compare_match(data, snapshot):
    # A missing matches collection also returns a missing document snapshot.
    if not snapshot.exists:
        return "CREATE", []
    if snapshot.id != data["matchId"]:
        raise ValidationError("The returned match document ID is inconsistent.")
    current = snapshot.to_dict()
    if not isinstance(current, dict):
        raise ValidationError("The existing match contains unexpected document data.")
    differences = []
    for field in MATCH_FIELDS:
        existing = current.get(field, MISSING)
        if not values_match(existing, data[field]):
            differences.append((field, existing, data[field]))
    return ("UPDATE" if differences else "NO CHANGE"), differences


def display_match_value(value):
    if isinstance(value, datetime):
        if value.utcoffset() is None:
            return "<datetime without a timezone>"
        utc_value = value.astimezone(timezone.utc)
        # Show nanoseconds when provided by the Firestore datetime subclass.
        nanoseconds = getattr(value, "nanosecond", value.microsecond * 1000)
        text = utc_value.strftime("%Y-%m-%dT%H:%M:%S")
        if nanoseconds:
            text += f".{nanoseconds:09d}"
        return f"Timestamp({text}Z)"
    if type(value) in (int, float, bool):
        if type(value) is float and not math.isfinite(value):
            return "<non-finite number>"
        return json.dumps(value)
    # Reuse escaped string/null/missing display and sensitive-content filtering.
    return display_value(value)


def display_preview(match_id, operation, differences):
    print(f"\n{operation}: matches/{match_id}")
    for field, existing, proposed in differences:
        print(f"  {field}:")
        print(f"    Existing: {display_match_value(existing)}")
        print(f"    Proposed: {display_match_value(proposed)}")
    print(
        f"\nSummary: CREATE {int(operation == 'CREATE')} | "
        f"UPDATE {int(operation == 'UPDATE')} | "
        f"NO CHANGE {int(operation == 'NO CHANGE')}"
    )


def main():
    try:
        # Validate everything locally before initializing Firebase or reading data.
        match = load_match()
        validate_match(match)
        data = prepare_match_data(match)
        print("Local match schema: VALID")
        if match["isDemo"]:
            print("DEMO ONLY: Fictional fixture data; never present it as a real match or result.")
        else:
            print("Structure only: real-match facts and source reuse permissions were not verified.")

        db = get_firestore_client()
        # Recheck both teams each time. A failed reference prevents a match preview.
        teams = []
        for role, field in (("Home", "homeTeamId"), ("Away", "awayTeamId")):
            document_id = match[field]
            name = read_team_reference(db, document_id)
            teams.append((role, document_id, name))

        snapshot = db.collection("matches").document(match["matchId"]).get(
            field_paths=MATCH_FIELDS, timeout=20, retry=None
        )
        operation, differences = compare_match(data, snapshot)
        # Only display a complete plan after both team reads and the match read.
        for role, document_id, name in teams:
            print(f"{role}: teams/{document_id} | {name} | VALID")
        display_preview(match["matchId"], operation, differences)
        return 0

    except (ValidationError, PreviewError) as error:
        print(f"Preview stopped: {error}")
    except GoogleAuthError:
        print("Preview stopped: Firebase authentication failed. Check the configured service account.")
    except (PermissionDenied, Unauthenticated):
        print("Preview stopped: Firestore access denied. Check the service account's read permissions.")
    except (GoogleAPICallError, FirebaseError, TimeoutError):
        print("Preview stopped: Firestore read failed. Check your connection, Firebase project and database.")
    except OSError:
        print("Preview stopped: Could not access the configured credentials file or connect to Firestore.")
    except (ValueError, TypeError, KeyError, AttributeError):
        # Never print raw SDK errors, credential paths or arbitrary remote data.
        print("Preview stopped: Invalid Firebase configuration or unexpected document data.")
    except KeyboardInterrupt:
        print("\nCANCELLED: Match preview interrupted.")
    finally:
        print(f"\n{DRY_RUN_MESSAGE}")
    return 1


# No upload option or writes. Run manually to perform the three document reads.
if __name__ == "__main__":
    raise SystemExit(main())
