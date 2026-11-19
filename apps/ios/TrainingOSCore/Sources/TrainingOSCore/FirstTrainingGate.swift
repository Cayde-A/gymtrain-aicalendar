import Foundation

public enum FirstTrainingGate {
    public static func evaluate(_ workouts: [CompletedWorkout], onOrBefore date: Date) -> TrainingAnchorStatus {
        let eligible = workouts.filter { $0.completedAt <= date }
        guard !eligible.isEmpty else {
            return .waitingForFirstTraining
        }
        return eligible.contains(where: { $0.activeSetCount > 0 })
            ? .ready
            : .firstTrainingNeedsData
    }
}
