import SwiftUI

struct MatchAnalysisView: View {
    @Environment(\.dismiss) private var dismiss

    // Pass another match when navigating here; the default is local demo data.
    var match: MatchAnalysisData = .demo

    private let background = Color(red: 12 / 255, green: 16 / 255, blue: 32 / 255)
    private let card = Color(red: 26 / 255, green: 38 / 255, blue: 61 / 255)
    private let primaryText = Color(red: 240 / 255, green: 243 / 255, blue: 251 / 255)
    private let secondaryText = Color(red: 166 / 255, green: 185 / 255, blue: 209 / 255)
    private let blue = Color(red: 40 / 255, green: 120 / 255, blue: 240 / 255)
    private let track = Color(red: 30 / 255, green: 48 / 255, blue: 76 / 255)

    var body: some View {
        ZStack {
            background.ignoresSafeArea()

            ScrollView {
                VStack(alignment: .leading, spacing: 0) {
                    HStack(spacing: 0) {
                        Button {
                            dismiss()
                        } label: {
                            Image(systemName: "chevron.left")
                                .font(.system(size: 15, weight: .bold))
                                .frame(width: 32, height: 44, alignment: .leading)
                                .contentShape(Rectangle())
                        }
                        .buttonStyle(.plain)
                        .accessibilityLabel("Back")

                        Text("Match Analysis")
                            .font(.system(size: 22, weight: .bold))
                            .accessibilityAddTraits(.isHeader)
                    }

                    summaryCard
                        .padding(.top, 16)

                    Text("Match Statistics")
                        .font(.system(size: 20, weight: .bold))
                        .accessibilityAddTraits(.isHeader)
                        .padding(.top, 30)
                        .padding(.bottom, 18)

                    VStack(spacing: 34) {
                        ForEach(match.statistics) { statistic in
                            statisticRow(statistic)
                        }
                    }

                    Text("Key Events")
                        .font(.system(size: 18, weight: .bold))
                        .accessibilityAddTraits(.isHeader)
                        .padding(.top, 60)

                    Text("No key events available yet.")
                        .font(.system(size: 13))
                        .foregroundColor(secondaryText)
                        .padding(.top, 12)
                }
                .foregroundColor(primaryText)
                .frame(maxWidth: 440, alignment: .leading)
                .padding(.horizontal, 22)
                .padding(.top, 20)
                .padding(.bottom, 32)
                .frame(maxWidth: .infinity)
            }
        }
        .preferredColorScheme(.dark)
        // The custom header above supplies the only back button.
        .navigationBarBackButtonHidden(true)
        .toolbar(.hidden, for: .navigationBar)
    }

    private var summaryCard: some View {
        VStack(spacing: 0) {
            HStack(alignment: .top) {
                Text(match.homeTeam.uppercased())
                    .frame(maxWidth: .infinity, alignment: .leading)
                Text(match.awayTeam.uppercased())
                    .frame(maxWidth: .infinity, alignment: .trailing)
            }
            .font(.system(size: 13, weight: .bold))
            .foregroundColor(secondaryText)

            Text("\(match.homeScore) : \(match.awayScore)")
                .font(.system(size: 32, weight: .bold))
                .monospacedDigit()
                .padding(.top, 16)
                .accessibilityLabel("\(match.homeTeam) \(match.homeScore), \(match.awayTeam) \(match.awayScore)")

            Text(match.status)
                .font(.system(size: 13))
                .foregroundColor(secondaryText)
                .multilineTextAlignment(.center)
                .padding(.top, 24)
        }
        .padding(.horizontal, 18)
        .padding(.vertical, 20)
        .frame(maxWidth: .infinity)
        .background(card)
        .clipShape(RoundedRectangle(cornerRadius: 23))
    }

    private func statisticRow(_ statistic: MatchAnalysisStatistic) -> some View {
        VStack(spacing: 10) {
            HStack {
                Text(statistic.homeDisplay)
                    .font(.system(size: 15, weight: .bold))
                    .frame(maxWidth: .infinity, alignment: .leading)
                Text(statistic.name)
                    .font(.system(size: 13))
                    .foregroundColor(secondaryText)
                Text(statistic.awayDisplay)
                    .font(.system(size: 15, weight: .bold))
                    .frame(maxWidth: .infinity, alignment: .trailing)
            }

            GeometryReader { geometry in
                ZStack(alignment: .leading) {
                    Capsule().fill(track)
                    Capsule()
                        .fill(blue)
                        .frame(width: geometry.size.width * statistic.homeProportion)
                }
            }
            .frame(height: 7)
            .accessibilityHidden(true)
        }
        .accessibilityElement(children: .ignore)
        .accessibilityLabel("\(statistic.name): \(match.homeTeam) \(statistic.homeDisplay), \(match.awayTeam) \(statistic.awayDisplay)")
    }
}

// Plain data models can be populated from an API later without changing the layout.
struct MatchAnalysisData {
    let homeTeam: String
    let awayTeam: String
    let homeScore: Int
    let awayScore: Int
    let status: String
    let statistics: [MatchAnalysisStatistic]

    static let demo = MatchAnalysisData(
        homeTeam: "City Blues",
        awayTeam: "Reds",
        homeScore: 3,
        awayScore: 2,
        status: "FULL TIME • DEMO MATCH",
        statistics: [
            MatchAnalysisStatistic(name: "Possession", homeValue: 57, awayValue: 43, isPercentage: true),
            MatchAnalysisStatistic(name: "Shots", homeValue: 14, awayValue: 9),
            MatchAnalysisStatistic(name: "On target", homeValue: 7, awayValue: 5),
            MatchAnalysisStatistic(name: "Corners", homeValue: 6, awayValue: 4)
        ]
    )
}

struct MatchAnalysisStatistic: Identifiable {
    let name: String
    let homeValue: Int
    let awayValue: Int
    var isPercentage = false

    // Each statistic name should be unique within a match.
    var id: String { name }
    var homeDisplay: String { "\(homeValue)\(isPercentage ? "%" : "")" }
    var awayDisplay: String { "\(awayValue)\(isPercentage ? "%" : "")" }

    var homeProportion: CGFloat {
        let home = CGFloat(max(0, homeValue))
        let away = CGFloat(max(0, awayValue))
        let total = home + away
        return total > 0 ? home / total : 0
    }
}

#Preview {
    NavigationStack {
        MatchAnalysisView(match: .demo)
    }
}
