"""Preview up to five Wikidata imports; apply only with a flag and confirmation."""

import argparse
import json
import os
import re
from datetime import date
from pathlib import Path

import firebase_admin
from firebase_admin import credentials, firestore
from firebase_admin.exceptions import FirebaseError
from google.api_core.exceptions import Aborted, GoogleAPICallError, PermissionDenied, Unauthenticated
from google.auth.exceptions import GoogleAuthError
from validate_match_schema import reject_duplicate_fields


INPUT_FILE = Path(__file__).resolve().parent / "output" / "players_prepared.json"
FIELDS = ("wikidataId", "name", "dateOfBirth", "nationality", "position", "source")
DRY_RUN_MESSAGE = "DRY RUN ONLY — No changes made to Firestore"
MISSING = object()


class PreviewError(ValueError):
    """A safe message explaining why the preview cannot continue."""


class ConflictError(PreviewError):
    """The database changed after the preview; nothing may be committed."""


def sensitive_text(value):
    # Avoid displaying credential blocks, paths, URLs or token-like strings if
    # unexpected content was accidentally placed in a public player field.
    return len(value) > 200 or re.search(
        r"-----BEGIN|private[_ -]?key|api[_ -]?key|access[_ -]?token|"
        r"password|client_secret|https?://|[A-Za-z]:[\\/]|"
        r"\b[A-Za-z0-9_-]{24,}\b",
        value,
        flags=re.IGNORECASE,
    ) is not None


def load_players():
    # Read and validate the ENTIRE file before initializing Firebase.
    with INPUT_FILE.open(encoding="utf-8-sig") as input_file:
        data = json.load(input_file, object_pairs_hook=reject_duplicate_fields)
    return validate_player_records(data)


def validate_player_records(data, *, max_records=5):
    """Share public-player validation without file access or Firebase setup.

    The importer retains its five-record limit. Read-only services can pass None
    to validate larger already-prepared lists without expanding upload scope.
    """
    records = data.get("players") if isinstance(data, dict) else None
    if not isinstance(records, list):
        raise PreviewError("The JSON must contain a players array.")
    if max_records is not None and (type(max_records) is not int or max_records < 0):
        raise PreviewError("The player validation limit must be a nonnegative integer or None.")
    if max_records is not None and len(records) > max_records:
        raise PreviewError(f"This preview accepts no more than {max_records} player records.")

    players = []
    seen_ids = set()
    for index, record in enumerate(records, start=1):
        if not isinstance(record, dict):
            raise PreviewError(f"Record {index} must be a JSON object.")
        wikidata_id = record.get("wikidataId")
        if not isinstance(wikidata_id, str) or not re.fullmatch(r"Q[1-9][0-9]*", wikidata_id):
            raise PreviewError(f"Record {index}: wikidataId must be a positive Q-number without leading zeros.")
        document_id = record.get("documentId")
        if document_id != f"wikidata_{wikidata_id}":
            raise PreviewError(f"Record {index}: documentId does not match wikidataId.")
        if document_id in seen_ids:
            raise PreviewError(f"Record {index}: duplicate documentId; preview stopped.")
        seen_ids.add(document_id)

        # Copy only the six public fields. Ignore all extra input properties.
        player = {}
        for field in FIELDS:
            value = record.get(field)
            if (not isinstance(value, str) or not value.strip()
                    or value.casefold().strip() in {"unknown", "n/a", "null", "none", "not available"}):
                raise PreviewError(f"Record {index}: {field} must contain a valid nonempty string.")
            if sensitive_text(value) or any(ord(character) < 32 for character in value):
                raise PreviewError(f"Record {index}: {field} contains unexpected non-public content.")
            player[field] = value
        if player["source"] != "Wikidata":
            raise PreviewError(f"Record {index}: source must be exactly Wikidata.")
        if not re.fullmatch(r"[0-9]{4}-[0-9]{2}-[0-9]{2}", player["dateOfBirth"]):
            raise PreviewError(f"Record {index}: dateOfBirth must use YYYY-MM-DD.")
        try:
            parsed_date = date.fromisoformat(player["dateOfBirth"])
        except ValueError:
            raise PreviewError(f"Record {index}: dateOfBirth is not a real calendar date.") from None
        if parsed_date > date.today():
            raise PreviewError(f"Record {index}: dateOfBirth cannot be in the future.")
        players.append((document_id, player))
    return players


