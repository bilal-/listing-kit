"""Configure the Flutter 3.29.3 platform templates in this Recipe Box example."""

import plistlib
from pathlib import Path
from shutil import copyfile

host = Path(__file__).resolve().parent
root = host.parent
gradle = root / "android/app/build.gradle.kts"
manifest = root / "android/app/src/main/AndroidManifest.xml"
project = root / "ios/Runner.xcodeproj/project.pbxproj"
plist = root / "ios/Runner/Info.plist"
activity = root / "android/app/src/main/kotlin/com/example/recipebox/MainActivity.kt"
delegate = root / "ios/Runner/AppDelegate.swift"

templates = (gradle, manifest, project, plist, activity, delegate)
missing = [str(path.relative_to(root)) for path in templates if not path.is_file()]
if missing:
    raise SystemExit("Run 'flutter create' (Flutter 3.29.3) first. Missing: " + ", ".join(missing))

for path in templates:
    if root not in path.resolve().parents or path.stat().st_nlink > 1:
        raise SystemExit(f"Refusing to edit a linked template: {path.relative_to(root)}")


def configure(path, old, new):
    text = path.read_text()
    if new in text:
        return
    if old not in text:
        raise SystemExit(f"Expected Flutter 3.29.3 template setting in {path}: {old}")
    path.write_text(text.replace(old, new))


base_id = "com.example.recipebox"
app_id = base_id + ".flutter"
configure(gradle, f'applicationId = "{base_id}"', f'applicationId = "{app_id}"')
configure(manifest, 'android:label="recipebox"', 'android:label="Recipe Box"')
configure(project, f"= {base_id};", f"= {app_id};")
info = plistlib.loads(plist.read_bytes())
info["CFBundleDisplayName"] = "Recipe Box"
plist.write_bytes(plistlib.dumps(info, sort_keys=False))
copyfile(host / "MainActivity.kt", activity)
copyfile(host / "AppDelegate.swift", delegate)
