import Foundation
#if canImport(CoreFoundation)
import CoreFoundation
#endif

enum ClientError: LocalizedError, CustomNSError {
    case invalidData(String), missingRecord, signedOut, conflict, mediaUnavailable
    var errorDescription: String? {
        switch self {
        case .invalidData(let field): return "Invalid or incomplete \(field). Refresh or request a data review."
        case .missingRecord: return "This record is unavailable or has been removed."
        case .signedOut: return "Your session changed. Please sign in again."
        case .conflict: return "This information changed on another device. Refresh before saving again."
        case .mediaUnavailable: return "No authorized video is available. Event metadata is still available."
        }
    }
    static var errorDomain: String { "MatchLens.Client" }
    var errorCode: Int {
        switch self { case .invalidData: return 1; case .missingRecord: return 2; case .signedOut: return 3; case .conflict: return 4; case .mediaUnavailable: return 5 }
    }
    var errorUserInfo: [String: Any] { [NSLocalizedDescriptionKey: errorDescription ?? "Unable to complete this operation."] }
}
enum ClientID {
    static let slug = "[a-z0-9]+(?:_[a-z0-9]+)*"
    static func matches(_ value: String, _ pattern: String) -> Bool {
        guard let range = value.range(of: "^(?:" + pattern + ")$", options: .regularExpression) else { return false }
        return range.lowerBound == value.startIndex && range.upperBound == value.endIndex
    }
    static func team(_ value: String) -> Bool { matches(value, "wikidata_Q[1-9][0-9]*") }
    static func match(_ value: String) -> Bool { matches(value, "(?:demo|match)_" + slug) }
    static func child(_ value: String, matchID: String, kind: String) -> Bool {
        guard match(matchID), let separator = matchID.firstIndex(of: "_") else { return false }
        let parent = String(matchID[matchID.index(after: separator)...])
        let prefix = (matchID.hasPrefix("demo_") ? "demo_" : "") + kind + "_" + parent + "__"
        return value.hasPrefix(prefix) && matches(String(value.dropFirst(prefix.count)), slug)
    }
    static func uid(_ value: String) -> Bool {
        !value.isEmpty && value.count <= 128 && value != "." && value != ".." &&
        !value.contains("/") && value.unicodeScalars.allSatisfy { $0.value >= 33 } &&
        value == value.trimmingCharacters(in: .whitespacesAndNewlines)
    }
}
// Exact revision precision for transactions; Date is only for display.
struct StoreStamp: Equatable, Comparable, Sendable {
    let seconds: Int64
    let nanoseconds: Int32
    var date: Date { Date(timeIntervalSince1970: Double(seconds) + Double(nanoseconds) / 1_000_000_000) }
    static func < (lhs: Self, rhs: Self) -> Bool {
        (lhs.seconds, lhs.nanoseconds) < (rhs.seconds, rhs.nanoseconds)
    }
}
struct DocumentFields {
    let data: [String: Any]
    static func isBoolean(_ number: NSNumber) -> Bool {
        #if canImport(CoreFoundation)
        return CFGetTypeID(number) == CFBooleanGetTypeID()
        #else
        // Swift Foundation on Windows does not ship CoreFoundation.
        return String(cString: number.objCType) == "c"
        #endif
    }
    func require(_ fields: Set<String>, exact: Bool = false) throws {
        guard fields.isSubset(of: Set(data.keys)), !exact || Set(data.keys) == fields else {
            throw ClientError.invalidData("document fields")
        }
    }
    func text(_ key: String) throws -> String {
        guard let value = data[key] as? String, !value.isEmpty, value.count <= 200,
              value == value.trimmingCharacters(in: .whitespacesAndNewlines),
              !value.unicodeScalars.contains(where: { $0.value < 32 }),
              !["unknown", "n/a", "null", "none"].contains(value.lowercased()) else {
            throw ClientError.invalidData(key)
        }
        return value
    }
    func nullableText(_ key: String) throws -> String? {
        guard let value = data[key] else { throw ClientError.invalidData(key) }
        return value is NSNull ? nil : try text(key)
    }
    func flag(_ key: String) throws -> Bool {
        guard let value = data[key] as? NSNumber, Self.isBoolean(value) else {
            throw ClientError.invalidData(key)
        }
        return value.boolValue
    }
    func integer(_ key: String) throws -> Int {
        guard let value = data[key] as? NSNumber, !Self.isBoolean(value),
              !["f", "d"].contains(String(cString: value.objCType)),
              value.doubleValue >= 0, value.doubleValue < Double(Int.max) else {
            throw ClientError.invalidData(key)
        }
        return value.intValue
    }
    func optionalInteger(_ key: String) throws -> Int? {
        guard let value = data[key] else { throw ClientError.invalidData(key) }
        return value is NSNull ? nil : try integer(key)
    }
    func seconds(_ key: String) throws -> Double? {
        guard let raw = data[key] else { throw ClientError.invalidData(key) }
        if raw is NSNull { return nil }
        guard let value = raw as? NSNumber, !Self.isBoolean(value),
              value.doubleValue.isFinite, value.doubleValue >= 0 else { throw ClientError.invalidData(key) }
        return value.doubleValue
    }
    func stamp(_ key: String) throws -> StoreStamp {
        guard let value = data[key] as? StoreStamp, (0..<1_000_000_000).contains(value.nanoseconds) else {
            throw ClientError.invalidData(key)
        }
        return value
    }
    static func date(_ text: String, format: String) throws -> Date {
        let formatter = DateFormatter()
        formatter.calendar = Calendar(identifier: .gregorian)
        formatter.locale = Locale(identifier: "en_US_POSIX")
        formatter.timeZone = TimeZone(secondsFromGMT: 0)
        formatter.dateFormat = format
        formatter.isLenient = false
        guard let date = formatter.date(from: text), formatter.string(from: date) == text else {
            throw ClientError.invalidData("date")
        }
        return date
    }
}
struct PlayerRecord: Identifiable, Sendable {
    let id: String, wikidataId: String, name: String, dateOfBirth: String, nationality: String, position: String
    init(id: String, data: [String: Any]) throws {
        let f = DocumentFields(data: data)
        try f.require(["wikidataId", "name", "dateOfBirth", "nationality", "position", "source"])
        guard ClientID.team(id), try f.text("wikidataId") == String(id.dropFirst(9)),
              try f.text("source") == "Wikidata" else { throw ClientError.invalidData("player identity") }
        self.id = id; wikidataId = try f.text("wikidataId"); name = try f.text("name")
        dateOfBirth = try f.text("dateOfBirth"); nationality = try f.text("nationality"); position = try f.text("position")
        guard ClientID.matches(dateOfBirth, "[0-9]{4}-[0-9]{2}-[0-9]{2}"),
              try DocumentFields.date(dateOfBirth, format: "yyyy-MM-dd") <= Date() else {
            throw ClientError.invalidData("birth date")
        }
    }
}
struct TeamRecord: Identifiable, Sendable {
    let id: String, name: String, shortName: String, country: String
    init(id: String, data: [String: Any]) throws {
        let f = DocumentFields(data: data)
        try f.require(["teamId", "wikidataId", "name", "shortName", "country", "source"])
        guard ClientID.team(id), try f.text("teamId") == id,
              try f.text("wikidataId") == String(id.dropFirst(9)), try f.text("source") == "Wikidata" else {
            throw ClientError.invalidData("team identity")
        }
        self.id = id; name = try f.text("name"); shortName = try f.text("shortName"); country = try f.text("country")
    }
}
struct CompetitionRecord: Identifiable, Equatable, Sendable {
    let id: String, name: String, kind: String?
    let country: String?, region: String?, source: String
    let isDemo: Bool
    init(id: String, data: [String: Any]) throws {
        let f = DocumentFields(data: data)
        try f.require(["competitionId", "name", "competitionType", "country", "region", "isDemo", "source"])
        isDemo = try f.flag("isDemo")
        guard try f.text("competitionId") == id,
              ClientID.matches(id, (isDemo ? "demo_competition_" : "competition_") + ClientID.slug) else {
            throw ClientError.invalidData("competition identity")
        }
        self.id = id; name = try f.text("name"); kind = try f.nullableText("competitionType")
        if let kind, !["domesticLeague", "nationalCup", "internationalTournament", "friendly"].contains(kind) {
            throw ClientError.invalidData("competition type")
        }
        country = try f.nullableText("country"); region = try f.nullableText("region")
        source = try f.text("source")
        guard isDemo ? source == "demo" : !source.lowercased().contains("demo") else {
            throw ClientError.invalidData("competition source")
        }
    }
}
struct CompetitionBindings {
    let competitions: [String: CompetitionRecord]
    let providerIDs: [String: String]
    init(data: [String: Any]) throws {
        guard let rows = data["competitions"] as? [[String: Any]],
              let mappings = data["providerMappings"] as? [[String: Any]] else {
            throw ClientError.invalidData("bundled competition catalog")
        }
        var identities: [String: CompetitionRecord] = [:], bindings: [String: String] = [:]
        var seen = Set<String>(), seenExternal = Set<String>()
        for row in rows {
            let id = try DocumentFields(data: row).text("competitionId")
            guard identities[id] == nil else { throw ClientError.invalidData("duplicate competition") }
            identities[id] = try CompetitionRecord(id: id, data: row)
        }
        for row in mappings {
            let f = DocumentFields(data: row), external = try f.text("providerCompetitionId")
            guard try f.text("provider") == "API-Football", ClientID.matches(external, "[1-9][0-9]*"),
                  seenExternal.insert(external).inserted else { throw ClientError.invalidData("provider mapping") }
            if try f.text("status") == "pending" {
                guard row["competitionId"] is NSNull, row["verificationEvidence"] is NSNull, row["verifiedAt"] is NSNull else {
                    throw ClientError.invalidData("pending competition mapping")
                }
                continue
            }
            let target = try f.text("competitionId")
            guard try f.text("status") == "verified", identities[target]?.isDemo == false,
                  seen.insert(target).inserted else { throw ClientError.invalidData("unverified competition mapping") }
            bindings[external] = target
        }
        competitions = identities; providerIDs = bindings
    }
    func validate(_ match: MatchRecord, competition: CompetitionRecord) throws {
        guard competition.id == match.competitionId, competition.isDemo == match.isDemo else {
            throw ClientError.invalidData("competition reference")
        }
        if !match.isDemo {
            guard competitions[competition.id] == competition else { throw ClientError.invalidData("reviewed competition identity") }
            if match.source == "API-Football" {
                guard let providerID = match.sourceCompetitionId, providerIDs[providerID] == competition.id else {
                    throw ClientError.invalidData("provider competition mapping")
                }
            }
        }
    }
}
struct ScorePair: Equatable, Sendable {
    let home: Int?, away: Int?
    var text: String { home.flatMap { h in away.map { "\(h)–\($0)" } } ?? "— : —" }
    init(_ f: DocumentFields, _ homeKey: String, _ awayKey: String) throws {
        home = try f.optionalInteger(homeKey); away = try f.optionalInteger(awayKey)
        guard (home == nil) == (away == nil) else { throw ClientError.invalidData("paired scores") }
    }
}
struct MatchRecord: Identifiable, Sendable {
    let id: String, homeTeamId: String, awayTeamId: String, competitionId: String?, season: String
    let status: String, finishType: String?, isDemo: Bool, kickoff: Date?
    let source: String, sourceMatchId: String?, sourceCompetitionId: String?
    let finalScore: ScorePair, regularTime: ScorePair, extraTime: ScorePair, penalties: ScorePair
    static let fields: Set<String> = ["matchId", "homeTeamId", "awayTeamId", "competitionId", "competition",
        "season", "kickoffUtc", "status", "homeScore", "awayScore", "isDemo", "source", "sourceMatchId",
        "sourceCompetitionId", "finishType", "regularTimeHomeScore", "regularTimeAwayScore",
        "extraTimeHomeScore", "extraTimeAwayScore", "penaltyHomeScore", "penaltyAwayScore"]
    init(id: String, data: [String: Any]) throws {
        let f = DocumentFields(data: data); try f.require(Self.fields)
        self.id = id; isDemo = try f.flag("isDemo")
        guard try f.text("matchId") == id, ClientID.matches(id, (isDemo ? "demo_" : "match_") + ClientID.slug) else {
            throw ClientError.invalidData("match identity")
        }
        homeTeamId = try f.text("homeTeamId"); awayTeamId = try f.text("awayTeamId")
        guard ClientID.team(homeTeamId), ClientID.team(awayTeamId), homeTeamId != awayTeamId else {
            throw ClientError.invalidData("match team references")
        }
        competitionId = try f.nullableText("competitionId")
        if let competitionId, !ClientID.matches(competitionId, (isDemo ? "demo_competition_" : "competition_") + ClientID.slug) {
            throw ClientError.invalidData("competition reference")
        }
        _ = try f.text("competition"); season = try f.text("season"); status = try f.text("status")
        guard ["scheduled", "live", "finished", "postponed", "cancelled"].contains(status) else {
            throw ClientError.invalidData("match status")
        }
        source = try f.text("source"); sourceMatchId = try f.nullableText("sourceMatchId")
        sourceCompetitionId = try f.nullableText("sourceCompetitionId")
        if isDemo {
            guard source == "demo", sourceMatchId == nil, sourceCompetitionId == nil else { throw ClientError.invalidData("demo provenance") }
        } else {
            guard !source.lowercased().contains("demo"), let sourceMatchId,
                  ClientID.matches(sourceMatchId, "[A-Za-z0-9][A-Za-z0-9_-]{0,99}") else { throw ClientError.invalidData("source identity") }
        }
        if let sourceCompetitionId, !ClientID.matches(sourceCompetitionId, "[A-Za-z0-9][A-Za-z0-9_-]{0,99}") {
            throw ClientError.invalidData("provider competition ID")
        }
        if data["kickoffUtc"] is NSNull {
            guard ["postponed", "cancelled"].contains(status) else { throw ClientError.invalidData("kickoff") }; kickoff = nil
        } else if let stamp = data["kickoffUtc"] as? StoreStamp {
            guard stamp.nanoseconds == 0 else { throw ClientError.invalidData("kickoff precision") }; kickoff = stamp.date
        } else {
            let text = try f.text("kickoffUtc")
            guard ClientID.matches(text, "[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}Z") else {
                throw ClientError.invalidData("UTC kickoff")
            }
            kickoff = try DocumentFields.date(text, format: "yyyy-MM-dd'T'HH:mm:ss'Z'")
        }
        finishType = try f.nullableText("finishType")
        finalScore = try ScorePair(f, "homeScore", "awayScore")
        regularTime = try ScorePair(f, "regularTimeHomeScore", "regularTimeAwayScore")
        extraTime = try ScorePair(f, "extraTimeHomeScore", "extraTimeAwayScore")
        penalties = try ScorePair(f, "penaltyHomeScore", "penaltyAwayScore")
        try validateScores()
    }
    private func validateScores() throws {
        if status == "finished" {
            guard finalScore.home != nil, ["regularTime", "extraTime", "penalties"].contains(finishType ?? "") else {
                throw ClientError.invalidData("finished scores")
            }
        } else if finishType != nil { throw ClientError.invalidData("unfinished finish type") }
        if ["scheduled", "postponed", "cancelled"].contains(status),
           ![finalScore, regularTime, extraTime, penalties].allSatisfy({ $0.home == nil }) { throw ClientError.invalidData("unplayed scores") }
        if finishType == "regularTime" && (extraTime.home != nil || penalties.home != nil) { throw ClientError.invalidData("regular-time finish") }
        if finishType == "extraTime" && penalties.home != nil { throw ClientError.invalidData("extra-time finish") }
        if finishType == "penalties", let home = penalties.home, home == penalties.away { throw ClientError.invalidData("tied shootout") }
        for (total, regular, extra) in [(finalScore.home, regularTime.home, extraTime.home), (finalScore.away, regularTime.away, extraTime.away)] {
            guard let total else { continue }
            if let regular, regular > total { throw ClientError.invalidData("regular-time goals") }
            if let extra, extra > total { throw ClientError.invalidData("extra-time goals") }
            if finishType == "regularTime", let regular, regular != total { throw ClientError.invalidData("final goals") }
            if let regular, let extra {
                let sum = regular.addingReportingOverflow(extra)
                guard !sum.overflow, sum.partialValue == total else { throw ClientError.invalidData("period goals") }
            }
        }
    }
}
struct MatchCard: Identifiable, Sendable {
    let match: MatchRecord, home: TeamRecord, away: TeamRecord, competition: CompetitionRecord
    var id: String { match.id }
    var title: String { "\(home.name) vs \(away.name)" }
}
struct EventRecord: Identifiable, Sendable {
    let id: String, matchId: String, teamId: String?, playerId: String?, kind: String, label: String
    let minute: Int?, addedTime: Int?
    var clock: String {
        guard let minute else { return "Unknown minute" }
        if let addedTime, addedTime > 0 { return "\(minute)+\(addedTime)" }
        return "\(minute)"
    }
    init(id: String, data: [String: Any], parent: MatchRecord) throws {
        let f = DocumentFields(data: data)
        try f.require(["eventId", "matchId", "teamId", "playerId", "eventType", "matchMinute", "addedTime", "label", "isDemo", "source"], exact: true)
        self.id = id; matchId = try f.text("matchId"); kind = try f.text("eventType"); label = try f.text("label")
        guard try f.text("eventId") == id, matchId == parent.id, ClientID.child(id, matchID: parent.id, kind: "event"),
              try f.flag("isDemo") == parent.isDemo, try f.text("source") == (parent.isDemo ? "demo" : "manual"),
              ["goal", "yellowCard", "redCard", "save", "substitution", "other"].contains(kind),
              ["live", "finished"].contains(parent.status) else { throw ClientError.invalidData("event identity") }
        teamId = try f.nullableText("teamId"); playerId = try f.nullableText("playerId")
        if let teamId, ![parent.homeTeamId, parent.awayTeamId].contains(teamId) { throw ClientError.invalidData("event team") }
        guard (kind == "other" || teamId != nil), playerId == nil || (ClientID.team(playerId!) && teamId != nil) else {
            throw ClientError.invalidData("event player context")
        }
        minute = try f.optionalInteger("matchMinute"); addedTime = try f.optionalInteger("addedTime")
        guard minute != nil || addedTime == nil else { throw ClientError.invalidData("event clock") }
    }
}
struct VideoMarker: Sendable { let eventId: String, seconds: Double }
struct HighlightRecord: Identifiable, Sendable {
    let id: String, matchId: String, title: String, duration: Double?, markers: [VideoMarker]
    init(id: String, data: [String: Any], parent: MatchRecord) throws {
        let f = DocumentFields(data: data)
        try f.require(["highlightId", "matchId", "title", "mediaType", "mediaReference", "durationSeconds",
                       "rightsStatus", "rightsEvidence", "markers", "isDemo", "source"], exact: true)
        guard try f.text("highlightId") == id, try f.text("matchId") == parent.id,
              ClientID.child(id, matchID: parent.id, kind: "highlight"), try f.flag("isDemo") == parent.isDemo,
              try f.text("source") == (parent.isDemo ? "demo" : "manual") else { throw ClientError.invalidData("highlight identity") }
        guard try f.text("rightsStatus") == "unconfirmed", data["mediaReference"] is NSNull,
              data["mediaType"] is NSNull, data["rightsEvidence"] is NSNull else { throw ClientError.mediaUnavailable }
        self.id = id; matchId = parent.id; title = try f.text("title"); duration = try f.seconds("durationSeconds")
        if let duration, duration <= 0 { throw ClientError.invalidData("video duration") }
        guard let rows = data["markers"] as? [[String: Any]], rows.count <= 100 else { throw ClientError.invalidData("video markers") }
        var seen = Set<String>()
        let suppliedDuration = duration
        markers = try rows.map { row in
            let fields = DocumentFields(data: row); try fields.require(["eventId", "videoSeconds"], exact: true)
            let eventId = try fields.text("eventId")
            guard ClientID.child(eventId, matchID: parent.id, kind: "event"), seen.insert(eventId).inserted,
                  let seconds = try fields.seconds("videoSeconds"), let suppliedDuration, seconds <= suppliedDuration else {
                throw ClientError.invalidData("video marker bounds")
            }
            return VideoMarker(eventId: eventId, seconds: seconds)
        }.sorted { $0.seconds == $1.seconds ? $0.eventId < $1.eventId : $0.seconds < $1.seconds }
    }
}
struct MatchDetail: Sendable {
    let card: MatchCard, events: [EventRecord], highlights: [HighlightRecord], players: [String: PlayerRecord]
    let eventsCursor: String?, highlightsCursor: String?
}
struct UserProfile: Equatable, Sendable {
    let uid: String, displayName: String, createdAt: StoreStamp, updatedAt: StoreStamp
    init(uid: String, data: [String: Any]) throws {
        let f = DocumentFields(data: data); try f.require(["uid", "displayName", "schemaVersion", "createdAt", "updatedAt"], exact: true)
        guard ClientID.uid(uid), try f.text("uid") == uid, try f.integer("schemaVersion") == 1 else { throw ClientError.signedOut }
        self.uid = uid; displayName = try f.text("displayName"); createdAt = try f.stamp("createdAt"); updatedAt = try f.stamp("updatedAt")
        guard displayName.count <= 80, createdAt <= updatedAt else { throw ClientError.invalidData("profile") }
    }
}
struct UserPreferences: Equatable, Sendable {
    var favoriteTeamId: String? = nil
    var scoreNotifications = false
    var highlightNotifications = false
    var appearance = "system"
    var revision: StoreStamp? = nil
    init() {}
    init(data: [String: Any]) throws {
        let f = DocumentFields(data: data)
        try f.require(["favoriteTeamId", "scoreNotifications", "highlightNotifications", "appearance", "schemaVersion", "updatedAt"], exact: true)
        guard try f.integer("schemaVersion") == 1 else { throw ClientError.invalidData("settings version") }
        favoriteTeamId = try f.nullableText("favoriteTeamId"); scoreNotifications = try f.flag("scoreNotifications")
        highlightNotifications = try f.flag("highlightNotifications"); appearance = try f.text("appearance")
        revision = try f.stamp("updatedAt"); try validate()
    }
    func validate() throws {
        guard ["system", "dark", "light"].contains(appearance), favoriteTeamId == nil || ClientID.team(favoriteTeamId!) else {
            throw ClientError.invalidData("settings")
        }
    }
}
enum SavedKind: String, CaseIterable, Sendable {
    case player, team, match, highlight
    var collection: String {
        switch self { case .player: return "players"; case .team: return "teams"; case .match: return "matches"; case .highlight: return "highlights" }
    }
    func savedDocumentID(_ targetID: String, watchlist: Bool) -> String {
        watchlist ? targetID : rawValue + "_" + targetID
    }
    func validate(_ id: String) throws {
        let valid: Bool
        switch self {
        case .team, .player: valid = ClientID.team(id)
        case .match: valid = ClientID.match(id)
        case .highlight: valid = ClientID.matches(id, "(?:demo_)?highlight_" + ClientID.slug + "__" + ClientID.slug)
        }
        guard valid else { throw ClientError.invalidData("saved reference") }
    }
}
struct SavedRecord: Identifiable, Sendable {
    let id: String, kind: SavedKind, targetId: String, createdAt: StoreStamp, watchlist: Bool
    init(id: String, data: [String: Any], watchlist: Bool) throws {
        let f = DocumentFields(data: data)
        try f.require(watchlist ? ["matchId", "schemaVersion", "createdAt"] : ["targetType", "targetId", "schemaVersion", "createdAt"], exact: true)
        guard try f.integer("schemaVersion") == 1 else { throw ClientError.invalidData("saved version") }
        if watchlist { kind = .match; targetId = try f.text("matchId") }
        else {
            guard let value = SavedKind(rawValue: try f.text("targetType")) else { throw ClientError.invalidData("favorite type") }
            kind = value; targetId = try f.text("targetId")
        }
        try kind.validate(targetId)
        guard id == kind.savedDocumentID(targetId, watchlist: watchlist) else { throw ClientError.invalidData("saved ID") }
        self.id = id; self.watchlist = watchlist; createdAt = try f.stamp("createdAt")
    }
}
struct SavedItem: Identifiable, Sendable {
    let record: SavedRecord, title: String, subtitle: String, available: Bool, matchId: String?
    var id: String { record.id }
}
struct ClientPage<Item> { let items: [Item], nextCursor: String?, issues: Int }
enum ClientPresentation {
    static func normalized(_ text: String) -> String {
        text.folding(options: [.caseInsensitive, .diacriticInsensitive], locale: Locale(identifier: "en_US_POSIX"))
            .trimmingCharacters(in: .whitespacesAndNewlines)
    }
    static func utc(_ date: Date?) -> String {
        guard let date else { return "Kickoff unavailable" }
        let formatter = DateFormatter()
        formatter.locale = Locale(identifier: "en_US_POSIX"); formatter.timeZone = TimeZone(secondsFromGMT: 0)
        formatter.dateFormat = "dd MMM yyyy, HH:mm 'UTC'"
        return formatter.string(from: date)
    }
}
