"""Read-only Firestore import preview for the prepared MatchLens teams."""

import json
import os
import re
from pathlib import Path

import firebase_admin
from firebase_admin import credentials, firestore
from firebase_admin.exceptions import FirebaseError
from google.api_core.exceptions import GoogleAPICallError, PermissionDenied, Unauthenticated
from google.auth.exceptions import GoogleAuthError
from validate_match_schema import reject_duplicate_fields


INPUT_FILE = Path(__file__).resolve().parent / "output" / "teams_prepared.json"
FIELDS = ("teamId", "wikidataId", "name", "shortName", "country", "source")
DRY_RUN_MESSAGE = "DRY RUN ONLY — No changes made to Firestore"
MISSING = object()


class PreviewError(ValueError):
    """A safe explanation of an input or local configuration problem."""


def sensitive_text(value):
    # Keep unexpected credential blocks, paths and token-like strings out of logs.
    return len(value) > 200 or re.search(
        r"-----BEGIN|private[_ -]?key|api[_ -]?key|access[_ -]?token|"
        r"password|client_secret|https?://|[A-Za-z]:[\\/]|"
        r"\b[A-Za-z0-9_-]{24,}\b",
        value,
        flags=re.IGNORECASE,
    ) is not None


def load_teams():
    # Validate the ENTIRE file before initializing Firebase or making requests.
    try:
        with INPUT_FILE.open(encoding="utf-8-sig") as input_file:
            data = json.load(input_file, object_pairs_hook=reject_duplicate_fields)
    except FileNotFoundError:
        raise PreviewError("Input file not found: Backend/output/teams_prepared.json.") from None
    except (ValueError, UnicodeError):
        raise PreviewError("The prepared input must contain valid UTF-8 JSON.") from None
    except OSError:
        raise PreviewError("Could not read the prepared input. Check file permissions.") from None

    return validate_team_records(data)


def validate_team_records(data):
    """Reuse the six-field contract for caller-supplied local data, without I/O."""

    records = data.get("teams") if isinstance(data, dict) else None
    if not isinstance(records, list):
        raise PreviewError("The JSON must contain a teams array.")
    teams = []
    seen_ids = set()
    for index, record in enumerate(records, start=1):
        if not isinstance(record, dict) or set(record) != set(FIELDS):
            raise PreviewError(f"Team {index} must contain exactly the six managed fields.")
        team = {}
        for field in FIELDS:
            value = record[field]
            if not isinstance(value, str) or not value.strip():
                raise PreviewError(f"Team {index}: {field} must be a nonempty string.")
            if sensitive_text(value) or any(ord(character) < 32 for character in value):
                raise PreviewError(f"Team {index}: {field} contains unexpected non-public content.")
            team[field] = value
        if not re.fullmatch(r"Q[1-9][0-9]*", team["wikidataId"]):
            raise PreviewError(f"Team {index}: wikidataId must be a valid Q-number.")
        if team["teamId"] != f"wikidata_{team['wikidataId']}":
            raise PreviewError(f"Team {index}: teamId does not match wikidataId.")
        if team["source"] != "Wikidata":
            raise PreviewError(f"Team {index}: source must be exactly Wikidata.")
        if team["teamId"] in seen_ids:
            raise PreviewError(f"Team {index}: duplicate teamId; preview stopped.")
        seen_ids.add(team["teamId"])
        # Preserve the prepared values exactly; do not silently normalize them.
        teams.append(team)
    return teams


def get_firestore_client():
    # Use ADC from the terminal, without displaying the path or credentials.
    credential_path = os.environ.get("GOOGLE_APPLICATION_CREDENTIALS")
    if not credential_path or not credential_path.strip():
        raise PreviewError("Set GOOGLE_APPLICATION_CREDENTIALS in this PowerShell terminal first.")
    if not Path(credential_path).is_file():
        raise PreviewError("The configured credentials file could not be found.")
    try:
        app = firebase_admin.get_app()
    except ValueError:
        app = firebase_admin.initialize_app(credentials.ApplicationDefault())
    return firestore.client(app=app)


def compare_team(team, snapshot):
    # A missing teams collection also produces a missing document snapshot.
    if not snapshot.exists:
        return "CREATE", []
    current = snapshot.to_dict() or {}
    differences = []
    for field in FIELDS:
        old_value = current.get(field, MISSING)
        if old_value != team[field]:
            differences.append((field, old_value, team[field]))
    return ("UPDATE" if differences else "NO CHANGE"), differences


def read_previews(db, teams):
    previews = []
    for team in teams:
        # Read only this target's managed fields; do not scan the collection.
        snapshot = db.collection("teams").document(team["teamId"]).get(
            field_paths=FIELDS, timeout=20, retry=None
        )
        operation, differences = compare_team(team, snapshot)
        previews.append((team, operation, differences))
    return previews


def display_value(value):
    if value is MISSING:
        return "<missing>"
    if value is None:
        return "null"
    if not isinstance(value, str):
        return "<unexpected non-string value hidden>"
    if sensitive_text(value):
        return "<potentially sensitive value hidden>"
    return json.dumps(value, ensure_ascii=False)


def display_previews(previews):
    rows = [("Team name", "Document ID", "Proposed operation")]
    totals = {"CREATE": 0, "UPDATE": 0, "NO CHANGE": 0}
    for team, operation, _ in previews:
        rows.append((team["name"], team["teamId"], operation))
        totals[operation] += 1
    widths = [max(len(row[column]) for row in rows) for column in range(3)]
    for index, row in enumerate(rows):
        print(" | ".join(value.ljust(width) for value, width in zip(row, widths)))
        if index == 0:
            print("-+-".join("-" * width for width in widths))
    for team, operation, differences in previews:
        if operation == "UPDATE":
            print(f"\nChanged fields for teams/{team['teamId']}:")
            for field, old_value, proposed_value in differences:
                print(f"  {field}:")
                print(f"    Existing: {display_value(old_value)}")
                print(f"    Proposed: {display_value(proposed_value)}")
    if not previews:
        print("The teams array is empty; there are no documents to preview.")
    print(
        f"\nSummary: CREATE {totals['CREATE']} | UPDATE {totals['UPDATE']} | "
        f"NO CHANGE {totals['NO CHANGE']}"
    )


def main():
    try:
        teams = load_teams()
        if teams:
            db = get_firestore_client()
            previews = read_previews(db, teams)
        else:
            previews = []
        # Never present a partial plan if any document read fails.
        display_previews(previews)
        return 0
    except PreviewError as error:
        print(f"Preview stopped: {error}")
    except GoogleAuthError:
        print("Firebase authentication failed. Check the configured service account.")
    except (PermissionDenied, Unauthenticated):
        print("Firestore access denied. Check the service account's read permissions.")
    except (GoogleAPICallError, FirebaseError, TimeoutError):
        print("Firestore read failed. Check your connection, Firebase project and database.")
    except OSError:
        print("Could not access the credentials file or connect to Firestore.")
    except (ValueError, TypeError, AttributeError):
        # Never print raw exceptions: they can contain private configuration.
        print("Invalid Firebase configuration or unexpected Firestore data. Preview stopped.")
    finally:
        print(f"\n{DRY_RUN_MESSAGE}")
    return 1


# Importing this file makes no requests. This script has no upload operation.
if __name__ == "__main__":
    raise SystemExit(main())
