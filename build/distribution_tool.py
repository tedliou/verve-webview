#!/usr/bin/env python3
"""Deterministic manifest and package-tree assembly for release fragments."""

import argparse
import hashlib
import json
import pathlib
import shutil


def sha256(path):
    digest = hashlib.sha256()
    with open(path, "rb") as source:
        for block in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def read_spec(path):
    entries = []
    for line in pathlib.Path(path).read_text(encoding="utf-8").splitlines():
        if not line:
            continue
        destination, source = line.split("\t", 1)
        entries.append((destination, pathlib.Path(source)))
    return entries


def manifest_entries(entries):
    return [
        {
            "path": destination,
            "sha256": sha256(source),
            "size": source.stat().st_size,
        }
        for destination, source in sorted(entries)
    ]


def write_json(path, value):
    pathlib.Path(path).write_text(
        json.dumps(value, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def fragment(arguments):
    entries = read_spec(arguments.spec)
    tree = pathlib.Path(arguments.tree)
    tree.mkdir(parents=True, exist_ok=True)
    for destination, source in sorted(entries):
        target = tree / destination
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, target)
    write_json(
        arguments.content,
        {"entries": manifest_entries(entries), "schema_version": 1},
    )
    write_json(
        arguments.provenance,
        {
            "architecture": arguments.architecture,
            "fragment_id": arguments.fragment_id,
            "platform": arguments.platform,
            "release_version": arguments.release_version,
            "schema_version": 1,
        },
    )

def verify(arguments):
    entries = read_spec(arguments.spec)
    expected = json.loads(pathlib.Path(arguments.content).read_text(encoding="utf-8"))
    if expected != {"entries": manifest_entries(entries), "schema_version": 1}:
        raise SystemExit("imported fragment content manifest verification failed")
    provenance = json.loads(pathlib.Path(arguments.provenance).read_text(encoding="utf-8"))
    required = {
        "architecture": arguments.architecture,
        "fragment_id": arguments.fragment_id,
        "platform": arguments.platform,
        "release_version": arguments.release_version,
        "schema_version": 1,
    }
    if provenance != required:
        raise SystemExit("imported fragment provenance verification failed")
    compatibility = json.loads(
        pathlib.Path(arguments.compatibility).read_text(encoding="utf-8")
    )
    if compatibility["sdk_version"] != arguments.release_version:
        raise SystemExit("imported fragment compatibility version mismatch")
    pathlib.Path(arguments.marker).write_text("verified\n", encoding="utf-8")


def merge(arguments):
    entries = read_spec(arguments.spec)
    compatibility = pathlib.Path(arguments.compatibility)
    compatibility_data = json.loads(compatibility.read_text(encoding="utf-8"))
    if compatibility_data["sdk_version"] != arguments.release_version:
        raise SystemExit("compatibility sdk_version differs from release_version")

    destinations = {destination.casefold(): destination for destination, _ in entries}
    metadata_root = "" if arguments.engine == "unity" else "addons/verve_webview/"
    compatibility_destination = metadata_root + "compatibility.json"
    manifest_destination = metadata_root + "content-manifest.json"
    for destination in (compatibility_destination, manifest_destination):
        if destination.casefold() in destinations:
            raise SystemExit("fragment must not install " + destination)
    entries.append((compatibility_destination, compatibility))

    if arguments.engine == "unity":
        try:
            package_json = next(
                source for destination, source in entries
                if destination == "package.json"
            )
        except StopIteration:
            raise SystemExit("Unity distribution requires package.json") from None
        package_data = json.loads(package_json.read_text(encoding="utf-8"))
        if package_data["version"] != arguments.release_version:
            raise SystemExit("package.json version differs from release_version")

    tree = pathlib.Path(arguments.tree)
    tree.mkdir(parents=True, exist_ok=True)
    for destination, source in sorted(entries):
        target = tree / destination
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, target)

    manifest = {"entries": manifest_entries(entries), "schema_version": 1}
    write_json(arguments.manifest, manifest)
    installed_manifest = tree / manifest_destination
    installed_manifest.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(arguments.manifest, installed_manifest)


def parser():
    root = argparse.ArgumentParser()
    commands = root.add_subparsers(dest="command", required=True)
    fragment_parser = commands.add_parser("fragment")
    fragment_parser.add_argument("--spec", required=True)
    fragment_parser.add_argument("--content", required=True)
    fragment_parser.add_argument("--tree", required=True)
    fragment_parser.add_argument("--provenance", required=True)
    fragment_parser.add_argument("--fragment-id", required=True)
    fragment_parser.add_argument("--platform", required=True)
    fragment_parser.add_argument("--architecture", required=True)
    fragment_parser.add_argument("--release-version", required=True)
    fragment_parser.set_defaults(handler=fragment)

    verify_parser = commands.add_parser("verify")
    verify_parser.add_argument("--spec", required=True)
    verify_parser.add_argument("--content", required=True)
    verify_parser.add_argument("--provenance", required=True)
    verify_parser.add_argument("--compatibility", required=True)
    verify_parser.add_argument("--marker", required=True)
    verify_parser.add_argument("--fragment-id", required=True)
    verify_parser.add_argument("--platform", required=True)
    verify_parser.add_argument("--architecture", required=True)
    verify_parser.add_argument("--release-version", required=True)
    verify_parser.set_defaults(handler=verify)

    merge_parser = commands.add_parser("merge")
    merge_parser.add_argument("--engine", choices=["unity", "godot"], required=True)
    merge_parser.add_argument("--spec", required=True)
    merge_parser.add_argument("--tree", required=True)
    merge_parser.add_argument("--manifest", required=True)
    merge_parser.add_argument("--compatibility", required=True)
    merge_parser.add_argument("--release-version", required=True)
    merge_parser.set_defaults(handler=merge)
    return root


if __name__ == "__main__":
    options = parser().parse_args()
    options.handler(options)
