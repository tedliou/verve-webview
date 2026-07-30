#!/usr/bin/env python3
"""Validate exact, fail-closed Release Evidence for one Release Candidate."""

import argparse
import hashlib
import json
import pathlib
import sys


ARTIFACT_IDS = {"unity.tgz", "unity.zip", "godot.zip"}


class EvidenceError(ValueError):
    """A release assertion was not proven."""


def read_json(path: pathlib.Path) -> object:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise EvidenceError(f"cannot read JSON {path}: {error}") from error


def sha256(path: pathlib.Path) -> str:
    digest = hashlib.sha256()
    try:
        with path.open("rb") as source:
            for block in iter(lambda: source.read(1024 * 1024), b""):
                digest.update(block)
    except OSError as error:
        raise EvidenceError(f"cannot read final artifact {path}: {error}") from error
    return digest.hexdigest()


def parse_artifacts(values: list[str]) -> dict[str, pathlib.Path]:
    artifacts: dict[str, pathlib.Path] = {}
    for value in values:
        artifact_id, separator, raw_path = value.partition("=")
        if not separator or artifact_id not in ARTIFACT_IDS or not raw_path:
            raise EvidenceError("artifact must be one of ID=PATH: " + value)
        if artifact_id in artifacts:
            raise EvidenceError("duplicate artifact id: " + artifact_id)
        artifacts[artifact_id] = pathlib.Path(raw_path)
    if set(artifacts) != ARTIFACT_IDS:
        raise EvidenceError(
            "exact candidate artifacts required: " + ", ".join(sorted(ARTIFACT_IDS))
        )
    return artifacts


def expected_digests(artifacts: dict[str, pathlib.Path]) -> dict[str, str]:
    return {artifact_id: sha256(path) for artifact_id, path in artifacts.items()}


def canonical_json(value: object) -> bytes:
    return json.dumps(
        value, ensure_ascii=True, separators=(",", ":"), sort_keys=True
    ).encode("utf-8")


def candidate_binding(
    path: pathlib.Path,
    compatibility_path: pathlib.Path,
    digests: dict[str, str],
) -> dict:
    manifest = read_json(path)
    required = {
        "schema_version",
        "candidate_id",
        "identity",
        "artifacts",
        "upm_package",
    }
    if set(manifest) != required or manifest.get("schema_version") != 1:
        raise EvidenceError("Release Candidate manifest shape is invalid")
    identity = manifest["identity"]
    if set(identity) != {
        "version",
        "channel",
        "source_sha",
        "compatibility_sha256",
        "artifact_sha256",
    }:
        raise EvidenceError("Release Candidate identity shape is invalid")
    expected_id = hashlib.sha256(canonical_json(identity)).hexdigest()
    if manifest["candidate_id"] != expected_id:
        raise EvidenceError("Release Candidate id differs from canonical identity")
    compatibility = read_json(compatibility_path)
    if identity["version"] != compatibility.get("sdk_version"):
        raise EvidenceError("Release Candidate version differs from compatibility")
    if identity["compatibility_sha256"] != sha256(compatibility_path):
        raise EvidenceError("Release Candidate compatibility digest mismatch")
    if identity["artifact_sha256"] != digests:
        raise EvidenceError("Release Candidate artifact digest mismatch")
    return {
        "candidate_id": manifest["candidate_id"],
        **identity,
    }


def required_environments(compatibility: dict) -> list[dict[str, str]]:
    environments = []
    profile_ids = [
        profile["id"] for profile in compatibility.get("verification_profiles", [])
    ]
    if len(profile_ids) != len(set(profile_ids)):
        raise EvidenceError("verification profile ids must be unique")
    for support in compatibility.get("supported", []):
        versions = {support["minimum_patch"], support["maximum_patch"]}
        for version in versions:
            for platform in support["platforms"]:
                profiles = [
                    profile
                    for profile in compatibility.get("verification_profiles", [])
                    if profile["platform"] == platform
                ]
                if not profiles:
                    raise EvidenceError(
                        "supported platform lacks verification profile: " + platform
                    )
                for profile in profiles:
                    environments.append(
                        {
                            "engine": support["engine"],
                            "engine_version": version,
                            "profile": profile["id"],
                            "platform": platform,
                            "architecture": profile["architecture"],
                            "os_requirement": profile["os_requirement"],
                            "runtime": profile["runtime"],
                        }
                    )
    return sorted(
        environments,
        key=lambda item: (
            item["engine"],
            item["engine_version"],
            item["profile"],
        ),
    )


def supported_combinations(compatibility: dict) -> set[tuple[str, str, str]]:
    return {
        (item["engine"], item["engine_version"], item["profile"])
        for item in required_environments(compatibility)
    }


