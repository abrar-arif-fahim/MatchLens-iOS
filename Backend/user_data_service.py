"""Owner-scoped user contracts and write plans; never write to Firebase.

The caller's UID must come from an authenticated Firebase session. These Python
checks support offline testing; deployed client rules are the security boundary.
"""

import copy

from app_contracts import (AccessError, require_owner, require_uid, utc_text, validate_public_path)
from app_service import NotFoundError
from app_repository import RepositoryError
from match_event_service import managed_values_equal
from validate_match_schema import ValidationError, require_text


PROFILE_FIELDS = {"uid", "displayName", "schemaVersion", "createdAt", "updatedAt"}
SETTINGS_FIELDS = {"favoriteTeamId", "scoreNotifications", "highlightNotifications", "appearance",
                   "schemaVersion", "updatedAt"}
SETTINGS_EDITABLE = SETTINGS_FIELDS - {"schemaVersion", "updatedAt"}
SAVED_FIELDS = {"targetType", "targetId", "schemaVersion", "createdAt"}
WATCH_FIELDS = {"matchId", "schemaVersion", "createdAt"}
TARGET_COLLECTIONS = {"team": "teams", "player": "players", "match": "matches", "highlight": "highlights"}
DEFAULT_SETTINGS = {"favoriteTeamId": None, "scoreNotifications": False, "highlightNotifications": False,
                    "appearance": "system", "schemaVersion": 1}
PLAN_FIELDS = {"path", "operation", "data", "serverTimestampFields", "expected"}


def favorite_id(kind, identifier):
    if not isinstance(kind, str) or kind not in TARGET_COLLECTIONS:
        raise ValidationError("Unsupported favorite type.")
    validate_public_path(TARGET_COLLECTIONS[kind], identifier)
    return f"{kind}_{identifier}"


def private_path(path, actor_uid):
    parts = path.split("/") if isinstance(path, str) else []
    if len(parts) not in (2, 4) or parts[0] != "users":
        raise AccessError("Only the authenticated user's private paths are supported.")
    require_owner(actor_uid, parts[1])
    if len(parts) == 4:
        if parts[2] == "settings" and parts[3] == "preferences":
            return parts
        if parts[2] not in {"favorites", "watchlist"} or not parts[3] or parts[3] in {".", ".."}:
            raise AccessError("Invalid private document path.")
    return parts


def validate_setting_values(data):
    for field in ("scoreNotifications", "highlightNotifications"):
        if type(data[field]) is not bool:
            raise ValidationError("Notification preferences must be booleans.")
    if not isinstance(data["appearance"], str) or data["appearance"] not in {"system", "dark", "light"}:
        raise ValidationError("Appearance must be system, dark or light.")
    if data["favoriteTeamId"] is not None:
        validate_public_path("teams", data["favoriteTeamId"])


def validate_user_document(path, record, actor_uid):
    parts = private_path(path, actor_uid)
    kind = "profile" if len(parts) == 2 else parts[2]
    expected = {"profile": PROFILE_FIELDS, "settings": SETTINGS_FIELDS,
                "favorites": SAVED_FIELDS, "watchlist": WATCH_FIELDS}[kind]
    if not isinstance(record, dict) or set(record) != expected:
        raise ValidationError("A private document must contain exactly its managed fields.")
    if type(record["schemaVersion"]) is not int or record["schemaVersion"] != 1:
        raise ValidationError("Unsupported private-document schema version.")
    data = copy.deepcopy(record)
    for field in ("createdAt", "updatedAt"):
        if field in expected:
            data[field] = utc_text(data[field])
    if kind == "profile":
        if data["uid"] != parts[1]:
            raise AccessError("The profile UID does not match its authenticated document owner.")
        require_text(data["displayName"], "Display name")
        if len(data["displayName"]) > 80:
            raise ValidationError("Display name must not exceed 80 characters.")
        if data["updatedAt"] < data["createdAt"]:
            raise ValidationError("Profile updatedAt cannot precede createdAt.")
    elif kind == "settings":
        validate_setting_values(data)
    elif kind == "favorites":
        if parts[3] != favorite_id(data["targetType"], data["targetId"]):
            raise ValidationError("Favorite document ID is inconsistent with its target.")
    else:
        validate_public_path("matches", data["matchId"])
        if parts[3] != data["matchId"]:
            raise ValidationError("Watchlist document ID must equal matchId.")
    return data


def _plan(path, operation, current, data=None, timestamps=()):
    return {"path": path, "operation": operation, "data": copy.deepcopy(data),
            "serverTimestampFields": list(timestamps), "expected": copy.deepcopy(current)}


