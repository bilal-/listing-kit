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
cp "$ROOT/tests/fixtures/shellbell/listing.new.json" "$T/plan-source"
mkdir -p "$T/.listing-kit"
python3 - "$T" <<'PY'
import json, sys
from pathlib import Path
p=Path(sys.argv[1])
d=json.loads((p/'plan-source').read_text())
d['platforms']={'supportsIphone': True, 'isUpdate': True}
(p/'.listing-kit/listing.json').write_text(json.dumps(d))
PY
OUT="$(LK_SUPPORTS_IPHONE=0 run)"; assert_contains "$OUT" $'supportsIphone\tyes\t.listing-kit/listing.json'
summary
