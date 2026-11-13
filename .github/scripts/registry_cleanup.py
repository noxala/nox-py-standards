# .github/scripts/registry_cleanup.py
from __future__ import annotations

import argparse
from collections.abc import Callable
from dataclasses import dataclass
import json
import os
from pathlib import Path
import sys
import time
from typing import cast
from urllib.error import HTTPError
from urllib.parse import quote, unquote, urlencode, urlsplit
from urllib.request import HTTPRedirectHandler, Request, build_opener

from packaging.version import InvalidVersion, Version

PROJECT = "prj-noxala-org-bootstrap-e7b2"
ROOT = f"projects/{PROJECT}/locations/us-central1"
NUMBER_ROOT = "projects/1017858744225/locations/us-central1"
REGISTRY = ROOT + "/repositories/noxala-org-python"
REPOSITORIES = {
    "noxala/nox-tach": ("1447471939", "nox-tach"),
    "noxala/nox-py-common": ("1453226895", "nox-py-common"),
    "noxala/nox-py-standards": ("1447529132", "nox-py-standards"),
}
type Transport = Callable[[str, str, dict[str, str]], object]


class CleanupError(RuntimeError):
    pass


class ApiError(CleanupError):
    def __init__(self, status: int) -> None:
        super().__init__(f"Package cleanup API returned HTTP {status}")
        self.status = status


class NoRedirects(HTTPRedirectHandler):
    def redirect_request(self, *args: object, **kwargs: object) -> None:
        raise CleanupError("Refusing an API redirect")


def request(method: str, url: str, headers: dict[str, str]) -> object:
    if urlsplit(url).scheme != "https" or urlsplit(url).netloc not in {
        "api.github.com",
        "artifactregistry.googleapis.com",
    }:
        raise CleanupError("Unexpected cleanup API host")
    try:
        with build_opener(NoRedirects()).open(
            Request(url, method=method, headers=headers), timeout=30
        ) as response:
            return cast(object, json.load(response))
    except HTTPError as error:
        raise ApiError(error.code) from None


def mapping(value: object) -> dict[str, object]:
    if not isinstance(value, dict):
        raise CleanupError("Malformed API object")
    return cast(dict[str, object], value)


def sequence(value: object) -> list[object]:
    if not isinstance(value, list):
        raise CleanupError("Malformed API list")
    return cast(list[object], value)


def text(value: object) -> str:
    if not isinstance(value, str) or not value:
        raise CleanupError("Missing API string")
    return value


def normalize_tag(tag: str) -> str:
    if not tag.startswith("v"):
        raise CleanupError("Package release tags must start with v")
    try:
        return str(Version(tag[1:]))
    except InvalidVersion:
        raise CleanupError("Invalid package release version") from None


def validate_context(event: str, ref: str, payload: object) -> None:
    if event in {"schedule", "workflow_dispatch"} and ref == "refs/heads/master":
        return
    if event == "release" and mapping(payload).get("action") == "deleted":
        tag = text(mapping(mapping(payload).get("release")).get("tag_name"))
        normalize_tag(tag)
        if ref == "refs/tags/" + tag:
            return
    raise CleanupError(
        "Cleanup requires master scheduling/manual execution or a deleted release"
    )


