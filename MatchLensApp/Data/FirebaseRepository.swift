import Foundation
import FirebaseAuth
import FirebaseFirestore

@MainActor
final class FirebaseRepository {
    let uid: String
    private let auth: Auth
    private let db: Firestore
    private let catalog: CompetitionBindings
    private let pageSize = 20

    init(auth: Auth, db: Firestore, uid: String, catalog: CompetitionBindings) throws {
        guard ClientID.uid(uid), auth.currentUser?.uid == uid else { throw ClientError.signedOut }
        self.auth = auth; self.db = db; self.uid = uid; self.catalog = catalog
    }
    func checkSession() throws {
        guard auth.currentUser?.uid == uid else { throw ClientError.signedOut }
    }
    nonisolated static func fields(_ data: [String: Any]) -> [String: Any] {
        data.mapValues { value in
            if let value = value as? Timestamp { return StoreStamp(seconds: value.seconds, nanoseconds: value.nanoseconds) }
            return value
        }
    }
    private func get(_ collection: String, _ id: String) async throws -> [String: Any] {
        try checkSession()
        let snapshot: DocumentSnapshot
        do { snapshot = try await db.collection(collection).document(id).getDocument(source: .server) }
        catch {
            let value = error as NSError
            if collection == "highlights", value.domain == FirestoreErrorDomain,
               FirestoreErrorCode.Code(rawValue: value.code) == .permissionDenied { throw ClientError.mediaUnavailable }
            throw error
        }
        try checkSession()
        guard let data = snapshot.data(), snapshot.exists else { throw ClientError.missingRecord }
        return Self.fields(data)
    }
    private func page(_ query: Query, path: String, cursor: String?,
                      belongs: ([String: Any]) -> Bool = { _ in true }) async throws -> ([QueryDocumentSnapshot], String?) {
        try checkSession()
        var query = query
        if let cursor {
            guard !cursor.isEmpty, !cursor.contains("/") else { throw ClientError.invalidData("page cursor") }
            let snapshot = try await db.collection(path).document(cursor).getDocument(source: .server)
            try checkSession()
            guard let data = snapshot.data(), snapshot.exists, belongs(Self.fields(data)) else { throw ClientError.conflict }
            query = query.start(afterDocument: snapshot)
        }
        let rows = try await query.limit(to: pageSize + 1).getDocuments(source: .server).documents
        try checkSession()
        let visible = Array(rows.prefix(pageSize))
        return (visible, rows.count > pageSize ? visible.last?.documentID : nil)
    }
    func player(_ id: String) async throws -> PlayerRecord {
        try SavedKind.player.validate(id)
        return try PlayerRecord(id: id, data: await get("players", id))
    }
    func team(_ id: String) async throws -> TeamRecord {
        try SavedKind.team.validate(id)
        return try TeamRecord(id: id, data: await get("teams", id))
    }
    func players(cursor: String?) async throws -> ClientPage<PlayerRecord> {
        let (rows, next) = try await page(db.collection("players").order(by: FieldPath.documentID()), path: "players", cursor: cursor)
        var items: [PlayerRecord] = [], issues = 0
        for row in rows {
            do { items.append(try PlayerRecord(id: row.documentID, data: Self.fields(row.data()))) }
            catch { issues += 1 }
        }
        return ClientPage(items: items, nextCursor: next, issues: issues)
    }
    func teams(cursor: String?) async throws -> ClientPage<TeamRecord> {
        let (rows, next) = try await page(db.collection("teams").order(by: FieldPath.documentID()), path: "teams", cursor: cursor)
        var items: [TeamRecord] = [], issues = 0
        for row in rows {
            do { items.append(try TeamRecord(id: row.documentID, data: Self.fields(row.data()))) }
            catch { issues += 1 }
        }
        return ClientPage(items: items, nextCursor: next, issues: issues)
    }
    private func card(_ match: MatchRecord) async throws -> MatchCard {
        guard let competitionID = match.competitionId else { throw ClientError.invalidData("unresolved competition") }
        let home = try await team(match.homeTeamId), away = try await team(match.awayTeamId)
        let competition = try CompetitionRecord(id: competitionID, data: await get("competitions", competitionID))
        try catalog.validate(match, competition: competition)
        return MatchCard(match: match, home: home, away: away, competition: competition)
    }
    func match(_ id: String) async throws -> MatchCard {
        try SavedKind.match.validate(id)
        return try await card(MatchRecord(id: id, data: await get("matches", id)))
    }
    func matches(cursor: String?, teamID: String? = nil, home: Bool = true) async throws -> ClientPage<MatchCard> {
        var query: Query = db.collection("matches").whereField("isDemo", isEqualTo: false)
        let side = home ? "homeTeamId" : "awayTeamId"
        if let teamID { try SavedKind.team.validate(teamID); query = query.whereField(side, isEqualTo: teamID) }
        query = query.order(by: "kickoffUtc", descending: true).order(by: FieldPath.documentID(), descending: true)
        let (rows, next) = try await page(query, path: "matches", cursor: cursor, belongs: {
            (try? DocumentFields(data: $0).flag("isDemo")) == false && (teamID == nil || $0[side] as? String == teamID)
        })
        var cards: [MatchCard] = [], issues = 0
        for row in rows {
            do {
                let record = try MatchRecord(id: row.documentID, data: Self.fields(row.data()))
                guard !record.isDemo else { throw ClientError.invalidData("real-match feed") }
                cards.append(try await card(record))
            } catch ClientError.invalidData { issues += 1 }
              catch ClientError.missingRecord { issues += 1 }
        }
        try checkSession()
        return ClientPage(items: cards, nextCursor: next, issues: issues)
    }
    func detail(_ id: String, eventCursor: String? = nil, highlightCursor: String? = nil) async throws -> MatchDetail {
        let card = try await match(id)
        let eventQuery = db.collection("matchEvents").whereField("matchId", isEqualTo: id).order(by: FieldPath.documentID())
        let highlightQuery = db.collection("highlights").whereField("matchId", isEqualTo: id)
            .whereField("rightsStatus", isEqualTo: "unconfirmed").whereField("mediaReference", isEqualTo: NSNull())
            .order(by: FieldPath.documentID())
        let (eventRows, nextEvent) = try await page(eventQuery, path: "matchEvents", cursor: eventCursor, belongs: { $0["matchId"] as? String == id })
        let (highlightRows, nextHighlight) = try await page(highlightQuery, path: "highlights", cursor: highlightCursor, belongs: {
            $0["matchId"] as? String == id && $0["rightsStatus"] as? String == "unconfirmed" && $0["mediaReference"] is NSNull
        })
        var events: [String: EventRecord] = [:], highlights: [HighlightRecord] = []
        for row in eventRows { events[row.documentID] = try EventRecord(id: row.documentID, data: Self.fields(row.data()), parent: card.match) }
        for row in highlightRows { highlights.append(try HighlightRecord(id: row.documentID, data: Self.fields(row.data()), parent: card.match)) }
        let needed = Set(highlights.flatMap { $0.markers.map(\.eventId) }).union(events.keys)
        guard needed.count <= 100 else { throw ClientError.invalidData("analysis reference budget") }
        for eventID in needed.sorted() where events[eventID] == nil {
            events[eventID] = try EventRecord(id: eventID, data: await get("matchEvents", eventID), parent: card.match)
        }
        var players: [String: PlayerRecord] = [:]
        for playerID in Set(events.values.compactMap(\.playerId)).sorted() { players[playerID] = try await player(playerID) }
        try checkSession()
        return MatchDetail(card: card, events: events.values.sorted {
            ($0.minute ?? Int.max, $0.addedTime ?? 0, $0.id) < ($1.minute ?? Int.max, $1.addedTime ?? 0, $1.id)
        }, highlights: highlights, players: players, eventsCursor: nextEvent, highlightsCursor: nextHighlight)
    }
    func profile() async throws -> UserProfile? {
        try checkSession()
        let snapshot = try await db.collection("users").document(uid).getDocument(source: .server)
        try checkSession()
        return try snapshot.data().map { try UserProfile(uid: uid, data: Self.fields($0)) }
    }
    func preferences() async throws -> UserPreferences {
        try checkSession()
        let snapshot = try await db.collection("users").document(uid).collection("settings").document("preferences").getDocument(source: .server)
        try checkSession()
        return try snapshot.data().map { try UserPreferences(data: Self.fields($0)) } ?? UserPreferences()
    }
    // All write methods are called only by explicit registration/save/remove buttons.
    // No profile/default settings are written during launch or session restoration.
    func saveProfile(name: String, expected: UserProfile?) async throws {
        let f = DocumentFields(data: ["displayName": name])
        let displayName = try f.text("displayName")
        guard displayName.count <= 80 else { throw ClientError.invalidData("display name") }
        try checkSession()
        let uid = self.uid, auth = self.auth, ref = db.collection("users").document(self.uid)
        _ = try await db.runTransaction { @Sendable transaction, errorPointer -> Any? in
            do {
                guard auth.currentUser?.uid == uid else { throw ClientError.signedOut }
                let snapshot = try transaction.getDocument(ref)
                let current = try snapshot.data().map { try UserProfile(uid: uid, data: Self.fields($0)) }
                guard current == expected else { throw ClientError.conflict }
                if let current {
                    if current.displayName != displayName {
                        transaction.updateData(["displayName": displayName, "updatedAt": FieldValue.serverTimestamp()], forDocument: ref)
                    }
                } else {
                    transaction.setData(["uid": uid, "displayName": displayName, "schemaVersion": 1,
                                         "createdAt": FieldValue.serverTimestamp(), "updatedAt": FieldValue.serverTimestamp()], forDocument: ref)
                }
            } catch { errorPointer?.pointee = error as NSError }
            return nil
        }
        try checkSession()
    }
    func savePreferences(_ desired: UserPreferences, expected: UserPreferences) async throws {
        try desired.validate(); try checkSession()
        let uid = self.uid, auth = self.auth, db = self.db
        let ref = db.collection("users").document(uid).collection("settings").document("preferences")
        _ = try await db.runTransaction { @Sendable transaction, errorPointer -> Any? in
            do {
                guard auth.currentUser?.uid == uid else { throw ClientError.signedOut }
                let snapshot = try transaction.getDocument(ref)
                let current = try snapshot.data().map { try UserPreferences(data: Self.fields($0)) } ?? UserPreferences()
                guard current == expected else { throw ClientError.conflict }
                if let teamID = desired.favoriteTeamId {
                    let team = try transaction.getDocument(db.collection("teams").document(teamID))
                    guard let data = team.data() else { throw ClientError.missingRecord }
                    _ = try TeamRecord(id: teamID, data: Self.fields(data))
                }
                var updated = desired; updated.revision = current.revision
                if snapshot.exists && updated == current { return nil }
                let teamValue: Any = desired.favoriteTeamId.map { $0 as Any } ?? NSNull()
                var data: [String: Any] = ["favoriteTeamId": teamValue,
                    "scoreNotifications": desired.scoreNotifications, "highlightNotifications": desired.highlightNotifications,
                    "appearance": desired.appearance, "updatedAt": FieldValue.serverTimestamp()]
                if snapshot.exists { transaction.updateData(data, forDocument: ref) }
                else { data["schemaVersion"] = 1; transaction.setData(data, forDocument: ref) }
            } catch { errorPointer?.pointee = error as NSError }
            return nil
        }
        try checkSession()
    }
    func setSaved(kind: SavedKind, targetID: String, saved: Bool, watchlist: Bool = false) async throws {
        try kind.validate(targetID); try checkSession()
        guard !watchlist || kind == .match else { throw ClientError.invalidData("watchlist target") }
        let uid = self.uid, auth = self.auth, db = self.db
        let id = watchlist ? targetID : kind.rawValue + "_" + targetID
        let ref = db.collection("users").document(uid).collection(watchlist ? "watchlist" : "favorites").document(id)
        _ = try await db.runTransaction { @Sendable transaction, errorPointer -> Any? in
            do {
                guard auth.currentUser?.uid == uid else { throw ClientError.signedOut }
                let current = try transaction.getDocument(ref)
                if let data = current.data() { _ = try SavedRecord(id: id, data: Self.fields(data), watchlist: watchlist) }
                if !saved { if current.exists { transaction.deleteDocument(ref) }; return nil }
                let target = try transaction.getDocument(db.collection(kind.collection).document(targetID))
                guard let raw = target.data() else { throw ClientError.missingRecord }
                let data = Self.fields(raw)
                switch kind {
                case .player: _ = try PlayerRecord(id: targetID, data: data)
                case .team: _ = try TeamRecord(id: targetID, data: data)
                case .match: _ = try MatchRecord(id: targetID, data: data)
                case .highlight:
                    let parentID = try DocumentFields(data: data).text("matchId")
                    guard ClientID.match(parentID) else { throw ClientError.invalidData("highlight parent") }
                    let parent = try transaction.getDocument(db.collection("matches").document(parentID))
                    guard let parentData = parent.data() else { throw ClientError.missingRecord }
                    _ = try HighlightRecord(id: targetID, data: data, parent: MatchRecord(id: parentID, data: Self.fields(parentData)))
                }
                if current.exists { return nil } // Desired state, never toggle or duplicate.
                var fields: [String: Any] = ["schemaVersion": 1, "createdAt": FieldValue.serverTimestamp()]
                if watchlist { fields["matchId"] = targetID }
                else { fields["targetType"] = kind.rawValue; fields["targetId"] = targetID }
                transaction.setData(fields, forDocument: ref)
            } catch { errorPointer?.pointee = error as NSError }
            return nil
        }
        try checkSession()
        let confirmed = try await ref.getDocument(source: .server)
        try checkSession()
        guard confirmed.exists == saved else { throw ClientError.conflict }
        if let data = confirmed.data(), saved {
            _ = try SavedRecord(id: id, data: Self.fields(data), watchlist: watchlist)
        }
    }
    func savedItems(watchlist: Bool, cursor: String?) async throws -> ClientPage<SavedItem> {
        let path = "users/\(uid)/" + (watchlist ? "watchlist" : "favorites")
        let (rows, next) = try await page(db.collection(path).order(by: FieldPath.documentID()), path: path, cursor: cursor)
        var result: [SavedItem] = []
        for row in rows {
            let record = try SavedRecord(id: row.documentID, data: Self.fields(row.data()), watchlist: watchlist)
            do {
                let title: String, subtitle: String, parentID: String?
                switch record.kind {
                case .player: let data = try await player(record.targetId); title = data.name; subtitle = data.position; parentID = nil
                case .team: let data = try await team(record.targetId); title = data.name; subtitle = data.country; parentID = nil
                case .match:
                    let card = try await match(record.targetId); title = card.title
                    subtitle = card.match.isDemo ? "Fictional demonstration" : card.match.finalScore.text; parentID = card.id
                case .highlight:
                    let raw = try await get("highlights", record.targetId)
                    let parent = try await match(DocumentFields(data: raw).text("matchId"))
                    let highlight = try HighlightRecord(id: record.targetId, data: raw, parent: parent.match)
                    title = highlight.title; subtitle = parent.match.isDemo ? "Fictional metadata — no video" : "Metadata only — no video"; parentID = parent.id
                }
                result.append(SavedItem(record: record, title: title, subtitle: subtitle, available: true, matchId: parentID))
            } catch ClientError.missingRecord {
                result.append(SavedItem(record: record, title: "Unavailable saved item", subtitle: "The target was removed.", available: false, matchId: nil))
            } catch ClientError.invalidData {
                result.append(SavedItem(record: record, title: "Saved item needs review", subtitle: "Its data could not be validated.", available: false, matchId: nil))
            } catch ClientError.mediaUnavailable {
                result.append(SavedItem(record: record, title: "Highlight unavailable", subtitle: "Media access has not been approved.", available: false, matchId: nil))
            }
        }
        try checkSession()
        return ClientPage(items: result, nextCursor: next, issues: 0)
    }
}
