import SwiftUI

struct HomeView: View {
    @State private var selectedTab: HomeTab = .home

    private let highlights = HomeHighlight.samples

    var body: some View {
        NavigationStack {
            ZStack {
                HomeStyle.background.ignoresSafeArea()

                if selectedTab == .home {
                    homeContent
                } else {
                    tabPlaceholder
                }
            }
            .safeAreaInset(edge: .bottom, spacing: 0) {
                bottomNavigation
            }
            .toolbar(.hidden, for: .navigationBar)
        }
        .tint(HomeStyle.blue)
        .preferredColorScheme(.dark)
    }

    private var homeContent: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 0) {
                VStack(alignment: .leading, spacing: 6) {
                    Text("FOOTBALL / DISCOVER")
                        .font(.system(size: 12))
                        .foregroundColor(HomeStyle.secondaryText)
                    Text("MatchLens")
                        .font(.system(size: 32, weight: .bold))
                        .accessibilityAddTraits(.isHeader)
                    Text("Every moment matters.")
                        .font(.system(size: 15))
                        .foregroundColor(HomeStyle.secondaryText)
                }

                featuredReplay
                    .padding(.top, 26)

                Text("Trending highlights")
                    .font(.system(size: 20, weight: .bold))
                    .accessibilityAddTraits(.isHeader)
                    .padding(.top, 22)
                    .padding(.bottom, 10)

                VStack(spacing: 14) {
                    ForEach(highlights) { highlight in
                        NavigationLink {
                            matchDestination(highlight)
                        } label: {
                            highlightCard(highlight)
                        }
                        .buttonStyle(.plain)
                    }
                }
            }
            .foregroundColor(HomeStyle.primaryText)
            .frame(maxWidth: 440, alignment: .leading)
            .padding(.horizontal, 22)
            .padding(.top, 18)
            .padding(.bottom, 30)
            .frame(maxWidth: .infinity)
        }
    }

    private var featuredReplay: some View {
        VStack(alignment: .leading, spacing: 0) {
            HomeStyle.blue
                .frame(height: 8)
                .clipShape(Capsule())

            VStack(alignment: .leading, spacing: 0) {
                Text("FEATURED REPLAY")
                    .font(.system(size: 11, weight: .bold))
                    .foregroundColor(HomeStyle.lime)

                Text("City Blues\nvs United Reds")
                    .font(.system(size: 26, weight: .bold))
                    .fixedSize(horizontal: false, vertical: true)
                    .padding(.top, 20)

                Text("Watch goals, saves & the winning moment")
                    .font(.system(size: 13))
                    .foregroundColor(HomeStyle.secondaryText)
                    .padding(.top, 16)

                NavigationLink {
                    HomePlaceholderView(
                        title: "Match Details",
                        message: "City Blues vs United Reds\nFeatured replay\n\nHighlights playback will be added here."
                    )
                } label: {
                    Text("PLAY HIGHLIGHTS")
                        .font(.system(size: 11, weight: .bold))
                        .foregroundColor(.white)
                        .padding(.horizontal, 14)
                        .frame(minHeight: 30)
                        .background(HomeStyle.blue)
                        .clipShape(Capsule())
                        // Keep the visual pill small, with a larger touch target.
                        .frame(minHeight: 44)
                        .contentShape(Rectangle())
                }
                .buttonStyle(.plain)
            }
            .padding(.horizontal, 18)
            .padding(.top, 14)
            .padding(.bottom, 2)
        }
        .frame(maxWidth: .infinity, alignment: .leading)
        .background(HomeStyle.replayBackground)
        .clipShape(RoundedRectangle(cornerRadius: 24))
        .overlay(alignment: .top) {
            HomeStyle.blue.frame(height: 8).clipShape(Capsule())
        }
    }

    private func highlightCard(_ highlight: HomeHighlight) -> some View {
        HStack(spacing: 12) {
            // Graphic placeholders: no team crests or replay images are available yet.
            ZStack(alignment: .top) {
                RoundedRectangle(cornerRadius: 15)
                    .fill(HomeStyle.replayBackground)
                if highlight.isFavorite {
                    RoundedRectangle(cornerRadius: 15)
                        .stroke(Color(red: 0, green: 0.62, blue: 1), lineWidth: 3)
                }
                HomeStyle.blue
                    .frame(height: 6)
                    .clipShape(Capsule())
                Group {
                    if highlight.isFavorite {
                        Image(systemName: "star.fill")
                            .foregroundColor(HomeStyle.lime)
                    } else {
                        Text("⚽️")
                    }
                }
                .font(.system(size: 21))
                .frame(maxWidth: .infinity, maxHeight: .infinity)
                .accessibilityHidden(true)
            }
            .frame(width: 110, height: 82)

            VStack(alignment: .leading, spacing: 10) {
                Text(highlight.title)
                    .font(.system(size: 14, weight: .bold))
                Text("\(highlight.score) • \(highlight.minutes) min • \(highlight.moments) moments")
                    .font(.system(size: 11))
                    .foregroundColor(HomeStyle.secondaryText)
                    .fixedSize(horizontal: false, vertical: true)
            }
            .frame(maxWidth: .infinity, alignment: .leading)
        }
        .padding(11)
        .frame(maxWidth: .infinity, alignment: .leading)
        .background(HomeStyle.cardBackground)
        .clipShape(RoundedRectangle(cornerRadius: 22))
        .contentShape(RoundedRectangle(cornerRadius: 22))
    }

    private var bottomNavigation: some View {
        HStack(spacing: 4) {
            ForEach(HomeTab.allCases) { tab in
                Button {
                    selectedTab = tab
                } label: {
                    Text(tab.rawValue)
                        .font(.system(size: 11, weight: selectedTab == tab ? .bold : .regular))
                        .foregroundColor(selectedTab == tab ? HomeStyle.primaryText : HomeStyle.secondaryText)
                        .frame(maxWidth: .infinity, minHeight: 44)
                        .background(selectedTab == tab ? HomeStyle.selectedTab : .clear)
                        .clipShape(Capsule())
                        .contentShape(Capsule())
                }
                .buttonStyle(.plain)
                .accessibilityAddTraits(selectedTab == tab ? .isSelected : [])
            }
        }
        .padding(5)
        .padding(.vertical, 4)
        .background(Color(red: 39 / 255, green: 48 / 255, blue: 65 / 255))
        .clipShape(RoundedRectangle(cornerRadius: 27))
        .overlay {
            RoundedRectangle(cornerRadius: 27)
                .stroke(HomeStyle.secondaryText.opacity(0.45), lineWidth: 1)
        }
        .frame(maxWidth: 450)
        .padding(.horizontal, 18)
        .padding(.bottom, 8)
        .frame(maxWidth: .infinity)
        .background(HomeStyle.background)
    }

    // Temporary destinations stay in this file until the remaining screens exist.
    private var tabPlaceholder: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 20) {
                Text(selectedTab == .saved ? "Favorites" : selectedTab.rawValue)
                    .font(.system(size: 30, weight: .bold))
                Text("Placeholder — this screen will be implemented later.")
                    .foregroundColor(HomeStyle.secondaryText)

                if selectedTab == .matches {
                    NavigationLink("Player Search") {
                        HomePlaceholderView(title: "Player Search", message: "Player search will be added here.")
                    }
                    NavigationLink("Team Details") {
                        HomePlaceholderView(title: "Team Details", message: "Team information will be added here.")
                    }
                    ForEach(highlights) { highlight in
                        NavigationLink(highlight.title) {
                            matchDestination(highlight)
                        }
                    }
                } else if selectedTab == .profile {
                    NavigationLink("Settings") {
                        HomePlaceholderView(title: "Settings", message: "Settings will be added here.")
                    }
                } else if selectedTab == .saved {
                    ForEach(highlights.filter { $0.isFavorite }) { highlight in
                        NavigationLink {
                            matchDestination(highlight)
                        } label: {
                            highlightCard(highlight)
                        }
                        .buttonStyle(.plain)
                    }
                }
            }
            .foregroundColor(HomeStyle.primaryText)
            .padding(22)
            .frame(maxWidth: .infinity, alignment: .leading)
        }
    }

    private func matchDestination(_ highlight: HomeHighlight) -> some View {
        HomePlaceholderView(
            title: "Match Details",
            message: "\(highlight.title)\nScore: \(highlight.score)\nStatus: Finished (mock)\n\(highlight.minutes) minutes • \(highlight.moments) moments\n\nMatch details and playback will be added here."
        )
    }
}

