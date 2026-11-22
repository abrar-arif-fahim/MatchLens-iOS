"""Reusable in-memory preparation and read-only previews. Never write or fetch APIs."""

import copy
import re
from types import SimpleNamespace

from competition_mapping import get_competition_seasons, validate_match_competition
from convert_api_football_fixture import convert_fixture
# Existing SDK-aware modules are safe to import; these helpers do not initialize it.
from preview_match_import import MATCH_FIELDS, compare_match, prepare_match_data
from preview_multiple_teams import PreviewError, validate_team_records
from validate_competition_schema import COMPETITION_FIELDS, validate_catalog, validate_competition
from validate_match_schema import SLUG, ValidationError, require_text, validate_match, validate_team_reference_data


TEAM_FIELDS = ("teamId", "wikidataId", "name", "shortName", "country", "source")
READ_FIELDS = {"teams": TEAM_FIELDS, "competitions": tuple(sorted(COMPETITION_FIELDS)), "matches": MATCH_FIELDS}
ID_PATTERNS = {"teams": r"wikidata_Q[1-9][0-9]*", "competitions": r"(?:demo_)?competition_" + SLUG,
               "matches": r"(?:demo|match)_" + SLUG}


def index_teams(teams):
    if not isinstance(teams, list) or not teams:
        raise ValidationError("Supply a nonempty array of validated team records.")
    try:
        records = validate_team_records({"teams": teams})
    except PreviewError as error:
        raise ValidationError(str(error)) from None
    return {team["teamId"]: dict(team) for team in records}


def prepare_matches(matches, teams, catalog):
    """Validate the entire input before any caller can start a preview read."""
    validate_catalog(catalog)
    indexed = index_teams(teams)
    if not isinstance(matches, list) or not matches:
        raise ValidationError("Supply a nonempty array of match records.")
    prepared, seen = [], set()
    for match in matches:
        validate_match(match)
        if match["matchId"] in seen:
            raise ValidationError("Duplicate matchId; the complete preview was stopped.")
        seen.add(match["matchId"])
        if any(match[field] not in indexed for field in ("homeTeamId", "awayTeamId")):
            raise ValidationError("A match references a team absent from the local records.")
        competition = validate_match_competition(match, catalog)
        prepared.append({
            "match": copy.deepcopy(match), "firestoreData": prepare_match_data(match),
            "homeTeam": dict(indexed[match["homeTeamId"]]), "awayTeam": dict(indexed[match["awayTeamId"]]),
            "competition": competition,
            "competitionSeasons": get_competition_seasons(catalog, competition["competitionId"]),
        })
    return prepared


def prepare_fixture(record, verified_team_mapping, teams, catalog, *, is_demo=None, demo_competition_id=None):
    """Convert one caller-supplied fixture in memory, then validate its references.

    Fictional inputs require explicit demo provenance and an explicitly selected
    demo competition. No synthetic record or provider response is saved here.
    """
    if is_demo is not True and demo_competition_id is not None:
        raise ValidationError("A real-source fixture cannot select a demo competition.")
    match = convert_fixture(record, verified_team_mapping, is_demo=is_demo, competition_catalog=catalog)
    if is_demo:
        # The provider number cannot establish a fictional internal association.
        match["competitionId"] = demo_competition_id
    return prepare_matches([match], teams, catalog)[0]


def validate_document_path(collection, document_id):
    if not isinstance(collection, str) or collection not in READ_FIELDS:
        raise ValidationError("Only canonical team, competition and match document paths may be read.")
    require_text(document_id, "Document ID")
    if not re.fullmatch(ID_PATTERNS[collection], document_id):
        raise ValidationError("Only canonical team, competition and match document paths may be read.")


def firestore_document_reader(db):
    """Wrap an already configured client. Creating this reader performs no I/O."""
    def read_document(collection, document_id):
        validate_document_path(collection, document_id)
        try:
            return db.collection(collection).document(document_id).get(
                field_paths=READ_FIELDS[collection], timeout=20, retry=None
            )
        except Exception:
            # Do not propagate SDK messages, which may include private configuration.
            raise ValidationError(
                "Firestore read failed; check credentials, read permissions and network access."
            ) from None
    return read_document


def local_document_reader(documents):
    """Use an isolated local snapshot store for demos/tests, without Firebase."""
    store = copy.deepcopy(documents)
    def read_document(collection, document_id):
        validate_document_path(collection, document_id)
        data = copy.deepcopy(store.get(collection, {}).get(document_id))
        return SimpleNamespace(id=document_id, exists=data is not None, to_dict=lambda: copy.deepcopy(data))
    return read_document


def preview_matches(matches, teams, catalog, read_document):
    """Return a complete CREATE/UPDATE/NO CHANGE plan, or raise without a plan.

    Validate every local record first; read each distinct reference only once.
    The injected reader is the only I/O boundary. There are no write operations.
    """
    prepared = prepare_matches(matches, teams, catalog)
    if not callable(read_document):
        raise ValidationError("Supply a read-only document reader.")
    cache = {}

    def read(collection, identifier):
        key = (collection, identifier)
        if key not in cache:
            try:
                snapshot = read_document(collection, identifier)
            except ValidationError:
                raise
            except Exception:
                raise ValidationError("A document read failed; no complete preview is available.") from None
            if (getattr(snapshot, "id", None) != identifier
                    or type(getattr(snapshot, "exists", None)) is not bool
                    or not callable(getattr(snapshot, "to_dict", None))):
                raise ValidationError("A returned document snapshot has inconsistent identifiers or existence data.")
            cache[key] = snapshot
        return cache[key]

    plan = []
    for item in prepared:
        match = item["match"]
        for field in ("homeTeamId", "awayTeamId"):
            identifier = match[field]
            snapshot = read("teams", identifier)
            if not snapshot.exists:
                raise ValidationError(f"teams/{identifier} does not exist; match preview stopped.")
            validate_team_reference_data(identifier, snapshot.to_dict())
        competition = item["competition"]
        snapshot = read("competitions", competition["competitionId"])
        if not snapshot.exists:
            raise ValidationError("The referenced competition document does not exist; match preview stopped.")
        current = snapshot.to_dict()
        if not isinstance(current, dict):
            raise ValidationError("The referenced competition document has invalid data.")
        current = {field: current[field] for field in COMPETITION_FIELDS if field in current}
        validate_competition(current)
        if current != competition:
            raise ValidationError("The competition document differs from the reviewed local identity; manual review is required.")
        snapshot = read("matches", match["matchId"])
        operation, differences = compare_match(item["firestoreData"], snapshot)
        plan.append({"matchId": match["matchId"], "operation": operation, "differences": differences,
                     "prepared": item})
    return plan


def summarize_plan(plan):
    return {operation: sum(entry["operation"] == operation for entry in plan)
            for operation in ("CREATE", "UPDATE", "NO CHANGE")}
