"""Install the Recipe Box hosts into a Flutter 3.29.3 app generated in the cwd."""

import plistlib
from pathlib import Path
from shutil import copyfile

host = Path(__file__).resolve().parent
base_id = "com.example.recipebox"
app_id = base_id + ".flutter"


def configure(path, old, new):
    path = Path(path)
    text = path.read_text()
    if new in text:
        return
    if old not in text:
        raise SystemExit(f"Expected Flutter 3.29.3 template setting in {path}: {old}")
    path.write_text(text.replace(old, new))


configure("android/app/build.gradle.kts", f'applicationId = "{base_id}"', f'applicationId = "{app_id}"')
configure("android/app/src/main/AndroidManifest.xml", 'android:label="recipebox"', 'android:label="Recipe Box"')
configure("ios/Runner.xcodeproj/project.pbxproj", f"= {base_id};", f"= {app_id};")
plist = Path("ios/Runner/Info.plist")
info = plistlib.loads(plist.read_bytes())
info["CFBundleDisplayName"] = "Recipe Box"
plist.write_bytes(plistlib.dumps(info, sort_keys=False))
copyfile(host / "MainActivity.kt", "android/app/src/main/kotlin/com/example/recipebox/MainActivity.kt")
copyfile(host / "AppDelegate.swift", "ios/Runner/AppDelegate.swift")
