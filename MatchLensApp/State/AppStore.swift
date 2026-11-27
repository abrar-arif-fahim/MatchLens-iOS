import Foundation
import Combine
import FirebaseCore
import FirebaseAuth
import FirebaseFirestore

enum SessionPhase: Equatable { case restoring, signedOut, profileRequired, profileError, ready, configurationRequired }
enum AppTab: String, CaseIterable, Hashable { case home = "Home", matches = "Matches", saved = "Saved", profile = "Profile" }

@MainActor
final class AppStore: ObservableObject {
    @Published private(set) var phase: SessionPhase = .restoring
    @Published private(set) var uid: String?
    @Published private(set) var email = ""
    @Published private(set) var profile: UserProfile?
    @Published private(set) var preferences = UserPreferences()
    @Published private(set) var sessionKey = UUID()
    @Published var tab: AppTab = .home
    @Published private(set) var authBusy = false
    @Published private(set) var saving = false
    @Published var errorMessage: String?
    @Published var mutationMessage: String?
    @Published var mutationSuccess: String?
    @Published private(set) var savedActionID: String?
    @Published private var savedMembership: [String: Bool] = [:]
    @Published private(set) var suggestedName = ""
    @Published private(set) var players: [PlayerRecord] = []
    @Published private(set) var teams: [TeamRecord] = []
    @Published private(set) var matches: [MatchCard] = []
    @Published private(set) var favorites: [SavedItem] = []
    @Published private(set) var watchlist: [SavedItem] = []
    @Published private(set) var playersCursor: String?
    @Published private(set) var teamsCursor: String?
    @Published private(set) var matchesCursor: String?
    @Published private(set) var favoritesCursor: String?
    @Published private(set) var watchlistCursor: String?
    @Published private(set) var playersLoading = false
    @Published private(set) var teamsLoading = false
    @Published private(set) var matchesLoading = false
    @Published private(set) var favoritesLoading = false
    @Published private(set) var watchlistLoading = false
    var savedLoading: Bool { favoritesLoading || watchlistLoading }
    @Published private(set) var playersError: String?
    @Published private(set) var teamsError: String?
    @Published private(set) var matchesError: String?
    @Published private(set) var favoritesError: String?
    @Published private(set) var watchlistError: String?
    @Published private(set) var playersIssues = 0
    @Published private(set) var teamsIssues = 0
    @Published private(set) var favoritesIssues = 0
    @Published private(set) var watchlistIssues = 0
    @Published private(set) var reviewCount = 0
    private(set) var repository: FirebaseRepository?
    private var auth: Auth?
    private var listener: AuthStateDidChangeListenerHandle?
    private var profileTask: Task<Void, Never>?
    private(set) var loadedPlayers = false, loadedTeams = false, loadedMatches = false
    private(set) var loadedFavorites = false, loadedWatchlist = false
    private var favoritesRequest = UUID(), watchlistRequest = UUID()

