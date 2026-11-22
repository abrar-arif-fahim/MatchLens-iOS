import SwiftUI

struct CatalogView: View {
    @EnvironmentObject private var app: AppStore
    @State private var search = ""
    @State private var showTeams = false
    private var needle: String { ClientPresentation.normalized(search) }
    var body: some View {
        ZStack {
            MatchLensStyle.background.ignoresSafeArea()
            ScrollView {
                VStack(alignment: .leading, spacing: 18) {
                    Picker("Catalog", selection: $showTeams) {
                        Text("Players").tag(false); Text("Teams").tag(true)
                    }.pickerStyle(.segmented)
                    TextField("Search loaded names", text: $search)
                        .textInputAutocapitalization(.never).autocorrectionDisabled()
                        .padding(16).background(MatchLensStyle.card).clipShape(RoundedRectangle(cornerRadius: 17))
                    if showTeams { teamList } else { playerList }
                    Text("Search covers the pages loaded so far. Load more to search a larger catalog.")
                        .font(.caption).foregroundStyle(MatchLensStyle.secondary)
                }.padding(22).frame(maxWidth: 480).frame(maxWidth: .infinity)
            }
            .refreshable { if showTeams { await app.loadTeams(reset: true) } else { await app.loadPlayers(reset: true) } }
        }
        .foregroundStyle(MatchLensStyle.primary)
        .navigationTitle("Players & teams").navigationBarTitleDisplayMode(.inline)
        .toolbar(.visible, for: .navigationBar)
        .task(id: showTeams) { if showTeams { await app.loadTeams() } else { await app.loadPlayers() } }
    }
    private var playerList: some View {
        VStack(alignment: .leading, spacing: 12) {
            if app.playersLoading { ProgressView("Loading players…") }
            if let error = app.playersError {
                DataNotice(title: "Players unavailable", message: error)
                Button("Retry") { Task { await app.loadPlayers(reset: true) } }
            }
            let rows = app.players.filter { needle.isEmpty || ClientPresentation.normalized($0.name).contains(needle) }
            ForEach(rows) { player in
                NavigationLink { PlayerProfileView(playerID: player.id) } label: {
                    DataNotice(title: player.name, message: player.nationality + " • " + player.position)
                }.buttonStyle(.plain)
            }
            if rows.isEmpty && !app.playersLoading { Text("No matching players in the loaded pages.").foregroundStyle(MatchLensStyle.secondary) }
            if app.playersCursor != nil {
                Button("Load more players") { Task { await app.loadPlayers(more: true) } }.disabled(app.playersLoading)
            }
        }
    }
    private var teamList: some View {
        VStack(alignment: .leading, spacing: 12) {
            if app.teamsLoading { ProgressView("Loading teams…") }
            if let error = app.teamsError {
                DataNotice(title: "Teams unavailable", message: error)
                Button("Retry") { Task { await app.loadTeams(reset: true) } }
            }
            let rows = app.teams.filter { needle.isEmpty || ClientPresentation.normalized($0.name + " " + $0.shortName).contains(needle) }
            ForEach(rows) { team in
                NavigationLink { TeamProfileView(teamID: team.id) } label: {
                    DataNotice(title: team.name, message: team.shortName + " • " + team.country)
                }.buttonStyle(.plain)
            }
            if rows.isEmpty && !app.teamsLoading { Text("No matching teams in the loaded pages.").foregroundStyle(MatchLensStyle.secondary) }
            if app.teamsCursor != nil {
                Button("Load more teams") { Task { await app.loadTeams(more: true) } }.disabled(app.teamsLoading)
            }
        }
    }
}

