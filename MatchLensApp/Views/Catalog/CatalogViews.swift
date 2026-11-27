import SwiftUI

struct CatalogView: View {
    @EnvironmentObject private var app: AppStore
    @State private var search = ""
    @State private var showTeams = false
    @State private var nationality = ""
    @State private var position = ""
    @State private var country = ""
    private var needle: String { ClientPresentation.normalized(search) }
    var body: some View {
        ZStack {
            MatchLensStyle.background.ignoresSafeArea()
            ScrollView {
                VStack(alignment: .leading, spacing: 18) {
                    Picker("Catalog", selection: $showTeams) {
                        Text("Players").tag(false); Text("Teams").tag(true)
                    }.pickerStyle(.segmented)
                    HStack {
                        TextField("Search loaded names", text: $search)
                            .textInputAutocapitalization(.never).autocorrectionDisabled()
                        if !search.isEmpty {
                            Button { search = "" } label: {
                                Image(systemName: "xmark.circle.fill").frame(width: 44, height: 44).contentShape(Rectangle())
                            }
                                .buttonStyle(.plain).accessibilityLabel("Clear search")
                        }
                    }.padding(16).background(MatchLensStyle.card).clipShape(RoundedRectangle(cornerRadius: 17))
                    if showTeams {
                        catalogFilter("Country", selection: $country, options: app.teams.map(\.country))
                    } else {
                        catalogFilter("Nationality", selection: $nationality, options: app.players.flatMap { labels($0.nationality) })
                        catalogFilter("Position", selection: $position, options: app.players.flatMap { labels($0.position) })
                    }
                    if !search.isEmpty || (showTeams ? !country.isEmpty : !nationality.isEmpty || !position.isEmpty) {
                        Button("Clear search and filters") {
                            search = ""
                            if showTeams { country = "" } else { nationality = ""; position = "" }
                        }
                    }
                    if showTeams { teamList } else { playerList }
                    Text("Search and filters cover loaded records only. Load more to include additional records.")
                        .font(.caption).foregroundStyle(MatchLensStyle.secondary)
                }.padding(22).frame(maxWidth: 480).frame(maxWidth: .infinity)
            }
            .refreshable { if showTeams { await app.loadTeams(reset: true) } else { await app.loadPlayers(reset: true) } }
            .scrollDismissesKeyboard(.interactively)
        }
        .foregroundStyle(MatchLensStyle.primary)
        .navigationTitle("Players & teams").navigationBarTitleDisplayMode(.inline)
        .toolbar(.visible, for: .navigationBar)
        .task {
            async let players: Void = app.loadPlayers()
            async let teams: Void = app.loadTeams()
            _ = await (players, teams)
        }
    }
    private func labels(_ field: String) -> [String] {
        field.split(separator: ";").map { $0.trimmingCharacters(in: .whitespacesAndNewlines) }
    }

