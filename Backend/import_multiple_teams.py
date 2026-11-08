"""Preview or explicitly confirm CREATE-only imports of five MatchLens teams."""

import argparse

from firebase_admin import firestore
from firebase_admin.exceptions import FirebaseError
from google.api_core.exceptions import (
    Aborted, AlreadyExists, FailedPrecondition, GoogleAPICallError,
    PermissionDenied, Unauthenticated,
)
from google.auth.exceptions import GoogleAuthError

# This read-only module has a main guard, so importing its helpers makes no
# requests. Reuse its exact six-field validation, ADC setup and safe display.
from preview_multiple_teams import (
    DRY_RUN_MESSAGE, FIELDS, PreviewError, compare_team, display_previews,
    get_firestore_client, load_teams,
)


EXPECTED_IDS = {"Q7156", "Q8682", "Q50602", "Q1130849", "Q15789"}
TARGET_COUNT = len(EXPECTED_IDS)


class ConflictError(PreviewError):
    """The preview became stale; the transaction must not commit."""


def load_expected_teams():
    # The shared loader reads Backend/output/teams_prepared.json and validates
    # every record, including duplicate IDs, before Firebase is initialized.
    teams = load_teams()
    actual_ids = {team["wikidataId"] for team in teams}
    if len(teams) != TARGET_COUNT or actual_ids != EXPECTED_IDS:
        raise PreviewError("The prepared input must contain exactly the five expected team IDs.")
    return teams


def read_plan(db, teams):
    plan = []
    for team in teams:
        # Collection and IDs are restricted by code and validated input.
        reference = db.collection("teams").document(team["teamId"])
        snapshot = reference.get(field_paths=FIELDS, timeout=20, retry=None)
        operation, differences = compare_team(team, snapshot)
        plan.append({
            "team": team,
            "reference": reference,
            "snapshot": snapshot,
            "operation": operation,
            "differences": differences,
        })
    return plan


def apply_creates(db, plan):
    if any(entry["operation"] not in {"CREATE", "NO CHANGE"} for entry in plan):
        raise PreviewError("UPDATE operations require manual review; nothing may be imported.")
    # Never automatically rerun the callback against a changed document version.
    transaction = db.transaction(max_attempts=1)

    @firestore.transactional
    def create_teams(active_transaction):
        # All reads must happen before any writes are queued. Recheck matching
        # records too, so changes to Barcelona cancel the entire operation.
        for entry in plan:
            original = entry["snapshot"]
            current = entry["reference"].get(
                field_paths=FIELDS, transaction=active_transaction, timeout=20, retry=None
            )
            if ((original.exists and original.update_time is None)
                    or (current.exists and current.update_time is None)):
                raise ConflictError("A target document version could not be verified.")
            if (current.exists != original.exists
                    or current.update_time != original.update_time):
                raise ConflictError(f"teams/{entry['team']['teamId']} changed after the preview.")
            if compare_team(entry["team"], current)[0] != entry["operation"]:
                raise ConflictError("A target document no longer matches the reviewed plan.")

        for entry in plan:
            if entry["operation"] == "CREATE":
                data = {field: entry["team"][field] for field in FIELDS}
                # SDK create adds exists=False. If even one document already
                # exists at commit, the entire transaction fails without overwrites.
                active_transaction.create(entry["reference"], data)

    try:
        create_teams(transaction)
    except (Aborted, AlreadyExists, FailedPrecondition):
        raise ConflictError("A transaction or existence precondition failed. Run a new preview.") from None
    except ValueError as error:
        # The SDK wraps an exhausted transaction conflict in ValueError.
        if isinstance(error.__cause__, Aborted):
            raise ConflictError("Firestore detected a transaction conflict. Run a new preview.") from None
        raise