struct PlayerProfileView: View {
    @EnvironmentObject private var app: AppStore
    let playerID: String
    @State private var player: PlayerRecord?
    @State private var error: String?
    @State private var loading = false
    var body: some View {
        ZStack {
            MatchLensStyle.background.ignoresSafeArea()
            ScrollView {
                VStack(alignment: .leading, spacing: 18) {
                    if loading { ProgressView("Loading player…") }
                    if let player {
                        Text(player.name).font(.largeTitle.bold())
                        DataNotice(title: "Nationality", message: player.nationality)
                        DataNotice(title: "Date of birth", message: player.dateOfBirth)
                        DataNotice(title: "Playing position", message: player.position)
                        SaveControls(kind: .player, id: player.id)
                        Text("Source: Wikidata • \(player.wikidataId)").font(.caption).foregroundStyle(MatchLensStyle.secondary)
                        DataNotice(title: "Club and statistics", message: "Verified roster and statistics data has not been collected.")
                    }
                    if let error { DataNotice(title: "Player unavailable", message: error); Button("Retry") { Task { await load() } } }
                }.padding(22).frame(maxWidth: 480).frame(maxWidth: .infinity)
            }.refreshable { await load() }
        }
        .foregroundStyle(MatchLensStyle.primary).navigationTitle("Player profile").navigationBarTitleDisplayMode(.inline)
        .toolbar(.visible, for: .navigationBar).task(id: playerID) { await load() }
    }
    private func load() async {
        guard !loading, let repo = app.repository else { return }
        let key = app.sessionKey
        loading = true; error = nil
        defer { if app.isCurrent(key) { loading = false } }
        do {
            let result = try await repo.player(playerID)
            guard app.isCurrent(key), !Task.isCancelled else { return }
            player = result
        } catch { if app.isCurrent(key) { self.error = FirebaseSetup.safeMessage(error) } }
    }
}

struct TeamProfileView: View {
    @EnvironmentObject private var app: AppStore
    let teamID: String
    @State private var team: TeamRecord?
    @State private var matches: [MatchCard] = []
    @State private var homeCursor: String?
    @State private var awayCursor: String?
    @State private var error: String?
    @State private var loading = false
    var body: some View {
        ZStack {
            MatchLensStyle.background.ignoresSafeArea()
            ScrollView {
                VStack(alignment: .leading, spacing: 18) {
                    if let team {
                        Text(team.name).font(.largeTitle.bold())
                        DataNotice(title: team.country, message: "App abbreviation: " + team.shortName + " • Source: Wikidata")
                        SaveControls(kind: .team, id: team.id)
                        Text("Team matches").font(.title2.bold())
                    }
                    if loading { ProgressView("Loading team information…") }
                    if let error { DataNotice(title: "Some information is unavailable", message: error); Button("Retry") { Task { await load() } } }
                    ForEach(matches) { card in
                        NavigationLink { MatchDetailView(matchID: card.id) } label: { MatchCardRow(card: card) }.buttonStyle(.plain)
                    }
                    if !loading && matches.isEmpty && error == nil {
                        Text("No published matches are available for this team.").foregroundStyle(MatchLensStyle.secondary)
                    }
                    HStack {
                        if homeCursor != nil { Button("More home matches") { Task { await loadMore(home: true) } } }
                        if awayCursor != nil { Button("More away matches") { Task { await loadMore(home: false) } } }
                    }.disabled(loading)
                    DataNotice(title: "Players", message: "A verified team roster has not been collected.")
                }.padding(22).frame(maxWidth: 480).frame(maxWidth: .infinity)
            }.refreshable { await load() }
        }
        .foregroundStyle(MatchLensStyle.primary).navigationTitle("Team information").navigationBarTitleDisplayMode(.inline)
        .toolbar(.visible, for: .navigationBar).task(id: teamID) { await load() }
    }
    private func load() async {
        guard !loading, let repo = app.repository else { return }
        let key = app.sessionKey
        loading = true; error = nil
        defer { if app.isCurrent(key) { loading = false } }
        do {
            let team = try await repo.team(teamID)
            guard app.isCurrent(key), !Task.isCancelled else { return }
            self.team = team
            let home = try await repo.matches(cursor: nil, teamID: teamID)
            let away = try await repo.matches(cursor: nil, teamID: teamID, home: false)
            guard app.isCurrent(key), !Task.isCancelled else { return }
            matches = home.items + away.items; homeCursor = home.nextCursor; awayCursor = away.nextCursor
        } catch { if app.isCurrent(key) { self.error = FirebaseSetup.safeMessage(error) } }
    }
    private func loadMore(home: Bool) async {
        guard !loading, let repo = app.repository else { return }
        let key = app.sessionKey
        loading = true
        defer { if app.isCurrent(key) { loading = false } }
        do {
            let page = try await repo.matches(cursor: home ? homeCursor : awayCursor, teamID: teamID, home: home)
            guard app.isCurrent(key), !Task.isCancelled else { return }
            matches += page.items.filter { row in !matches.contains { $0.id == row.id } }
            if home { homeCursor = page.nextCursor } else { awayCursor = page.nextCursor }
        } catch { if app.isCurrent(key) { self.error = FirebaseSetup.safeMessage(error) } }
    }
}
