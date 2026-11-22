"""Session lifecycle contracts using fictional identities, never real Auth calls."""

import unittest

from app_contracts import AccessError
from auth_contracts import auth_error_message, session_view
from validate_match_schema import ValidationError


class AuthContractTests(unittest.TestCase):
    def setUp(self):
        self.identity = {"uid": "test-alice", "email": "alice@example.invalid", "emailVerified": False}
        self.profile = {"uid": "test-alice", "displayName": "Fictional fan", "schemaVersion": 1,
                        "createdAt": "2030-01-01T00:00:00Z", "updatedAt": "2030-01-01T00:00:00Z"}

    def test_signed_out_state_discards_previous_private_profile(self):
        self.assertEqual(session_view(None, self.profile), {"state": "signedOut", "user": None, "profile": None})

    def test_authentication_without_profile_requires_recoverable_provisioning(self):
        result = session_view(self.identity)
        self.assertEqual(result["state"], "profileRequired")
        self.assertIsNone(result["profile"])
        self.assertFalse(result["user"]["emailVerified"])

    def test_existing_profile_is_ready_only_for_the_same_firebase_uid(self):
        result = session_view(self.identity, self.profile)
        self.assertEqual(result["state"], "ready")
        self.assertEqual(result["user"]["email"], "alice@example.invalid")
        self.assertNotIn("email", result["profile"])
        self.assertEqual(self.profile["createdAt"], "2030-01-01T00:00:00Z")

    def test_account_switch_cannot_reuse_the_previous_private_profile(self):
        with self.assertRaises(AccessError):
            session_view(dict(self.identity, uid="test-bob"), self.profile)

    def test_auth_state_rejects_credentials_or_unverified_token_payload_fields(self):
        for changes in ({"idToken": "fictional-not-a-field"}, {"password": "fictional-not-a-field"},
                        {"emailVerified": 1}, {"uid": None}, {"email": "not-an-email"}):
            with self.subTest(changes=changes), self.assertRaises(ValidationError):
                session_view(dict(self.identity, **changes))

    def test_credential_errors_do_not_reveal_account_existence(self):
        messages = {auth_error_message(case) for case in ("invalidCredential", "userNotFound", "wrongPassword")}
        self.assertEqual(len(messages), 1)
        self.assertNotIn("alice@", next(iter(messages)))

    def test_raw_auth_error_content_is_never_reflected(self):
        for error in ("PRIVATE_TOKEN_MARKER", RuntimeError("PRIVATE_TOKEN_MARKER"), None):
            self.assertNotIn("PRIVATE_TOKEN_MARKER", auth_error_message(error))


if __name__ == "__main__":
    unittest.main()
