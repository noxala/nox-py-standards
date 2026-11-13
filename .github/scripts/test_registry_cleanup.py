# .github/scripts/test_registry_cleanup.py
from __future__ import annotations

from collections.abc import Sequence
from dataclasses import replace

import pytest
import registry_cleanup as cleanup

REPO: dict[str, object] = {
    "id": 1447471939,
    "owner": {"id": 320680816},
    "permissions": {"push": True},
}


class Queue:
    def __init__(self, responses: Sequence[object]) -> None:
        self.responses = list(responses)
        self.calls: list[tuple[str, str, dict[str, str]]] = []

    def request(self, method: str, url: str, headers: dict[str, str]) -> object:
        self.calls.append((method, url, headers))
        if not self.responses:
            raise AssertionError("Unexpected API request")
        result = self.responses.pop(0)
        if isinstance(result, Exception):
            raise result
        return result


def client(responses: Sequence[object]) -> tuple[cleanup.Client, Queue]:
    queue = Queue(responses)
    result = cleanup.Client(
        repository="noxala/nox-tach",
        github_token="github-test",
        google_token="google-test",
        transport=queue.request,
        sleep=lambda _: None,
    )
    return (result, queue)


def versions(*values: str) -> dict[str, object]:
    return {
        "versions": [
            {"name": cleanup.REGISTRY + "/packages/nox-tach/versions/" + value}
            for value in values
        ]
    }


def test_release_versions_include_drafts_prereleases_and_normalized_aliases() -> None:
    subject, queue = client(
        [
            REPO,
            [
                {"tag_name": "v1.0-rc1", "draft": True},
                {"tag_name": "v0.9.0", "prerelease": False},
                {"tag_name": "notes"},
            ],
            versions("1.0rc1", "0.9.0", "0.8.0"),
        ]
    )
    assert subject.candidates() == ["0.8.0"]
    assert all((method == "GET" for method, _, _ in queue.calls))


def test_both_inventories_are_paginated_before_any_cleanup() -> None:
    first = versions("0.8.0") | {"nextPageToken": "second"}
    subject, queue = client(
        [
            REPO,
            [{"tag_name": "v1.0.0"}] * 100,
            [{"tag_name": "v2.0.0", "draft": True}],
            first,
            versions("2.0.0", "1.0.0"),
        ]
    )
    assert subject.candidates() == ["0.8.0"]
    assert "page=2" in queue.calls[2][1]
    assert "pageToken=second" in queue.calls[4][1]


def test_unknown_repository_does_not_call_any_api() -> None:
    subject, queue = client([])
    with pytest.raises(cleanup.CleanupError):
        replace(subject, repository="noxala/other").candidates()
    assert queue.calls == []


def test_each_repository_can_only_target_its_own_package() -> None:
    for repository, (repository_id, package) in cleanup.REPOSITORIES.items():
        subject, queue = client(
            [
                REPO | {"id": int(repository_id)},
                [],
                cleanup.ApiError(404),
                {"done": True},
            ]
        )
        assert replace(subject, repository=repository).delete("0.8.0") == "deleted"
        assert queue.calls[3][1].endswith(f"/packages/{package}/versions/0.8.0")


def test_repository_identity_and_draft_visibility_are_required() -> None:
    changes: tuple[dict[str, object], ...] = (
        {"id": 1},
        {"owner": {"id": 1}},
        {"permissions": {}},
        {"permissions": {"push": False}},
    )
    for change in changes:
        subject, queue = client([REPO | change])
        with pytest.raises(cleanup.CleanupError):
            subject.candidates()
        assert len(queue.calls) == 1


def test_api_failures_cannot_be_interpreted_as_empty_releases() -> None:
    for status in (401, 403, 404, 429, 500):
        subject, queue = client([REPO, cleanup.ApiError(status)])
        with pytest.raises(cleanup.ApiError):
            subject.candidates()
        assert all((method == "GET" for method, _, _ in queue.calls))


def test_incomplete_release_and_registry_pages_abort() -> None:
    response_sets: tuple[list[object], ...] = (
        [REPO, [{"tag_name": "v1.0.0"}] * 100, cleanup.ApiError(500)],
        [
            REPO,
            [],
            versions("0.8.0") | {"nextPageToken": "later"},
            cleanup.ApiError(500),
        ],
    )
    for responses in response_sets:
        subject, queue = client(responses)
        with pytest.raises(cleanup.ApiError):
            subject.candidates()
        assert all((method == "GET" for method, _, _ in queue.calls))


def test_repeated_registry_page_token_aborts() -> None:
    page = versions("0.8.0") | {"nextPageToken": "same"}
    subject, _ = client([REPO, [], page, page])
    with pytest.raises(cleanup.CleanupError):
        subject.candidates()


def test_malformed_or_cross_package_versions_abort() -> None:
    for bad in (
        None,
        {"versions": "invalid"},
        versions("1.0-rc1"),
        versions("1.0/extra"),
        {"versions": [{"name": "projects/other/versions/1.0"}]},
    ):
        subject, _ = client([REPO, [], bad])
        with pytest.raises(cleanup.CleanupError):
            subject.candidates()


def test_missing_package_is_an_empty_inventory_but_permission_errors_fail() -> None:
    subject, _ = client([REPO, [], cleanup.ApiError(404)])
    assert subject.candidates() == []
    subject, _ = client([REPO, [], cleanup.ApiError(403)])
    with pytest.raises(cleanup.ApiError):
        subject.candidates()