    func start() {
        guard listener == nil else { return }
        FirebaseSetup.configure()
        guard FirebaseApp.app() != nil else {
            errorMessage = FirebaseSetup.message
            phase = .configurationRequired
            return
        }
        let auth = Auth.auth()
        self.auth = auth
        listener = auth.addStateDidChangeListener { @Sendable [weak self] _, user in
            Task { @MainActor [weak self] in
                guard let self, !self.authBusy, user?.uid == self.auth?.currentUser?.uid else { return }
                self.receive()
            }
        }
    }
    private func clearSessionData() {
        profileTask?.cancel()
        sessionKey = UUID()
        repository = nil; profile = nil; uid = nil; email = ""; suggestedName = ""
        preferences = UserPreferences(); tab = .home
        players = []; teams = []; matches = []; favorites = []; watchlist = []
        playersCursor = nil; teamsCursor = nil; matchesCursor = nil; favoritesCursor = nil; watchlistCursor = nil
        playersLoading = false; teamsLoading = false; matchesLoading = false
        favoritesLoading = false; watchlistLoading = false
        favoritesRequest = UUID(); watchlistRequest = UUID()
        playersError = nil; teamsError = nil; matchesError = nil; favoritesError = nil; watchlistError = nil
        favoritesIssues = 0; watchlistIssues = 0
        playersIssues = 0; teamsIssues = 0
        loadedPlayers = false; loadedTeams = false; loadedMatches = false; loadedFavorites = false; loadedWatchlist = false
        saving = false; mutationMessage = nil; mutationSuccess = nil; reviewCount = 0
        savedMembership = [:]
        savedActionID = nil
    }
    private func receive(force: Bool = false, name: String? = nil, profileSaveError: String? = nil) {
        // Always use the current SDK session, including after a cancelled/stale auth operation.
        let user = auth?.currentUser
        if !force, let user, uid == user.uid, repository != nil { return }
        let retainedName = uid == user?.uid ? suggestedName : ""
        clearSessionData()
        errorMessage = nil
        guard let user else { phase = .signedOut; return }
        suggestedName = name ?? retainedName
        uid = user.uid; email = user.email ?? ""
        let key = sessionKey
        phase = .restoring
        profileTask = Task { @MainActor [weak self] in
            guard let self else { return }
            do {
                let repo = try FirebaseRepository(auth: Auth.auth(), db: Firestore.firestore(),
                                                  uid: user.uid, catalog: FirebaseSetup.catalog())
                self.repository = repo
                let profile = try await repo.profile()
                guard self.isCurrent(key), !Task.isCancelled else { return }
                guard let profile else {
                    self.errorMessage = profileSaveError
                    self.phase = .profileRequired
                    return
                }
                let settings = try await repo.preferences()
                guard self.isCurrent(key), !Task.isCancelled else { return }
                self.profile = profile; self.preferences = settings
                self.phase = .ready
            } catch {
                guard self.isCurrent(key), !Task.isCancelled else { return }
                self.errorMessage = FirebaseSetup.safeMessage(error)
                self.phase = .profileError
            }
        }
    }
    func isCurrent(_ key: UUID) -> Bool { key == sessionKey && auth?.currentUser?.uid == uid && uid != nil }
    func retryProfile() { receive(force: true) }

    func signIn(email: String, password: String) async {
        guard phase == .signedOut, !authBusy, let auth else { return }
        authBusy = true; errorMessage = nil
        do {
            _ = try await auth.signIn(withEmail: email, password: password)
            authBusy = false; suggestedName = ""
            receive(force: true)
        } catch {
            authBusy = false
            if auth.currentUser != nil { receive(force: true) }
            else { errorMessage = FirebaseSetup.safeMessage(error) }
        }
    }
    func register(name: String, email: String, password: String) async {
        guard phase == .signedOut, !authBusy, let auth else { return }
        guard name.count <= 80, (try? DocumentFields(data: ["displayName": name]).text("displayName")) != nil else {
            errorMessage = "Enter a valid display name of at most 80 characters."
            return
        }
        authBusy = true; errorMessage = nil; suggestedName = name
        do {
            // Explicit Create Account action; never run from a restoration listener.
            let result = try await auth.createUser(withEmail: email, password: password)
            var profileSaveError: String?
            do {
                let repo = try FirebaseRepository(auth: auth, db: Firestore.firestore(),
                    uid: result.user.uid, catalog: FirebaseSetup.catalog())
                try await repo.saveProfile(name: name, expected: nil)
            } catch {
                // Auth succeeded. Keep the account and let the recovery screen retry the profile.
                profileSaveError = FirebaseSetup.safeMessage(error)
            }
            authBusy = false
            let isRegisteredUser = auth.currentUser?.uid == result.user.uid
            receive(force: true, name: isRegisteredUser ? name : nil,
                    profileSaveError: isRegisteredUser ? profileSaveError : nil)
        } catch {
            authBusy = false
            if auth.currentUser != nil { receive(force: true) }
            else { errorMessage = FirebaseSetup.safeMessage(error) }
        }
    }
    func signOut() {
        guard !authBusy, !saving, let auth else { return }
        do {
            try auth.signOut()
            clearSessionData(); suggestedName = ""; errorMessage = nil; phase = .signedOut
        } catch { errorMessage = FirebaseSetup.safeMessage(error) }
    }
    func completeProfile(name: String) async {
        guard !authBusy, let repository else { return }
        authBusy = true; errorMessage = nil
        do {
            try await repository.saveProfile(name: name, expected: nil)
            authBusy = false
            retryProfile()
        } catch { authBusy = false; errorMessage = FirebaseSetup.safeMessage(error) }
    }
    func updateProfile(name: String) async -> Bool {
        guard !saving, let repository else { return false }
        let key = sessionKey, expected = profile
        saving = true; mutationMessage = nil; savedActionID = nil
        defer { if isCurrent(key) { saving = false } }
        do {
            try await repository.saveProfile(name: name, expected: expected)
            let result = try await repository.profile()
            guard isCurrent(key), !Task.isCancelled else { return false }
            guard result?.displayName == name else { throw ClientError.conflict }
            profile = result
            return true
        } catch { if isCurrent(key) { mutationMessage = FirebaseSetup.safeMessage(error) }; return false }
    }
    func reloadPrivate() async -> Bool {
        guard !saving, let repository else { return false }
        let key = sessionKey
        saving = true; mutationMessage = nil; savedActionID = nil
        defer { if isCurrent(key) { saving = false } }
        do {
            let profile = try await repository.profile(), preferences = try await repository.preferences()
            guard isCurrent(key), !Task.isCancelled else { return false }
            self.profile = profile; self.preferences = preferences
            if profile == nil { phase = .profileRequired }
            return true
        } catch {
            if isCurrent(key) { mutationMessage = FirebaseSetup.safeMessage(error) }
            return false
        }
    }
    func savePreferences(_ desired: UserPreferences) async -> Bool {
        guard !saving, let repository else { return false }
        let key = sessionKey, expected = preferences
        saving = true; mutationMessage = nil; mutationSuccess = nil; savedActionID = nil
        defer { if isCurrent(key) { saving = false } }
        do {
            try await repository.savePreferences(desired, expected: expected)
            let result = try await repository.preferences()
            var comparable = result; comparable.revision = desired.revision
            guard isCurrent(key), !Task.isCancelled else { return false }
            guard comparable == desired else { throw ClientError.conflict }
            preferences = result
            return true
        } catch { if isCurrent(key) { mutationMessage = FirebaseSetup.safeMessage(error) }; return false }
    }
    func savedStatus(_ kind: SavedKind, id: String, watchlist: Bool = false) -> Bool? {
        savedMembership[kind.savedDocumentID(id, watchlist: watchlist)]
    }

