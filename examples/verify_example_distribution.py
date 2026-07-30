#!/usr/bin/env python3
"""Black-box installation checks for Example Apps and final SDK archives."""

import pathlib
import sys
import tarfile
import tempfile
import zipfile


def main(arguments: list[str]) -> int:
    engine, *raw_files = arguments
    files = [pathlib.Path(value) for value in raw_files]
    with tempfile.TemporaryDirectory() as directory:
        project = pathlib.Path(directory)
        if engine == "unity":
            archive = next(path for path in files if path.suffix == ".tgz")
            with tarfile.open(archive, "r:gz") as bundle:
                bundle.extractall(project / "Packages", filter="data")
            installed = project / "Packages/package"
            required = installed / "Runtime/WebView.cs"
        elif engine == "godot":
            archive = next(path for path in files if path.suffix == ".zip")
            with zipfile.ZipFile(archive) as bundle:
                bundle.extractall(project)
            installed = project / "addons/verve_webview"
            required = installed / "webview.gd"
        else:
            raise AssertionError("unknown Example App engine")
        if not required.is_file():
            raise AssertionError("final Engine SDK Distribution did not install")
        if not (installed / "compatibility.json").is_file():
            raise AssertionError("Example App installation lacks compatibility metadata")
        if not (installed / "content-manifest.json").is_file():
            raise AssertionError("Example App installation lacks content manifest")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main(sys.argv[1:]))
    except (AssertionError, StopIteration) as error:
        print(f"verify_example_distribution: {error}", file=sys.stderr)
        raise SystemExit(1)
