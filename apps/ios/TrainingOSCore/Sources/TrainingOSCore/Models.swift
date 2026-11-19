import Foundation

public enum CustomerTab: String, CaseIterable, Hashable, Sendable {
    case today
    case training
    case nutrition
    case progress
}

public enum TrainingAnchorStatus: String, Codable, Hashable, Sendable {
    case waitingForFirstTraining
    case firstTrainingNeedsData
    case ready
}

public struct CompletedWorkout: Identifiable, Codable, Equatable, Sendable {
    public let id: UUID
    public var completedAt: Date
    public var activityName: String
    public var activeSetCount: Int

    public init(
        id: UUID = UUID(),
        completedAt: Date,
        activityName: String,
        activeSetCount: Int
    ) {
        self.id = id
        self.completedAt = completedAt
        self.activityName = activityName
        self.activeSetCount = activeSetCount
    }
}

public struct RecoverySnapshot: Codable, Equatable, Sendable {
    public var sleepScore: Int?
    public var bodyBattery: Int?
    public var trainingReadiness: Int?
    public var hrvStatus: String?

    public init(
        sleepScore: Int? = nil,
        bodyBattery: Int? = nil,
        trainingReadiness: Int? = nil,
        hrvStatus: String? = nil
    ) {
        self.sleepScore = sleepScore
        self.bodyBattery = bodyBattery
        self.trainingReadiness = trainingReadiness
        self.hrvStatus = hrvStatus
    }
}

public struct WorkoutPlanSummary: Codable, Equatable, Sendable {
    public var title: String
    public var primaryMuscleGroup: String
    public var exerciseCount: Int
    public var estimatedMinutes: Int

    public init(title: String, primaryMuscleGroup: String, exerciseCount: Int, estimatedMinutes: Int) {
        self.title = title
        self.primaryMuscleGroup = primaryMuscleGroup
        self.exerciseCount = exerciseCount
        self.estimatedMinutes = estimatedMinutes
    }
}

public enum EatingPlan: String, Codable, CaseIterable, Hashable, Sendable {
    case balanced
    case fatLoss
    case muscleGain
    case timeRestricted16x8
}

public struct NutritionDaySummary: Codable, Equatable, Sendable {
    public var caloriesConsumed: Int
    public var calorieTarget: Int
    public var proteinGrams: Int
    public var proteinTargetGrams: Int
    public var waterMilliliters: Int
    public var waterTargetMilliliters: Int
    public var eatingPlan: EatingPlan

    public init(
        caloriesConsumed: Int = 0,
        calorieTarget: Int = 2_200,
        proteinGrams: Int = 0,
        proteinTargetGrams: Int = 160,
        waterMilliliters: Int = 0,
        waterTargetMilliliters: Int = 2_500,
        eatingPlan: EatingPlan = .balanced
    ) {
        self.caloriesConsumed = caloriesConsumed
        self.calorieTarget = calorieTarget
        self.proteinGrams = proteinGrams
        self.proteinTargetGrams = proteinTargetGrams
        self.waterMilliliters = waterMilliliters
        self.waterTargetMilliliters = waterTargetMilliliters
        self.eatingPlan = eatingPlan
    }
}

public struct TodaySnapshot: Codable, Equatable, Sendable {
    public var anchorStatus: TrainingAnchorStatus
    public var recovery: RecoverySnapshot
    public var workout: WorkoutPlanSummary?
    public var nutrition: NutritionDaySummary

    public init(
        anchorStatus: TrainingAnchorStatus,
        recovery: RecoverySnapshot,
        workout: WorkoutPlanSummary?,
        nutrition: NutritionDaySummary
    ) {
        self.anchorStatus = anchorStatus
        self.recovery = recovery
        self.workout = workout
        self.nutrition = nutrition
    }
}