def verify_targets(plan, results):
    mismatches = []
    # Verify ALL five targets, including the existing documents we skipped.
    for entry in plan:
        snapshot = entry["reference"].get(field_paths=FIELDS, timeout=20, retry=None)
        operation, differences = compare_team(entry["team"], snapshot)
        if operation == "NO CHANGE":
            results["VERIFIED"] += 1
        else:
            details = ", ".join(field for field, _, _ in differences) if snapshot.exists else "document missing"
            mismatches.append(f"{entry['team']['teamId']}: {details}")
    if mismatches:
        raise PreviewError("Verification failed: " + "; ".join(mismatches))


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="Preview or confirm CREATE-only imports of the five expected teams.",
        allow_abbrev=False,
    )
    parser.add_argument(
        "--apply", action="store_true",
        help="Allow a create transaction only after reviewing the plan and typing YES.",
    )
    args = parser.parse_args(argv)
    results = {"CREATED": 0, "SKIPPED": 0, "FAILED": 0, "VERIFIED": 0}
    creates = []
    state = "not started"
    error_message = None
    try:
        teams = load_expected_teams()
        db = get_firestore_client()
        plan = read_plan(db, teams)
        # Display a complete plan only after every validation and read succeeds.
        display_previews([
            (entry["team"], entry["operation"], entry["differences"]) for entry in plan
        ])
        creates = [entry for entry in plan if entry["operation"] == "CREATE"]
        updates = [entry for entry in plan if entry["operation"] == "UPDATE"]
        results["SKIPPED"] = sum(entry["operation"] == "NO CHANGE" for entry in plan)
        if updates:
            results["FAILED"] = len(updates)
            raise PreviewError(
                "Manual review required: an existing team needs UPDATE. "
                "This CREATE-only importer will not write any documents."
            )
        if not args.apply:
            return 0

        if creates:
            try:
                answer = input(f"\nType YES to create all {len(creates)} new team documents: ")
            except (EOFError, KeyboardInterrupt):
                print("\nImport cancelled. No writes were issued.")
                return 0
            # Exact confirmation only: no trimming or case conversion.
            if answer != "YES":
                print("Import cancelled: confirmation was not exactly YES. No writes were issued.")
                return 0
            state = "applying"
            apply_creates(db, plan)
            state = "committed"
            results["CREATED"] = len(creates)
            print("Create transaction committed. Verifying all five team documents...")
        else:
            state = "verifying"
            print("All teams already match. No writes are needed; verifying existing documents...")
        verify_targets(plan, results)
        state = "verified"
        print("Success! All five targets match the six prepared fields.")
        return 0

    except ConflictError as error:
        state = "cancelled"
        error_message = f"Import cancelled: {error} No writes were committed."
    except PreviewError as error:
        error_message = f"Import stopped: {error}"
    except GoogleAuthError:
        error_message = "Firebase authentication failed. Check the configured service account."
    except (PermissionDenied, Unauthenticated):
        error_message = "Firestore access denied. Check the service account's permissions."
    except (GoogleAPICallError, FirebaseError, TimeoutError):
        error_message = "Firestore operation failed. Check your connection, Firebase project and database."
    except OSError:
        error_message = "Could not access the configured credentials file or connect to Firestore."
    except (ValueError, TypeError, KeyError, AttributeError):
        # Raw exception messages may contain private configuration; never log them.
        error_message = "Invalid Firebase configuration or unexpected document data. Import stopped."
    except KeyboardInterrupt:
        error_message = "Import interrupted."
    finally:
        if error_message:
            print(error_message)
            if state == "applying":
                # The server may have committed before a connection was lost.
                results["CREATED"] = "UNKNOWN"
                results["FAILED"] = "UNKNOWN"
                print("The atomic commit outcome is uncertain. Run a dry run before retrying.")
            elif state in {"committed", "verifying"}:
                results["FAILED"] = TARGET_COUNT - results["VERIFIED"]
                if state == "committed":
                    print("The create transaction committed, but verification is incomplete.")
            elif not results["FAILED"]:
                results["FAILED"] = len(creates) if creates else TARGET_COUNT
        # CREATED counts actual committed creates; SKIPPED counts preview matches.
        # Verification is not performed in dry-run mode.
        print(
            f"\nResults: CREATED {results['CREATED']} | SKIPPED {results['SKIPPED']} | "
            f"FAILED {results['FAILED']}"
        )
        print(f"Verification: {results['VERIFIED']}/{TARGET_COUNT} targets matched all six fields.")
        if not args.apply:
            print(f"\n{DRY_RUN_MESSAGE}")
    return 1


# Importing the module makes no requests. Dry run is the default.
if __name__ == "__main__":
    raise SystemExit(main())