private enum HomeTab: String, CaseIterable, Identifiable {
    case home = "Home"
    case matches = "Matches"
    case saved = "Saved"
    case profile = "Profile"

    var id: String { rawValue }
}

// Local sample data; replace with API-backed data in a later development stage.
private struct HomeHighlight: Identifiable {
    let id: String
    let title: String
    let score: String
    let minutes: Int
    let moments: Int
    let isFavorite: Bool

    static let samples = [
        HomeHighlight(id: "derby", title: "Derby Night", score: "3–2", minutes: 12, moments: 5, isFavorite: false),
        HomeHighlight(id: "comeback", title: "Classic Comeback", score: "2–2", minutes: 9, moments: 4, isFavorite: true)
    ]
}

private enum HomeStyle {
    static let background = Color(red: 11 / 255, green: 15 / 255, blue: 31 / 255)
    static let cardBackground = Color(red: 26 / 255, green: 38 / 255, blue: 58 / 255)
    static let replayBackground = Color(red: 30 / 255, green: 48 / 255, blue: 76 / 255)
    static let primaryText = Color(red: 240 / 255, green: 243 / 255, blue: 251 / 255)
    static let secondaryText = Color(red: 166 / 255, green: 185 / 255, blue: 209 / 255)
    static let blue = Color(red: 41 / 255, green: 119 / 255, blue: 250 / 255)
    static let lime = Color(red: 166 / 255, green: 1, blue: 0)
    static let selectedTab = Color(red: 39 / 255, green: 69 / 255, blue: 119 / 255)
}

private struct HomePlaceholderView: View {
    let title: String
    let message: String

    var body: some View {
        ZStack {
            HomeStyle.background.ignoresSafeArea()
            ScrollView {
                VStack(alignment: .leading, spacing: 16) {
                    Text("Placeholder")
                        .font(.headline)
                    Text(message)
                        .foregroundColor(HomeStyle.secondaryText)
                }
                .padding(24)
                .frame(maxWidth: .infinity, alignment: .leading)
            }
        }
        .foregroundColor(HomeStyle.primaryText)
        .navigationTitle(title)
        .navigationBarTitleDisplayMode(.inline)
        .toolbar(.visible, for: .navigationBar)
    }
}

#Preview {
    HomeView()
}
