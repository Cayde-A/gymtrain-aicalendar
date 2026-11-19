import SwiftUI

struct ProgressView: View {
    @State private var showingSettings = false

    var body: some View {
        NavigationStack {
            List {
                Section("progress.training") {
                    LabeledContent("progress.trainingDays", value: "0")
                    LabeledContent("progress.activeSets", value: "0")
                    LabeledContent("progress.prs", value: "0")
                }

                Section("progress.bodyRecovery") {
                    Text("progress.noTrendData")
                        .foregroundStyle(.secondary)
                }

                Section("progress.nutrition") {
                    Text("progress.noNutritionTrendData")
                        .foregroundStyle(.secondary)
                }
            }
            .navigationTitle("progress.title")
            .toolbar {
                ToolbarItem(placement: .topBarTrailing) {
                    Button("settings.title", systemImage: "gearshape") {
                        showingSettings = true
                    }
                }
            }
            .sheet(isPresented: $showingSettings) {
                SettingsSheet()
            }
        }
    }
}

private struct SettingsSheet: View {
    @Environment(\.dismiss) private var dismiss

    var body: some View {
        NavigationStack {
            List {
                Section("settings.connections") {
                    LabeledContent("settings.garmin", value: String(localized: "settings.notConnected"))
                    LabeledContent("settings.appleHealth", value: String(localized: "settings.notConnected"))
                }
                Section("settings.preferences") {
                    NavigationLink("settings.notifications") { Text("settings.notificationsPlanned") }
                    NavigationLink("settings.privacy") { Text("settings.privacyPlanned") }
                }
            }
            .navigationTitle("settings.title")
            .toolbar {
                ToolbarItem(placement: .confirmationAction) {
                    Button("action.done") { dismiss() }
                }
            }
        }
    }
}
