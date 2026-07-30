#!/usr/bin/env python3
"""Black-box checks for the public Unity Engine SDK Distribution outputs."""

import hashlib
import json
import pathlib
import sys
import tarfile
import tempfile
import zipfile


PACKAGE_ID = "com.tedliou.verve-webview"
REQUIRED_PATHS = {
    "package.json",
    "compatibility.json",
    "content-manifest.json",
    "Runtime/Verve.WebView.asmdef",
    "Runtime/Plugins/Android/verve-webview.aar",
    "Runtime/Plugins/iOS/VerveWebViewIOS.xcframework.zip",
    "Runtime/Plugins/Windows/x86_64/verve_webview_windows.dll",
    "Runtime/Plugins/WebGL/verve_webview.jslib",
    "Runtime/Web/Core/verve_webview_core.js",
    "Runtime/Web/Core/verve_webview_core_bg.wasm",
    "Runtime/Web/Core/verve_webview_core_facade.js",
    "Editor/Verve.WebView.Editor.asmdef",
    "Editor/WebBuildPostprocessor.cs",
}


def digest(path: pathlib.Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def normalized_tar_members(archive: pathlib.Path) -> set[str]:
    with tarfile.open(archive, "r:gz") as bundle:
        return {
            member.name.removeprefix("package/")
            for member in bundle.getmembers()
            if member.isfile()
        }


def normalized_zip_members(archive: pathlib.Path) -> set[str]:
    prefix = PACKAGE_ID + "/"
    with zipfile.ZipFile(archive) as bundle:
        names = {name for name in bundle.namelist() if not name.endswith("/")}
        if not names or any(not name.startswith(prefix) for name in names):
            raise AssertionError("Unity ZIP must contain exactly one package-id root")
        return {name.removeprefix(prefix) for name in names}


def main(arguments: list[str]) -> int:
    files = [pathlib.Path(value) for value in arguments]
    tgz = next((path for path in files if path.suffix == ".tgz"), None)
    zip_path = next((path for path in files if path.suffix == ".zip"), None)
    tree = next((path for path in files if path.is_dir()), None)
    if tgz is None or zip_path is None or tree is None:
        raise AssertionError("sdk must expose .tgz, .zip, and verified package tree")

    manifest_path = tree / "content-manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    tree_paths = {
        path.relative_to(tree).as_posix()
        for path in tree.rglob("*")
        if path.is_file()
    }
    declared_paths = {entry["path"] for entry in manifest["entries"]}

    if not REQUIRED_PATHS.issubset(tree_paths):
        raise AssertionError(
            "missing required package entries: "
            + ", ".join(sorted(REQUIRED_PATHS - tree_paths))
        )
    if tree_paths != declared_paths | {"content-manifest.json"}:
        raise AssertionError("package tree and content manifest disagree")
    for entry in manifest["entries"]:
        path = tree / entry["path"]
        if path.stat().st_size != entry["size"] or digest(path) != entry["sha256"]:
            raise AssertionError("content manifest digest mismatch: " + entry["path"])

    expected_archive_paths = tree_paths
    if normalized_tar_members(tgz) != expected_archive_paths:
        raise AssertionError("UPM .tgz differs from the verified package tree")
    if normalized_zip_members(zip_path) != expected_archive_paths:
        raise AssertionError("Unity ZIP differs from the verified package tree")

    package = json.loads((tree / "package.json").read_text(encoding="utf-8"))
    compatibility = json.loads(
        (tree / "compatibility.json").read_text(encoding="utf-8")
    )
    if package["name"] != PACKAGE_ID:
        raise AssertionError("formal UPM id is not stable")
    if package["version"] != compatibility["sdk_version"]:
        raise AssertionError("package and compatibility versions differ")
    asmdefs = list(tree.rglob("*.asmdef"))
    runtime_asmdefs = [
        path
        for path in asmdefs
        if json.loads(path.read_text(encoding="utf-8"))["name"] == "Verve.WebView"
    ]
    if len(runtime_asmdefs) != 1:
        raise AssertionError("distribution must expose exactly one runtime assembly")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main(sys.argv[1:]))
    except (AssertionError, StopIteration) as error:
        print(f"sdk_distribution_test: {error}", file=sys.stderr)
        raise SystemExit(1)