def get_firestore_client():
    # Use the terminal's existing ADC configuration; never print its contents.
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


def compare_player(player, snapshot):
    if not snapshot.exists:
        return "CREATE", [(field, MISSING, player[field]) for field in FIELDS]
    current = snapshot.to_dict() or {}
    differences = []
    for field in FIELDS:
        old_value = current.get(field, MISSING)
        if old_value != player[field]:
            differences.append((field, old_value, player[field]))
    return ("UPDATE" if differences else "NO CHANGE"), differences


def display_value(value):
    if value is MISSING:
        return "<missing>"
    if value is None:
        return "null"
    # Do not dump nested objects or arbitrary data from the database.
    if not isinstance(value, str):
        return "<unexpected non-string value hidden>"
    if sensitive_text(value):
        return "<potentially sensitive value hidden>"
    return json.dumps(value, ensure_ascii=False)


def read_previews(db, players):
    previews = []
    for document_id, player in players:
        reference = db.collection("players").document(document_id)
        # Field projections still include the document's full version timestamp.
        snapshot = reference.get(field_paths=FIELDS, timeout=20, retry=None)
        operation, differences = compare_player(player, snapshot)
        previews.append({
            "documentId": document_id,
            "reference": reference,
            "player": player,
            "snapshot": snapshot,
            "operation": operation,
            "differences": differences,
        })
    return previews


def display_previews(previews):
    totals = {"CREATE": 0, "UPDATE": 0, "NO CHANGE": 0}
    for entry in previews:
        operation = entry["operation"]
        totals[operation] += 1
        print(f"\n{operation}: players/{entry['documentId']} ({entry['player']['name']})")
        for field, old_value, proposed_value in entry["differences"]:
            print(f"  {field}:")
            print(f"    Existing: {display_value(old_value)}")
            print(f"    Proposed: {display_value(proposed_value)}")
    print(
        f"\nSummary: CREATE {totals['CREATE']} | UPDATE {totals['UPDATE']} | "
        f"NO CHANGE {totals['NO CHANGE']}"
    )
    return totals


def apply_import(db, previews):
    # One attempt: never automatically retry against a different document version.
    transaction = db.transaction(max_attempts=1)

    @firestore.transactional
    def save_players(active_transaction):
        # Firestore requires ALL transaction reads before ANY queued writes.
        for entry in previews:
            original = entry["snapshot"]
            current = entry["reference"].get(
                field_paths=FIELDS, transaction=active_transaction, timeout=20, retry=None
            )
            if ((original.exists and original.update_time is None)
                    or (current.exists and current.update_time is None)):
                raise ConflictError("A document version could not be verified. Import cancelled.")
            if (current.exists != original.exists
                    or current.update_time != original.update_time):
                raise ConflictError(
                    f"players/{entry['documentId']} changed since the preview. Import cancelled."
                )

        # These writes are committed together, or none are committed.
        for entry in previews:
            if entry["operation"] != "NO CHANGE":
                data = {field: entry["player"][field] for field in FIELDS}
                active_transaction.set(entry["reference"], data, merge=True)

    try:
        save_players(transaction)
    except Aborted:
        raise ConflictError("Firestore aborted the transaction. Run a new preview.") from None
    except ValueError as error:
        # The SDK wraps an exhausted transaction conflict in ValueError.
        if isinstance(error.__cause__, Aborted):
            raise ConflictError("Firestore detected transaction contention. Run a new preview.") from None
        raise


