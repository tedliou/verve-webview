#!/usr/bin/env python3
"""Create an explicit Bazel repository from downloaded cross-host fragments."""

import argparse
import json
import pathlib
import shutil


ARCHITECTURES = {
    "android": "arm64-v8a",
    "ios": "device-arm64_simulator-arm64-x86_64",
    "windows": "x86_64",
    "web": "wasm32",
}


def quoted(value):
    return json.dumps(value, ensure_ascii=True)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--downloads", required=True)
    parser.add_argument("--output", required=True)
    arguments = parser.parse_args()
    downloads = pathlib.Path(arguments.downloads)
    output = pathlib.Path(arguments.output)
    output.mkdir(parents=True, exist_ok=True)

    declarations = [
        'load("@verve_webview//build:module_rules.bzl", "fragment_import")',
        "",
        'package(default_visibility = ["//visibility:public"])',
        "",
    ]
    for platform in ("android", "ios", "windows", "web"):
        source = downloads / platform
        destination = output / platform
        if destination.exists():
            shutil.rmtree(destination)
        shutil.copytree(source, destination)
        manifest_path = destination / "content-manifest.json"
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        entries = {}
        for entry in manifest["entries"]:
            path = entry["path"]
            source_file = destination / "tree" / path
            if not source_file.is_file():
                raise SystemExit(f"{platform} fragment is missing {path}")
            entries[f"{platform}/tree/{path}"] = path

        declarations.extend(
            [
                "fragment_import(",
                f"    name = {quoted(platform)},",
                f"    architecture = {quoted(ARCHITECTURES[platform])},",
                '    compatibility = "@verve_webview//compatibility:compatibility.json",',
                f"    content_manifest = {quoted(platform + '/content-manifest.json')},",
                "    entries = {",
            ]
        )
        for source_path, install_path in sorted(entries.items()):
            declarations.append(
                f"        {quoted(source_path)}: {quoted(install_path)},"
            )
        declarations.extend(
            [
                "    },",
                f"    fragment_id = {quoted('binding_' + platform)},",
                f"    fragment_manifest = {quoted(platform + '/fragment-manifest.json')},",
                f"    platform = {quoted(platform)},",
                ")",
                "",
            ]
        )

    (output / "BUILD.bazel").write_text(
        "\n".join(declarations),
        encoding="utf-8",
    )


if __name__ == "__main__":
    main()