class UserDataService:
    def __init__(self, repository, resolve_reference, *, actor_uid):
        require_uid(actor_uid)
        if not callable(resolve_reference):
            raise ValidationError("Supply the validated public-reference resolver.")
        self.repository, self.resolve_reference, self.actor_uid = repository, resolve_reference, actor_uid

    def _owner(self, owner_uid):
        owner = self.actor_uid if owner_uid is None else owner_uid
        require_owner(self.actor_uid, owner)
        return owner

    def _read(self, path):
        parts = private_path(path, self.actor_uid)
        raw = self.repository.get("/".join(parts[:-1]), parts[-1])
        return None if raw is None else validate_user_document(path, raw, self.actor_uid)

    def profile(self, *, owner_uid=None):
        owner = self._owner(owner_uid)
        return self._read(f"users/{owner}")  # Missing after Auth creation is recoverable, not a fake account.

    def settings(self, *, owner_uid=None):
        owner = self._owner(owner_uid)
        current = self._read(f"users/{owner}/settings/preferences")
        return {"values": current or dict(DEFAULT_SETTINGS, updatedAt=None), "persisted": current is not None}

    def plan_profile(self, display_name, *, owner_uid=None):
        owner = self._owner(owner_uid)
        require_text(display_name, "Display name")
        if len(display_name) > 80:
            raise ValidationError("Display name must not exceed 80 characters.")
        path = f"users/{owner}"
        current = self._read(path)
        if current is None:
            return _plan(path, "CREATE", None, {"uid": owner, "displayName": display_name, "schemaVersion": 1},
                         ("createdAt", "updatedAt"))
        if current["displayName"] == display_name:
            return _plan(path, "NO CHANGE", current)
        return _plan(path, "UPDATE", current, {"displayName": display_name}, ("updatedAt",))

    def plan_settings(self, changes, *, owner_uid=None):
        owner = self._owner(owner_uid)
        if not isinstance(changes, dict) or not set(changes).issubset(SETTINGS_EDITABLE):
            raise ValidationError("Only the four documented settings may be edited.")
        path = f"users/{owner}/settings/preferences"
        current = self._read(path)
        desired = dict(current or DEFAULT_SETTINGS, **copy.deepcopy(changes))
        # Validate the whole prospective state before resolving a reference or returning a plan.
        validate_setting_values(desired)
        if desired["favoriteTeamId"] is not None:
            self.resolve_reference("team", desired["favoriteTeamId"])
        if current is None:
            return _plan(path, "CREATE", None, {key: desired[key] for key in DEFAULT_SETTINGS}, ("updatedAt",))
        changed = {key: desired[key] for key in SETTINGS_EDITABLE
                   if not managed_values_equal(current[key], desired[key])}
        return _plan(path, "UPDATE", current, changed, ("updatedAt",)) if changed else _plan(path, "NO CHANGE", current)

    def plan_favorite(self, kind, identifier, *, saved=True, owner_uid=None):
        owner = self._owner(owner_uid)
        if type(saved) is not bool:
            raise ValidationError("Saved must be a boolean, never a toggle or counter.")
        path = f"users/{owner}/favorites/{favorite_id(kind, identifier)}"
        current = self._read(path)
        if not saved:
            return _plan(path, "DELETE" if current is not None else "NO CHANGE", current)
        self.resolve_reference(kind, identifier)
        if current is not None:
            return _plan(path, "NO CHANGE", current)
        return _plan(path, "CREATE", None, {"targetType": kind, "targetId": identifier, "schemaVersion": 1}, ("createdAt",))

    def plan_watchlist(self, match_id, *, saved=True, owner_uid=None):
        owner = self._owner(owner_uid)
        validate_public_path("matches", match_id)
        if type(saved) is not bool:
            raise ValidationError("Saved must be a boolean.")
        path = f"users/{owner}/watchlist/{match_id}"
        current = self._read(path)
        if not saved:
            return _plan(path, "DELETE" if current is not None else "NO CHANGE", current)
        self.resolve_reference("match", match_id)
        return (_plan(path, "NO CHANGE", current) if current is not None else
                _plan(path, "CREATE", None, {"matchId": match_id, "schemaVersion": 1}, ("createdAt",)))

    def saved_items(self, kind="favorites", *, owner_uid=None, page_size=20, cursor=None):
        owner = self._owner(owner_uid)
        if not isinstance(kind, str) or kind not in {"favorites", "watchlist"}:
            raise ValidationError("Choose favorites or watchlist.")
        page = self.repository.private_page(self.actor_uid, owner, kind, page_size=page_size, after_id=cursor)
        result = []
        for identifier, raw in page["items"]:
            data = validate_user_document(f"users/{owner}/{kind}/{identifier}", raw, self.actor_uid)
            target_kind = data["targetType"] if kind == "favorites" else "match"
            target_id = data["targetId"] if kind == "favorites" else data["matchId"]
            try:
                target = self.resolve_reference(target_kind, target_id)
                availability = "available"
            except RepositoryError:
                raise
            except NotFoundError:
                target, availability = None, "missing"
            except ValidationError:
                target, availability = None, "reviewRequired"
            result.append({"documentId": identifier, "saved": data, "target": target, "availability": availability})
        return dict(page, items=result)


