import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

AREA, KIT = map(Path, sys.argv[1:])
LIB = KIT / "scripts/lib"
sys.path.insert(0, str(LIB))
import plan

FIXTURES = KIT.parents[1] / "tests/fixtures/layouts"
CLI = KIT / "bin/listing-kit"
SCAN = LIB / "secret-scan.sh"
TOKEN = "sk_live_" + "z" * 30


class LayoutTest(unittest.TestCase):
    def setUp(self):
        self.root = Path(tempfile.mkdtemp(dir=AREA))
        self.run_cmd("git", "init", "-q")

    def run_cmd(self, *args, success=True):
        result = subprocess.run(args, cwd=self.root, stdout=subprocess.PIPE,
                                stderr=subprocess.STDOUT, text=True)
        if success:
            self.assertEqual(result.returncode, 0, result.stdout)
        else:
            self.assertNotEqual(result.returncode, 0, result.stdout)
        return result.stdout

    def write(self, path, text):
        dest = self.root / path
        dest.parent.mkdir(exist_ok=True, parents=True)
        dest.write_text(text)

    def fixture(self, name):
        shutil.copytree(FIXTURES / name, self.root, dirs_exist_ok=True)

    def listing(self, **extra):
        self.write(".listing-kit/listing.json", json.dumps(dict(
            format=2, app="org.example.app", locales=["en-US"], targets=[], screens=[], **extra)))

    def dirs(self):
        return [str(tree["fastlaneDir"]) for tree in plan.listing_trees(self.root).values()]

    def test_existing_content(self):
        self.fixture("root-listing-build-ios")
        self.assertEqual(self.dirs(), ["fastlane", "fastlane"])

    def test_play_only_root_and_build_only_ios(self):
        self.fixture("play-root-build-ios")
        self.assertEqual(self.dirs(), ["fastlane", "fastlane"])
        self.listing(trees={"apple": {"fastlaneDir": "ios/fastlane"}})
        self.assertEqual(self.dirs(), ["ios/fastlane", "fastlane"])

    def test_apple_only_root_and_build_only_android(self):
        self.fixture("apple-root-build-android")
        self.assertEqual(self.dirs(), ["fastlane", "fastlane"])

    def test_root_listing_in_workspace(self):
        self.fixture("monorepo-js")
        self.fixture("play-root-build-ios")
        # This package uses app.json as a directory. Root resolution should
        # finish before inspecting any child configuration.
        (self.root / "packages/shared/app.json").mkdir()
        self.assertEqual(self.dirs(), ["fastlane", "fastlane"])

    def test_native_listing_in_workspace(self):
        self.fixture("monorepo-js")
        self.write("ios/fastlane/screenshots/en-US/01.png", "screenshot")
        self.assertEqual(self.dirs(), ["ios/fastlane", "fastlane"])

    def test_child_needs_app_evidence(self):
        self.write("packages/data/app.json", '{"name":"data"}')
        self.write("packages/data/app.config.backup", "old config")
        self.write("packages/widgetbook/lib/main.dart", "void main() {}")
        self.write("packages/library/app/build.gradle", "plugins { id 'com.android.library' }")
        self.write("packages/sdk/SDK.xcodeproj/project.pbxproj", '{"objects":{}}')
        self.assertEqual(self.dirs(), ["fastlane", "fastlane"])

    def test_flutter_app_in_workspace(self):
        self.write("packages/client/pubspec.yaml", "name: client\ndependencies:\n  flutter:\n    sdk: flutter\n")
        self.write("packages/client/lib/main.dart", "void main() {}")
        output = self.run_cmd(CLI, "detect", ".", success=False)
        self.assertIn("packages/client", output)
        self.assertIn("trees", output)

    def test_disabled_android_plugins(self):
        self.write("gradle/libs.versions.toml", '[plugins]\nmobile = { id = "com.android.application" }')
        for plugin in ('id("com.android.application")', "id 'com.android.application'", 'alias(libs.plugins.mobile)'):
            for suffix in (' apply false', '.apply(false)', ' version("1").apply(false)',
                           '.version("1").apply(false)', ' version "1" apply false'):
                with self.subTest(plugin=plugin, suffix=suffix):
                    self.write("apps/aggregate/build.gradle.kts", "plugins { " + plugin + suffix + " }")
                    self.assertEqual(self.dirs(), ["fastlane", "fastlane"])

    def test_disabled_app_submodule(self):
        self.write("app/build.gradle.kts", 'plugins { id("com.android.application").apply(false) }')
        self.assertIn("stack\tunknown\n", self.run_cmd(CLI, "detect"))

    def test_catalog_stops_at_selected_workspace(self):
        self.write("gradle/libs.versions.toml", '[plugins]\nmobile = { id = "com.android.application" }')
        self.write("nested/apps/module/build.gradle.kts", "plugins { alias(libs.plugins.mobile) }")
        self.assertEqual(self.run_cmd(CLI, "detect", "nested").splitlines()[0], "stack\tunknown")

    def test_catalog_only_staged_change(self):
        catalog = "android/gradle/libs.versions.toml"

        def declare(kind):
            self.write(catalog, f'[plugins]\nandroid-application = {{ id = "com.android.{kind}" }}')

        declare("application")
        self.write("android/app/build.gradle.kts", "plugins { alias(libs.plugins.android.application) }")
        self.write("android/app/src/main/AndroidManifest.xml",
                   '<manifest xmlns:android="http://schemas.android.com/apk/res/android">'
                   '<uses-feature android:name="android.hardware.type.watch"/></manifest>')
        self.write("fastlane/metadata/android/en-US/title.txt", "Watch")
        self.write("listing-review.html", "old page")
        self.commit_fixture()

        declare("library")
        self.assertIn("hasWearOs\tunknown", self.run_cmd(CLI, "detect"))
        self.run_cmd("git", "add", catalog)
        declare("application")
        self.assertIn("hasWearOs\tyes", self.run_cmd(CLI, "detect"))
        self.assertIn("no Wear OS screenshots", self.run_cmd(CLI, "validate", success=False))
        self.run_cmd("bash", ".git/hooks/pre-commit")
        page = self.run_cmd("git", "show", ":listing-review.html")
        self.assertIn("Watch", page)
        self.assertNotIn("no Wear OS screenshots", page)

    def test_duplicate(self):
        self.fixture("duplicate-apple")
        with self.assertRaisesRegex(ValueError, r"fastlane.*ios/fastlane.*trees"):
            self.dirs()

    def test_store_ownership(self):
        self.fixture("android-lanes-only")
        self.assertEqual(self.dirs(), ["fastlane", "android/fastlane"])

    def test_play_graphics_are_not_screenshot_evidence(self):
        self.write("fastlane/metadata/android/en-US/images/icon.png", "icon")
        self.write("android/fastlane/metadata/android/en-US/images/phoneScreenshots/01.jpg", "shot")
        self.assertEqual(self.dirs(), ["fastlane", "android/fastlane"])

    def test_screenshots_win(self):
        self.write("ios/fastlane/screenshots/en-US/01.jpg", "image fixture")
        self.write("fastlane/metadata/android/en-US/images/phoneScreenshots/01.png", "image fixture")
        self.write("fastlane/Fastfile", "# root lanes")
        self.assertEqual(self.dirs(), ["ios/fastlane", "fastlane"])

    def test_libraries(self):
        self.fixture("flutter")
        self.write("packages/shared/package.json", '{"dependencies":{"react-native":"1"}}')
        self.assertEqual(self.dirs(), ["fastlane", "fastlane"])

    def test_explicit_workspace(self):
        self.fixture("monorepo-js")
        self.listing(trees={"apple":{"fastlaneDir":"itunes"}})
        self.assertEqual(self.dirs(), ["itunes", "fastlane"])
        self.assertIn("itunes", self.run_cmd(CLI, "detect", "."))

    def test_workspace_outside_apps(self):
        self.write("package.json", '{"workspaces":["mobile"]}')
        self.write("mobile/app.json", '{"expo":{}}')
        self.assertIn("mobile", self.run_cmd(CLI, "detect", ".", success=False))

    def test_reference_paths(self):
        for name in ("metadata/fastlane-layout.md", "stores/apple-app-store.md", "stores/google-play.md"):
            with self.subTest(name=name):
                self.assertIn("listing-kit detect", (KIT / "references" / name).read_text())

    def test_detect_paths(self):
        self.fixture("android-lanes-only")
        output = self.run_cmd(CLI, "detect", ".")
        for key, path in (("apple.fastlaneDir","fastlane"), ("apple.metadata","fastlane/metadata"),
                          ("apple.screenshots","fastlane/screenshots"), ("play.fastlaneDir","android/fastlane"),
                          ("play.metadata","android/fastlane/metadata/android"),
                          ("play.screenshots","android/fastlane/metadata/android")):
            self.assertIn(f"{key}\t{path}\n", output)

    def test_scan_default(self):
        self.write("ios/fastlane/metadata/en-US/name.txt", TOKEN)
        self.assertIn("POTENTIAL SECRET", self.run_cmd("bash", SCAN, success=False))

    def test_scan_staged_layout(self):
        self.listing(trees={"apple": {"metadata": "staged-copy"}})
        self.write("staged-copy/en-US/name.txt", TOKEN)
        self.run_cmd("git", "add", "-f", ".listing-kit/listing.json", "staged-copy")
        self.listing(trees={"apple": {"metadata": "working-copy"}})
        self.write("staged-copy/en-US/name.txt", "safe working copy")
        for args in ((), ("--listing", ".")):
            with self.subTest(args=args):
                output = self.run_cmd("bash", SCAN, *args, success=False)
                self.assertIn("POTENTIAL SECRET", output)
                self.assertNotIn(TOKEN, output)

    def test_scan_missing(self):
        self.run_cmd("bash", SCAN, "absent", success=False)

    def test_unknown_key_is_private(self):
        self.listing(**{"private customer identifier": "typo"})
        output = self.run_cmd(CLI, "plan", "manifest", ".", success=False)
        self.assertNotIn("private customer identifier", output)
        self.assertIn("unknown key", output)

    def test_unknown_platform_key_is_private(self):
        self.listing(platforms={"private customer identifier": False})
        output = self.run_cmd(CLI, "plan", "manifest", ".", success=False)
        self.assertNotIn("private customer identifier", output)
        self.assertIn("unknown condition", output)

    def test_locale_checker(self):
        self.listing(trees={"apple":{"metadata":"copy"}})
        self.write("copy/en-US/name.txt", "Name")
        output = self.run_cmd(sys.executable, LIB / "listing.py", "apple-locales", "--app-root", ".")
        self.assertIn("copy/en-US", output)

    def test_metadata_commands_require_app_root(self):
        self.write("ios/fastlane/metadata/en-US/name.txt", "Name")
        for script, args in (("fields.py", ["apple", "ios/fastlane/metadata/en-US"]),
                             ("listing.py", ["apple-locales", "ios/fastlane"])):
            with self.subTest(script=script):
                out = self.run_cmd(sys.executable, LIB / script, *args, success=False)
                self.assertIn("--app-root", out)
                self.assertIn("required", out)

    def test_legacy_locale_directory_with_explicit_app_root(self):
        self.write("legacy/lanes/metadata/en-US/name.txt", "Name")
        out = self.run_cmd(sys.executable, LIB / "listing.py", "apple-locales",
                           "legacy/lanes", "--app-root", ".")
        self.assertIn("legacy/lanes/metadata/en-US", out)

    def test_plan_secret(self):
        self.listing(**{TOKEN: "oops"})
        for args in ((CLI, "validate", "."), (CLI, "review", "."), ("bash", SCAN, "--listing", "."),
                     (CLI, "plan", "manifest", ".")):
            with self.subTest(command=args):
                output = self.run_cmd(*args, success=False)
                self.assertNotIn(TOKEN, output)
                self.assertIn("SECRET", output.upper())

    def test_filtered_review(self):
        self.fixture("root-listing-build-ios")
        self.listing(style={"logo":"repo:brand/logo.png"})
        self.write("brand/logo.png", "logo")
        self.write(".gitignore", ".listing-kit/local.json")
        self.write(".listing-kit/local.json", "{}")
        self.run_cmd(CLI, "review", ".")
        page = (self.root / "listing-review.html").read_text()
        self.assertIn("Root Apple", page)
        self.assertNotIn("repo: requires", page)

    def test_filtered_review_of_invalid_platform_plan(self):
        self.fixture("root-listing-build-ios")
        self.listing(platforms={"supportsIpad": "invalid"})
        self.write(".gitignore", ".listing-kit/local.json")
        self.write(".listing-kit/local.json", "{}")
        self.run_cmd(CLI, "review", ".")
        page = (self.root / "listing-review.html").read_text()
        self.assertIn("Root Apple", page)
        self.assertIn("platform overrides ignored", page)

    def test_symlinked_root_in_filtered_review(self):
        self.write("sources/metadata/en-US/name.txt", "Linked name")
        (self.root / "ios").mkdir()
        (self.root / "ios/fastlane").symlink_to("../sources")
        self.listing(trees={"apple": {"fastlaneDir": "ios/fastlane"}})
        self.write(".gitignore", ".listing-kit/local.json")
        self.write(".listing-kit/local.json", "{}")
        self.run_cmd(CLI, "review", ".")
        self.assertIn("Linked name", (self.root / "listing-review.html").read_text())

    def test_ci_filters(self):
        self.listing(trees={"apple":{"fastlaneDir":"ios/fastlane","metadata":"copy","screenshots":"shots"},
                            "play":{"fastlaneDir":"android/fastlane"}, "storeAssets":"art"})
        for provider, file, suffix in (("github",".github/workflows/listing.yml","/**"),
                                       ("gitlab",".gitlab-ci.yml","/**/*")):
            with self.subTest(provider=provider):
                self.run_cmd(CLI, "ci", "init", "--provider", provider, "--kit-ref", "v1")
                workflow = (self.root / file).read_text()
                for folder in ("ios/fastlane", "android/fastlane", "copy", "shots", "art", ".listing-kit"):
                    self.assertIn("'" + folder + suffix + "'", workflow)

    def test_field_checker(self):
        self.write(".listing-kit/specs.override.json", '{"stores":{"apple":{"fields":[{"stem":"subtitle","limit":31}]}}}')
        self.write("ios/fastlane/metadata/en-US/subtitle.txt", "ok")
        output = self.run_cmd(sys.executable, LIB / "fields.py", "apple", "ios/fastlane/metadata/en-US", "--app-root", ".")
        self.assertIn("subtitle: 2/31", output)

    def install(self):
        self.run_cmd("bash", KIT / "scripts/package/install-review-hook.sh", ".")

    def test_staged_custom_trigger(self):
        self.listing(trees={"apple":{"metadata":"ad-copy"}})
        self.run_cmd("git", "add", "-f", ".listing-kit/listing.json")
        self.run_cmd("git", "-c", "user.name=Test", "-c", "user.email=test@example.com", "commit", "-qm", "layout")
        self.install()
        self.write("ad-copy/en-US/name.txt", TOKEN)
        self.run_cmd("git", "add", "ad-copy")
        self.listing(trees={"apple":{"metadata":"unstaged"}})
        output = self.run_cmd("bash", ".git/hooks/pre-commit", success=False)
        self.assertIn("credential", output.lower())
        self.assertNotIn(TOKEN, output)

    def test_staged_config_scanned_before_layout_error(self):
        self.listing(trees={"apple": {"metadata": 12}})
        self.write(".listing-kit/notes.txt", TOKEN)
        self.run_cmd("git", "add", "-f", ".listing-kit")
        self.install()
        output = self.run_cmd("bash", ".git/hooks/pre-commit", success=False)
        self.assertIn("POTENTIAL SECRET", output)
        self.assertNotIn(TOKEN, output)

    def test_staged_play_screenshot_selects_native_without_fastfile(self):
        self.run_cmd("git", "config", "core.ignorecase", "true")
        self.write("android/fastlane/metadata/android/en-US/images/phoneScreenshots/01.png", TOKEN)
        self.run_cmd("git", "add", "android")
        self.install()
        self.assertIn("POTENTIAL SECRET", self.run_cmd("bash", ".git/hooks/pre-commit", success=False))

    def test_staged_native_scan(self):
        self.write("ios/fastlane/metadata/en-US/name.txt", TOKEN)
        self.write("app.json", '{"expo":{}}')
        self.run_cmd("git", "add", ".")
        self.write("ios/fastlane/metadata/en-US/name.txt", "clean")
        self.install()
        self.run_cmd("bash", ".git/hooks/pre-commit", success=False)

    def test_nested_config_listing_survives_refresh(self):
        self.listing(trees={"apple": {"metadata": ".listing-kit/copy"}})
        self.write(".listing-kit/copy/en-US/name.txt", "Nested listing")
        self.write("listing-review.html", "old page")
        self.run_cmd("git", "add", "-f", ".listing-kit", "listing-review.html")
        self.install()
        self.run_cmd("bash", ".git/hooks/pre-commit")
        self.assertIn("Nested listing", self.run_cmd("git", "show", ":listing-review.html"))
        self.run_cmd(CLI, "review", ".")

    def commit_fixture(self):
        self.run_cmd("git", "add", "-f", ".")
        self.run_cmd("git", "-c", "user.name=Test", "-c", "user.email=test@example.com", "commit", "-qm", "fixture")
        self.install()

    def test_workspace_hook_allows_unrelated_build_change(self):
        self.fixture("monorepo-js")
        self.commit_fixture()
        self.write("packages/tools/build.gradle", "// build configuration")
        self.run_cmd("git", "add", "packages/tools")
        self.run_cmd("git", "-c", "user.name=Test", "-c", "user.email=test@example.com",
                     "commit", "-qm", "edit tools")
        self.assertFalse((self.root / "listing-review.html").exists())

    def test_workspace_hook_refreshes_root_listing(self):
        self.fixture("monorepo-js")
        self.fixture("play-root-build-ios")
        self.commit_fixture()
        self.write("fastlane/metadata/android/en-US/title.txt", "Updated root title")
        self.run_cmd("git", "add", "fastlane")
        self.run_cmd("bash", ".git/hooks/pre-commit")
        self.assertIn("Updated root title", self.run_cmd("git", "show", ":listing-review.html"))

    def test_unselected_native_lane_does_not_refresh(self):
        self.listing(trees={"apple": {"fastlaneDir": "apple-lanes"}})
        self.write("apple-lanes/metadata/en-US/name.txt", "Metadata")
        self.write("listing-review.html", "previous review")
        self.commit_fixture()
        self.write("ios/fastlane/Fastfile", "# build only")
        self.run_cmd("git", "add", "ios")
        self.run_cmd("bash", ".git/hooks/pre-commit")
        self.assertEqual("previous review", self.run_cmd("git", "show", ":listing-review.html"))

    def test_page_removal_requires_a_staged_listing_deletion(self):
        self.write("listing-review.html", "previous review")
        self.commit_fixture()
        self.write("app.json", '{"expo": {}}')
        self.run_cmd("git", "add", "app.json")
        self.run_cmd("bash", ".git/hooks/pre-commit")
        self.assertEqual("previous review", self.run_cmd("git", "show", ":listing-review.html"))

    def test_last_native_listing_deletion_removes_page(self):
        self.write("ios/fastlane/metadata/en-US/name.txt", "Metadata")
        self.write("listing-review.html", "previous review")
        self.commit_fixture()
        self.run_cmd("git", "rm", "-r", "ios")
        self.run_cmd("bash", ".git/hooks/pre-commit")
        self.assertFalse((self.root / "listing-review.html").exists())
        self.assertEqual("", self.run_cmd("git", "ls-files", "listing-review.html"))

    def test_staged_refresh(self):
        self.fixture("android-lanes-only")
        self.write("android/fastlane/metadata/android/en-US/title.txt", "Indexed title")
        self.write("listing-review.html", "old page")
        self.run_cmd("git", "add", ".")
        self.write("fastlane/metadata/android/en-US/title.txt", "Unstaged title")
        self.install()
        self.run_cmd("bash", ".git/hooks/pre-commit")
        page = self.run_cmd("git", "show", ":listing-review.html")
        self.assertIn("Indexed title", page)
        self.assertNotIn("Unstaged title", page)
        self.assertEqual(page, (self.root / "listing-review.html").read_text())


if __name__ == "__main__":
    unittest.main(argv=sys.argv[:1], verbosity=2)
