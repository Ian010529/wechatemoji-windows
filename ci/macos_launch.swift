// AI-drafted acceptance probe: launch only the supplied test app and close it afterwards.
import AppKit
import CoreGraphics
import Foundation

let path = CommandLine.arguments[1]
var application: NSRunningApplication?
var launchError: Error?
var completed = false
let configuration = NSWorkspace.OpenConfiguration()
configuration.createsNewApplicationInstance = true
configuration.environment = ["PATH": "/usr/bin:/bin:/usr/sbin:/sbin", "HOME": NSHomeDirectory(), "TMPDIR": NSTemporaryDirectory()]
configuration.activates = false
NSWorkspace.shared.openApplication(at: URL(fileURLWithPath: path), configuration: configuration) { app, error in
    application = app
    launchError = error
    completed = true
}
func pump() { RunLoop.current.run(until: Date().addingTimeInterval(0.1)) }
var deadline = Date().addingTimeInterval(45)
while !completed && Date() < deadline { pump() }
var result: [String: Any] = ["status": "failed", "launch_completed": completed]
if let app = application {
    result["pid"] = app.processIdentifier
    deadline = Date().addingTimeInterval(30)
    var visibleWindow = false
    while Date() < deadline && !app.isTerminated {
        let windows = CGWindowListCopyWindowInfo([.optionOnScreenOnly, .excludeDesktopElements], kCGNullWindowID) as? [[String: Any]] ?? []
        visibleWindow = visibleWindow || windows.contains { row in
            guard let owner = row[kCGWindowOwnerPID as String] as? Int,
                  let bounds = row[kCGWindowBounds as String] as? [String: Any],
                  let width = bounds["Width"] as? Double,
                  let height = bounds["Height"] as? Double else { return false }
            return owner == Int(app.processIdentifier) && width >= 600 && height >= 400
        }
        pump()
    }
    result["window_observed"] = visibleWindow
    result["survived_30_seconds"] = !app.isTerminated
    if visibleWindow && !app.isTerminated { result["status"] = "passed" }
    if !app.isTerminated { _ = app.terminate() }
    deadline = Date().addingTimeInterval(15)
    while !app.isTerminated && Date() < deadline { pump() }
    result["closed_cleanly"] = app.isTerminated
    if !app.isTerminated { _ = app.forceTerminate(); result["status"] = "failed" }
} else {
    result["error"] = launchError?.localizedDescription ?? "Launch Services did not return an application"
}
let data = try JSONSerialization.data(withJSONObject: result, options: [.sortedKeys])
print(String(data: data, encoding: .utf8)!)
exit(result["status"] as? String == "passed" ? 0 : 1)
