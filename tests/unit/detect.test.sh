#!/usr/bin/env bash
. "$(dirname "${BASH_SOURCE[0]}")/../helpers.sh"
new_tempdir T
run(){ python3 -I -B "$SCRIPTS/lib/detect.py" "$T"; }
it "unknown facts have no invented defaults"
OUT="$(run)"; assert_contains "$OUT" $'supportsIphone\tunknown'
assert_contains "$OUT" $'isUpdate\tunknown'
mkdir -p "$T/node_modules/mod" "$T/Pods" "$T/android"
printf 'TARGETED_DEVICE_FAMILY = 1; SDKROOT = watchos;' > "$T/Pods/sample.pbxproj"
cat > "$T/App.pbxproj" <<'PBX'
TARGETED_DEVICE_FAMILY = 2;
TVOS_DEPLOYMENT_TARGET = 16;
SUPPORTED_PLATFORMS = "iphoneos xros";
SUPPORTS_MACCATALYST = YES;
PBX
cat > "$T/android/AndroidManifest.xml" <<'XML'
<manifest xmlns:android="http://schemas.android.com/apk/res/android">
 <uses-feature android:name="android.hardware.type.watch"/>
 <uses-feature android:name="android.software.leanback" android:required="false"/>
 <uses-feature android:name="android.software.xr.api.spatial" android:required="false"/>
</manifest>
XML
it "detectors report evidence for each declared platform and prune dependency files"
OUT="$(run)"
for cond in supportsIpad hasTvApp hasVisionApp hasMacApp; do assert_contains "$OUT" "$cond"$'\tyes\tApp.pbxproj'; done
for cond in supportsIphone hasWatchApp; do assert_contains "$OUT" "$cond"$'\tno\tApp.pbxproj'; done
for cond in hasWearOs hasAndroidTv hasAndroidXr; do assert_contains "$OUT" "$cond"$'\tyes\tandroid/AndroidManifest.xml'; done
assert_contains "$OUT" $'supportsAndroidPhone\tno\tandroid/AndroidManifest.xml'
OUT="$(LK_SUPPORTS_IPHONE=1 run)"; assert_contains "$OUT" $'supportsIphone\tyes\tLK_SUPPORTS_IPHONE'
it "a validated plan takes precedence over environment flags"
mkdir -p "$T/.listing-kit"
cat > "$T/.listing-kit/listing.json" <<'JSON'
{"format":2,"app":{"id":"example"},"locales":["en-US"],"targets":[{"id":"phone","store":"play","slot":"phone","size":[1080,1920],"state":"active"}],"screens":[{"id":"one","flow":"one.yaml"},{"id":"two","flow":"two.yaml"}],"platforms":{"supportsIphone":true,"isUpdate":true}}
JSON
OUT="$(LK_SUPPORTS_IPHONE=0 run)"; assert_contains "$OUT" $'supportsIphone\tyes\t.listing-kit/listing.json'
assert_contains "$OUT" $'isUpdate\tyes\t.listing-kit/listing.json'
printf 'invalid' > "$T/.listing-kit/listing.json"
OUT="$(LK_SUPPORTS_IPHONE=0 run)"; assert_contains "$OUT" $'supportsIphone\tno\tLK_SUPPORTS_IPHONE'
it "Info.plist and Expo declarations work without evaluating app code"
rm "$T/App.pbxproj"
python3 - "$T/Info.plist" <<'PYTEST'
import plistlib, sys
with open(sys.argv[1], "wb") as f:
    plistlib.dump({"UIDeviceFamily": [1]}, f, fmt=plistlib.FMT_BINARY)
PYTEST
OUT="$(run)"; assert_contains "$OUT" $'supportsIphone\tyes\tInfo.plist'
assert_contains "$OUT" $'supportsIpad\tno\tInfo.plist'
rm "$T/Info.plist"
printf 'export default { ios: { supportsTablet: true } }; throw Error("do not run")' > "$T/app.config.ts"
OUT="$(run)"; assert_contains "$OUT" $'supportsIpad\tyes\tapp.config.ts'
it "nested Expo settings and an iPad-only declaration are read as static literals"
printf '%s' 'export default { ios: { infoPlist: { note: "}" }, isTabletOnly: true, supportsTablet: true } };' > "$T/app.config.ts"
OUT="$(run)"
assert_contains "$OUT" $'supportsIphone\tno\tapp.config.ts'
assert_contains "$OUT" $'supportsIpad\tyes\tapp.config.ts'
it "a computed Expo capability stays unknown"
printf '%s' 'export default { ios: { supportsTablet: process.env.TABLET } };' > "$T/app.config.ts"
OUT="$(run)"; assert_contains "$OUT" $'supportsIpad\tunknown'
it "malformed native metadata leaves detection available"
printf '<?xml version="1.0"?><plist><dict>' > "$T/Info.plist"
OUT="$(run)"; assert_eq 0 "$?"; assert_contains "$OUT" $'supportsIpad\tunknown'
summary
