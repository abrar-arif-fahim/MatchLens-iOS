"""App-facing catalog/feed/detail contracts, using injected read-only repositories.

UIDs here represent an already authenticated caller in an offline contract test;
this module does not verify tokens or replace Firebase client security rules.
"""

import copy

from app_contracts import (MAX_PAGE_SIZE, PUBLIC_FIELDS, match_document, player_document, project,
                           require_uid, search_text, team_document, validate_page_size, validate_public_path)
from app_repository import RepositoryError
from competition_mapping import get_competition
from highlight_service import HIGHLIGHT_FIELDS, MARKER_FIELDS, prepare_highlight_bundles
from match_event_service import EVENT_FIELDS, validate_related_id
from match_service import prepare_matches
from validate_competition_schema import COMPETITION_FIELDS, validate_catalog, validate_competition
from validate_match_schema import STATUSES, ValidationError


MAX_ANALYSIS_LINKS = 100
MEDIA_MESSAGE = "Playback unavailable: no actual authorized media has been demonstrated."


class NotFoundError(ValidationError):
    """A requested visible record is absent, without exposing hidden data."""


class AppReadService:
    def __init__(self, repository, catalog, *, actor_uid, demo_mode=False):
        require_uid(actor_uid)
        if type(demo_mode) is not bool:
            raise ValidationError("Demo mode must be an explicit boolean.")
        validate_catalog(catalog)
        self.repository, self.catalog = repository, copy.deepcopy(catalog)
        self.actor_uid, self.demo_mode = actor_uid, demo_mode

    def _get(self, collection, identifier, cache=None):
        validate_public_path(collection, identifier)
        key = (collection, identifier)
        if cache is not None and key in cache:
            return copy.deepcopy(cache[key])
        record = self.repository.get(collection, identifier)
        if record is None:
            raise NotFoundError("A required public record is missing; refresh or review its references.")
        if cache is not None:
            cache[key] = copy.deepcopy(record)
        return record

    def get_player(self, player_id):
        return {"player": player_document(player_id, self._get("players", player_id)),
                "team": None, "statistics": None, "rosterStatus": "notCollected"}

    def get_team(self, team_id):
        return {"team": team_document(team_id, self._get("teams", team_id)),
                "players": None, "rosterStatus": "notCollected"}

    def _search(self, collection, query, page_size, cursor):
        validate_page_size(page_size)
        needle = search_text(query)
        page = self.repository.page(collection, page_size=MAX_PAGE_SIZE, after_id=cursor)
        items, issues, scanned = [], [], 0
        next_cursor = page["nextCursor"]
        for index, (identifier, raw) in enumerate(page["items"]):
            scanned += 1
            try:
                data = player_document(identifier, raw) if collection == "players" else team_document(identifier, raw)
                text = data["name"] + (" " + data["shortName"] if collection == "teams" else "")
                # Names can exceed the user's 100-character search-input limit.
                normalized = search_text(text, max_length=401)
                if needle in normalized:
                    items.append(data)
            except ValidationError:
                issues.append({"documentId": identifier, "reason": "Invalid stored identity fields."})
            if len(items) == page_size:
                more = index < len(page["items"]) - 1 or page["hasMore"]
                next_cursor = identifier if more else None
                break
        return {"items": items, "nextCursor": next_cursor, "hasMore": next_cursor is not None,
                "searchScope": "boundedCatalogPage", "scanned": scanned, "issues": issues}

    def search_players(self, query="", *, page_size=20, cursor=None):
        return self._search("players", query, page_size, cursor)

    def search_teams(self, query="", *, page_size=20, cursor=None):
        return self._search("teams", query, page_size, cursor)

    def _basic_match(self, identifier, raw=None, cache=None):
        match = match_document(identifier, self._get("matches", identifier, cache) if raw is None else raw)
        if match["isDemo"] != self.demo_mode:
            raise NotFoundError("This match is outside the selected real/demo catalog.")
        teams = [team_document(match[field], self._get("teams", match[field], cache))
                 for field in ("homeTeamId", "awayTeamId")]
        expected = get_competition(self.catalog, match["competitionId"])
        current = project(self._get("competitions", expected["competitionId"], cache), COMPETITION_FIELDS)
        validate_competition(current)
        if current != expected:
            raise ValidationError("Competition identity differs from the reviewed catalog; review required.")
        prepared = prepare_matches([match], teams, self.catalog)[0]
        # Exclude the internal SDK Timestamp write projection from the JSON read DTO.
        return {field: prepared[field] for field in ("match", "homeTeam", "awayTeam", "competition", "competitionSeasons")}

    def _match_page(self, filters, page_size, cursor):
        page = self.repository.page("matches", filters=(("isDemo", self.demo_mode),) + tuple(filters),
                                    order_by="kickoffUtc", page_size=page_size, after_id=cursor)
        items, issues, cache = [], [], {}
        for identifier, raw in page["items"]:
            try:
                items.append(self._basic_match(identifier, raw, cache))
            except RepositoryError:
                raise  # A connection failure is not an empty or successful feed.
            except ValidationError:
                issues.append({"documentId": identifier, "reason": "Invalid or unresolved match references; review required."})
        return {"items": items, "nextCursor": page["nextCursor"], "hasMore": page["hasMore"], "issues": issues}

    def list_matches(self, *, page_size=20, cursor=None, status=None):
        if status is not None and (not isinstance(status, str) or status not in STATUSES):
            raise ValidationError("Unsupported match status filter.")
        return self._match_page(() if status is None else (("status", status),), page_size, cursor)

    def home_feed(self, *, page_size=20, cursor=None):
        return {"matches": self.list_matches(page_size=page_size, cursor=cursor), "isDemo": self.demo_mode,
                "dataLabel": "Fictional demonstration - not real match results." if self.demo_mode else "Real-source catalog.",
                "featuredHighlights": [], "mediaMessage": MEDIA_MESSAGE}

    def team_matches(self, team_id, *, page_size=20, home_cursor=None, away_cursor=None):
        validate_page_size(page_size)
        for cursor in (home_cursor, away_cursor):
            if cursor is not None:
                validate_public_path("matches", cursor)
        self.get_team(team_id)
        return {"home": self._match_page((("homeTeamId", team_id),), page_size, home_cursor),
                "away": self._match_page((("awayTeamId", team_id),), page_size, away_cursor)}

    def _analysis(self, basic, event_rows, highlight_rows):
        match = basic["match"]
        events = {}
        for identifier, raw in event_rows:
            data = project(raw, EVENT_FIELDS)
            if data["eventId"] != identifier or data["matchId"] != match["matchId"]:
                raise ValidationError("Stored event identity is inconsistent.")
            events[identifier] = data
        highlights, needed = [], set()
        for identifier, raw in highlight_rows:
            data = project(raw, HIGHLIGHT_FIELDS)
            if data["highlightId"] != identifier or data["matchId"] != match["matchId"]:
                raise ValidationError("Stored highlight identity is inconsistent.")
            # The app contract deliberately supports metadata-only highlights now.
            if data["rightsStatus"] != "unconfirmed" or data["mediaReference"] is not None:
                raise ValidationError(MEDIA_MESSAGE)
            if not isinstance(data["markers"], list):
                raise ValidationError("Stored highlight markers must be an array.")
            if len(data["markers"]) > MAX_ANALYSIS_LINKS:
                raise ValidationError("Analysis reference budget exceeded; use smaller event/highlight pages.")
            for marker in data["markers"]:
                if not isinstance(marker, dict) or set(marker) != MARKER_FIELDS:
                    raise ValidationError("Stored highlight marker fields are invalid.")
                validate_related_id(marker["eventId"], match["matchId"], "event")
                needed.add(marker["eventId"])
            highlights.append(data)
        if len(needed | set(events)) > MAX_ANALYSIS_LINKS:
            raise ValidationError("Analysis reference budget exceeded; use smaller event/highlight pages.")
        for identifier in sorted(needed - set(events)):
            raw = self._get("matchEvents", identifier)
            data = project(raw, EVENT_FIELDS)
            if data["eventId"] != identifier:
                raise ValidationError("A referenced event document ID is inconsistent.")
            events[identifier] = data
        players = []
        player_ids = set()
        for event in events.values():
            identifier = event["playerId"]
            if identifier is not None:
                validate_public_path("players", identifier)
                player_ids.add(identifier)
        for identifier in sorted(player_ids):
            data = player_document(identifier, self._get("players", identifier))
            players.append(dict(project(data, PUBLIC_FIELDS["players"]), documentId=identifier))
        return prepare_highlight_bundles([match], [basic["homeTeam"], basic["awayTeam"]], players,
                                         self.catalog, list(events.values()), highlights)[0]

    @staticmethod
    def _highlight_dto(highlight):
        fields = ("highlightId", "matchId", "title", "durationSeconds", "rightsStatus", "markers", "isDemo", "source")
        return dict(project(highlight, fields), playbackAvailable=False, unavailableReason=MEDIA_MESSAGE)

    def get_match_detail(self, match_id, *, page_size=20, event_cursor=None, highlight_cursor=None):
        validate_page_size(page_size)
        for collection, cursor in (("matchEvents", event_cursor), ("highlights", highlight_cursor)):
            if cursor is not None:
                validate_public_path(collection, cursor)
        basic = self._basic_match(match_id)
        event_page = self.repository.page("matchEvents", filters=(("matchId", match_id),),
                                          page_size=page_size, after_id=event_cursor)
        highlight_page = self.repository.page("highlights", page_size=page_size, after_id=highlight_cursor,
            filters=(("matchId", match_id), ("rightsStatus", "unconfirmed"), ("mediaReference", None)))
        prepared = self._analysis(basic, event_page["items"], highlight_page["items"])
        visible_events = {row[0] for row in event_page["items"]}
        result = dict(basic, eventPlayers=prepared["eventPlayers"], highlightTimelines=prepared["highlightTimelines"],
                      statistics=None, lineups=None, mediaMessage=MEDIA_MESSAGE)
        result["events"] = {"items": [row for row in prepared["events"] if row["eventId"] in visible_events],
                            "nextCursor": event_page["nextCursor"], "hasMore": event_page["hasMore"]}
        result["highlights"] = {"items": [self._highlight_dto(row) for row in prepared["highlights"]],
                                "nextCursor": highlight_page["nextCursor"], "hasMore": highlight_page["hasMore"]}
        result["isDemo"] = basic["match"]["isDemo"]
        result["dataLabel"] = "Fictional demonstration - not a real match result." if result["isDemo"] else "Real-source record."
        return result

    def resolve_reference(self, kind, identifier):
        if kind == "player":
            return self.get_player(identifier)["player"]
        if kind == "team":
            return self.get_team(identifier)["team"]
        if kind == "match":
            return self._basic_match(identifier)["match"]
        if kind == "highlight":
            raw = self._get("highlights", identifier)
            data = project(raw, HIGHLIGHT_FIELDS)
            basic = self._basic_match(data["matchId"])
            prepared = self._analysis(basic, [], [(identifier, data)])
            return self._highlight_dto(prepared["highlights"][0])
        raise ValidationError("Unsupported saved-reference type.")
