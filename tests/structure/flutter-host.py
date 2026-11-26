"""Exercise host/configure.py against generated-file stand-ins in a fixture."""

import plistlib
import subprocess
import sys
from pathlib import Path

example = Path(sys.argv[1])
caller = example.parent / "other-flutter-app"
gradle = "android/app/build.gradle.kts"
manifest = "android/app/src/main/AndroidManifest.xml"
project = "ios/Runner.xcodeproj/project.pbxproj"
plist = "ios/Runner/Info.plist"
activity = "android/app/src/main/kotlin/com/example/recipebox/MainActivity.kt"
delegate = "ios/Runner/AppDelegate.swift"

templates = {
    gradle: b'applicationId = "com.example.recipebox"',
    manifest: b'<application android:label="recipebox"/>',
    project: b"PRODUCT_BUNDLE_IDENTIFIER = com.example.recipebox;",
    plist: plistlib.dumps({"CFBundleDisplayName": "Recipebox", "Other": "preserved"}),
    activity: b"// original Android host",
    delegate: b"// original iOS host",
}


def install_template(root, name):
    path = root / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(templates[name])


def configure():
    return subprocess.run(
        [sys.executable, example / "host/configure.py"], cwd=caller,
        stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
    )


# Even a complete app in the caller's directory must be ignored.
for name in templates:
    install_template(caller, name)
install_template(example, gradle)
result = configure()
assert result.returncode != 0, result.stdout
assert len(result.stdout.splitlines()) == 1 and "flutter create" in result.stdout, result.stdout
for name in templates.keys() - {gradle}:
    assert name in result.stdout, result.stdout
assert gradle not in result.stdout and (example / gradle).read_bytes() == templates[gradle]

for name in templates.keys() - {gradle, delegate}:
    install_template(example, name)
(example / delegate).symlink_to(caller / delegate)
result = configure()
assert result.returncode != 0 and delegate in result.stdout, result.stdout
assert (caller / delegate).read_bytes() == templates[delegate]
(example / delegate).unlink()
install_template(example, delegate)

for _ in range(2):
    result = configure()
    assert result.returncode == 0, result.stdout
    assert (example / gradle).read_text() == 'applicationId = "com.example.recipebox.flutter"'
    assert (example / manifest).read_text() == '<application android:label="Recipe Box"/>'
    assert (example / project).read_text() == "PRODUCT_BUNDLE_IDENTIFIER = com.example.recipebox.flutter;"
    assert plistlib.loads((example / plist).read_bytes()) == {
        "CFBundleDisplayName": "Recipe Box", "Other": "preserved",
    }
    for name in (activity, delegate):
        assert (example / name).read_bytes() == (example / "host" / Path(name).name).read_bytes()
    for name, original in templates.items():
        assert (caller / name).read_bytes() == original, name
