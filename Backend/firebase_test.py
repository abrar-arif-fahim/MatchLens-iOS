"""Read one existing player from Firestore without changing the database."""

import os
from pathlib import Path

import firebase_admin
from firebase_admin import credentials, firestore
from firebase_admin.exceptions import FirebaseError
from google.api_core.exceptions import (
    GoogleAPICallError,
    PermissionDenied,
    Unauthenticated,
)
from google.auth.exceptions import GoogleAuthError


def main():
    # PowerShell passes this environment variable to Python. Never print its
    # contents or read/copy the private service-account JSON into this script.
    credential_path = os.environ.get("GOOGLE_APPLICATION_CREDENTIALS")
    if not credential_path or not credential_path.strip():
        print(
            "Credentials are missing. Set GOOGLE_APPLICATION_CREDENTIALS in "
            "this VS Code PowerShell terminal before running the script."
        )
        return 1

    try:
        if not Path(credential_path).is_file():
            print(
                "The credentials file could not be found. Check the file path "
                "in GOOGLE_APPLICATION_CREDENTIALS."
            )
            return 1

        # Reuse the default app if another part of Python initialized it.
        try:
            app = firebase_admin.get_app()
        except ValueError:
            # ADC loads credentials using GOOGLE_APPLICATION_CREDENTIALS.
            app = firebase_admin.initialize_app(credentials.ApplicationDefault())

        db = firestore.client(app=app)

        # Read only this document. No collection scan, writes or retries.
        document = db.collection("players").document("wikidata_Q615")
        snapshot = document.get(timeout=20, retry=None)

        # A missing document is a normal result, so check before reading fields.
        if not snapshot.exists:
            print(
                "Player document players/wikidata_Q615 was not found. "
                "Check that it exists in the Firebase project used by your credentials."
            )
            return 1

        player = snapshot.to_dict() or {}
        print("Success! Retrieved players/wikidata_Q615 from Firestore.")
        for field in (
            "wikidataId", "name", "dateOfBirth", "nationality", "position", "source"
        ):
            # Show missing fields clearly rather than raising a KeyError.
            value = player.get(field)
            print(f"{field}: {value if value is not None else 'Not available'}")
        return 0

    except GoogleAuthError:
        print(
            "Authentication failed. Check that GOOGLE_APPLICATION_CREDENTIALS "
            "points to a valid service-account file and that the account is active."
        )
    except (PermissionDenied, Unauthenticated):
        print(
            "Firestore access was denied. Check that the service account "
            "has permission to read this project's database."
        )
    except (GoogleAPICallError, FirebaseError):
        print(
            "Could not read from Firestore. Check your internet connection, "
            "Firebase project and database availability, then try again."
        )
    except OSError:
        print("Could not access the credentials file. Check its path and file permissions.")
    except ValueError:
        print(
            "Firebase configuration is invalid. Check the service-account file "
            "and its project configuration."
        )

    # Keep raw exception messages private: they may contain sensitive details.
    return 1


# Importing this file does not initialize Firebase or read any documents.
if __name__ == "__main__":
    raise SystemExit(main())
