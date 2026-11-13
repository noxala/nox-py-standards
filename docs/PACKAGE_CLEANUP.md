# Private package cleanup

Deleting a GitHub release makes its matching private package version eligible for
deletion. This is intentional removal, including versions still pinned by other
repositories: those consumers must move to a retained version. An existing
release, including a draft or prerelease, preserves its package version.
Keeping a Git tag without a GitHub release does not preserve the package.

## Automatic cleanup

The release caller invokes [reconciliation](../.github/workflows/prune-python.yml)
on the `deleted` release activity. It calls the workflow from protected `master`,
which checks the actual event activity before any deletion. Publication still
runs only on `published` or an explicit manual backfill.

GitHub loads release-event callers from the tagged commit. Older tags may lack
the deletion hook, so a daily run from `master` also reconciles the registry with
GitHub. Existing tags do not need to move. The daily fallback also handles old
orphans and deletion of draft releases, which do not emit the release activity.

The helper paginates both inventories and compares normalized PEP 440 versions.
It only proposes versions of this repository's whitelisted package. Failed or
restricted GitHub reads are errors, never evidence that releases were deleted.
The GitHub token has Contents write permission so drafts are visible; the helper
uses only GitHub GET requests and never edits releases, tags or repository files.

Each deletion acquires `package-version-<canonical version>`, the same concurrency
group as the private publisher. These groups use `queue: max` to retain pending
publication and cleanup jobs ([GitHub queue semantics](https://docs.github.com/en/actions/how-tos/write-workflows/choose-when-workflows-run/control-workflow-concurrency)). After acquiring it, cleanup rechecks releases and
the exact version tag before deleting. Recreated releases are retained. Registry
deletion waits for the operation to finish; already absent versions are harmless
on retries. Failures stop the affected job; completed deletions stay completed.
Batches contain at most 200 versions, with remaining orphans handled by later runs.

## Manual preview and retry

Open **Actions → Reconcile private package versions → Run workflow** and select
`master`. Leave **dry_run** checked to list candidates without deleting them.
Uncheck it to reconcile immediately. Preview and deletion use the same inventory
rules; every deletion rechecks the release instead of trusting a saved preview.

## Access and rollout

The organization [registry contract](https://github.com/noxala/gcp-infrastructure/blob/master/docs/PYTHON_PACKAGES.md)
must include and apply the separate `cleanup` federation provider and custom
version-cleanup role. It admits only this repository's protected reconciliation
workflow, or its exact release caller using that workflow from `master`.
Ordinary readers and publishers do not receive delete permission.

The cleanup role permits version listing, metadata reads and version deletion on
the shared registry. The protected script fixes the package target using the
repository's identity; package isolation is enforced there rather than by a
package-specific IAM role. No key or credential file is created.

Merge the package and infrastructure changes, apply the reviewed organization
Terraform plan, and run a manual preview to verify effective access. Once active,
automatic runs also remove existing orphan versions; there is no age-based expiry.
Workflow tests and executable cloud-policy tests use synthetic data and never
delete a real package. Live preview/deletion acceptance follows the cloud apply.
