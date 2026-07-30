#!/usr/bin/env python3
"""Create, verify, and promote one immutable Verve WebView Release Candidate."""

from __future__ import annotations

import argparse
import base64
import hashlib
import json
import os
import pathlib
import re
import sys
import tarfile
import urllib.error
import urllib.parse
import urllib.request
import zipfile


ARTIFACT_IDS = {"unity.tgz", "unity.zip", "godot.zip"}
CHANNEL_PATTERNS = {
    "stable": re.compile(r"^[0-9]+\.[0-9]+\.[0-9]+$"),
    "prerelease": re.compile(r"^[0-9]+\.[0-9]+\.[0-9]+-pre\.[0-9]+$"),
    "experimental": re.compile(r"^[0-9]+\.[0-9]+\.[0-9]+-exp\.[0-9]+$"),
}
PROMOTION_BOUNDARIES = [
    "upm_commit",
    "draft_release",
    "release_assets",
    "source_tag",
    "upm_tag",
    "published_release",
    "upm_branch",
]
SHA256 = re.compile(r"^[0-9a-f]{64}$")
SOURCE_SHA = re.compile(r"^[0-9a-f]{40}$")


class ReleaseError(ValueError):
    """A release invariant was not proven."""


def sha256_bytes(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def sha256_file(path: pathlib.Path) -> str:
    digest = hashlib.sha256()
    try:
        with path.open("rb") as source:
            for block in iter(lambda: source.read(1024 * 1024), b""):
                digest.update(block)
    except OSError as error:
        raise ReleaseError(f"cannot read {path}: {error}") from error
    return digest.hexdigest()


def canonical_json(value: object) -> bytes:
    return json.dumps(
        value, ensure_ascii=True, separators=(",", ":"), sort_keys=True
    ).encode("utf-8")


def write_json(path: pathlib.Path, value: object) -> None:
    path.write_text(
        json.dumps(value, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def read_json(path: pathlib.Path) -> object:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise ReleaseError(f"cannot read JSON {path}: {error}") from error


def safe_relative_path(raw: str) -> pathlib.PurePosixPath:
    if (
        not raw
        or "\\" in raw
        or "\x00" in raw
        or raw.startswith("/")
        or (len(raw) > 1 and raw[1] == ":")
    ):
        raise ReleaseError("unsafe archive path: " + raw)
    path = pathlib.PurePosixPath(raw)
    if any(part in ("", ".", "..") for part in path.parts):
        raise ReleaseError("unsafe archive path: " + raw)
    return path


def checked_file_map(entries: list[tuple[str, bytes]]) -> dict[str, bytes]:
    result: dict[str, bytes] = {}
    folded: dict[str, str] = {}
    for raw_path, content in entries:
        path = safe_relative_path(raw_path).as_posix()
        key = path.casefold()
        if key in folded:
            raise ReleaseError(
                f"case-folded archive collision: {folded[key]} and {path}"
            )
        folded[key] = path
        result[path] = content
    return result


def read_zip(path: pathlib.Path, prefix: str = "") -> dict[str, bytes]:
    try:
        with zipfile.ZipFile(path) as archive:
            entries = []
            for member in archive.infolist():
                if member.is_dir():
                    continue
                raw = safe_relative_path(member.filename).as_posix()
                if prefix:
                    expected = prefix.rstrip("/") + "/"
                    if not raw.startswith(expected):
                        raise ReleaseError(
                            f"{path.name} entry is outside {prefix}: {raw}"
                        )
                    raw = raw[len(expected) :]
                mode = member.external_attr >> 16
                if mode and (mode & 0o170000) not in (0, 0o100000):
                    raise ReleaseError(f"{path.name} contains a non-file entry: {raw}")
                entries.append((raw, archive.read(member)))
    except (OSError, zipfile.BadZipFile) as error:
        raise ReleaseError(f"cannot inspect ZIP {path}: {error}") from error
    return checked_file_map(entries)


def read_tgz(path: pathlib.Path, prefix: str) -> dict[str, bytes]:
    try:
        with tarfile.open(path, "r:*") as archive:
            entries = []
            expected = prefix.rstrip("/") + "/"
            for member in archive.getmembers():
                if member.isdir():
                    continue
                raw = safe_relative_path(member.name).as_posix()
                if not member.isfile():
                    raise ReleaseError(f"{path.name} contains a non-file entry: {raw}")
                if not raw.startswith(expected):
                    raise ReleaseError(
                        f"{path.name} entry is outside {prefix}: {raw}"
                    )
                extracted = archive.extractfile(member)
                if extracted is None:
                    raise ReleaseError(f"cannot read archive member: {raw}")
                entries.append((raw[len(expected) :], extracted.read()))
    except (OSError, tarfile.TarError) as error:
        raise ReleaseError(f"cannot inspect TGZ {path}: {error}") from error
    return checked_file_map(entries)


def read_tree(root: pathlib.Path) -> dict[str, bytes]:
    if not root.is_dir():
        raise ReleaseError("UPM package tree is missing: " + str(root))
    entries = []
    for path in sorted(root.rglob("*")):
        if path.is_symlink():
            raise ReleaseError("UPM package tree contains a symlink: " + str(path))
        if path.is_file():
            entries.append((path.relative_to(root).as_posix(), path.read_bytes()))
    return checked_file_map(entries)


def verify_content_manifest(files: dict[str, bytes], manifest_path: str) -> None:
    if manifest_path not in files:
        raise ReleaseError("distribution lacks " + manifest_path)
    try:
        manifest = json.loads(files[manifest_path])
    except json.JSONDecodeError as error:
        raise ReleaseError(f"invalid {manifest_path}: {error}") from error
    expected_keys = {"entries", "schema_version"}
    if set(manifest) != expected_keys or manifest["schema_version"] != 1:
        raise ReleaseError("invalid content manifest shape: " + manifest_path)
    declared = {}
    for item in manifest["entries"]:
        if set(item) != {"path", "sha256", "size"}:
            raise ReleaseError("invalid content manifest entry: " + manifest_path)
        path = safe_relative_path(item["path"]).as_posix()
        if path in declared:
            raise ReleaseError("duplicate content manifest path: " + path)
        declared[path] = (item["sha256"], item["size"])
    actual = {
        name: (sha256_bytes(content), len(content))
        for name, content in files.items()
        if name != manifest_path
    }
    if declared != actual:
        raise ReleaseError("content manifest differs from final bytes: " + manifest_path)


def tree_descriptor(files: dict[str, bytes]) -> dict:
    entries = [
        {"path": path, "sha256": sha256_bytes(content), "size": len(content)}
        for path, content in sorted(files.items())
    ]
    return {
        "sha256": sha256_bytes(canonical_json(entries)),
        "entries": entries,
    }


def parse_artifacts(values: list[str], bundle: pathlib.Path) -> dict[str, pathlib.Path]:
    artifacts = {}
    for value in values:
        artifact_id, separator, name = value.partition("=")
        if not separator or artifact_id not in ARTIFACT_IDS or not name:
            raise ReleaseError("artifact must be one of ID=RELATIVE_PATH: " + value)
        if artifact_id in artifacts:
            raise ReleaseError("duplicate artifact id: " + artifact_id)
        relative = safe_relative_path(name)
        if len(relative.parts) != 1:
            raise ReleaseError("release artifact must be at bundle root: " + name)
        artifacts[artifact_id] = bundle / relative.as_posix()
    if set(artifacts) != ARTIFACT_IDS:
        raise ReleaseError("exact Unity TGZ/ZIP and Godot ZIP are required")
    for path in artifacts.values():
        if not path.is_file():
            raise ReleaseError("release artifact is missing: " + str(path))
    return artifacts


def parse_key_values(values: list[str], label: str) -> dict[str, str]:
    result = {}
    for value in values:
        key, separator, item = value.partition("=")
        if not separator or not key or not item or key in result:
            raise ReleaseError(f"{label} must contain unique KEY=VALUE entries")
        result[key] = item
    if not result:
        raise ReleaseError(label + " must identify the exact host environment")
    return dict(sorted(result.items()))


def fragment_values(
    fragment: pathlib.Path,
    compatibility_path: pathlib.Path,
    source_sha: str,
    toolchain: dict[str, str],
) -> dict:
    if not SOURCE_SHA.fullmatch(source_sha):
        raise ReleaseError("fragment source SHA must be a full lowercase SHA-1")
    tree = read_tree(fragment / "tree")
    content_path = fragment / "content-manifest.json"
    provenance_path = fragment / "fragment-manifest.json"
    content = read_json(content_path)
    provenance = read_json(provenance_path)
    if set(content) != {"entries", "schema_version"} or content["schema_version"] != 1:
        raise ReleaseError("fragment content manifest shape is invalid")
    payloads = [
        {"path": path, "sha256": sha256_bytes(data), "size": len(data)}
        for path, data in sorted(tree.items())
    ]
    if content["entries"] != payloads:
        raise ReleaseError("fragment payload differs from its content manifest")
    required_provenance = {
        "architecture",
        "fragment_id",
        "platform",
        "release_version",
        "schema_version",
    }
    if set(provenance) != required_provenance or provenance["schema_version"] != 1:
        raise ReleaseError("fragment Bazel provenance shape is invalid")
    compatibility = read_json(compatibility_path)
    if compatibility.get("sdk_version") != provenance["release_version"]:
        raise ReleaseError("fragment version differs from compatibility")
    if not toolchain:
        raise ReleaseError("fragment toolchain identity is required")
    return {
        "schema_version": 1,
        "fragment_id": provenance["fragment_id"],
        "platform": provenance["platform"],
        "architecture": provenance["architecture"],
        "version": provenance["release_version"],
        "source_sha": source_sha,
        "compatibility_sha256": sha256_file(compatibility_path),
        "content_manifest_sha256": sha256_file(content_path),
        "provenance_sha256": sha256_file(provenance_path),
        "toolchain": dict(sorted(toolchain.items())),
        "payloads": payloads,
    }


def fragment_record(arguments: argparse.Namespace) -> None:
    fragment = pathlib.Path(arguments.fragment)
    value = fragment_values(
        fragment,
        pathlib.Path(arguments.compatibility),
        arguments.source_sha,
        parse_key_values(arguments.toolchain, "toolchain"),
    )
    write_json(pathlib.Path(arguments.output), value)
    print("recorded checksummed fragment " + value["fragment_id"])


def fragment_verify(arguments: argparse.Namespace) -> None:
    fragment = pathlib.Path(arguments.fragment)
    envelope = read_json(fragment / "release-fragment.json")
    if not isinstance(envelope, dict) or set(envelope) != {
        "schema_version",
        "fragment_id",
        "platform",
        "architecture",
        "version",
        "source_sha",
        "compatibility_sha256",
        "content_manifest_sha256",
        "provenance_sha256",
        "toolchain",
        "payloads",
    }:
        raise ReleaseError("release fragment envelope shape is invalid")
    expected = fragment_values(
        fragment,
        pathlib.Path(arguments.compatibility),
        arguments.source_sha,
        envelope.get("toolchain", {}),
    )
    if envelope != expected:
        raise ReleaseError("release fragment envelope differs from payload bytes")
    print("verified checksummed fragment " + envelope["fragment_id"])


def verify_distributions(
    artifacts: dict[str, pathlib.Path],
    upm_tree: pathlib.Path,
    compatibility: bytes,
) -> dict:
    tree = read_tree(upm_tree)
    unity_tgz = read_tgz(artifacts["unity.tgz"], "package")
    unity_zip = read_zip(artifacts["unity.zip"], "com.tedliou.verve-webview")
    if tree != unity_tgz or tree != unity_zip:
        raise ReleaseError("Unity distributions differ from the verified UPM tree")
    verify_content_manifest(tree, "content-manifest.json")
    if tree.get("compatibility.json") != compatibility:
        raise ReleaseError("Unity embedded compatibility.json differs")

    godot = read_zip(artifacts["godot.zip"])
    godot_manifest = "addons/verve_webview/content-manifest.json"
    verify_content_manifest(godot, godot_manifest)
    if godot.get("addons/verve_webview/compatibility.json") != compatibility:
        raise ReleaseError("Godot embedded compatibility.json differs")
    return tree_descriptor(tree)


def validate_version_channel(version: str, channel: str) -> None:
    pattern = CHANNEL_PATTERNS.get(channel)
    if pattern is None or not pattern.fullmatch(version):
        raise ReleaseError(f"{version} is invalid for channel {channel}")


def artifact_records(artifacts: dict[str, pathlib.Path]) -> list[dict]:
    return [
        {
            "id": artifact_id,
            "name": path.name,
            "sha256": sha256_file(path),
            "size": path.stat().st_size,
        }
        for artifact_id, path in sorted(artifacts.items())
    ]


def expected_artifact_names(version: str) -> dict[str, str]:
    return {
        "unity.tgz": f"com.tedliou.verve-webview-{version}.tgz",
        "unity.zip": f"com.tedliou.verve-webview-{version}.zip",
        "godot.zip": f"verve-webview-godot-{version}.zip",
    }


def expected_sums(manifest: dict, compatibility_name: str = "compatibility.json") -> str:
    rows = [
        f"{item['sha256']}  {item['name']}"
        for item in sorted(manifest["artifacts"], key=lambda item: item["name"])
    ]
    rows.append(
        f"{manifest['identity']['compatibility_sha256']}  {compatibility_name}"
    )
    return "\n".join(rows) + "\n"


def candidate_create(arguments: argparse.Namespace) -> None:
    bundle = pathlib.Path(arguments.bundle).resolve()
    compatibility_path = pathlib.Path(arguments.compatibility).resolve()
    upm_tree = pathlib.Path(arguments.upm_tree).resolve()
    validate_version_channel(arguments.version, arguments.channel)
    if not SOURCE_SHA.fullmatch(arguments.source_sha):
        raise ReleaseError("source SHA must be a full lowercase SHA-1")
    compatibility = compatibility_path.read_bytes()
    compatibility_data = read_json(compatibility_path)
    if compatibility_data.get("sdk_version") != arguments.version:
        raise ReleaseError("compatibility SDK version differs from candidate version")
    artifacts = parse_artifacts(arguments.artifact, bundle)
    for artifact_id, expected_name in expected_artifact_names(
        arguments.version
    ).items():
        if artifacts[artifact_id].name != expected_name:
            raise ReleaseError(
                f"artifact filename for {artifact_id} must be {expected_name}"
            )
    upm = verify_distributions(artifacts, upm_tree, compatibility)
    records = artifact_records(artifacts)
    identity = {
        "version": arguments.version,
        "channel": arguments.channel,
        "source_sha": arguments.source_sha,
        "compatibility_sha256": sha256_bytes(compatibility),
        "artifact_sha256": {
            item["id"]: item["sha256"] for item in sorted(records, key=lambda x: x["id"])
        },
    }
    manifest = {
        "schema_version": 1,
        "candidate_id": sha256_bytes(canonical_json(identity)),
        "identity": identity,
        "artifacts": records,
        "upm_package": upm,
    }
    output = pathlib.Path(arguments.output)
    write_json(output, manifest)
    (bundle / "SHA256SUMS").write_text(expected_sums(manifest), encoding="utf-8")
    candidate_verify_values(output, bundle)
    print(manifest["candidate_id"])


def strict_candidate(manifest: object) -> dict:
    if not isinstance(manifest, dict):
        raise ReleaseError("candidate manifest must be an object")
    if set(manifest) != {
        "schema_version",
        "candidate_id",
        "identity",
        "artifacts",
        "upm_package",
    } or manifest.get("schema_version") != 1:
        raise ReleaseError("candidate manifest shape is invalid")
    identity = manifest["identity"]
    if set(identity) != {
        "version",
        "channel",
        "source_sha",
        "compatibility_sha256",
        "artifact_sha256",
    }:
        raise ReleaseError("candidate identity shape is invalid")
    validate_version_channel(identity["version"], identity["channel"])
    if not SOURCE_SHA.fullmatch(identity["source_sha"]):
        raise ReleaseError("candidate source SHA is invalid")
    if not SHA256.fullmatch(identity["compatibility_sha256"]):
        raise ReleaseError("candidate compatibility digest is invalid")
    if set(identity["artifact_sha256"]) != ARTIFACT_IDS:
        raise ReleaseError("candidate artifact identity is incomplete")
    expected_id = sha256_bytes(canonical_json(identity))
    if manifest["candidate_id"] != expected_id:
        raise ReleaseError("candidate ID differs from its canonical identity")
    return manifest


def candidate_verify_values(candidate_path: pathlib.Path, bundle: pathlib.Path) -> dict:
    manifest = strict_candidate(read_json(candidate_path))
    compatibility = bundle / "compatibility.json"
    if sha256_file(compatibility) != manifest["identity"]["compatibility_sha256"]:
        raise ReleaseError("compatibility digest mismatch")
    compatibility_data = read_json(compatibility)
    if compatibility_data.get("sdk_version") != manifest["identity"]["version"]:
        raise ReleaseError("compatibility SDK version differs from candidate")
    by_id = {}
    expected_names = expected_artifact_names(manifest["identity"]["version"])
    for item in manifest["artifacts"]:
        if set(item) != {"id", "name", "sha256", "size"}:
            raise ReleaseError("candidate artifact record shape is invalid")
        if item["id"] in by_id or item["id"] not in ARTIFACT_IDS:
            raise ReleaseError("candidate artifact records are invalid")
        if item["name"] != expected_names[item["id"]]:
            raise ReleaseError(
                f"artifact filename for {item['id']} must be {expected_names[item['id']]}"
            )
        path = bundle / safe_relative_path(item["name"]).as_posix()
        if path.parent != bundle:
            raise ReleaseError("candidate artifact is outside bundle root")
        if not path.is_file():
            raise ReleaseError("candidate artifact is missing: " + item["name"])
        actual = sha256_file(path)
        if actual != item["sha256"]:
            raise ReleaseError("artifact digest mismatch: " + item["id"])
        if path.stat().st_size != item["size"]:
            raise ReleaseError("artifact size mismatch: " + item["id"])
        if manifest["identity"]["artifact_sha256"][item["id"]] != actual:
            raise ReleaseError("artifact identity mismatch: " + item["id"])
        by_id[item["id"]] = path
    if set(by_id) != ARTIFACT_IDS:
        raise ReleaseError("candidate artifact records are incomplete")
    upm = verify_distributions(
        by_id,
        bundle / "upm-package",
        compatibility.read_bytes(),
    )
    if upm != manifest["upm_package"]:
        raise ReleaseError("UPM package descriptor differs from candidate")
    sums = bundle / "SHA256SUMS"
    if not sums.is_file() or sums.read_text(encoding="utf-8") != expected_sums(manifest):
        raise ReleaseError("SHA256SUMS differs from candidate final bytes")
    return manifest


def candidate_verify(arguments: argparse.Namespace) -> None:
    manifest = candidate_verify_values(
        pathlib.Path(arguments.candidate),
        pathlib.Path(arguments.bundle).resolve(),
    )
    print("verified Release Candidate " + manifest["candidate_id"])


def synthetic_upm_commit(manifest: dict) -> str:
    value = (
        manifest["candidate_id"]
        + "\0"
        + manifest["upm_package"]["sha256"]
    ).encode("ascii")
    return hashlib.sha1(value).hexdigest()


def release_assets(manifest: dict) -> dict[str, str]:
    assets = {item["name"]: item["sha256"] for item in manifest["artifacts"]}
    assets["compatibility.json"] = manifest["identity"]["compatibility_sha256"]
    return dict(sorted(assets.items()))


def durable_release_assets(manifest: dict, bundle: pathlib.Path) -> dict[str, str]:
    assets = release_assets(manifest)
    for name in ("candidate.json", "SHA256SUMS"):
        path = bundle / name
        if not path.is_file():
            raise ReleaseError("candidate bundle lacks durable asset: " + name)
        assets[name] = sha256_file(path)
    return dict(sorted(assets.items()))


def semver_key(version: str) -> tuple[int, int, int, int, int]:
    match = re.fullmatch(
        r"([0-9]+)\.([0-9]+)\.([0-9]+)(?:-(pre|exp)\.([0-9]+))?",
        version,
    )
    if not match:
        raise ReleaseError("invalid SDK version: " + version)
    major, minor, patch = (int(match.group(index)) for index in (1, 2, 3))
    kind = match.group(4)
    rank = 2 if kind is None else (1 if kind == "pre" else 0)
    number = int(match.group(5) or 0)
    return major, minor, patch, rank, number


def promotion_preflight(manifest: dict, state: dict, upm_commit: str) -> None:
    source_tag = state.get("source_tag")
    if source_tag is not None and source_tag != manifest["identity"]["source_sha"]:
        raise ReleaseError("conflicting immutable source tag")
    upm_tag = state.get("upm_tag")
    if upm_tag is not None and upm_tag != upm_commit:
        raise ReleaseError("conflicting immutable UPM tag")
    release = state.get("release")
    if release is not None:
        if (
            release.get("candidate_id") != manifest["candidate_id"]
            or release.get("assets") not in (None, {}, release_assets(manifest))
            or release.get("prerelease")
            != (manifest["identity"]["channel"] != "stable")
        ):
            raise ReleaseError("conflicting GitHub Release")
    if manifest["identity"]["channel"] == "stable" and state.get("latest_stable"):
        if semver_key(manifest["identity"]["version"]) < semver_key(
            state["latest_stable"]
        ):
            raise ReleaseError("stable promotion is not monotonic")
        if (
            manifest["identity"]["version"] == state["latest_stable"]
            and (
                state.get("source_tag") != manifest["identity"]["source_sha"]
                or state.get("upm_tag") != upm_commit
            )
        ):
            raise ReleaseError("existing stable version is not this exact candidate")
    if manifest["identity"]["version"] in state.get("withdrawn", {}):
        raise ReleaseError("a Withdrawn Release version cannot be promoted again")


def promotion_simulate(arguments: argparse.Namespace) -> None:
    manifest = strict_candidate(read_json(pathlib.Path(arguments.candidate)))
    state_path = pathlib.Path(arguments.state)
    state = read_json(state_path)
    if not isinstance(state, dict) or state.get("schema_version") != 1:
        raise ReleaseError("promotion state shape is invalid")
    upm_commit = synthetic_upm_commit(manifest)
    promotion_preflight(manifest, state, upm_commit)
    boundaries = list(PROMOTION_BOUNDARIES)
    if manifest["identity"]["channel"] != "stable":
        boundaries.remove("upm_branch")
    if arguments.stop_after and arguments.stop_after not in boundaries:
        raise ReleaseError("stop boundary does not apply to this channel")

    for boundary in boundaries:
        if boundary == "upm_commit":
            state["upm_commit"] = upm_commit
        elif boundary == "draft_release":
            release = state.setdefault(
                "release",
                {
                    "candidate_id": manifest["candidate_id"],
                    "draft": True,
                    "prerelease": manifest["identity"]["channel"] != "stable",
                    "assets": {},
                },
            )
            release.setdefault("assets", {})
        elif boundary == "release_assets":
            state["release"]["assets"] = release_assets(manifest)
        elif boundary == "source_tag":
            state["source_tag"] = manifest["identity"]["source_sha"]
        elif boundary == "upm_tag":
            state["upm_tag"] = upm_commit
        elif boundary == "published_release":
            state["release"]["draft"] = False
        elif boundary == "upm_branch":
            state["upm_branch"] = upm_commit
            state["latest_stable"] = manifest["identity"]["version"]
        state["last_boundary"] = boundary
        if arguments.stop_after == boundary:
            write_json(pathlib.Path(arguments.output), state)
            print("stopped after " + boundary)
            return
    state["status"] = "promoted"
    state["candidate_id"] = manifest["candidate_id"]
    write_json(pathlib.Path(arguments.output), state)
    print("promotion converged for " + manifest["candidate_id"])


class GitHubApi:
    """Minimal authenticated GitHub REST boundary used only by protected promotion."""

    def __init__(self, repository: str, token: str):
        if not re.fullmatch(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+", repository):
            raise ReleaseError("repository must be OWNER/NAME")
        if not token:
            raise ReleaseError("GITHUB_TOKEN is required for promotion")
        self.repository = repository
        self.token = token

    def request(
        self,
        method: str,
        path: str,
        payload: object | None = None,
        *,
        raw: bytes | None = None,
        accept: str = "application/vnd.github+json",
        base: str = "https://api.github.com",
        allow_missing: bool = False,
    ) -> object | bytes | None:
        url = base + path
        data = raw
        headers = {
            "Accept": accept,
            "Authorization": "Bearer " + self.token,
            "User-Agent": "verve-webview-release-promotion",
            "X-GitHub-Api-Version": "2026-03-10",
        }
        if payload is not None:
            data = canonical_json(payload)
            headers["Content-Type"] = "application/json"
        elif raw is not None:
            headers["Content-Type"] = "application/octet-stream"
        request = urllib.request.Request(
            url, data=data, headers=headers, method=method
        )
        try:
            with urllib.request.urlopen(request, timeout=120) as response:
                content = response.read()
                if accept == "application/octet-stream":
                    return content
                return json.loads(content) if content else None
        except urllib.error.HTTPError as error:
            if allow_missing and error.code == 404:
                return None
            detail = error.read().decode("utf-8", errors="replace")
            raise ReleaseError(
                f"GitHub API {method} {path} failed ({error.code}): {detail}"
            ) from error
        except urllib.error.URLError as error:
            raise ReleaseError(f"GitHub API {method} {path} failed: {error}") from error

    def repo_path(self, suffix: str) -> str:
        return f"/repos/{self.repository}{suffix}"

    def get_ref(self, ref: str) -> str | None:
        value = self.request(
            "GET",
            self.repo_path("/git/ref/" + urllib.parse.quote(ref, safe="/")),
            allow_missing=True,
        )
        return None if value is None else value["object"]["sha"]

    def create_ref(self, ref: str, sha: str) -> None:
        self.request(
            "POST",
            self.repo_path("/git/refs"),
            {"ref": "refs/" + ref, "sha": sha},
        )

    def update_ref_fast_forward(self, ref: str, sha: str) -> None:
        self.request(
            "PATCH",
            self.repo_path("/git/refs/" + urllib.parse.quote(ref, safe="/")),
            {"sha": sha, "force": False},
        )


def git_blob_sha(content: bytes) -> str:
    header = f"blob {len(content)}\0".encode("ascii")
    return hashlib.sha1(header + content).hexdigest()


def github_releases(api: GitHubApi) -> list[dict]:
    releases = api.request("GET", api.repo_path("/releases?per_page=100"))
    if not isinstance(releases, list):
        raise ReleaseError("GitHub Releases response is invalid")
    return releases


def release_candidate_marker(candidate_id: str) -> str:
    return f"<!-- verve-candidate:{candidate_id} -->"


def release_by_version(releases: list[dict], version: str) -> dict | None:
    matches = [item for item in releases if item.get("tag_name") == "v" + version]
    if len(matches) > 1:
        raise ReleaseError("conflicting duplicate GitHub Releases")
    return matches[0] if matches else None


def download_asset(api: GitHubApi, asset: dict) -> bytes:
    value = api.request(
        "GET",
        api.repo_path("/releases/assets/" + str(asset["id"])),
        accept="application/octet-stream",
    )
    if not isinstance(value, bytes):
        raise ReleaseError("GitHub Release asset download was not binary")
    return value


def verify_remote_assets(
    api: GitHubApi, release: dict, expected: dict[str, str]
) -> dict[str, dict]:
    assets = release.get("assets", [])
    by_name = {}
    for asset in assets:
        name = asset.get("name")
        if name in by_name:
            raise ReleaseError("conflicting duplicate Release asset: " + str(name))
        by_name[name] = asset
    unknown = set(by_name) - set(expected)
    if unknown:
        raise ReleaseError(
            "conflicting undeclared Release assets: " + ", ".join(sorted(unknown))
        )
    for name, asset in by_name.items():
        if sha256_bytes(download_asset(api, asset)) != expected[name]:
            raise ReleaseError("conflicting Release asset bytes: " + name)
    return by_name


def expected_upm_blobs(bundle: pathlib.Path) -> dict[str, str]:
    return {
        path: git_blob_sha(content)
        for path, content in read_tree(bundle / "upm-package").items()
    }


def remote_commit_matches_upm(
    api: GitHubApi, commit_sha: str, expected: dict[str, str]
) -> bool:
    commit = api.request(
        "GET", api.repo_path("/git/commits/" + commit_sha)
    )
    tree = api.request(
        "GET",
        api.repo_path("/git/trees/" + commit["tree"]["sha"] + "?recursive=1"),
    )
    if tree.get("truncated"):
        raise ReleaseError("UPM Git tree response was truncated")
    actual = {
        item["path"]: item["sha"]
        for item in tree["tree"]
        if item["type"] == "blob"
    }
    return actual == expected


def create_upm_commit(
    api: GitHubApi,
    bundle: pathlib.Path,
    version: str,
    parent: str,
) -> str:
    entries = []
    for path, content in sorted(read_tree(bundle / "upm-package").items()):
        blob = api.request(
            "POST",
            api.repo_path("/git/blobs"),
            {
                "content": base64.b64encode(content).decode("ascii"),
                "encoding": "base64",
            },
        )
        entries.append(
            {"path": path, "mode": "100644", "type": "blob", "sha": blob["sha"]}
        )
    tree = api.request(
        "POST",
        api.repo_path("/git/trees"),
        {"tree": entries},
    )
    identity = {
        "name": "Verve WebView Release Automation",
        "email": "release-automation@users.noreply.github.com",
        "date": "2000-01-01T00:00:00Z",
    }
    commit = api.request(
        "POST",
        api.repo_path("/git/commits"),
        {
            "message": "UPM package " + version,
            "tree": tree["sha"],
            "parents": [parent],
            "author": identity,
            "committer": identity,
        },
    )
    return commit["sha"]


def compare_remote_stable_versions(releases: list[dict], version: str) -> None:
    current = []
    for release in releases:
        tag = release.get("tag_name", "")
        if (
            not release.get("draft")
            and not release.get("prerelease")
            and tag.startswith("v")
            and CHANNEL_PATTERNS["stable"].fullmatch(tag[1:])
        ):
            current.append(tag[1:])
    if current and semver_key(version) < max(semver_key(item) for item in current):
        raise ReleaseError("stable promotion is not monotonic")


def actual_asset_paths(manifest: dict, bundle: pathlib.Path) -> dict[str, pathlib.Path]:
    result = {
        item["name"]: bundle / item["name"] for item in manifest["artifacts"]
    }
    result.update(
        {
            "compatibility.json": bundle / "compatibility.json",
            "candidate.json": bundle / "candidate.json",
            "SHA256SUMS": bundle / "SHA256SUMS",
        }
    )
    return dict(sorted(result.items()))


def upload_release_asset(
    api: GitHubApi, release_id: int, name: str, path: pathlib.Path
) -> None:
    query = urllib.parse.urlencode({"name": name})
    api.request(
        "POST",
        f"/repos/{api.repository}/releases/{release_id}/assets?{query}",
        raw=path.read_bytes(),
        base="https://uploads.github.com",
    )


def promotion_apply(arguments: argparse.Namespace) -> None:
    bundle = pathlib.Path(arguments.bundle).resolve()
    candidate_path = pathlib.Path(arguments.candidate).resolve()
    manifest = candidate_verify_values(candidate_path, bundle)
    api = GitHubApi(arguments.repository, os.environ.get("GITHUB_TOKEN", ""))
    version = manifest["identity"]["version"]
    channel = manifest["identity"]["channel"]
    expected_assets = durable_release_assets(manifest, bundle)
    paths = actual_asset_paths(manifest, bundle)
    source_ref = "tags/v" + version
    upm_tag_ref = "tags/upm-v" + version
    source_sha = api.get_ref(source_ref)
    if source_sha is not None and source_sha != manifest["identity"]["source_sha"]:
        raise ReleaseError("conflicting immutable source tag")
    upm_tag_sha = api.get_ref(upm_tag_ref)
    upm_blobs = expected_upm_blobs(bundle)
    if upm_tag_sha is not None and not remote_commit_matches_upm(
        api, upm_tag_sha, upm_blobs
    ):
        raise ReleaseError("conflicting immutable UPM tag")

    releases = github_releases(api)
    if channel == "stable":
        compare_remote_stable_versions(releases, version)
    release = release_by_version(releases, version)
    marker = release_candidate_marker(manifest["candidate_id"])
    if release is not None:
        if (
            marker not in release.get("body", "")
            or release.get("prerelease") != (channel != "stable")
        ):
            raise ReleaseError("conflicting GitHub Release")
        verify_remote_assets(api, release, expected_assets)

    upm_branch = api.get_ref("heads/upm")
    if upm_tag_sha is None:
        parent = upm_branch or manifest["identity"]["source_sha"]
        upm_commit = create_upm_commit(api, bundle, version, parent)
    else:
        upm_commit = upm_tag_sha

    if release is None:
        release = api.request(
            "POST",
            api.repo_path("/releases"),
            {
                "tag_name": "v" + version,
                "target_commitish": manifest["identity"]["source_sha"],
                "name": "Verve WebView " + version,
                "body": (
                    marker
                    + "\n\nCandidate identity: `"
                    + manifest["candidate_id"]
                    + "`\n"
                ),
                "draft": True,
                "prerelease": channel != "stable",
                "make_latest": "false" if channel != "stable" else "true",
            },
        )
    published = not release.get("draft")
    if published:
        if source_sha != manifest["identity"]["source_sha"] or upm_tag_sha != upm_commit:
            raise ReleaseError("published Release lacks exact immutable tags")
    else:
        present = verify_remote_assets(api, release, expected_assets)
        for name, path in paths.items():
            if name not in present:
                upload_release_asset(api, release["id"], name, path)
        release = api.request(
            "GET", api.repo_path("/releases/" + str(release["id"]))
        )
        verify_remote_assets(api, release, expected_assets)

        if source_sha is None:
            api.create_ref(source_ref, manifest["identity"]["source_sha"])
        if upm_tag_sha is None:
            api.create_ref(upm_tag_ref, upm_commit)
        api.request(
            "PATCH",
            api.repo_path("/releases/" + str(release["id"])),
            {"draft": False},
        )
    if channel == "stable":
        if upm_branch is None:
            api.create_ref("heads/upm", upm_commit)
        elif upm_branch != upm_commit:
            api.update_ref_fast_forward("heads/upm", upm_commit)

    final_source = api.get_ref(source_ref)
    final_upm_tag = api.get_ref(upm_tag_ref)
    final_upm_branch = api.get_ref("heads/upm")
    final_release = release_by_version(github_releases(api), version)
    verify_remote_assets(api, final_release, expected_assets)
    if (
        final_source != manifest["identity"]["source_sha"]
        or final_upm_tag != upm_commit
        or final_release.get("draft")
        or (channel == "stable" and final_upm_branch != upm_commit)
    ):
        raise ReleaseError("final promotion reconciliation did not converge")
    evidence = {
        "schema_version": 1,
        "candidate_id": manifest["candidate_id"],
        "repository": arguments.repository,
        "version": version,
        "channel": channel,
        "source_tag": final_source,
        "upm_tag": final_upm_tag,
        "upm_branch": final_upm_branch if channel == "stable" else None,
        "release_id": final_release["id"],
        "assets": expected_assets,
        "status": "promoted",
    }
    if arguments.output:
        write_json(pathlib.Path(arguments.output), evidence)
    summary = os.environ.get("GITHUB_STEP_SUMMARY")
    if summary:
        with pathlib.Path(summary).open("a", encoding="utf-8") as output:
            output.write(
                "## Release Promotion\n\n"
                f"- Candidate: `{manifest['candidate_id']}`\n"
                f"- Version: `{version}` ({channel})\n"
                f"- Source tag: `v{version}` → `{final_source}`\n"
                f"- UPM tag: `upm-v{version}` → `{final_upm_tag}`\n"
                "- Final reconciliation: exact\n"
            )
    print("promotion converged for " + manifest["candidate_id"])


def withdrawal_record(arguments: argparse.Namespace) -> None:
    state = read_json(pathlib.Path(arguments.state))
    if not isinstance(state, dict) or state.get("schema_version") != 1:
        raise ReleaseError("withdrawal state shape is invalid")
    release = state.get("release")
    if not release or release.get("draft") or state.get("status") != "promoted":
        raise ReleaseError("only a published Release can be withdrawn")
    if semver_key(arguments.corrective_version) <= semver_key(arguments.version):
        raise ReleaseError("corrective version must be newer than withdrawn version")
    if not arguments.reason.strip():
        raise ReleaseError("withdrawal requires an audit reason")
    withdrawn = state.setdefault("withdrawn", {})
    existing = withdrawn.get(arguments.version)
    record = {
        "corrective_version": arguments.corrective_version,
        "reason": arguments.reason,
    }
    if existing is not None and existing != record:
        raise ReleaseError("conflicting withdrawal record")
    withdrawn[arguments.version] = record
    release["withdrawn"] = True
    write_json(pathlib.Path(arguments.output), state)
    print("recorded immutable withdrawal for " + arguments.version)


def parser() -> argparse.ArgumentParser:
    root = argparse.ArgumentParser()
    commands = root.add_subparsers(dest="command", required=True)

    fragment = commands.add_parser("fragment")
    fragment_commands = fragment.add_subparsers(dest="fragment_command", required=True)
    fragment_record_parser = fragment_commands.add_parser("record")
    fragment_record_parser.add_argument("--fragment", required=True)
    fragment_record_parser.add_argument("--output", required=True)
    fragment_record_parser.add_argument("--source-sha", required=True)
    fragment_record_parser.add_argument("--compatibility", required=True)
    fragment_record_parser.add_argument("--toolchain", action="append", default=[])
    fragment_record_parser.set_defaults(handler=fragment_record)
    fragment_verify_parser = fragment_commands.add_parser("verify")
    fragment_verify_parser.add_argument("--fragment", required=True)
    fragment_verify_parser.add_argument("--source-sha", required=True)
    fragment_verify_parser.add_argument("--compatibility", required=True)
    fragment_verify_parser.set_defaults(handler=fragment_verify)

    candidate = commands.add_parser("candidate")
    candidate_commands = candidate.add_subparsers(dest="candidate_command", required=True)
    create = candidate_commands.add_parser("create")
    create.add_argument("--output", required=True)
    create.add_argument("--bundle", required=True)
    create.add_argument("--version", required=True)
    create.add_argument("--channel", choices=sorted(CHANNEL_PATTERNS), required=True)
    create.add_argument("--source-sha", required=True)
    create.add_argument("--compatibility", required=True)
    create.add_argument("--upm-tree", required=True)
    create.add_argument("--artifact", action="append", default=[])
    create.set_defaults(handler=candidate_create)
    verify = candidate_commands.add_parser("verify")
    verify.add_argument("--candidate", required=True)
    verify.add_argument("--bundle", required=True)
    verify.set_defaults(handler=candidate_verify)

    promotion = commands.add_parser("promotion")
    promotion_commands = promotion.add_subparsers(dest="promotion_command", required=True)
    simulate = promotion_commands.add_parser("simulate")
    simulate.add_argument("--candidate", required=True)
    simulate.add_argument("--state", required=True)
    simulate.add_argument("--output", required=True)
    simulate.add_argument("--stop-after", choices=PROMOTION_BOUNDARIES)
    simulate.set_defaults(handler=promotion_simulate)
    apply = promotion_commands.add_parser("apply")
    apply.add_argument("--candidate", required=True)
    apply.add_argument("--bundle", required=True)
    apply.add_argument("--repository", required=True)
    apply.add_argument("--output")
    apply.set_defaults(handler=promotion_apply)

    withdrawal = commands.add_parser("withdrawal")
    withdrawal_commands = withdrawal.add_subparsers(
        dest="withdrawal_command", required=True
    )
    record = withdrawal_commands.add_parser("record")
    record.add_argument("--state", required=True)
    record.add_argument("--version", required=True)
    record.add_argument("--corrective-version", required=True)
    record.add_argument("--reason", required=True)
    record.add_argument("--output", required=True)
    record.set_defaults(handler=withdrawal_record)
    return root


def main() -> int:
    arguments = parser().parse_args()
    try:
        arguments.handler(arguments)
    except (ReleaseError, KeyError, TypeError, OSError) as error:
        print("release_tool: " + str(error), file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
