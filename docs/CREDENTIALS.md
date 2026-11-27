# Store credentials

**UNVERIFIED against the consoles.** The role names, permissions for individual fields, key creation and revocation screens, and CI settings below were not tested in a live account. Use the linked vendor instructions for the current steps. Publishing is gated on a live test for each store.

## Choose the least access

**Apple.** Fastlane uses an App Store Connect API key to read and edit listing metadata and screenshots for an existing app version. For listing text and images, start with the Marketing role. Check each intended edit against Apple's role table. Prefer an individual key for a dedicated user with access to the one app. Individual keys inherit that user's access. A team key with the same role can reach multiple apps. Keep account administration, signing and release work with separate identities. [Apple role permissions](https://developer.apple.com/help/account/access/roles/) and [App Store Connect API keys](https://developer.apple.com/help/app-store-connect/get-started/app-store-connect-api/).

The Apple credential here is fastlane's API key JSON file. It contains the key ID, private signing key and the issuer ID for a team key. Follow fastlane's format for an individual key. The private key signs short-lived requests. The JSON file is a secret in its own right. [Fastlane API key format](https://docs.fastlane.tools/app-store-connect-api/).

**Google Play.** Fastlane uses a Google Cloud service account to authenticate to the Google Play Android Developer API. Enable that API. Give the service account access to the target app in Play Console. Use the app-level permissions to view app information and manage store presence for listing copy and graphics. Leave release tracks, financial data, user administration and other apps out of its grant. A Cloud project Owner role is unnecessary for the publishing identity. The downloaded service account JSON contains a private key. [Play Developer API setup](https://developers.google.com/android-publisher/getting_started) and [Play Console access and permissions](https://support.google.com/googleplay/android-developer/answer/9844686).

## Local use

Keep both credential files outside the checkout and outside synced project folders. Give only your user access to the directory and files. Set one of these environment variables to the absolute file path for the store you need.

| Store | Environment variable | Alternate field in `.listing-kit/local.json` |
| --- | --- | --- |
| Apple | `APP_STORE_CONNECT_API_KEY_PATH` | `fastlane.appleApiKeyPath` |
| Play | `SUPPLY_JSON_KEY` | `fastlane.playJsonKeyPath` |

The fields belong inside a JSON object named `fastlane`. Store only paths there. The environment variable overrides the saved path. Use `listing-kit fastlane setup --apple-api-key-path PATH` or `listing-kit fastlane setup --play-json-key-path PATH` to select a path explicitly. An explicit path takes precedence during setup. Store only the path. Never ask an agent to open, paste or print a store credential. Add `.listing-kit/local.json` to the app's `.gitignore`. Check with `git check-ignore .listing-kit/local.json` and confirm that `git ls-files -- .listing-kit/local.json` prints nothing. Never put key material in the app repo, plan, launcher or shell history.

For a demo login used during capture, have the user export a `MAESTRO_` variable in their shell or source it from git-ignored `.listing-kit/secrets.local`. Use the variable reference in the YAML. [Maestro flow example](../skills/listing-kit/references/driving/maestro.md#write-a-flow)

To scan the selected app’s resolved listing directories, run the installed skill’s `scripts/lib/secret-scan.sh --listing <app-root>`.

## CI use

Enter credentials yourself using the provider’s secure settings. Scope `APP_STORE_CONNECT_API_KEY_JSON` to `store-listing-apple` and `PLAY_SERVICE_ACCOUNT_JSON` to `store-listing-play`. On GitHub, store the complete JSON as an environment secret. On GitLab, use protected **File** variables with variable expansion disabled. The job prepares a private file for the selected store and gives fastlane its path. [CI setup and approvals](CI.md).

Store access alone does not enable uploads. Agents must never pass `--yes` to publish or set the maintainers' live-test switch, `LK_PUBLISH_UNVERIFIED`.

## Rotate or revoke

For a planned rotation, create a replacement key for the same scoped identity. Replace the local file or CI secret. Check authentication with a read-only operation against the intended app. Revoke the old Apple key or delete the old Google service account key. Remove old downloads and temporary copies. If the integration is retired, also remove the CI secret and the identity's store access. [Apple API key management](https://developer.apple.com/help/app-store-connect/get-started/app-store-connect-api/) and [Google service account key management](https://cloud.google.com/iam/docs/keys-create-delete).

## If a key was pasted into a chat, a log or a commit

1. Treat the key as exposed. Stop affected publish jobs. Revoke the Apple key or disable or delete the Google service account key immediately. If Google access tokens may still be active, follow Google's compromised credential guidance. [Apple API keys](https://developer.apple.com/help/app-store-connect/get-started/app-store-connect-api/) and [Google compromised credentials](https://cloud.google.com/docs/security/compromised-credentials).
2. Tell the store account owner and your security contact. Record the key ID, time and locations of exposure. Never include the private key in the report. Review store changes, access grants and available audit logs from that time onward.
3. Remove the exposed message or contact the chat administrator for deletion. Restrict access to affected logs. Delete the affected job logs, artifacts and caches. Ask recipients to remove downloaded copies.
4. For a commit, remove the file from tracking and ignore the private path. Coordinate a history cleanup with the repository owner. Include affected branches, tags, forks, pull requests and clones. Anyone with an old copy could still read it after a rewrite. [GitHub sensitive data removal](https://docs.github.com/en/authentication/keeping-your-account-and-data-secure/removing-sensitive-data-from-a-repository) and [GitLab repository cleanup](https://docs.gitlab.com/user/project/repository/repository_size/).
5. Create a fresh key with minimal access. Update each authorized consumer through its secret settings. Check read-only access before re-enabling the publish job.

## App Review demo account

Enter the demo username and password in App Store Connect. During an Apple pull, fastlane itself downloads both values into `review_information/demo_user.txt` and `review_information/demo_password.txt`. Setup and publish use the same download. The kit deletes both files as soon as the metadata download returns, before reading the listing or downloading screenshots.

The download runs inside a private `listing-kit-fastlane-*` folder in the system temporary directory (normally `$TMPDIR` or `/tmp`, with `/tmp` used if the temp directory is inside the repository). The kit removes the folder on exit, including when it is interrupted, terminated, or its terminal is closed (SIGINT, SIGTERM, SIGHUP, SIGQUIT). A hard kill such as SIGKILL during the download can leave both files there, because fastlane keeps running after the kit is gone. Delete the leftover `listing-kit-fastlane-*` folder.
