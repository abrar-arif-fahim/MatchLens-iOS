"""Preview FC Barcelona's document, or apply it after explicit confirmation."""

import argparse
import json
import os
import re
from pathlib import Path

import firebase_admin
from firebase_admin import credentials, firestore
from firebase_admin.exceptions import FirebaseError
from google.api_core.exceptions import Aborted, GoogleAPICallError, PermissionDenied, Unauthenticated
from google.auth.exceptions import GoogleAuthError
from validate_match_schema import reject_duplicate_fields


INPUT_FILE = Path(__file__).resolve().parent / "output" / "team_barcelona.json"
DOCUMENT_ID = "wikidata_Q7156"
FIELDS = ("teamId", "wikidataId", "name", "shortName", "country", "source")
EXPECTED_VALUES = {
    "teamId": DOCUMENT_ID,
    "wikidataId": "Q7156",
    "name": "FC Barcelona",
    "country": "Spain",
    "source": "Wikidata",
}
DRY_RUN_MESSAGE = "DRY RUN ONLY — No changes made to Firestore"
MISSING = object()


class PreviewError(ValueError):
    """A safe explanation of a validation or local configuration problem."""


class ConflictError(PreviewError):
    """The document changed since the preview, so the import must be cancelled."""


def sensitive_text(value):
    # Public team fields should never contain credential blocks, paths or tokens.
    return len(value) > 200 or re.search(
        r"-----BEGIN|private[_ -]?key|api[_ -]?key|access[_ -]?token|"
        r"password|client_secret|https?://|[A-Za-z]:[\\/]|"
        r"\b[A-Za-z0-9_-]{24,}\b",
        value,
        flags=re.IGNORECASE,
    ) is not None


def load_team():
    # Validate locally before initializing Firebase or making any request.
    try:
        with INPUT_FILE.open(encoding="utf-8-sig") as input_file:
            record = json.load(input_file, object_pairs_hook=reject_duplicate_fields)
    except FileNotFoundError:
        raise PreviewError("Input file not found: Backend/output/team_barcelona.json.") from None
    except (ValueError, UnicodeError):
        raise PreviewError("The team file must contain valid UTF-8 JSON.") from None
    except OSError:
        raise PreviewError("Could not read the team file. Check file permissions.") from None

    if not isinstance(record, dict) or set(record) != set(FIELDS):
        raise PreviewError("The team JSON must contain exactly the six required team fields.")

    team = {}
    for field in FIELDS:
        value = record[field]
        if not isinstance(value, str) or not value.strip():
            raise PreviewError(f"{field} must be a nonempty string.")
        if sensitive_text(value) or any(ord(character) < 32 for character in value):
            raise PreviewError(f"{field} contains unexpected non-public content.")
        if field in EXPECTED_VALUES and value != EXPECTED_VALUES[field]:
            raise PreviewError(f"{field} does not match the required FC Barcelona value.")
        # Preserve the validated values exactly; never silently correct them.
        team[field] = value
    return team


def get_firestore_client():
    # ADC uses the environment variable; never display its value or file contents.
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
    # A missing collection also returns a missing document; no creation is needed.
    if not snapshot.exists:
        return "CREATE", []
    current = snapshot.to_dict() or {}
    differences = []
    for field in FIELDS:
        old_value = current.get(field, MISSING)
        if old_value != team[field]:
            differences.append((field, old_value, team[field]))
    return ("UPDATE" if differences else "NO CHANGE"), differences


def display_value(value):
    if value is MISSING:
        return "<missing>"
    if value is None:
        return "null"
    # Do not dump nested objects or suspicious content from an existing document.
    if not isinstance(value, str):
        return "<unexpected non-string value hidden>"
    if sensitive_text(value):
        return "<potentially sensitive value hidden>"
    return json.dumps(value, ensure_ascii=False)