def verify_import(changes, results):
    mismatches = []
    for entry in changes:
        snapshot = entry["reference"].get(field_paths=FIELDS, timeout=20, retry=None)
        if compare_player(entry["player"], snapshot)[0] == "NO CHANGE":
            results["VERIFIED"] += 1
        else:
            mismatches.append(entry["documentId"])
    if mismatches:
        raise PreviewError("Read-back verification failed for: " + ", ".join(mismatches))


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="Preview or confirm up to five Wikidata player imports.",
        allow_abbrev=False,
    )
    parser.add_argument(
        "--apply", action="store_true",
        help="Allow a transaction only after reviewing the plan and typing YES.",
    )
    args = parser.parse_args(argv)
    results = {"CREATED": 0, "UPDATED": 0, "UNCHANGED": 0, "VERIFIED": 0}
    state = "not started"
    try:
        players = load_players()
        db = get_firestore_client() if players else None
        previews = read_previews(db, players) if players else []
        # Show the complete plan only after every validation and read succeeds.
        totals = display_previews(previews)
        results["UNCHANGED"] = totals["NO CHANGE"]
        changes = [entry for entry in previews if entry["operation"] != "NO CHANGE"]
        if not args.apply:
            return 0
        if not changes:
            print("No changes are needed. No transaction or write was issued.")
            return 0

        try:
            answer = input(f"\nType YES to apply all {len(changes)} proposed changes: ")
        except (EOFError, KeyboardInterrupt):
            print("\nImport cancelled. No writes were issued.")
            return 0
        # Do not strip spaces or change case: confirmation must be exactly YES.
        if answer != "YES":
            print("Import cancelled: confirmation was not exactly YES. No writes were issued.")
            return 0

        state = "applying"
        apply_import(db, previews)
        state = "committed"
        results["CREATED"] = totals["CREATE"]
        results["UPDATED"] = totals["UPDATE"]
        print("Transaction committed. Reading every affected document to verify its fields...")
        verify_import(changes, results)
        state = "verified"
        print("Success! All changed documents were imported and their six selected fields verified.")
        return 0

    except ConflictError as error:
        state = "cancelled"
        print(f"Import cancelled: {error} No writes were committed.")
    except PreviewError as error:
        print(f"Import stopped: {error}")
    except FileNotFoundError:
        print("Input file not found: Backend/output/players_prepared.json.")
    except (json.JSONDecodeError, UnicodeError):
        print("The input file must contain valid UTF-8 JSON.")
    except GoogleAuthError:
        print("Firebase authentication failed. Check the configured service account.")
    except (PermissionDenied, Unauthenticated):
        print("Firestore access denied. Check the service account's permissions for this operation.")
    except (GoogleAPICallError, FirebaseError, TimeoutError):
        print("A Firestore operation failed. Check your connection, Firebase project and database.")
    except OSError:
        print("Could not access a local file or connect to Firestore. Check file access and connection.")
    except (ValueError, TypeError, AttributeError):
        # Raw exception details can contain private configuration; keep them hidden.
        print("Invalid Firebase configuration or unexpected Firestore data. Import stopped.")
    except KeyboardInterrupt:
        print("\nImport interrupted.")
    finally:
        if not args.apply:
            print(f"\n{DRY_RUN_MESSAGE}")
        else:
            if state == "applying":
                # A lost connection can hide a successful atomic commit.
                results["CREATED"] = "UNKNOWN"
                results["UPDATED"] = "UNKNOWN"
                print("Transaction outcome is uncertain. Run a dry run before retrying an upload.")
            elif state == "committed":
                print("The transaction committed, but verification is incomplete. Run a dry run to inspect it.")
            print(
                f"\nResults: CREATED {results['CREATED']} | UPDATED {results['UPDATED']} | "
                f"UNCHANGED {results['UNCHANGED']} | VERIFIED {results['VERIFIED']}"
            )
    return 1


# Importing the module makes no Firebase requests. Dry run is the default.
if __name__ == "__main__":
    raise SystemExit(main())
