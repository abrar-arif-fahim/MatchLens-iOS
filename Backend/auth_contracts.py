"""Firebase client session handoff and safe errors, never password authentication.

The identity argument MUST be projected from Firebase Auth's current authenticated
User, not a form, cached UID or unverified token. This is a reference contract for
the Swift client, not a token-verification service or authentication simulator.
"""

import copy
import re

from app_contracts import AccessError, require_uid
from user_data_service import validate_user_document
from validate_match_schema import ValidationError


AUTH_USER_FIELDS = {"uid", "email", "emailVerified"}
ERROR_MESSAGES = {
    "invalidCredential": "Email or password is incorrect.",
    "wrongPassword": "Email or password is incorrect.",
    "userNotFound": "Email or password is incorrect.",
    "invalidEmail": "Enter a valid email address.",
    "emailAlreadyInUse": "Unable to create the account. Try signing in or resetting your password.",
    "weakPassword": "Choose a stronger password that meets the registration requirements.",
    "userDisabled": "Sign-in is unavailable for this account. Contact project support.",
    "networkError": "Unable to connect. Check your connection and retry.",
    "tooManyRequests": "Too many attempts. Please try again later.",
    "requiresRecentLogin": "Sign in again before changing sensitive account information.",
}


def session_view(auth_user, profile=None):
    # A sign-out/session switch must discard prior private state immediately.
    if auth_user is None:
        return {"state": "signedOut", "user": None, "profile": None}
    if not isinstance(auth_user, dict) or set(auth_user) != AUTH_USER_FIELDS:
        raise ValidationError("Project only UID, email and emailVerified from Firebase Auth's current User.")
    uid = require_uid(auth_user["uid"])
    email = auth_user["email"]
    if (not isinstance(email, str) or len(email) > 254 or email != email.strip()
            or not re.fullmatch(r"[^\s@]+@[^\s@]+\.[^\s@]+", email)):
        raise ValidationError("The Email/Password session has no valid Firebase Auth email.")
    if type(auth_user["emailVerified"]) is not bool:
        raise ValidationError("Firebase Auth emailVerified must be a boolean.")
    if profile is None:
        return {"state": "profileRequired", "user": copy.deepcopy(auth_user), "profile": None}
    if not isinstance(profile, dict) or profile.get("uid") != uid:
        raise AccessError("Cached profile does not belong to the current Firebase Auth session.")
    validated = validate_user_document(f"users/{uid}", profile, uid)
    return {"state": "ready", "user": copy.deepcopy(auth_user), "profile": validated}


def auth_error_message(sdk_case):
    # Accept mapped AuthErrorCode case names, never raw SDK errors/userInfo/tokens.
    if not isinstance(sdk_case, str):
        return "Authentication failed. Please retry."
    return ERROR_MESSAGES.get(sdk_case, "Authentication failed. Please retry.")