@dataclass(frozen=True, slots=True, kw_only=True)
class Client:
    repository: str
    github_token: str
    google_token: str
    transport: Transport = request
    sleep: Callable[[float], None] = time.sleep

    @property
    def package(self) -> str:
        try:
            return REPOSITORIES[self.repository][1]
        except KeyError:
            raise CleanupError("Repository is not whitelisted for cleanup") from None

    def github(self, suffix: str) -> object:
        return self.transport(
            "GET",
            f"https://api.github.com/repos/{self.repository}{suffix}",
            {
                "Authorization": f"Bearer {self.github_token}",
                "Accept": "application/vnd.github+json",
                "X-GitHub-Api-Version": "2022-11-28",
            },
        )

    def google(self, method: str, name: str, query: str = "") -> object:
        return self.transport(
            method,
            "https://artifactregistry.googleapis.com/v1/" + name + query,
            {
                "Authorization": f"Bearer {self.google_token}",
                "X-Goog-User-Project": PROJECT,
            },
        )

    def releases(self) -> set[str]:
        # Push permission is needed to include drafts in GitHub's release list.
        # Never interpret a restricted or failed listing as deletion.
        if self.repository not in REPOSITORIES:
            raise CleanupError("Repository is not whitelisted for cleanup")
        expected_id = REPOSITORIES[self.repository][0]
        repo = mapping(self.github(""))
        if (
            str(repo.get("id")) != expected_id
            or str(mapping(repo.get("owner")).get("id")) != "320680816"
            or mapping(repo.get("permissions")).get("push") is not True
        ):
            raise CleanupError("Cannot verify repository identity and draft visibility")
        versions: set[str] = set()
        for page in range(1, 1001):
            entries = sequence(self.github(f"/releases?per_page=100&page={page}"))
            for entry in entries:
                tag = text(mapping(entry).get("tag_name"))
                if tag.startswith("v"):
                    versions.add(normalize_tag(tag))
            if len(entries) < 100:
                return versions
        raise CleanupError("Release listing exceeded the pagination limit")

    def versions(self) -> list[str]:
        prefix = f"{REGISTRY}/packages/{self.package}/versions/"
        number_prefix = (
            f"{NUMBER_ROOT}/repositories/noxala-org-python/"
            f"packages/{self.package}/versions/"
        )
        versions: list[str] = []
        tokens: set[str] = set()
        token = ""
        for _ in range(1000):
            try:
                page = mapping(
                    self.google(
                        "GET",
                        prefix.rstrip("/"),
                        "?"
                        + urlencode(
                            {
                                "pageSize": 100,
                                "pageToken": token,
                            }
                        ),
                    )
                )
            except ApiError as error:
                if error.status == 404 and not versions and not token:
                    return []
                raise
            for entry in sequence(page.get("versions", [])):
                name = text(mapping(entry).get("name"))
                matched = next(
                    (root for root in (prefix, number_prefix) if name.startswith(root)),
                    None,
                )
                if matched is None or "/" in name[len(matched) :]:
                    raise CleanupError("Registry returned another package's version")
                version = unquote(name[len(matched) :])
                if normalize_tag("v" + version) != version:
                    raise CleanupError("Registry version is not canonical")
                versions.append(version)
            raw_token = page.get("nextPageToken", "")
            if raw_token == "":
                return sorted(set(versions), key=Version)
            token = text(raw_token)
            if token in tokens:
                raise CleanupError("Registry repeated a pagination token")
            tokens.add(token)
        raise CleanupError("Registry listing exceeded the pagination limit")

    def candidates(self) -> list[str]:
        retained = self.releases()
        # Complete both inventories before proposing any mutation.
        return [version for version in self.versions() if version not in retained][:200]

    def delete(self, version: str) -> str:
        if normalize_tag("v" + version) != version:
            raise CleanupError("Refusing a noncanonical package version")
        # This job holds the same per-version concurrency group as publication.
        # Recheck GitHub after acquiring it: a release may have been recreated.
        if version in self.releases():
            return "retained"
        try:
            self.github("/releases/tags/" + quote("v" + version, safe=""))
        except ApiError as error:
            if error.status != 404:
                raise
        else:
            return "retained"
        name = f"{REGISTRY}/packages/{self.package}/versions/{quote(version, safe='')}"
        try:
            operation = mapping(self.google("DELETE", name))
        except ApiError as error:
            if error.status == 404:
                return "already absent"
            raise
        for _ in range(60):
            if "error" in operation:
                raise CleanupError("Registry version deletion failed")
            if operation.get("done") is True:
                return "deleted"
            operation_name = text(operation.get("name"))
            prefix = next(
                (
                    root + "/operations/"
                    for root in (ROOT, NUMBER_ROOT)
                    if operation_name.startswith(root + "/operations/")
                ),
                None,
            )
            if prefix is None or "/" in operation_name[len(prefix) :]:
                raise CleanupError("Unexpected registry operation name")
            self.sleep(2)
            operation = mapping(
                self.google(
                    "GET", prefix + quote(operation_name[len(prefix) :], safe="")
                )
            )
        raise CleanupError("Registry deletion did not finish before the timeout")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("command", choices=("normalize", "plan", "delete"))
    parser.add_argument("--tag", default="")
    parser.add_argument("--version", default="")
    options = parser.parse_args()
    try:
        if options.command == "normalize":
            sys.stdout.write(normalize_tag(options.tag) + "\n")
            return 0
        validate_context(
            os.environ["GITHUB_EVENT_NAME"],
            os.environ["GITHUB_REF"],
            json.loads(Path(os.environ["GITHUB_EVENT_PATH"]).read_text()),
        )
        client = Client(
            repository=os.environ["GITHUB_REPOSITORY"],
            github_token=os.environ["GITHUB_TOKEN"],
            google_token=os.environ["PACKAGE_CLEANUP_TOKEN"],
        )
        if options.command == "plan":
            versions = client.candidates()
            with Path(os.environ["GITHUB_OUTPUT"]).open("a") as output:
                output.write("versions=" + json.dumps(versions) + "\n")
            sys.stdout.write(f"Cleanup candidates for {client.package}: {versions}\n")
        else:
            result = client.delete(options.version)
            sys.stdout.write(f"{client.package} {options.version}: {result}\n")
        return 0
    except CleanupError as error:
        sys.stderr.write(
            f"Package cleanup failed: {error}. No further deletions were attempted.\n"
        )
        return 1
    except OSError, ValueError, KeyError:
        # API tokens and potentially private response bodies must never be logged.
        sys.stderr.write(
            "Package cleanup failed; no further deletions were attempted. "
            "Check API access and inventory validity.\n"
        )
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
