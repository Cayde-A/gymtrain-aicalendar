import SwiftUI
import TrainingOSCore

struct NutritionView: View {
    @EnvironmentObject private var store: AppStore
    @State private var showingCapturePlan = false

    var body: some View {
        NavigationStack {
            List {
                Section("nutrition.quickAdd") {
                    Button("nutrition.photo", systemImage: "camera") {
                        showingCapturePlan = true
                    }
                    Button("nutrition.barcode", systemImage: "barcode.viewfinder") {
                        showingCapturePlan = true
                    }
                    Button("nutrition.manual", systemImage: "plus.circle") {
                        showingCapturePlan = true
                    }
                }

                Section("nutrition.today") {
                    ProgressMetric(
                        title: "nutrition.calories",
                        value: store.today.nutrition.caloriesConsumed,
                        target: store.today.nutrition.calorieTarget,
                        unit: "unit.kcal"
                    )
                    ProgressMetric(
                        title: "nutrition.protein",
                        value: store.today.nutrition.proteinGrams,
                        target: store.today.nutrition.proteinTargetGrams,
                        unit: "unit.gram"
                    )
                }

                Section("nutrition.hydration") {
                    ProgressMetric(
                        title: "nutrition.water",
                        value: store.today.nutrition.waterMilliliters,
                        target: store.today.nutrition.waterTargetMilliliters,
                        unit: "unit.ml"
                    )
                    HStack {
                        Button("+250 ml") { store.addWater(250) }
                            .buttonStyle(.bordered)
                        Button("+500 ml") { store.addWater(500) }
                            .buttonStyle(.bordered)
                    }
                }

                Section("nutrition.plan") {
                    Picker("nutrition.plan", selection: eatingPlanBinding) {
                        Text("nutrition.planBalanced").tag(EatingPlan.balanced)
                        Text("nutrition.planFatLoss").tag(EatingPlan.fatLoss)
                        Text("nutrition.planMuscleGain").tag(EatingPlan.muscleGain)
                        Text("nutrition.plan16x8").tag(EatingPlan.timeRestricted16x8)
                    }
                    if store.today.nutrition.eatingPlan == .timeRestricted16x8 {
                        LabeledContent("nutrition.eatingWindow", value: "12:00-20:00")
                        Text("nutrition.reminderPlaceholder")
                            .font(.caption)
                            .foregroundStyle(.secondary)
                    }
                }
            }
            .navigationTitle("nutrition.title")
            .alert("nutrition.capturePlannedTitle", isPresented: $showingCapturePlan) {
                Button("action.ok", role: .cancel) {}
            } message: {
                Text("nutrition.capturePlannedMessage")
            }
        }
    }

    private var eatingPlanBinding: Binding<EatingPlan> {
        Binding(
            get: { store.today.nutrition.eatingPlan },
            set: { store.selectEatingPlan($0) }
        )
    }
}
