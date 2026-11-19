import Combine
import Foundation
import TrainingOSCore

@MainActor
final class AppStore: ObservableObject {
    @Published var selectedTab: CustomerTab = .today
    @Published var today: TodaySnapshot
    @Published var recentWorkouts: [CompletedWorkout]

    init(today: TodaySnapshot, recentWorkouts: [CompletedWorkout]) {
        self.today = today
        self.recentWorkouts = recentWorkouts
    }

    func addWater(_ milliliters: Int) {
        let nextValue = today.nutrition.waterMilliliters + milliliters
        today.nutrition.waterMilliliters = max(0, min(nextValue, 10_000))
    }

    func selectEatingPlan(_ plan: EatingPlan) {
        today.nutrition.eatingPlan = plan
    }

    static let preview = AppStore(
        today: TodaySnapshot(
            anchorStatus: .waitingForFirstTraining,
            recovery: RecoverySnapshot(),
            workout: nil,
            nutrition: NutritionDaySummary()
        ),
        recentWorkouts: []
    )
}