def test_canonical_project_number_and_encoded_python_versions_are_supported() -> None:
    entry = {
        "versions": [
            {
                "name": cleanup.NUMBER_ROOT
                + "/repositories/noxala-org-python/packages/"
                + "nox-tach/versions/1.0%2Blocal"
            }
        ]
    }
    subject, _ = client([REPO, [], entry])
    assert subject.candidates() == ["1.0+local"]
    operation = cleanup.NUMBER_ROOT + "/operations/cleanup-123"
    subject, queue = client(
        [REPO, [], cleanup.ApiError(404), {"name": operation}, {"done": True}]
    )
    assert subject.delete("1.0+local") == "deleted"
    assert queue.calls[3][1].endswith("/versions/1.0%2Blocal")
    assert queue.calls[4][1].endswith(operation)


def test_recreated_release_is_preserved_under_version_lock() -> None:
    subject, queue = client(
        [REPO, [], versions("0.8.0"), REPO, [{"tag_name": "v0.8.0", "draft": True}]]
    )
    assert subject.candidates() == ["0.8.0"]
    assert subject.delete("0.8.0") == "retained"
    assert all((method == "GET" for method, _, _ in queue.calls))


def test_deletion_waits_for_the_operation_and_keeps_tokens_on_their_hosts() -> None:
    operation = cleanup.ROOT + "/operations/cleanup-123"
    subject, queue = client(
        [
            REPO,
            [],
            cleanup.ApiError(404),
            {"name": operation},
            {"name": operation, "done": True},
        ]
    )
    assert subject.delete("0.8.0") == "deleted"
    assert queue.calls[3][0] == "DELETE"
    assert queue.calls[3][1].endswith("/packages/nox-tach/versions/0.8.0")
    assert queue.calls[0][2]["Authorization"] == "Bearer github-test"
    assert queue.calls[3][2]["Authorization"] == "Bearer google-test"
    assert queue.calls[3][2]["X-Goog-User-Project"] == cleanup.PROJECT
    assert (
        queue.calls[4][1] == "https://artifactregistry.googleapis.com/v1/" + operation
    )


def test_already_absent_version_is_idempotent_but_denial_is_not() -> None:
    subject, _ = client([REPO, [], cleanup.ApiError(404), cleanup.ApiError(404)])
    assert subject.delete("0.8.0") == "already absent"
    subject, _ = client([REPO, [], cleanup.ApiError(404), cleanup.ApiError(403)])
    with pytest.raises(cleanup.ApiError):
        subject.delete("0.8.0")


def test_failed_or_unexpected_operations_do_not_report_success() -> None:
    for operation in (
        {"done": True, "error": {"code": 7}},
        {"name": "projects/other/locations/us/operations/123"},
    ):
        subject, _ = client([REPO, [], cleanup.ApiError(404), operation])
        with pytest.raises(cleanup.CleanupError):
            subject.delete("0.8.0")


def test_operation_timeout_is_a_failure() -> None:
    operation = {"name": cleanup.ROOT + "/operations/123"}
    subject, _ = client([REPO, [], cleanup.ApiError(404), *[operation] * 61])
    with pytest.raises(cleanup.CleanupError):
        subject.delete("0.8.0")


def test_invalid_delete_versions_cannot_reach_an_api() -> None:
    for version in ("../other", "1.0/extra", "1.0-rc1", "$(command)"):
        subject, queue = client([])
        with pytest.raises(cleanup.CleanupError):
            subject.delete(version)
        assert queue.calls == []


def test_exact_tag_check_preserves_a_release_added_during_pagination() -> None:
    subject, queue = client([REPO, [], {"tag_name": "v0.8.0", "draft": True}])
    assert subject.delete("0.8.0") == "retained"
    assert all((method == "GET" for method, _, _ in queue.calls))


def test_pep440_normalization_matches_publish_lock_keys() -> None:
    for tag, expected in (
        ("v1.0-rc1", "1.0rc1"),
        ("v1.0+ABC", "1.0+abc"),
        ("v1!2.0", "1!2.0"),
        ("v0.4.2", "0.4.2"),
    ):
        assert cleanup.normalize_tag(tag) == expected
    for tag in ("0.4.2", "v../other", "vnot-a-version"):
        with pytest.raises(cleanup.CleanupError):
            cleanup.normalize_tag(tag)


def test_unsafe_api_hosts_are_rejected_before_network_access() -> None:
    for url in (
        "https://evil.invalid/",
        "http://api.github.com/",
        "https://api.github.com@evil.invalid/",
    ):
        with pytest.raises(cleanup.CleanupError):
            cleanup.request("GET", url, {})


def test_cleanup_context_requires_master_or_actual_release_deletion() -> None:
    for event in ("schedule", "workflow_dispatch"):
        cleanup.validate_context(event, "refs/heads/master", {})
        with pytest.raises(cleanup.CleanupError):
            cleanup.validate_context(event, "refs/heads/feature", {})
    deleted: dict[str, object] = {
        "action": "deleted",
        "release": {"tag_name": "v0.4.2"},
    }
    cleanup.validate_context("release", "refs/tags/v0.4.2", deleted)
    for action in ("published", "edited", "unpublished", "created"):
        with pytest.raises(cleanup.CleanupError):
            cleanup.validate_context(
                "release", "refs/tags/v0.4.2", deleted | {"action": action}
            )
    for event, ref, payload in (
        ("release", "refs/tags/v0.4.3", deleted),
        ("release", "refs/tags/v0.4.2", {}),
        ("pull_request", "refs/heads/master", {}),
    ):
        with pytest.raises(cleanup.CleanupError):
            cleanup.validate_context(event, ref, payload)