    func loadSavedStatus(_ kind: SavedKind, id: String, watchlist: Bool = false) async throws {
        let documentID = kind.savedDocumentID(id, watchlist: watchlist)
        guard savedMembership[documentID] == nil, let repository else { return }
        let key = sessionKey
        let saved = try await repository.savedStatus(kind: kind, targetID: id, watchlist: watchlist)
        guard isCurrent(key), !Task.isCancelled, savedMembership[documentID] == nil else { return }
        savedMembership[documentID] = saved
    }

    func setSaved(_ kind: SavedKind, id: String, saved: Bool, watchlist: Bool = false) async {
        guard !saving, let repository else { return }
        let key = sessionKey
        let documentID = kind.savedDocumentID(id, watchlist: watchlist)
        let previous = savedMembership[documentID] ?? (watchlist ? self.watchlist : favorites).contains { $0.id == documentID }
        saving = true; mutationMessage = nil; mutationSuccess = nil
        savedMembership[documentID] = saved
        savedActionID = documentID
        defer { if isCurrent(key) { saving = false } }
        do {
            try await repository.setSaved(kind: kind, targetID: id, saved: saved, watchlist: watchlist)
            guard isCurrent(key) else { return }
            if !saved {
                if watchlist { self.watchlist.removeAll { $0.id == documentID } }
                else { favorites.removeAll { $0.id == documentID } }
            }
            await loadSaved(watchlist: watchlist, reset: true)
            guard isCurrent(key) else { return }
            mutationSuccess = saved ? "Saved to your collection." : "Removed from your collection."
        } catch {
            guard isCurrent(key) else { return }
            savedMembership[documentID] = previous
            let verified = try? await repository.savedStatus(kind: kind, targetID: id, watchlist: watchlist)
            guard isCurrent(key) else { return }
            if let verified {
                savedMembership[documentID] = verified
                if !verified {
                    if watchlist { self.watchlist.removeAll { $0.id == documentID } }
                    else { favorites.removeAll { $0.id == documentID } }
                }
                await loadSaved(watchlist: watchlist, reset: true)
            }
            guard isCurrent(key) else { return }
            if verified == saved {
                mutationSuccess = saved ? "Saved to your collection." : "Removed from your collection."
            } else {
                mutationMessage = FirebaseSetup.safeMessage(error)
            }
        }
    }
    func loadPlayers(reset: Bool = false, more: Bool = false) async {
        guard let repository, !playersLoading, reset || !loadedPlayers || (more && playersCursor != nil) else { return }
        let key = sessionKey, cursor = reset ? nil : playersCursor
        playersLoading = true; playersError = nil
        defer { if isCurrent(key) { playersLoading = false } }
        do {
            let page = try await repository.players(cursor: cursor)
            guard isCurrent(key), !Task.isCancelled else { return }
            players = reset ? page.items : players.filter { old in !page.items.contains { $0.id == old.id } } + page.items
            playersCursor = page.nextCursor; loadedPlayers = true
            playersIssues = reset ? page.issues : playersIssues + page.issues
        } catch { if isCurrent(key), !Task.isCancelled { playersError = FirebaseSetup.safeMessage(error) } }
    }
    func loadTeams(reset: Bool = false, more: Bool = false) async {
        guard let repository, !teamsLoading, reset || !loadedTeams || (more && teamsCursor != nil) else { return }
        let key = sessionKey, cursor = reset ? nil : teamsCursor
        teamsLoading = true; teamsError = nil
        defer { if isCurrent(key) { teamsLoading = false } }
        do {
            let page = try await repository.teams(cursor: cursor)
            guard isCurrent(key), !Task.isCancelled else { return }
            teams = reset ? page.items : teams.filter { old in !page.items.contains { $0.id == old.id } } + page.items
            teamsCursor = page.nextCursor; loadedTeams = true
            teamsIssues = reset ? page.issues : teamsIssues + page.issues
        } catch { if isCurrent(key), !Task.isCancelled { teamsError = FirebaseSetup.safeMessage(error) } }
    }
    func loadMatches(reset: Bool = false, more: Bool = false) async {
        guard let repository, !matchesLoading, reset || !loadedMatches || (more && matchesCursor != nil) else { return }
        let key = sessionKey, cursor = reset ? nil : matchesCursor
        matchesLoading = true; matchesError = nil
        defer { if isCurrent(key) { matchesLoading = false } }
        do {
            let page = try await repository.matches(cursor: cursor)
            guard isCurrent(key), !Task.isCancelled else { return }
            matches = reset ? page.items : matches.filter { old in !page.items.contains { $0.id == old.id } } + page.items
            matchesCursor = page.nextCursor; loadedMatches = true
            reviewCount = reset ? page.issues : reviewCount + page.issues
        } catch { if isCurrent(key), !Task.isCancelled { matchesError = FirebaseSetup.safeMessage(error) } }
    }
    func loadSaved(watchlist: Bool, reset: Bool = false, more: Bool = false) async {
        let loaded = watchlist ? loadedWatchlist : loadedFavorites
        let cursor = watchlist ? watchlistCursor : favoritesCursor
        guard let repository else { return }
        if reset {
            if watchlist { watchlistRequest = UUID(); watchlistLoading = false }
            else { favoritesRequest = UUID(); favoritesLoading = false }
        }
        guard !(watchlist ? watchlistLoading : favoritesLoading), reset || !loaded || (more && cursor != nil) else { return }
        let key = sessionKey, request = watchlist ? watchlistRequest : favoritesRequest
        if watchlist { watchlistLoading = true } else { favoritesLoading = true }
        if watchlist { watchlistError = nil } else { favoritesError = nil }
        defer {
            if isCurrent(key), request == (watchlist ? watchlistRequest : favoritesRequest) {
                if watchlist { watchlistLoading = false } else { favoritesLoading = false }
            }
        }
        do {
            let page = try await repository.savedItems(watchlist: watchlist, cursor: reset ? nil : cursor)
            guard isCurrent(key), !Task.isCancelled, request == (watchlist ? watchlistRequest : favoritesRequest) else { return }
            if watchlist {
                self.watchlist = reset ? page.items : self.watchlist.filter { old in !page.items.contains { $0.id == old.id } } + page.items
                watchlistCursor = page.nextCursor; loadedWatchlist = true
                watchlistIssues = reset ? page.issues : watchlistIssues + page.issues
            } else {
                favorites = reset ? page.items : favorites.filter { old in !page.items.contains { $0.id == old.id } } + page.items
                favoritesCursor = page.nextCursor; loadedFavorites = true
                favoritesIssues = reset ? page.issues : favoritesIssues + page.issues
            }
        } catch {
            if isCurrent(key), !Task.isCancelled, request == (watchlist ? watchlistRequest : favoritesRequest) {
                if watchlist { watchlistError = FirebaseSetup.safeMessage(error) }
                else { favoritesError = FirebaseSetup.safeMessage(error) }
            }
        }
    }
}
