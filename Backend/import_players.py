"""Preview one Wikidata player import, or apply it after explicit confirmation."""

import argparse
import json
import os
import re
from datetime import date
from http.client import HTTPException
from pathlib import Path
from urllib.error import HTTPError, URLError

import firebase_admin
from firebase_admin import credentials, firestore
from firebase_admin.exceptions import FirebaseError
from google.api_core.exceptions import Aborted, GoogleAPICallError, PermissionDenied, Unauthenticated
from google.auth.exceptions import GoogleAuthError
from validate_match_schema import reject_duplicate_fields

# These modules have main guards, so importing their helpers makes no requests.
# Call only Wikidata helpers: no API-Football requests or API keys are needed.
from prepare_player_data import (
    get_wikidata,
    normalize_position,
    wikidata_birth_date,
    wikidata_labels,
)


INPUT_FILE = Path(__file__).resolve().parent / "output" / "player_messi.json"
PUBLIC_FIELDS = ("wikidataId", "name", "dateOfBirth", "nationality", "position")
TARGET_WIKIDATA_ID = "Q615"
TARGET_DOCUMENT_ID = "wikidata_Q615"
DRY_RUN_MESSAGE = "DRY RUN ONLY — No changes made to Firestore"


class PreviewError(ValueError):
    """A safe explanation written by this script, rather than a remote service."""


class ConflictError(PreviewError):
    """A concurrent edit must be reviewed before the user confirms again."""


def load_player():
    # Resolve the input relative to this script, regardless of the terminal folder.
    with INPUT_FILE.open(encoding="utf-8-sig") as input_file:
        data = json.load(input_file, object_pairs_hook=reject_duplicate_fields)
    if not isinstance(data, dict):
        raise PreviewError("The player JSON must contain one object.")

    # Build a new dictionary, copying ONLY the five allowed public fields.
    player = {}
    for field in PUBLIC_FIELDS:
        value = data.get(field)
        if not isinstance(value, str) or not value.strip():
            raise PreviewError(f"Required field {field} must be a nonempty string.")
        value = value.strip()
        if value.casefold() in {"unknown", "not available", "n/a", "null", "none"}:
            raise PreviewError(f"Required field {field} is missing a usable value.")
        player[field] = value

    if not re.fullmatch(r"Q[1-9][0-9]*", player["wikidataId"]):
        raise PreviewError("wikidataId must be a Wikidata ID such as Q615.")
    if player["wikidataId"] != TARGET_WIKIDATA_ID:
        raise PreviewError("This importer accepts only Q615 (Lionel Messi).")

    birth_date = player["dateOfBirth"]
    if not re.fullmatch(r"[0-9]{4}-[0-9]{2}-[0-9]{2}", birth_date):
        raise PreviewError("dateOfBirth must use YYYY-MM-DD.")
    try:
        parsed_date = date.fromisoformat(birth_date)
    except ValueError:
        raise PreviewError("dateOfBirth must be a real calendar date.") from None
    if parsed_date > date.today():
        raise PreviewError("dateOfBirth cannot be in the future.")
    if player["position"] not in {"Forward", "Midfielder", "Defender", "Goalkeeper"}:
        raise PreviewError("position must be Forward, Midfielder, Defender or Goalkeeper.")
    return player


def verify_wikidata_fields(player):
    # The existing JSON lists multiple sources without per-field provenance.
    # Removing provider IDs alone would not prove that the remaining values
    # came from Wikidata. Verify every value directly before assigning source.
    entity = get_wikidata(player["wikidataId"])
    name = entity.get("labels", {}).get("en", {}).get("value")
    cache = {}
    countries = wikidata_labels(entity, "P27", cache)
    positions = {
        normalize_position(label)
        for label in wikidata_labels(entity, "P413", cache)
    }
    verified_values = {
        "name": {name},
        "dateOfBirth": {wikidata_birth_date(entity)},
        "nationality": countries,
        "position": positions,
    }
    for field, allowed_values in verified_values.items():
        if player[field] not in allowed_values:
            raise PreviewError(
                f"{field} could not be verified against Wikidata. Preview stopped."
            )
    # Keep this separate from the input's mixed-provider sources list.
    player["source"] = "Wikidata"


def get_player_document():
    credential_path = os.environ.get("GOOGLE_APPLICATION_CREDENTIALS")
    if not credential_path or not credential_path.strip():
        raise PreviewError(
            "Set GOOGLE_APPLICATION_CREDENTIALS in this PowerShell terminal first."
        )
    if not Path(credential_path).is_file():
        raise PreviewError("The configured credentials file could not be found.")

    try:
        app = firebase_admin.get_app()
    except ValueError:
        app = firebase_admin.initialize_app(credentials.ApplicationDefault())
    db = firestore.client(app=app)
    # The target is fixed in code, never supplied by JSON or command-line flags.
    return db.collection("players").document(TARGET_DOCUMENT_ID)


def display_comparison(player, snapshot):
    current = {}
    if snapshot.exists:
        current = snapshot.to_dict() or {}
    changed = False
    if not snapshot.exists:
        print("The document does not exist yet.")
    print("\nField comparison (only the six preview fields):")
    for field, proposed_value in player.items():
        if field not in current or current[field] is None or current[field] == "":
            status = "MISSING"
        elif current[field] == proposed_value:
            status = "UNCHANGED"
        else:
            status = "DIFFERENT"
        if status != "UNCHANGED":
            changed = True
        # Print statuses rather than dumping the existing database document.
        print(f"  {field}: {status}")

    if not snapshot.exists:
        operation = "CREATE"
    elif changed:
        operation = "UPDATE"
    else:
        operation = "NO CHANGE"
    print(f"\nProposed operation: {operation}")
    return operation


