import Flutter
import UIKit

@main
@objc class AppDelegate: FlutterAppDelegate {
    override func application(
        _ application: UIApplication,
        didFinishLaunchingWithOptions launchOptions: [UIApplication.LaunchOptionsKey: Any]?
    ) -> Bool {
        let controller = window!.rootViewController as! FlutterViewController
        let channel = FlutterMethodChannel(name: "recipebox/launch", binaryMessenger: controller.binaryMessenger)
        channel.setMethodCallHandler { call, result in
            if call.method == "demo" {
                result(UserDefaults.standard.string(forKey: "recipeBoxState") == "demo")
            } else {
                result(FlutterMethodNotImplemented)
            }
        }
        GeneratedPluginRegistrant.register(with: self)
        return super.application(application, didFinishLaunchingWithOptions: launchOptions)
    }
}