def validate_evidence(
    evidence: dict,
    compatibility: dict,
    suites: dict,
    digests: dict[str, str],
    exact_candidate: dict | None = None,
) -> tuple[str, str, str]:
    required_top = {
        "schema_version",
        "candidate",
        "environment",
        "suite_version",
        "results",
    }
    if set(evidence) != required_top or evidence.get("schema_version") != 1:
        raise EvidenceError("Release Evidence top-level shape is invalid")

    candidate = evidence["candidate"]
    if exact_candidate is not None:
        if candidate != exact_candidate:
            raise EvidenceError("candidate identity mismatch")
    else:
        if candidate.get("sdk_version") != compatibility.get("sdk_version"):
            raise EvidenceError("Release Evidence SDK version differs from compatibility")
        declared_artifacts = candidate.get("artifacts", [])
        declared = {
            item.get("id"): item.get("sha256")
            for item in declared_artifacts
            if isinstance(item, dict)
        }
        if len(declared_artifacts) != 3 or set(declared) != ARTIFACT_IDS:
            raise EvidenceError("Release Evidence must bind the exact three artifacts")
        for artifact_id, expected in digests.items():
            if declared[artifact_id] != expected:
                raise EvidenceError("artifact digest mismatch: " + artifact_id)

    if evidence["suite_version"] != suites.get("suite_version"):
        raise EvidenceError("shared suite version mismatch")
    results = evidence["results"]
    by_suite = {}
    for result in results:
        suite = result.get("suite")
        if suite in by_suite:
            raise EvidenceError("duplicate suite result: " + str(suite))
        by_suite[suite] = result.get("result")
    for suite in suites.get("required_suites", []):
        if by_suite.get(suite) != "passed":
            raise EvidenceError("required suite is not passed: " + suite)

    environment = evidence["environment"]
    required_environment = {
        "engine",
        "engine_version",
        "profile",
        "platform",
        "architecture",
        "os",
        "toolchain",
        "runtime",
    }
    if set(environment) != required_environment:
        raise EvidenceError("Release Evidence environment shape is invalid")
    if (
        not environment["os"]
        or not environment["toolchain"]
        or not environment["runtime"]
    ):
        raise EvidenceError("exact OS, toolchain, and runtime evidence is required")
    runtime_name = environment["runtime"].get("name")
    runtime_version = environment["runtime"].get("version")
    if not runtime_name or not runtime_version or runtime_version == "unverified":
        raise EvidenceError("exact runtime version is required")
    if any(value == "unverified" for value in environment["toolchain"].values()):
        raise EvidenceError("exact toolchain versions are required")
    key = (
        environment["engine"],
        environment["engine_version"],
        environment["profile"],
    )
    if key not in supported_combinations(compatibility):
        raise EvidenceError("environment is not a declared support combination")
    requirement = next(
        item
        for item in required_environments(compatibility)
        if (
            item["engine"],
            item["engine_version"],
            item["profile"],
        )
        == key
    )
    actual_shape = (
        environment["platform"],
        environment["architecture"],
        runtime_name,
    )
    expected_shape = (
        requirement["platform"],
        requirement["architecture"],
        requirement["runtime"],
    )
    if actual_shape != expected_shape:
        raise EvidenceError("environment differs from its verification profile")
    return key


def verify_command(arguments: argparse.Namespace) -> None:
    artifacts = parse_artifacts(arguments.artifact)
    digests = expected_digests(artifacts)
    exact_candidate = (
        candidate_binding(
            pathlib.Path(arguments.candidate),
            pathlib.Path(arguments.compatibility),
            digests,
        )
        if arguments.candidate
        else None
    )
    validate_evidence(
        read_json(pathlib.Path(arguments.evidence)),
        read_json(pathlib.Path(arguments.compatibility)),
        read_json(pathlib.Path(arguments.suites)),
        digests,
        exact_candidate,
    )
    print("verified Release Evidence against exact final artifact digests")


def gate_command(arguments: argparse.Namespace) -> None:
    artifacts = parse_artifacts(arguments.artifact)
    compatibility = read_json(pathlib.Path(arguments.compatibility))
    suites = read_json(pathlib.Path(arguments.suites))
    digests = expected_digests(artifacts)
    exact_candidate = (
        candidate_binding(
            pathlib.Path(arguments.candidate),
            pathlib.Path(arguments.compatibility),
            digests,
        )
        if arguments.candidate
        else None
    )
    manifest = read_json(pathlib.Path(arguments.manifest))
    if set(manifest) != {"schema_version", "evidence"} or manifest["schema_version"] != 1:
        raise EvidenceError("Release Evidence manifest shape is invalid")
    proven = set()
    candidate_identity = None
    for raw_path in manifest["evidence"]:
        evidence = read_json(pathlib.Path(raw_path))
        key = validate_evidence(
            evidence, compatibility, suites, digests, exact_candidate
        )
        identity = canonical_json(evidence["candidate"])
        if candidate_identity is None:
            candidate_identity = identity
        elif identity != candidate_identity:
            raise EvidenceError("evidence refers to multiple Release Candidates")
        if key in proven:
            raise EvidenceError("duplicate successful Release Evidence: " + repr(key))
        proven.add(key)
    missing = supported_combinations(compatibility) - proven
    if missing:
        formatted = ", ".join("/".join(item) for item in sorted(missing))
        raise EvidenceError("missing successful Release Evidence: " + formatted)
    print("release gate passed for every declared support combination")


