#!/usr/bin/env python3
"""Deterministic manifest and package-tree assembly for release fragments."""

import argparse
import hashlib
import json
import pathlib
import shutil
import zipfile


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


def expanded_entries(entries):
    expanded = []
    for destination, source in entries:
        if source.is_dir():
            for child in sorted(source.rglob("*")):
                if child.is_symlink():
                    raise SystemExit("distribution sources must not contain symbolic links")
                if child.is_file():
                    relative = child.relative_to(source).as_posix()
                    expanded.append((destination.rstrip("/") + "/" + relative, child))
        else:
            expanded.append((destination, source))
    return expanded


def manifest_entries(entries):
    return [
        {
            "path": destination,
            "sha256": sha256(source),
            "size": source.stat().st_size,
        }
        for destination, source in sorted(expanded_entries(entries))
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
    for destination, source in sorted(expanded_entries(entries)):
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
    for destination, source in sorted(expanded_entries(entries)):
        target = tree / destination
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, target)

    manifest = {"entries": manifest_entries(entries), "schema_version": 1}
    write_json(arguments.manifest, manifest)
    installed_manifest = tree / manifest_destination
    installed_manifest.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(arguments.manifest, installed_manifest)


def extract_zip(arguments):
    destination = pathlib.Path(arguments.tree)
    destination.mkdir(parents=True, exist_ok=True)
    strip_prefix = pathlib.PurePosixPath(arguments.strip_prefix)
    with zipfile.ZipFile(arguments.archive) as archive:
        for member in archive.infolist():
            path = pathlib.PurePosixPath(member.filename)
            if (
                path.is_absolute()
                or ".." in path.parts
                or member.is_dir()
                or member.filename.endswith("/")
            ):
                if path.is_absolute() or ".." in path.parts:
                    raise SystemExit("ZIP member escapes extraction root")
                continue
            if arguments.strip_prefix:
                try:
                    path = path.relative_to(strip_prefix)
                except ValueError:
                    raise SystemExit(
                        "ZIP member is outside required strip prefix"
                    ) from None
            target = destination.joinpath(*path.parts)
            target.parent.mkdir(parents=True, exist_ok=True)
            with archive.open(member) as source, target.open("wb") as output:
                shutil.copyfileobj(source, output)


def archive_zip(arguments):
    tree = pathlib.Path(arguments.tree)
    with zipfile.ZipFile(
        arguments.output,
        "w",
        compression=zipfile.ZIP_DEFLATED,
        compresslevel=9,
    ) as archive:
        for source in sorted(path for path in tree.rglob("*") if path.is_file()):
            relative = source.relative_to(tree).as_posix()
            info = zipfile.ZipInfo(relative, date_time=(1980, 1, 1, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            info.create_system = 3
            info.external_attr = 0o100644 << 16
            archive.writestr(info, source.read_bytes(), compresslevel=9)


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

    extract_parser = commands.add_parser("extract-zip")
    extract_parser.add_argument("--archive", required=True)
    extract_parser.add_argument("--tree", required=True)
    extract_parser.add_argument("--strip-prefix", default="")
    extract_parser.set_defaults(handler=extract_zip)

    archive_parser = commands.add_parser("archive-zip")
    archive_parser.add_argument("--tree", required=True)
    archive_parser.add_argument("--output", required=True)
    archive_parser.set_defaults(handler=archive_zip)
    return root


if __name__ == "__main__":
    options = parser().parse_args()
    options.handler(options)