    private func catalogFilter(_ title: String, selection: Binding<String>, options: [String]) -> some View {
        let values = Set(options.filter { !$0.isEmpty } + [selection.wrappedValue].filter { !$0.isEmpty })
        return Picker(title, selection: selection) {
            Text("All").tag("")
            ForEach(values.sorted(), id: \.self) { Text($0).tag($0) }
        }.pickerStyle(.menu)
    }
    private var playerList: some View {
        VStack(alignment: .leading, spacing: 12) {
            if app.players.isEmpty && app.playersError == nil && (app.playersLoading || !app.loadedPlayers) {
                LoadingCard(title: "Loading players…")
            }
            if let error = app.playersError {
                DataNotice(title: app.players.isEmpty ? "Players unavailable" : "Couldn’t update players", message: error) {
                    Task { await app.loadPlayers(reset: true) }
                }
            }
            if app.playersIssues > 0 {
                DataNotice(title: "Some players need review", message: "Invalid player records could not be displayed.")
            }
            let rows = app.players.filter {
                (needle.isEmpty || ClientPresentation.normalized($0.name).contains(needle)) &&
                (nationality.isEmpty || labels($0.nationality).contains(nationality)) &&
                (position.isEmpty || labels($0.position).contains(position))
            }
            ForEach(rows) { player in
                NavigationLink { PlayerProfileView(playerID: player.id) } label: {
                    DataNotice(title: player.name, message: player.nationality + " • " + player.position)
                }.buttonStyle(.plain)
            }
            if rows.isEmpty && app.loadedPlayers && !app.playersLoading && app.playersError == nil {
                DataNotice(title: "No players found", message: app.playersCursor == nil
                    ? "Try a different name or clear your filters." : "Load more players to search additional records.")
            }
            if app.playersCursor != nil {
                Button(app.playersLoading ? "Loading players…" : "Load more players") {
                    Task { await app.loadPlayers(more: true) }
                }.disabled(app.playersLoading)
            }
        }
    }
    private var teamList: some View {
        VStack(alignment: .leading, spacing: 12) {
            if app.teams.isEmpty && app.teamsError == nil && (app.teamsLoading || !app.loadedTeams) {
                LoadingCard(title: "Loading teams…")
            }
            if let error = app.teamsError {
                DataNotice(title: app.teams.isEmpty ? "Teams unavailable" : "Couldn’t update teams", message: error) {
                    Task { await app.loadTeams(reset: true) }
                }
            }
            if app.teamsIssues > 0 {
                DataNotice(title: "Some teams need review", message: "Invalid team records could not be displayed.")
            }
            let rows = app.teams.filter {
                (needle.isEmpty || ClientPresentation.normalized($0.name + " " + $0.shortName).contains(needle)) &&
                (country.isEmpty || $0.country == country)
            }
            ForEach(rows) { team in
                NavigationLink { TeamProfileView(teamID: team.id) } label: {
                    DataNotice(title: team.name, message: team.shortName + " • " + team.country)
                }.buttonStyle(.plain)
            }
            if rows.isEmpty && app.loadedTeams && !app.teamsLoading && app.teamsError == nil {
                DataNotice(title: "No teams found", message: app.teamsCursor == nil
                    ? "Try a different name or clear your filters." : "Load more teams to search additional records.")
            }
            if app.teamsCursor != nil {
                Button(app.teamsLoading ? "Loading teams…" : "Load more teams") {
                    Task { await app.loadTeams(more: true) }
                }.disabled(app.teamsLoading)
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
                    if loading && player == nil { LoadingCard(title: "Loading player…") }
                    if let player {
                        ArtworkPlaceholder(symbol: "person.fill")
                        Text(player.name).font(.largeTitle.bold()).accessibilityAddTraits(.isHeader)
                        DataNotice(title: "Nationality", message: player.nationality)
                        DataNotice(title: "Date of birth", message: player.dateOfBirth)
                        DataNotice(title: "Playing position", message: player.position)
                        SaveControls(kind: .player, id: player.id)
                        Text("Source: Wikidata • \(player.wikidataId)").font(.caption).foregroundStyle(MatchLensStyle.secondary)
                        DataNotice(title: "Club and statistics", message: "Verified roster and statistics data has not been collected.")
                    }
                    if let error {
                        DataNotice(title: player == nil ? "Player unavailable" : "Couldn’t update player", message: error) {
                            Task { await load() }
                        }
                    }
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
        } catch { if app.isCurrent(key), !Task.isCancelled { self.error = FirebaseSetup.safeMessage(error) } }
    }
}

struct TeamProfileView: View {
    @EnvironmentObject private var app: AppStore
    let teamID: String
    @State private var team: TeamRecord?
    @State private var matches: [MatchCard] = []
    @State private var homeCursor: String?
    @State private var awayCursor: String?
    @State private var retryHomePage: Bool?
    @State private var error: String?
    @State private var loading = false
    var body: some View {
        ZStack {
            MatchLensStyle.background.ignoresSafeArea()
            ScrollView {
                VStack(alignment: .leading, spacing: 18) {
                    if let team {
                        ArtworkPlaceholder(symbol: "shield.fill")
                        Text(team.name).font(.largeTitle.bold()).accessibilityAddTraits(.isHeader)
                        DataNotice(title: team.country, message: "App abbreviation: " + team.shortName + " • Source: Wikidata")
                        SaveControls(kind: .team, id: team.id)
                        Text("Team matches").font(.title2.bold()).accessibilityAddTraits(.isHeader)
                    }
                    if loading && matches.isEmpty {
                        LoadingCard(title: team == nil ? "Loading team information…" : "Loading team matches…")
                    }
                    if let error {
                        DataNotice(title: team == nil ? "Team unavailable" : "Some team information couldn’t be updated", message: error) {
                            Task {
                                if let retryHomePage { await loadMore(home: retryHomePage) }
                                else { await load() }
                            }
                        }
                    }
                    ForEach(matches) { card in
                        NavigationLink { MatchDetailView(matchID: card.id) } label: { MatchCardRow(card: card) }.buttonStyle(.plain)
                    }
                    if team != nil && !loading && matches.isEmpty && error == nil {
                        DataNotice(title: "No team matches to show", message: "Check back when more fixtures have been published.")
                    }
                    AdaptiveActionRow {
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
        loading = true; error = nil; retryHomePage = nil
        defer { if app.isCurrent(key) { loading = false } }
        do {
            let team = try await repo.team(teamID)
            guard app.isCurrent(key), !Task.isCancelled else { return }
            self.team = team
            let home = try await repo.matches(cursor: nil, teamID: teamID)
            let away = try await repo.matches(cursor: nil, teamID: teamID, home: false)
            guard app.isCurrent(key), !Task.isCancelled else { return }
            matches = home.items + away.items; homeCursor = home.nextCursor; awayCursor = away.nextCursor
        } catch { if app.isCurrent(key), !Task.isCancelled { self.error = FirebaseSetup.safeMessage(error) } }
    }
    private func loadMore(home: Bool) async {
        guard !loading, let repo = app.repository else { return }
        let key = app.sessionKey
        loading = true; error = nil; retryHomePage = home
        defer { if app.isCurrent(key) { loading = false } }
        do {
            let page = try await repo.matches(cursor: home ? homeCursor : awayCursor, teamID: teamID, home: home)
            guard app.isCurrent(key), !Task.isCancelled else { return }
            matches += page.items.filter { row in !matches.contains { $0.id == row.id } }
            if home { homeCursor = page.nextCursor } else { awayCursor = page.nextCursor }
        } catch { if app.isCurrent(key), !Task.isCancelled { self.error = FirebaseSetup.safeMessage(error) } }
    }
}
