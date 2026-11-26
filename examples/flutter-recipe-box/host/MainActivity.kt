package com.example.recipebox

import io.flutter.embedding.android.FlutterActivity
import io.flutter.embedding.engine.FlutterEngine
import io.flutter.plugin.common.MethodChannel

class MainActivity : FlutterActivity() {
    override fun configureFlutterEngine(flutterEngine: FlutterEngine) {
        super.configureFlutterEngine(flutterEngine)
        MethodChannel(flutterEngine.dartExecutor.binaryMessenger, "recipebox/launch")
            .setMethodCallHandler { call, result ->
                if (call.method == "demo") {
                    result.success(intent.getStringExtra("recipeBoxState") == "demo")
                } else {
                    result.notImplemented()
                }
            }
    }
}
