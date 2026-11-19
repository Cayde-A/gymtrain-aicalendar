import SwiftUI
import TrainingOSCore

struct RootTabView: View {
    @EnvironmentObject private var store: AppStore

    var body: some View {
        TabView(selection: $store.selectedTab) {
            TodayView()
                .tabItem { Label("tab.today", systemImage: "sun.max") }
                .tag(CustomerTab.today)

            TrainingView()
                .tabItem { Label("tab.training", systemImage: "dumbbell") }
                .tag(CustomerTab.training)

            NutritionView()
                .tabItem { Label("tab.nutrition", systemImage: "fork.knife") }
                .tag(CustomerTab.nutrition)

            ProgressView()
                .tabItem { Label("tab.progress", systemImage: "chart.xyaxis.line") }
                .tag(CustomerTab.progress)
        }
    }
}