def apply_player(document, player, preview_snapshot):
    # The preview already initialized the default Firebase app.
    # Read and write in one transaction so a concurrent edit cancels the upload.
    transaction = firestore.client().transaction(max_attempts=1)

    @firestore.transactional
    def save_player(active_transaction):
        fields = (*PUBLIC_FIELDS, "source")
        current = document.get(
            field_paths=fields, transaction=active_transaction, timeout=20, retry=None
        )
        if ((preview_snapshot.exists and preview_snapshot.update_time is None)
                or (current.exists and current.update_time is None)):
            raise ConflictError("The document version could not be verified.")
        if (current.exists != preview_snapshot.exists
                or current.update_time != preview_snapshot.update_time):
            raise ConflictError("players/wikidata_Q615 changed since the preview.")
        # Preserve unrelated fields and send only the six verified values.
        active_transaction.set(document, {field: player[field] for field in fields}, merge=True)

    try:
        save_player(transaction)
    except Aborted:
        raise ConflictError("Firestore aborted the transaction. Run a new preview.") from None
    except ValueError as error:
        if isinstance(error.__cause__, Aborted):
            raise ConflictError("Firestore detected a transaction conflict. Run a new preview.") from None
        raise


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="Preview or confirm one Wikidata upload to players/wikidata_Q615.",
        allow_abbrev=False,
    )
    parser.add_argument(
        "--apply", action="store_true",
        help="Enable a write only after you review the preview and type YES.",
    )
    args = parser.parse_args(argv)
    if args.apply:
        print("APPLY MODE — Review the preview before confirming a write.")
    else:
        print(DRY_RUN_MESSAGE)

    write_attempted = False
    write_completed = False
    write_verified = False
    try:
        # Validate locally and verify against Wikidata before any database call.
        player = load_player()
        print("Verifying public fields against Wikidata (read-only requests)...")
        verify_wikidata_fields(player)
        document = get_player_document()
        snapshot = document.get(timeout=20, retry=None)

        print(f"\nFirestore document: players/{TARGET_DOCUMENT_ID}")
        print("Verified Wikidata preview:")
        print(json.dumps(player, ensure_ascii=False, indent=2))
        operation = display_comparison(player, snapshot)
        if operation == "NO CHANGE":
            print("All selected fields already match. No write is needed.")
            return 0
        if not args.apply:
            return 0

        # No trimming or case conversion: only the exact response YES permits a write.
        try:
            answer = input(
                f"\nType YES to {operation} players/{TARGET_DOCUMENT_ID}: "
            )
        except (EOFError, KeyboardInterrupt):
            print("\nUpload cancelled.")
            return 0
        if answer != "YES":
            print("Upload cancelled: confirmation was not exactly YES.")
            return 0

        # One transaction attempt; a conflict requires another preview and YES.
        write_attempted = True
        apply_player(document, player, snapshot)
        write_completed = True
        print("Write completed. Reading the document again to verify the values...")

        saved_snapshot = document.get(timeout=20, retry=None)
        if not saved_snapshot.exists:
            raise PreviewError("The document was not found during upload verification.")
        saved_player = saved_snapshot.to_dict() or {}
        mismatches = [field for field, value in player.items()
                      if saved_player.get(field) != value]
        if mismatches:
            raise PreviewError(
                "Upload verification did not match these fields: " + ", ".join(mismatches)
            )
        write_verified = True
        print(
            f"Success! {operation} completed for players/{TARGET_DOCUMENT_ID}. "
            "All six selected fields were verified."
        )
        return 0

    except ConflictError as error:
        write_attempted = False
        print(f"Upload cancelled: {error}")
    except PreviewError as error:
        print(f"Import stopped: {error}")
    except FileNotFoundError:
        print("Input file not found: Backend/output/player_messi.json.")
    except (json.JSONDecodeError, UnicodeError):
        print("The player file must contain valid UTF-8 JSON.")
    except GoogleAuthError:
        print("Firebase authentication failed. Check the configured service account.")
    except (PermissionDenied, Unauthenticated):
        print("Firestore access denied. Check the service account's permissions for this operation.")
    except (GoogleAPICallError, FirebaseError):
        print("Firestore operation failed. Check your connection, Firebase project and database.")
    except (HTTPError, URLError, TimeoutError, HTTPException):
        print("Wikidata verification failed. Check your connection and try again later.")
    except OSError:
        print("Could not read a local file or reach a service. Check file access and connection.")
    except (ValueError, KeyError, TypeError, AttributeError):
        # Never display raw exceptions, input records, credentials or API keys.
        print("Invalid source data or Firebase configuration. Import stopped.")
    finally:
        if not args.apply:
            print(f"\n{DRY_RUN_MESSAGE}")
        elif not write_attempted:
            print("No write was issued.")
        elif not write_completed:
            # A connection failure may hide a successful server-side write.
            print("The write outcome is uncertain. Read the document before retrying.")
        elif not write_verified:
            print("The write completed but was not verified. Read the document before retrying.")
    return 1


# Dry run is the default. Importing this file does not make requests.
if __name__ == "__main__":
    raise SystemExit(main())