def simulate_user_plan(plan, documents, *, actor_uid, server_time, resolve_reference):
    """Apply one plan to a COPY of local dictionaries, never a database.

    A real Swift executor must re-read in a Firestore transaction, compare the
    expected managed state, then use FieldValue.serverTimestamp() for listed
    fields. This simulator's supplied clock is explicitly an offline test clock.
    """
    if not isinstance(plan, dict) or set(plan) != PLAN_FIELDS:
        raise ValidationError("Malformed private write plan.")
    parts = private_path(plan["path"], actor_uid)
    collection, identifier = "/".join(parts[:-1]), parts[-1]
    store = copy.deepcopy(documents)
    raw = store.get(collection, {}).get(identifier)
    current = None if raw is None else validate_user_document(plan["path"], raw, actor_uid)
    if not managed_values_equal(current, plan["expected"]):
        raise ValidationError("Conflict: private data changed since the preview; refresh before retrying.")
    operation = plan["operation"]
    if not isinstance(operation, str):
        raise ValidationError("Unsupported private write plan.")
    if operation == "NO CHANGE":
        if plan["data"] is not None or plan["serverTimestampFields"]:
            raise ValidationError("Malformed no-change plan.")
        return store
    if operation == "DELETE":
        if plan["data"] is not None or plan["serverTimestampFields"]:
            raise ValidationError("Malformed removal plan.")
        if len(parts) != 4 or parts[2] not in {"favorites", "watchlist"}:
            raise AccessError("Only saved references may be removed by this contract.")
        store.get(collection, {}).pop(identifier, None)
        return store
    if operation not in {"CREATE", "UPDATE"} or not isinstance(plan["data"], dict):
        raise ValidationError("Unsupported private write plan.")
    if (operation == "CREATE") != (current is None):
        raise ValidationError("Private operation does not match document existence.")
    kind = "profile" if len(parts) == 2 else parts[2]
    timestamp_fields = {"profile": ["createdAt", "updatedAt"] if operation == "CREATE" else ["updatedAt"],
                        "settings": ["updatedAt"], "favorites": ["createdAt"], "watchlist": ["createdAt"]}[kind]
    if plan["serverTimestampFields"] != timestamp_fields:
        raise ValidationError("Server timestamps must match the private operation.")
    allowed = {"profile": PROFILE_FIELDS - {"createdAt", "updatedAt"} if operation == "CREATE" else {"displayName"},
               "settings": set(DEFAULT_SETTINGS) if operation == "CREATE" else SETTINGS_EDITABLE,
               "favorites": SAVED_FIELDS - {"createdAt"}, "watchlist": WATCH_FIELDS - {"createdAt"}}[kind]
    if (not set(plan["data"]).issubset(allowed)
            or (operation == "CREATE" and set(plan["data"]) != allowed)
            or (operation == "UPDATE" and kind in {"favorites", "watchlist"})):
        raise ValidationError("Private operation contains protected or unsupported fields.")
    data = dict(current or {}, **copy.deepcopy(plan["data"]))
    for field in plan["serverTimestampFields"]:
        data[field] = utc_text(server_time)
    data = validate_user_document(plan["path"], data, actor_uid)
    if current is not None and "createdAt" in current and data["createdAt"] != current["createdAt"]:
        raise ValidationError("createdAt is immutable.")
    if len(parts) == 4 and parts[2] == "favorites":
        resolve_reference(data["targetType"], data["targetId"])
    elif len(parts) == 4 and parts[2] == "watchlist":
        resolve_reference("match", data["matchId"])
    elif len(parts) == 4 and parts[2] == "settings" and data["favoriteTeamId"] is not None:
        resolve_reference("team", data["favoriteTeamId"])
    store.setdefault(collection, {})[identifier] = data
    return store
