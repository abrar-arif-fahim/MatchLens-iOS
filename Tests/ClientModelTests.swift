import Foundation

// Foundation-only tests against the existing local schemas; never imports Firebase.
@main
struct ClientModelTests {
    static var checks = 0
    static func expect(_ value: @autoclosure () throws -> Bool, _ label: String) rethrows {
        let result = try value()
        precondition(result, label); checks += 1
    }
    static func rejects(_ label: String, _ operation: () throws -> Void) {
        var rejected = false
        do { try operation() } catch { rejected = true }
        expect(rejected, label)
    }
    static func json(_ path: String) throws -> [String: Any] {
        let data = try Data(contentsOf: URL(fileURLWithPath: path))
        guard let result = try JSONSerialization.jsonObject(with: data) as? [String: Any] else {
            throw ClientError.invalidData("local test input")
        }
        return result
    }
    static func main() throws {
        let matchRows = try json("Backend/input/match_schema_test_cases.json")["matches"] as! [[String: Any]]
        for row in matchRows {
            let record = try MatchRecord(id: row["matchId"] as! String, data: row)
            expect(record.isDemo, "Fictional schema cases retain their provenance")
            expect(record.sourceMatchId == nil, "Demo IDs are not provider fixture IDs")
        }
        let players = try json("Backend/output/players_prepared.json")["players"] as! [[String: Any]]
        for row in players {
            let record = try PlayerRecord(id: row["documentId"] as! String, data: row)
            expect(record.id == "wikidata_" + record.wikidataId, "Player identity format")
        }
        let teams = try json("Backend/output/teams_prepared.json")["teams"] as! [[String: Any]]
        for row in teams {
            let record = try TeamRecord(id: row["teamId"] as! String, data: row)
            expect(!record.name.isEmpty, "Team labels are present")
        }
        let rawCatalog = try json("Backend/input/competition_mappings.json")
        let catalog = try CompetitionBindings(data: rawCatalog)
        expect(catalog.providerIDs.count == 4, "Reuse all four reviewed provider mappings")
        expect(catalog.providerIDs["140"] == "competition_la_liga", "Separate provider/internal competition IDs")
        var duplicate = rawCatalog
        var mappings = duplicate["providerMappings"] as! [[String: Any]]
        mappings.append(mappings[0]); duplicate["providerMappings"] = mappings
        rejects("Duplicate provider mappings fail") { _ = try CompetitionBindings(data: duplicate) }
        mappings = rawCatalog["providerMappings"] as! [[String: Any]]
        mappings.append(["provider": "API-Football", "providerCompetitionId": "900001", "status": "pending",
                         "competitionId": NSNull(), "verificationEvidence": NSNull(), "verifiedAt": NSNull()])
        var pending = rawCatalog; pending["providerMappings"] = mappings
        let withPending = try CompetitionBindings(data: pending)
        expect(withPending.providerIDs["900001"] == nil, "Pending mappings are not guessed")

        let prototype = matchRows[0], id = prototype["matchId"] as! String
        let invalid: [[String: Any]] = [
            ["homeTeamId": prototype["awayTeamId"]!], ["homeScore": true], ["homeScore": 1.5],
            ["awayScore": NSNull()], ["status": "AET"], ["status": "scheduled"], ["isDemo": 1],
            ["source": "API-Football"], ["kickoffUtc": "2030-02-30T00:00:00Z"],
            ["kickoffUtc": "2030-01-01T18:00:00+00:00"], ["kickoffUtc": NSNull()],
            ["kickoffUtc": StoreStamp(seconds: 1_893_520_800, nanoseconds: 1)],
            ["finishType": NSNull()], ["extraTimeHomeScore": 0, "extraTimeAwayScore": 0],
            ["matchId": "match_wrong_namespace"],
        ]
        for changes in invalid {
            var row = prototype; row.merge(changes) { _, new in new }
            rejects("Invalid score/status/identity/UTC fields fail") { _ = try MatchRecord(id: id, data: row) }
        }
        var missing = prototype; missing.removeValue(forKey: "homeScore")
        rejects("Missing score is distinct from explicit null") { _ = try MatchRecord(id: id, data: missing) }
        var real = prototype
        real.merge(["matchId": "match_api_football_fixture_900001", "isDemo": false, "source": "API-Football",
                    "sourceMatchId": "900001", "sourceCompetitionId": "140", "competitionId": "competition_la_liga"]) { _, new in new }
        let syntheticRealContract = try MatchRecord(id: "match_api_football_fixture_900001", data: real)
        try catalog.validate(syntheticRealContract, competition: catalog.competitions["competition_la_liga"]!)
        expect(syntheticRealContract.sourceMatchId == "900001", "Synthetic real-source branch preserves provider ID")
        rejects("Do not invent a provider mapping") {
            var unknown = real; unknown["sourceCompetitionId"] = "900002"
            try catalog.validate(MatchRecord(id: "match_api_football_fixture_900001", data: unknown),
                                 competition: catalog.competitions["competition_la_liga"]!)
        }

        let parent = try MatchRecord(id: id, data: prototype)
        var event: [String: Any] = ["eventId": "demo_event_regular_001__goal_1", "matchId": id,
            "teamId": parent.homeTeamId, "playerId": NSNull(), "eventType": "goal", "matchMinute": 45,
            "addedTime": 2, "label": "Fictional goal", "isDemo": true, "source": "demo"]
        let eventID = event["eventId"] as! String
        try expect(try EventRecord(id: eventID, data: event, parent: parent).clock == "45+2", "Added time stays separate")
        event["matchMinute"] = NSNull(); event["addedTime"] = NSNull()
        try expect(try EventRecord(id: eventID, data: event, parent: parent).clock == "Unknown minute", "Unknown clock remains unknown")
        event["addedTime"] = 1
        rejects("Added time requires a base minute") { _ = try EventRecord(id: eventID, data: event, parent: parent) }
        event["addedTime"] = NSNull(); event["isDemo"] = false
        rejects("Event provenance cannot change silently") { _ = try EventRecord(id: eventID, data: event, parent: parent) }
        expect(!ClientID.child("demo_event_other__goal_1", matchID: id, kind: "event"), "Reject cross-match child ID")
        var highlight: [String: Any] = ["highlightId": "demo_highlight_regular_001__clip_1", "matchId": id,
            "title": "Fictional virtual timeline", "mediaType": NSNull(), "mediaReference": NSNull(),
            "durationSeconds": 120, "rightsStatus": "unconfirmed", "rightsEvidence": NSNull(),
            "markers": [["eventId": eventID, "videoSeconds": 30.5]], "isDemo": true, "source": "demo"]
        let highlightID = highlight["highlightId"] as! String
        try expect(try HighlightRecord(id: highlightID, data: highlight, parent: parent).markers[0].seconds == 30.5, "Fractional clip timestamps")
        for changes: [String: Any] in [
            ["rightsStatus": "authorized"], ["mediaReference": "fictional_nonexistent.mp4"],
            ["durationSeconds": NSNull()], ["durationSeconds": true],
            ["markers": [["eventId": eventID, "videoSeconds": -1]]],
            ["markers": [["eventId": eventID, "videoSeconds": 121]]],
            ["markers": [["eventId": eventID, "videoSeconds": true]]],
            ["markers": [["eventId": eventID, "videoSeconds": Double.infinity]]],
            ["markers": [["eventId": eventID, "videoSeconds": 1], ["eventId": eventID, "videoSeconds": 2]]],
        ] {
            var data = highlight; data.merge(changes) { _, new in new }
            rejects("Media and marker restrictions") { _ = try HighlightRecord(id: highlightID, data: data, parent: parent) }
        }
        highlight["durationSeconds"] = NSNull(); highlight["markers"] = [[String: Any]]()
        try expect(try HighlightRecord(id: highlightID, data: highlight, parent: parent).duration == nil, "No invented video duration")

        let stamp = StoreStamp(seconds: 1_893_456_000, nanoseconds: 123456789)
        let next = StoreStamp(seconds: stamp.seconds, nanoseconds: 123456790)
        expect(stamp < next && stamp != next, "Preserve exact revision nanoseconds")
        let profile: [String: Any] = ["uid": "test-alice", "displayName": "Fictional fan", "schemaVersion": 1,
                                     "createdAt": stamp, "updatedAt": next]
        try expect(try UserProfile(uid: "test-alice", data: profile).updatedAt == next, "Profile timestamps remain exact")
        rejects("Cross-user profile rejected") { _ = try UserProfile(uid: "test-bob", data: profile) }
        var secretField = profile; secretField["password"] = "fictional-invalid-field"
        rejects("No credential fields in profile") { _ = try UserProfile(uid: "test-alice", data: secretField) }
        let preferences: [String: Any] = ["favoriteTeamId": NSNull(), "scoreNotifications": false,
            "highlightNotifications": false, "appearance": "system", "schemaVersion": 1, "updatedAt": stamp]
        try expect(try UserPreferences(data: preferences).favoriteTeamId == nil, "Nullable favorite team")
        expect(UserPreferences().revision == nil, "Missing settings are not presented as persisted")
        for changes in [["scoreNotifications": 1], ["appearance": "automatic"], ["favoriteTeamId": "529"]] as [[String: Any]] {
            var data = preferences; data.merge(changes) { _, new in new }
            rejects("Private settings field validation") { _ = try UserPreferences(data: data) }
        }
        let saved: [String: Any] = ["targetType": "player", "targetId": "wikidata_Q615", "schemaVersion": 1, "createdAt": stamp]
        try expect(try SavedRecord(id: "player_wikidata_Q615", data: saved, watchlist: false).targetId == "wikidata_Q615", "Deterministic favorite ID")
        rejects("Wrong favorite ID rejected") { _ = try SavedRecord(id: "wrong", data: saved, watchlist: false) }
        rejects("Watchlist cannot target a team") {
            _ = try SavedRecord(id: "wikidata_Q7156", data: ["matchId": "wikidata_Q7156", "schemaVersion": 1, "createdAt": stamp], watchlist: true)
        }
        expect(ClientPresentation.normalized("  MbAPPÉ ") == "mbappe", "Accent-insensitive search")
        expect(!ClientID.uid("test-alice/other"), "UID path injection rejected")
        expect(!ClientID.team("529") && !ClientID.team("wikidata_Q01"), "Provider IDs and malformed IDs rejected")
        expect(!ClientID.team("wikidata_Q615\n"), "No trailing newline in team/player IDs")
        expect(!ClientID.match("match_one\n"), "No trailing newline in match IDs")
        print("Native client model checks passed (\(checks) assertions). Fictional fixtures only; no Firebase calls.")
    }
}