def plan_command(arguments: argparse.Namespace) -> None:
    compatibility = read_json(pathlib.Path(arguments.compatibility))
    suites = read_json(pathlib.Path(arguments.suites))
    environments = required_environments(compatibility)
    print(
        json.dumps(
            {
                "schema_version": 1,
                "sdk_version": compatibility["sdk_version"],
                "suite_version": suites["suite_version"],
                "required_suites": suites["required_suites"],
                "required_environments": environments,
            },
            indent=2,
            sort_keys=True,
        )
    )


def parse_key_values(values: list[str], label: str) -> dict[str, str]:
    parsed = {}
    for value in values:
        key, separator, item = value.partition("=")
        if not separator or not key or not item or key in parsed:
            raise EvidenceError(f"{label} must contain unique KEY=VALUE entries")
        parsed[key] = item
    if not parsed:
        raise EvidenceError(label + " must identify an exact environment")
    return parsed


def record_command(arguments: argparse.Namespace) -> None:
    compatibility = read_json(pathlib.Path(arguments.compatibility))
    suites = read_json(pathlib.Path(arguments.suites))
    artifacts = parse_artifacts(arguments.artifact)
    toolchain = parse_key_values(arguments.toolchain, "toolchain")
    runtime = parse_key_values(arguments.runtime, "runtime")
    environment_key = (
        arguments.engine,
        arguments.engine_version,
        arguments.profile,
    )
    if environment_key not in supported_combinations(compatibility):
        raise EvidenceError("cannot record an undeclared support combination")
    supplied_results = parse_key_values(arguments.result, "result")
    required_suites = suites["required_suites"]
    unknown = set(supplied_results) - set(required_suites)
    if unknown:
        raise EvidenceError("unknown shared suite: " + ", ".join(sorted(unknown)))
    if not set(supplied_results.values()) <= {"passed", "failed", "unverified"}:
        raise EvidenceError("suite result must be passed, failed, or unverified")
    digests = expected_digests(artifacts)
    exact_candidate = (
        candidate_binding(
            pathlib.Path(arguments.candidate),
            pathlib.Path(arguments.compatibility),
            digests,
        )
        if arguments.candidate
        else None
    )
    evidence = {
        "schema_version": 1,
        "candidate": exact_candidate
        or {
            "sdk_version": compatibility["sdk_version"],
            "artifacts": [
                {"id": artifact_id, "sha256": digests[artifact_id]}
                for artifact_id in sorted(digests)
            ],
        },
        "environment": {
            "engine": arguments.engine,
            "engine_version": arguments.engine_version,
            "profile": arguments.profile,
            "platform": arguments.platform,
            "architecture": arguments.architecture,
            "os": arguments.os,
            "toolchain": toolchain,
            "runtime": runtime,
        },
        "suite_version": suites["suite_version"],
        "results": [
            {
                "suite": suite,
                "result": supplied_results.get(suite, "unverified"),
            }
            for suite in required_suites
        ],
    }
    pathlib.Path(arguments.output).write_text(
        json.dumps(evidence, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print("recorded Release Evidence with fail-closed suite defaults")


def parser() -> argparse.ArgumentParser:
    root = argparse.ArgumentParser()
    commands = root.add_subparsers(dest="command", required=True)
    for name, handler in (("verify", verify_command), ("gate", gate_command)):
        command = commands.add_parser(name)
        if name == "verify":
            command.add_argument("--evidence", required=True)
        else:
            command.add_argument("--manifest", required=True)
        command.add_argument("--compatibility", required=True)
        command.add_argument("--suites", required=True)
        command.add_argument("--candidate")
        command.add_argument("--artifact", action="append", default=[])
        command.set_defaults(handler=handler)
    plan = commands.add_parser("plan")
    plan.add_argument("--compatibility", required=True)
    plan.add_argument("--suites", required=True)
    plan.set_defaults(handler=plan_command)
    record = commands.add_parser("record")
    record.add_argument("--output", required=True)
    record.add_argument("--compatibility", required=True)
    record.add_argument("--suites", required=True)
    record.add_argument("--candidate")
    record.add_argument("--engine", choices=["unity", "godot"], required=True)
    record.add_argument("--engine-version", required=True)
    record.add_argument("--profile", required=True)
    record.add_argument(
        "--platform",
        choices=["android", "ios", "windows", "web"],
        required=True,
    )
    record.add_argument("--architecture", required=True)
    record.add_argument("--os", required=True)
    record.add_argument("--toolchain", action="append", default=[])
    record.add_argument("--runtime", action="append", default=[])
    record.add_argument("--result", action="append", default=[])
    record.add_argument("--artifact", action="append", default=[])
    record.set_defaults(handler=record_command)
    return root


def main() -> int:
    arguments = parser().parse_args()
    try:
        arguments.handler(arguments)
    except (EvidenceError, KeyError, TypeError) as error:
        print(f"release_evidence: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
