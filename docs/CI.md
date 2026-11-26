# Store listing CI

From a kit checkout, run `skills/listing-kit/bin/listing-kit link` to install the launcher. Follow its PATH hint. Then run the command from your app directory. In a monorepo, pass `--app-root 'apps/my app'` to select the listing. The generator writes CI files at the Git repository root. Outside Git it uses the app directory. App paths must be literal paths without CI expression or glob characters.

```sh
listing-kit ci init --provider github
listing-kit ci init --provider gitlab
```

Choose the command for your provider. Review and commit the generated file. GitHub uses `.github/workflows/listing.yml`. GitLab uses `.gitlab-ci.yml` for a new pipeline. If that file already exists, the generator writes `listing-kit.gitlab-ci.yml` and prints a one-line local include. Add it to your existing includes. Use `--force` to replace a generated destination. Projects with custom GitLab stages must make the `test` and `deploy` stages available or adapt the jobs.

## Validate a listing change

A pull request or merge request that changes `fastlane/**`, `store-assets/**` or `.listing-kit/**` under the app root triggers validation. The runner checks out the app, clones the kit into temporary storage and installs ImageMagick. It runs `listing-kit validate`, builds a fresh review page, and uploads `listing-review.html` for inspection. A validation failure still fails the job. Validation needs no store secrets. Capture and compose run locally. Commit the resulting listing assets before opening the request.

Both jobs fetch the ref recorded in the workflow. The default is the generating kit's version tag, such as `v0.5.0`. Use `--kit-ref <tag-or-full-commit-SHA>` to choose a tested revision. Confirm that the ref contains the CLI and the adapters you use. Regenerate and review the diff when upgrading. **UNVERIFIED:** The GitHub action pins are major tags. Replace the checkout and artifact action tags with reviewed full commit SHAs before release.

## Approve a publish

1. Create a protected environment named `store-listing`. Configure required reviewers and restrict which branches or tags may deploy. Where supported, prevent self-approval. The YAML names the environment. A maintainer must configure its protection rules separately. Check that your provider plan supports the required approval gate before adding keys. [GitHub deployment environments](https://docs.github.com/en/actions/how-tos/deploy/configure-and-manage-deployments/manage-environments) and [GitLab deployment approvals](https://docs.gitlab.com/ci/environments/deployment_approvals/).
2. Enter the selected store's complete JSON credential yourself. Use `APP_STORE_CONNECT_API_KEY_JSON` or `PLAY_SERVICE_ACCOUNT_JSON`. On GitHub, create environment secrets in `store-listing`. On GitLab, create protected **File** variables scoped to `store-listing`, with variable expansion disabled. GitLab supplies file paths to the job. Keep the keys out of general project variables and validation jobs. [GitHub Actions secrets](https://docs.github.com/en/actions/how-tos/write-workflows/choose-what-workflows-do/use-secrets) and [GitLab CI/CD variables](https://docs.gitlab.com/ci/variables/).
3. On GitHub, manually dispatch the workflow on the reviewed ref and choose `apple` or `play`. On GitLab, select the manual job for that store on a protected ref. The environment reviewer should check the commit, review page and workflow before approving the deployment. [GitHub manual workflows](https://docs.github.com/en/actions/how-tos/manage-workflow-runs/manually-run-a-workflow) and [GitLab protected environments](https://docs.gitlab.com/ci/environments/protected_environments/).

Publish uses fastlane 2.242.0. It creates a private temporary credential file outside the checkout, exports the selected store's file path and runs `listing-kit publish --store <store> --yes <app-root>`. It removes the temporary copy when the shell exits. The job collects `.listing-kit/publish.receipt.json` even after a failed publish. Inspect the receipt for the outcome of the attempt. GitLab treats each manual job as optional. Check the selected job’s status directly.

Publishing stays off for each store until its live test passes. With the adapter, the job reports that publishing to that store is disabled and directs you to the hand-upload folder. A build without the adapter prints `this command is not part of this build of listing-kit` and exits 3.

## Keeping keys away from your agent

An agent with a shell can read any file its user can read. A private file outside the repository and a git-ignored path protect against accidental commits. They still allow an agent running as you to read the file.

For strong protection, keep keys only in the CI secret store. Use a trusted, isolated runner. Restrict who can change the workflow, approve deployments or run jobs that receive secrets. Let the agent write the workflow using secret names. Enter the values yourself in the provider settings. Never give secret values to the agent in chat, a terminal command, an issue or a test fixture. [Credential access, rotation and incident response](CREDENTIALS.md).
