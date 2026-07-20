#!/usr/bin/env python3
"""Verify the representative distribution shapes without external packages."""

from __future__ import annotations

import hashlib
import json
import tarfile
import zipfile
from pathlib import Path


ROOT = Path(__file__).resolve().parent
OUTPUT = ROOT / "bazel-bin"


def require_members(actual: set[str], expected: set[str], artifact: str) -> None:
    missing = expected - actual
    if missing:
        raise SystemExit(f"{artifact} is missing: {sorted(missing)}")


def zip_members(name: str) -> set[str]:
    with zipfile.ZipFile(OUTPUT / name) as archive:
        return set(archive.namelist())


def tar_members(name: str) -> set[str]:
    with tarfile.open(OUTPUT / name) as archive:
        return set(archive.getnames())


def zip_content_digest(name: str) -> str:
    """Hash names and uncompressed bytes, intentionally excluding ZIP metadata."""
    digest = hashlib.sha256()
    with zipfile.ZipFile(OUTPUT / name) as archive:
        for member in sorted(info.filename for info in archive.infolist() if not info.is_dir()):
            digest.update(member.encode())
            digest.update(b"\0")
            digest.update(hashlib.sha256(archive.read(member)).digest())
    return digest.hexdigest()


aar = zip_members("verve-webview.aar")
require_members(aar, {"AndroidManifest.xml", "classes.jar"}, "Android AAR")
with zipfile.ZipFile(OUTPUT / "verve-webview.aar") as archive:
    manifest = archive.read("AndroidManifest.xml").decode()
if 'android:minSdkVersion="24"' not in manifest:
    raise SystemExit("Android AAR does not declare minSdk 24")

xcframework = zip_members("VerveWebView.xcframework.zip")
require_members(
    xcframework,
    {
        "VerveWebView.xcframework/Info.plist",
        "VerveWebView.xcframework/ios-arm64/libVerveWebView.a",
        "VerveWebView.xcframework/ios-arm64_x86_64-simulator/libVerveWebView.a",
    },
    "Apple XCFramework",
)

unity = tar_members("unity_package_tree.tar")
require_members(
    unity,
    {
        "package/package.json",
        "package/Runtime/Plugins/Android/verve-webview.aar",
        "package/Runtime/Plugins/iOS/libverve_webview_ios.a",
        "package/Runtime/Plugins/Windows/x86_64/verve_webview_windows.dll",
        "package/Runtime/Plugins/WebGL/verve_webview.jslib",
    },
    "Unity package tree",
)
with tarfile.open(OUTPUT / "unity_package_tree.tar") as archive:
    package_json_file = archive.extractfile("package/package.json")
    assert package_json_file is not None
    package_json = json.load(package_json_file)
if package_json["name"] != "com.tedliou.verve.webview":
    raise SystemExit("Unity package id drifted")
if package_json["unity"] != "2021.3":
    raise SystemExit("Unity compatibility baseline drifted")

godot = zip_members("verve-webview-godot.zip")
require_members(
    godot,
    {
        "addons/verve_webview/plugin.cfg",
        "addons/verve_webview/plugin.gd",
        "addons/verve_webview/bin/verve-webview.aar",
        "addons/verve_webview/bin/verve_webview.gdextension",
        "addons/verve_webview/bin/verve_webview.windows.x86_64.dll",
        "ios/plugins/verve_webview/verve_webview.gdip",
    },
    "Godot addon fragments",
)

for artifact in (
    "verve-webview.aar",
    "VerveWebView.xcframework.zip",
    "unity_package_tree.tar",
    "verve-webview-godot.zip",
):
    digest = hashlib.sha256((OUTPUT / artifact).read_bytes()).hexdigest()
    print(f"bytes={digest}  {artifact}")
    if artifact.endswith((".aar", ".zip")):
        print(f"contents={zip_content_digest(artifact)}  {artifact}")

print("Representative artifact shapes verified.")
