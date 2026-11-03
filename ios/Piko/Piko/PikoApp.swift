import SwiftUI
@main
struct WappaiApp:App {
    init(){
        #if DEBUG
        if ProcessInfo.processInfo.arguments.contains("--qa-ui-fixture") && ProcessInfo.processInfo.arguments.contains("--qa-ui-reset") {
            for key in ["wappai.pip.x","wappai.pip.y","wappai.pip.hidden","wappai.appearance"] {UserDefaults.standard.removeObject(forKey:key)}
        }
        #endif
    }
    var body:some Scene{WindowGroup{RootView().environment(\.layoutDirection,.rightToLeft)}}
}
