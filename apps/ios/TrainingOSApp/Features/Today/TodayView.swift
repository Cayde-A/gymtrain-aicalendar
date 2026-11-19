import SwiftUI
import TrainingOSCore

struct TodayView: View {
    @EnvironmentObject private var store: AppStore

    var body: some View {
        NavigationStack {
            List {
                anchorSection
                recoverySection
                trainingSection
                nutritionSection
            }
            .navigationTitle("today.title")
        }
    }

    @ViewBuilder
    private var anchorSection: some View {
        if store.today.anchorStatus != .ready {
            Section {
                Label(anchorMessage, systemImage: "clock.badge.exclamationmark")
                    .foregroundStyle(.secondary)
            }
        }
    }

    private var recoverySection: some View {
        Section("today.recovery") {
            metricRow("metric.sleepScore", store.today.recovery.sleepScore)
            metricRow("metric.bodyBattery", store.today.recovery.bodyBattery)
            metricRow("metric.readiness", store.today.recovery.trainingReadiness)
            LabeledContent("metric.hrv", value: store.today.recovery.hrvStatus ?? String(localized: "value.none"))
        }
    }

    private var trainingSection: some View {
        Section("today.training") {
            if let workout = store.today.workout {
                LabeledContent("training.primaryGroup", value: workout.primaryMuscleGroup)
                LabeledContent("training.duration", value: "\(workout.estimatedMinutes) min")
                Button("training.start") { store.selectedTab = .training }
                    .buttonStyle(.borderedProminent)
            } else {
                Text("today.noPlan")
                    .foregroundStyle(.secondary)
            }
        }
    }

    private var nutritionSection: some View {
        Section("today.nutrition") {
            ProgressMetric(
                title: "nutrition.calories",
                value: store.today.nutrition.caloriesConsumed,
                target: store.today.nutrition.calorieTarget,
                unit: "unit.kcal"
            )
            ProgressMetric(
                title: "nutrition.water",
                value: store.today.nutrition.waterMilliliters,
                target: store.today.nutrition.waterTargetMilliliters,
                unit: "unit.ml"
            )
        }
    }

    private func metricRow(_ key: LocalizedStringKey, _ value: Int?) -> some View {
        LabeledContent(key, value: value.map(String.init) ?? String(localized: "value.none"))
    }

    private var anchorMessage: LocalizedStringKey {
        store.today.anchorStatus == .waitingForFirstTraining
            ? "anchor.waiting"
            : "anchor.needsData"
    }
}
