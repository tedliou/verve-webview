#!/usr/bin/env python3
"""Black-box checks for the Godot Engine SDK Distribution."""

import hashlib
import io
import json
import pathlib
import sys
import zipfile


REQUIRED_PATHS = {
    "addons/verve_webview/plugin.cfg",
    "addons/verve_webview/plugin.gd",
    "addons/verve_webview/compatibility.json",
    "addons/verve_webview/content-manifest.json",
    "addons/verve_webview/export/android_export_plugin.gd",
    "addons/verve_webview/export/web_export_plugin.gd",
    "addons/verve_webview/bin/android/verve-webview-backend.aar",
    "addons/verve_webview/bin/android/verve-webview-godot.aar",
    "addons/verve_webview/bin/windows/verve_webview.gdextension",
    "addons/verve_webview/bin/windows/x86_64/verve_webview_windows.dll",
    "addons/verve_webview/bin/web/api-contract.js",
    "addons/verve_webview/bin/web/verve_webview_core.js",
    "addons/verve_webview/bin/web/verve_webview_core_bg.wasm",
    "addons/verve_webview/bin/web/verve_webview_core_facade.js",
    "addons/verve_webview/bin/web/verve_webview_web_backend.js",
    "ios/plugins/verve_webview/verve_webview.gdip",
    "ios/plugins/verve_webview/VerveWebViewIOS.debug.xcframework.zip",
    "ios/plugins/verve_webview/VerveWebViewIOS.release.xcframework.zip",
}


def digest(path: pathlib.Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main(arguments: list[str]) -> int:
    files = [pathlib.Path(value) for value in arguments]
    archives = [path for path in files if path.suffix == ".zip"]
    tree = next((path for path in files if path.is_dir()), None)
    if len(archives) != 1 or tree is None:
        raise AssertionError("Godot sdk must expose one ZIP and the verified tree")

    tree_paths = {
        path.relative_to(tree).as_posix()
        for path in tree.rglob("*")
        if path.is_file()
    }
    if not REQUIRED_PATHS.issubset(tree_paths):
        raise AssertionError(
            "missing Godot SDK entries: "
            + ", ".join(sorted(REQUIRED_PATHS - tree_paths))
        )
    roots = {path.split("/", 1)[0] for path in tree_paths}
    if roots != {"addons", "ios"}:
        raise AssertionError(f"Godot ZIP must have exactly dual roots: {roots}")

    manifest = json.loads(
        (tree / "addons/verve_webview/content-manifest.json").read_text(
            encoding="utf-8"
        )
    )
    declared = {entry["path"] for entry in manifest["entries"]}
    if tree_paths != declared | {"addons/verve_webview/content-manifest.json"}:
        raise AssertionError("Godot package tree and content manifest disagree")
    for entry in manifest["entries"]:
        path = tree / entry["path"]
        if path.stat().st_size != entry["size"] or digest(path) != entry["sha256"]:
            raise AssertionError("content digest mismatch: " + entry["path"])

    with zipfile.ZipFile(archives[0]) as bundle:
        archive_paths = {
            name for name in bundle.namelist() if not name.endswith("/")
        }
    if archive_paths != tree_paths:
        raise AssertionError("Godot ZIP differs from verified dual-root tree")

    compatibility = json.loads(
        (tree / "addons/verve_webview/compatibility.json").read_text(
            encoding="utf-8"
        )
    )
    supported = [
        item for item in compatibility["supported"] if item["engine"] == "godot"
    ]
    if len(supported) != 1:
        raise AssertionError("compatibility must declare one Godot support interval")
    if supported[0]["minimum_patch"] != "4.7.1" or supported[0][
        "maximum_patch"
    ] != "4.7.1":
        raise AssertionError("Godot compatibility must be pinned to 4.7.1")

    plugin_aar = tree / "addons/verve_webview/bin/android/verve-webview-godot.aar"
    with zipfile.ZipFile(plugin_aar) as bundle:
        manifest_text = bundle.read("AndroidManifest.xml").decode("utf-8")
        if "org.godotengine.plugin.v2.VerveWebView" not in manifest_text:
            raise AssertionError("Android wrapper is not a Godot v2 plugin")
        classes_bytes = bundle.read("classes.jar")
    with zipfile.ZipFile(io.BytesIO(classes_bytes)) as classes:
        expected_class = (
            "com/tedliou/verve/webview/godot/"
            "VerveWebViewGodotPlugin.class"
        )
        if expected_class not in classes.namelist():
            raise AssertionError("Android v2 init class is missing")

    for profile in ("debug", "release"):
        xcframework = (
            tree
            / "ios/plugins/verve_webview"
            / f"VerveWebViewIOS.{profile}.xcframework.zip"
        )
        with zipfile.ZipFile(xcframework) as bundle:
            names = bundle.namelist()
            if not any(name.endswith(".xcframework/Info.plist") for name in names):
                raise AssertionError(f"{profile} iOS XCFramework metadata is missing")
            if not any("ios-arm64" in name for name in names):
                raise AssertionError(f"{profile} iOS device slice is missing")
            if not any("ios-arm64_x86_64-simulator" in name for name in names):
                raise AssertionError(f"{profile} iOS simulator slices are missing")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main(sys.argv[1:]))
    except AssertionError as error:
        print(f"sdk_distribution_test: {error}", file=sys.stderr)
        raise SystemExit(1)
