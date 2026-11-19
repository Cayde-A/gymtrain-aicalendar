import SwiftUI
import TrainingOSCore

struct TrainingView: View {
    @EnvironmentObject private var store: AppStore

    var body: some View {
        NavigationStack {
            List {
                Section("training.today") {
                    if let workout = store.today.workout {
                        Text(workout.title)
                            .font(.headline)
                        LabeledContent("training.primaryGroup", value: workout.primaryMuscleGroup)
                        LabeledContent("training.exercises", value: String(workout.exerciseCount))
                        Button("training.start") {}
                            .buttonStyle(.borderedProminent)
                    } else {
                        ContentUnavailableView(
                            "training.noWorkout",
                            systemImage: "dumbbell",
                            description: Text("training.noWorkoutDescription")
                        )
                    }
                }

                Section("training.recent") {
                    if store.recentWorkouts.isEmpty {
                        Text("training.noHistory")
                            .foregroundStyle(.secondary)
                    } else {
                        ForEach(store.recentWorkouts) { workout in
                            NavigationLink {
                                WorkoutCorrectionPlaceholder(workout: workout)
                            } label: {
                                VStack(alignment: .leading) {
                                    Text(workout.activityName)
                                    Text(workout.completedAt, style: .date)
                                        .font(.caption)
                                        .foregroundStyle(.secondary)
                                }
                            }
                        }
                    }
                }
            }
            .navigationTitle("training.title")
            .toolbar {
                ToolbarItem(placement: .topBarTrailing) {
                    Button("training.sync", systemImage: "arrow.triangle.2.circlepath") {}
                }
            }
        }
    }
}

private struct WorkoutCorrectionPlaceholder: View {
    let workout: CompletedWorkout

    var body: some View {
        List {
            LabeledContent("training.activeSets", value: String(workout.activeSetCount))
            Text("training.correctionPlanned")
                .foregroundStyle(.secondary)
        }
        .navigationTitle(workout.activityName)
    }
}