def apply_team(db, document, team, preview_snapshot):
    # A transaction protects the recheck and write from changes in between them.
    # Use one attempt so a conflict requires a new preview and confirmation.
    transaction = db.transaction(max_attempts=1)

    @firestore.transactional
    def save_team(active_transaction):
        current = document.get(
            field_paths=FIELDS, transaction=active_transaction, timeout=20, retry=None
        )
        if ((preview_snapshot.exists and preview_snapshot.update_time is None)
                or (current.exists and current.update_time is None)):
            raise ConflictError("The document version could not be verified.")
        # The version timestamp detects changes to unrelated fields too.
        if (current.exists != preview_snapshot.exists
                or current.update_time != preview_snapshot.update_time):
            raise ConflictError("teams/wikidata_Q7156 changed since the preview.")
        data = {field: team[field] for field in FIELDS}
        active_transaction.set(document, data, merge=True)

    try:
        save_team(transaction)
    except Aborted:
        raise ConflictError("Firestore aborted the transaction. Run a new preview.") from None
    except ValueError as error:
        # The SDK wraps a commit conflict in ValueError when attempts run out.
        if isinstance(error.__cause__, Aborted):
            raise ConflictError("Firestore detected a transaction conflict. Run a new preview.") from None
        raise


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="Preview or confirm an upload to teams/wikidata_Q7156.",
        allow_abbrev=False,
    )
    parser.add_argument(
        "--apply", action="store_true",
        help="Allow a write only after reviewing the preview and typing YES.",
    )
    args = parser.parse_args(argv)
    state = "not started"
    try:
        team = load_team()
        db = get_firestore_client()
        # The target is fixed in code, never taken from an unchecked input value.
        document = db.collection("teams").document(DOCUMENT_ID)
        snapshot = document.get(field_paths=FIELDS, timeout=20, retry=None)
        operation, differences = compare_team(team, snapshot)

        print(f"Firestore preview: teams/{DOCUMENT_ID}")
        print("Prepared fields:")
        print(json.dumps(team, ensure_ascii=False, indent=2))
        if operation == "CREATE":
            print("The target document is missing; the teams collection may not exist yet.")
        elif operation == "UPDATE":
            print("\nFields that differ:")
            for field, old_value, proposed_value in differences:
                print(f"  {field}:")
                print(f"    Existing: {display_value(old_value)}")
                print(f"    Proposed: {display_value(proposed_value)}")
        else:
            print("All six selected fields already match.")
        print(f"\nSummary: {operation} for teams/{DOCUMENT_ID}")
        if operation == "NO CHANGE":
            print("No write is needed.")
            return 0
        if not args.apply:
            return 0

        try:
            answer = input(f"\nType YES to {operation} teams/{DOCUMENT_ID}: ")
        except (EOFError, KeyboardInterrupt):
            print("\nUpload cancelled.")
            return 0
        # Only the exact response YES is accepted; do not trim or change case.
        if answer != "YES":
            print("Upload cancelled: confirmation was not exactly YES.")
            return 0

        state = "applying"
        apply_team(db, document, team, snapshot)
        state = "committed"
        print("Write committed. Reading the document again to verify its fields...")
        saved_snapshot = document.get(field_paths=FIELDS, timeout=20, retry=None)
        if not saved_snapshot.exists:
            raise PreviewError("The document was not found during read-back verification.")
        _, remaining_differences = compare_team(team, saved_snapshot)
        if remaining_differences:
            fields = ", ".join(field for field, _, _ in remaining_differences)
            raise PreviewError("Read-back verification failed for: " + fields)
        state = "verified"
        print(f"Success! {operation} completed for teams/{DOCUMENT_ID}; all six fields verified.")
        return 0

    except ConflictError as error:
        state = "cancelled"
        print(f"Upload cancelled: {error} No writes were committed.")
    except PreviewError as error:
        print(f"Import stopped: {error}")
    except GoogleAuthError:
        print("Firebase authentication failed. Check the configured service account.")
    except (PermissionDenied, Unauthenticated):
        print("Firestore access denied. Check the service account's permissions for this operation.")
    except (GoogleAPICallError, FirebaseError, TimeoutError):
        print("Firestore operation failed. Check your connection, Firebase project and database.")
    except OSError:
        print("Could not access the credentials file or connect to Firestore.")
    except (ValueError, TypeError, AttributeError):
        # Raw exception messages could expose private configuration.
        print("Invalid Firebase configuration or unexpected Firestore data. Import stopped.")
    except KeyboardInterrupt:
        print("\nImport interrupted.")
    finally:
        if not args.apply:
            print(f"\n{DRY_RUN_MESSAGE}")
        elif state == "not started":
            print("No writes were issued.")
        elif state == "applying":
            # A lost connection can hide a successful server-side commit.
            print("The write outcome is uncertain. Run a dry run before retrying an upload.")
        elif state == "committed":
            print("The write committed but verification is incomplete. Run a dry run to inspect it.")
    return 1


# Importing the file makes no requests. Dry run is the default.
if __name__ == "__main__":
    raise SystemExit(main())
