import Foundation
import XCTest
@testable import TrainingOSCore

final class FirstTrainingGateTests: XCTestCase {
    private let now = Date(timeIntervalSince1970: 1_800_000_000)

    func testNoHistoryWaitsForFirstTraining() {
        XCTAssertEqual(FirstTrainingGate.evaluate([], onOrBefore: now), .waitingForFirstTraining)
    }

    func testSessionWithoutActiveSetsNeedsCorrection() {
        let workout = CompletedWorkout(
            completedAt: now.addingTimeInterval(-3_600),
            activityName: "Strength",
            activeSetCount: 0
        )
        XCTAssertEqual(FirstTrainingGate.evaluate([workout], onOrBefore: now), .firstTrainingNeedsData)
    }

    func testCompletedWorkoutBecomesReady() {
        let workout = CompletedWorkout(
            completedAt: now.addingTimeInterval(-3_600),
            activityName: "Legs",
            activeSetCount: 12
        )
        XCTAssertEqual(FirstTrainingGate.evaluate([workout], onOrBefore: now), .ready)
    }

    func testFutureWorkoutCannotAnchorToday() {
        let workout = CompletedWorkout(
            completedAt: now.addingTimeInterval(3_600),
            activityName: "Future",
            activeSetCount: 8
        )
        XCTAssertEqual(FirstTrainingGate.evaluate([workout], onOrBefore: now), .waitingForFirstTraining)
    }
}
