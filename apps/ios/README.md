# TrainingOS iOS

This directory is the native iOS-first customer application.

## Baseline

- iOS 17 or later;
- Swift 6;
- SwiftUI;
- four customer tabs: Today, Training, Nutrition, and Progress;
- local `TrainingOSCore` Swift package for domain models and gates;
- English and Simplified Chinese system localization;
- no third-party runtime dependency in the initial shell.

The current shell intentionally does not claim that Garmin, Apple Health,
camera recognition, notifications, or cloud sync are connected. Their service
contracts and customer locations are defined, but permissions and adapters are
implemented in later milestones.

## Project Generation

Install the full Xcode application and select it as the active developer
directory. Xcode Command Line Tools alone do not include the iOS SDK or
simulator.

Install XcodeGen, then generate the project:

```bash
cd apps/ios
xcodegen generate
open TrainingOS.xcodeproj
```

`project.yml` is the source of truth. The generated `.xcodeproj` and local
DerivedData are ignored by Git.

The source tree can be edited in VS Code. Xcode remains required for iOS SDK
compilation, simulator execution, signing, capabilities, and device testing.

## Core Tests

With a matching Swift compiler and macOS SDK:

```bash
swift test --package-path apps/ios/TrainingOSCore
```

The first tests cover the same onboarding rule as the existing local backend:

- no completed history waits for the first workout;
- an activity without active sets requires correction;
- a completed workout with active sets unlocks analysis.

## Privacy Baseline

- Food photos must produce an editable draft before calories are saved.
- Raw photos are not persisted by the shell.
- Health, camera, and notification permissions are requested only when the
  user enters the relevant workflow.
- API keys, raw Garmin payloads, provider switching, and debug controls are not
  customer UI.
- Local storage remains the private source of truth until optional cloud sync
  is explicitly enabled.

## Next Implementation Steps

1. Generate and build the project with full Xcode; resolve iOS type-check and signing issues.
2. Add local persistence and map normalized TrainingOS records into `TrainingOSCore`.
3. Implement Training import/history/correction before enabling live AI actions.
4. Add local water, meal, eating-window, and notification models.
5. Add camera/barcode adapters with mandatory user correction.
6. Add Garmin/Apple Health adapters and optional minimized cloud sync.
