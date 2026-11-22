"""Check the example match's two Firestore team references without any writes."""

from firebase_admin.exceptions import FirebaseError
from google.api_core.exceptions import GoogleAPICallError, PermissionDenied, Unauthenticated
from google.auth.exceptions import GoogleAuthError

# These existing modules have main guards: importing helpers makes no requests.
from validate_match_schema import ValidationError, load_match, validate_match, validate_team_reference_data
from preview_multiple_teams import PreviewError, display_value, get_firestore_client


TEAM_FIELDS = ("teamId", "wikidataId", "name")
READ_ONLY_MESSAGE = "READ ONLY — No changes made to Firestore"


def read_team_reference(db, document_id):
    # The local schema has already checked the ID's format. Read only this team.
    snapshot = db.collection("teams").document(document_id).get(
        field_paths=TEAM_FIELDS, timeout=20, retry=None
    )
    if not snapshot.exists:
        raise ValidationError(f"teams/{document_id} does not exist.")
    if snapshot.id != document_id:
        raise ValidationError("The returned team document ID does not match the requested ID.")

    team = snapshot.to_dict()
    validate_team_reference_data(document_id, team)

    # Names are optional for this reference check. Reuse safe, escaped display
    # rather than printing arbitrary Firestore values or nested objects.
    name = team.get("name")
    if not isinstance(name, str) or not name.strip():
        return "Name unavailable"
    return display_value(name)


def main():
    try:
        # Finish local validation BEFORE initializing Firebase or reading teams.
        match = load_match()
        validate_match(match)
        print("Local match schema: VALID")
        if match["isDemo"]:
            print("DEMO ONLY: This reference check does not verify a real football fixture.")

        # Reuse ADC configuration from GOOGLE_APPLICATION_CREDENTIALS, including
        # the existing initialized-app handling. Never print credential contents.
        db = get_firestore_client()
        failures = 0
        for role, field in (("Home", "homeTeamId"), ("Away", "awayTeamId")):
            document_id = match[field]
            try:
                name = read_team_reference(db, document_id)
            except ValidationError as error:
                # Report both teams' identifier problems when reads succeed.
                failures += 1
                print(f"{role}: INVALID - {error}")
            else:
                print(f"{role}: teams/{document_id} | {name} | VALID")

        if failures:
            print(f"FAILED: {failures} of 2 team references are invalid.")
            return 1
        print("SUCCESS: Both team references exist and have consistent identifiers.")
        return 0

    except (ValidationError, PreviewError) as error:
        print(f"FAILED: {error}")
    except GoogleAuthError:
        print("FAILED: Firebase authentication failed. Check the configured service account.")
    except (PermissionDenied, Unauthenticated):
        print("FAILED: Firestore access denied. Check the service account's read permissions.")
    except (GoogleAPICallError, FirebaseError, TimeoutError):
        print("FAILED: Firestore read failed. Check your connection, Firebase project and database.")
    except OSError:
        print("FAILED: Could not access the configured credentials file or connect to Firestore.")
    except (ValueError, TypeError, KeyError, AttributeError):
        # Raw SDK errors can contain private configuration; keep them private.
        print("FAILED: Invalid Firebase configuration or unexpected document data.")
    except KeyboardInterrupt:
        print("\nCANCELLED: Team-reference validation interrupted.")
    finally:
        print(f"\n{READ_ONLY_MESSAGE}")
    return 1


# No reads happen on import. Run this script manually to perform the check.
if __name__ == "__main__":
    raise SystemExit(main())
