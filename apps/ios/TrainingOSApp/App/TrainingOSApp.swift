import SwiftUI

@main
struct TrainingOSApp: App {
    @StateObject private var store = AppStore.preview

    var body: some Scene {
        WindowGroup {
            RootTabView()
                .environmentObject(store)
        }
    }
}
