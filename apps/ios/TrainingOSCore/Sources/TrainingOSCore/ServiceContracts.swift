import Foundation

public protocol TrainingDataService: Sendable {
    func completedWorkouts() async throws -> [CompletedWorkout]
    func todayWorkout() async throws -> WorkoutPlanSummary?
}

public protocol RecoveryDataService: Sendable {
    func latestRecovery() async throws -> RecoverySnapshot
}

public protocol NutritionDataService: Sendable {
    func todayNutrition() async throws -> NutritionDaySummary
    func addWater(milliliters: Int) async throws
}

public protocol FoodRecognitionService: Sendable {
    func recognizeFood(imageData: Data) async throws -> FoodRecognitionDraft
}

public struct FoodRecognitionDraft: Codable, Equatable, Sendable {
    public var name: String
    public var servingDescription: String
    public var estimatedCalories: Int
    public var confidence: Double
    public var requiresUserConfirmation: Bool

    public init(
        name: String,
        servingDescription: String,
        estimatedCalories: Int,
        confidence: Double,
        requiresUserConfirmation: Bool = true
    ) {
        self.name = name
        self.servingDescription = servingDescription
        self.estimatedCalories = estimatedCalories
        self.confidence = confidence
        self.requiresUserConfirmation = requiresUserConfirmation
    }
}
