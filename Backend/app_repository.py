"""Bounded read interfaces for offline tests and explicitly supplied Admin clients.

The Admin adapter is public-read-only and bypasses client security rules. It is
not an authentication backend. The iOS app will use its own Firebase Swift client.
"""

import copy

from app_contracts import PUBLIC_FIELDS, AccessError, project, require_uid, validate_page_size, validate_public_path
from validate_match_schema import ValidationError


FILTER_FIELDS = {"players": set(), "teams": set(), "competitions": {"isDemo"},
                 "matches": {"isDemo", "homeTeamId", "awayTeamId", "status"},
                 "matchEvents": {"matchId"}, "highlights": {"matchId", "isDemo", "rightsStatus", "mediaReference"}}


class RepositoryError(ValidationError):
    """Safe storage failure, distinct from invalid stored data."""


def validate_collection(collection, *, private=False):
    if isinstance(collection, str) and collection in PUBLIC_FIELDS:
        return
    parts = collection.split("/") if isinstance(collection, str) else []
    if private and parts == ["users"]:
        return
    if private and len(parts) == 3 and parts[0] == "users" and parts[2] in {"favorites", "watchlist", "settings"}:
        require_uid(parts[1])
        return
    raise AccessError("This collection is outside the repository's read interface.")


def validate_query(collection, filters, order_by, page_size, after_id):
    validate_collection(collection)
    validate_page_size(page_size)
    if not isinstance(filters, (tuple, list)):
        raise ValidationError("Query filters must be an array.")
    for condition in filters:
        if (not isinstance(condition, (tuple, list)) or len(condition) != 2
                or not isinstance(condition[0], str) or condition[0] not in FILTER_FIELDS[collection]):
            raise ValidationError("Only supported equality filters are allowed.")
    if order_by not in ("documentId", "kickoffUtc") or (order_by == "kickoffUtc" and collection != "matches"):
        raise ValidationError("Unsupported collection ordering.")
    if after_id is not None:
        validate_public_path(collection, after_id)


def matches_filters(data, filters):
    return all(field in data and type(data[field]) is type(value) and data[field] == value for field, value in filters)


def page_result(rows, page_size):
    has_more = len(rows) > page_size
    items = rows[:page_size]
    return {"items": items, "nextCursor": items[-1][0] if has_more else None, "hasMore": has_more}


class MemoryRepository:
    """Isolated local snapshots; changes never reach the input or any database."""

    def __init__(self, documents):
        if not isinstance(documents, dict):
            raise ValidationError("Local documents must be a collection dictionary.")
        self.documents = copy.deepcopy(documents)

    def get(self, collection, identifier):
        validate_collection(collection, private=True)
        if collection in PUBLIC_FIELDS:
            validate_public_path(collection, identifier)
        elif collection == "users":
            require_uid(identifier)
        elif not isinstance(identifier, str) or not identifier or "/" in identifier:
            raise AccessError("Invalid private document path.")
        return copy.deepcopy(self.documents.get(collection, {}).get(identifier))

    def page(self, collection, *, filters=(), order_by="documentId", page_size=20, after_id=None):
        validate_query(collection, filters, order_by, page_size, after_id)
        rows = [(identifier, copy.deepcopy(data)) for identifier, data in self.documents.get(collection, {}).items()
                if isinstance(data, dict) and matches_filters(data, filters)]
        if order_by == "kickoffUtc":
            from app_contracts import utc_text
            rows.sort(key=lambda row: (utc_text(row[1]["kickoffUtc"]) if row[1].get("kickoffUtc") is not None else "",
                                       row[0]), reverse=True)
        else:
            rows.sort(key=lambda row: row[0])
        if after_id is not None:
            positions = [index for index, row in enumerate(rows) if row[0] == after_id]
            if not positions:
                raise ValidationError("Pagination cursor is missing or belongs to a different query; refresh the list.")
            rows = rows[positions[0] + 1:]
        return page_result(rows[:page_size + 1], page_size)

    def private_page(self, actor_uid, owner_uid, kind, *, page_size=20, after_id=None):
        from app_contracts import require_owner
        require_owner(actor_uid, owner_uid)
        if not isinstance(kind, str) or kind not in {"favorites", "watchlist"}:
            raise AccessError("Unsupported private list.")
        validate_page_size(page_size)
        rows = sorted(copy.deepcopy(self.documents.get(f"users/{owner_uid}/{kind}", {})).items())
        if after_id is not None:
            positions = [index for index, row in enumerate(rows) if row[0] == after_id]
            if not positions:
                raise ValidationError("Private pagination cursor is missing; refresh the list.")
            rows = rows[positions[0] + 1:]
        return page_result(rows, page_size)


class FirestoreReadRepository:
    def __init__(self, db):
        self.db = db  # Never initialize a client, access credentials or read on construction.

    def get(self, collection, identifier):
        validate_collection(collection)
        validate_public_path(collection, identifier)
        try:
            snapshot = self.db.collection(collection).document(identifier).get(
                field_paths=PUBLIC_FIELDS[collection], timeout=20, retry=None)
            if snapshot.id != identifier or type(snapshot.exists) is not bool:
                raise ValidationError("The returned public document has inconsistent identity.")
            return snapshot.to_dict() if snapshot.exists else None
        except ValidationError:
            raise
        except Exception:
            raise RepositoryError("Firestore read failed; check authentication, permissions and connectivity.") from None

    def page(self, collection, *, filters=(), order_by="documentId", page_size=20, after_id=None):
        validate_query(collection, filters, order_by, page_size, after_id)
        # Import the installed SDK only on this explicitly requested read path.
        from google.cloud.firestore_v1.base_query import FieldFilter
        try:
            reference = self.db.collection(collection)
            query = reference.select(PUBLIC_FIELDS[collection])
            for field, value in filters:
                query = query.where(filter=FieldFilter(field, "==", value))
            if order_by == "kickoffUtc":
                query = query.order_by("kickoffUtc", direction="DESCENDING").order_by("__name__", direction="DESCENDING")
            else:
                query = query.order_by("__name__")
            if after_id is not None:
                cursor = reference.document(after_id).get(field_paths=PUBLIC_FIELDS[collection], timeout=20, retry=None)
                if not cursor.exists or cursor.id != after_id or not matches_filters(cursor.to_dict() or {}, filters):
                    raise ValidationError("Pagination cursor is missing or belongs to a different query; refresh the list.")
                query = query.start_after(cursor)
            snapshots = list(query.limit(page_size + 1).stream(timeout=20, retry=None))
            rows = []
            for snapshot in snapshots:
                validate_public_path(collection, snapshot.id)
                rows.append((snapshot.id, project(snapshot.to_dict(), PUBLIC_FIELDS[collection])))
            return page_result(rows, page_size)
        except ValidationError:
            raise
        except Exception:
            raise RepositoryError("Firestore query failed; check permissions, connectivity and required indexes.") from None
