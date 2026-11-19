import SwiftUI

struct ProgressMetric: View {
    let title: LocalizedStringKey
    let value: Int
    let target: Int
    let unit: LocalizedStringKey

    private var progress: Double {
        guard target > 0 else { return 0 }
        return min(1, max(0, Double(value) / Double(target)))
    }

    var body: some View {
        VStack(alignment: .leading, spacing: 8) {
            HStack {
                Text(title)
                Spacer()
                Text("\(value) / \(target) ") + Text(unit)
            }
            .font(.subheadline)
            ProgressView(value: progress)
        }
        .accessibilityElement(children: .combine)
    }
}
