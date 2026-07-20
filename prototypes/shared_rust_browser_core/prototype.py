#!/usr/bin/env python3
"""PROTOTYPE ONLY: build, stage, export, and inspect the browser Core proof."""

from __future__ import annotations

import argparse
import hashlib
import os
from pathlib import Path
import shutil
import subprocess
import sys


ROOT = Path(__file__).resolve().parent
BUNDLE_NAMES = (
    "verve_webview_core.js",
    "verve_webview_core_bg.wasm",
    "verve_webview_core_facade.js",
)


def run(command: list[str], cwd: Path = ROOT) -> None:
    print("+", " ".join(command), flush=True)
    subprocess.run(command, cwd=cwd, check=True)


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def build_core(bazel: str) -> Path:
    # Batch mode avoids a long-lived gRPC server, which is unnecessary for this
    # one-shot proof and brittle in restricted WSL/CI environments.
    run([bazel, "--batch", "build", ":core_bindgen"])
    output = ROOT / "bazel-bin" / "core_bindgen"
    for name in BUNDLE_NAMES[:2]:
        if not (output / name).is_file():
            raise SystemExit(f"Bazel did not produce {output / name}")
    return output


def stage_bundle(bindgen_output: Path) -> dict[str, str]:
    sources = {
        BUNDLE_NAMES[0]: bindgen_output / BUNDLE_NAMES[0],
        BUNDLE_NAMES[1]: bindgen_output / BUNDLE_NAMES[1],
        BUNDLE_NAMES[2]: ROOT / "browser" / BUNDLE_NAMES[2],
    }
    destinations = (
        ROOT / "unity" / "package" / "Runtime" / "Web" / "Core",
        ROOT / "godot" / "project" / "addons" / "verve_webview" / "web",
    )
    for destination in destinations:
        destination.mkdir(parents=True, exist_ok=True)
        for name, source in sources.items():
            staged = destination / name
            # Bazel outputs are read-only. Do not propagate that mode into the
            # package/addon staging directories or a second run cannot refresh
            # the bundle.
            staged.unlink(missing_ok=True)
            shutil.copyfile(source, staged)

    digests = {name: sha256(source) for name, source in sources.items()}
    for destination in destinations:
        for name, expected in digests.items():
            actual = sha256(destination / name)
            if actual != expected:
                raise SystemExit(f"Staging changed {name}: {actual} != {expected}")
    return digests


def engine_path(path: Path, executable: str) -> str:
    if executable.lower().endswith(".exe") and shutil.which("wslpath"):
        return subprocess.check_output(["wslpath", "-w", str(path)], text=True).strip()
    return str(path)


def build_unity(executable: str, workspace: Path | None) -> Path:
    unity_root = ROOT / "unity"
    if executable.lower().endswith(".exe"):
        if workspace is None:
            raise SystemExit(
                "Windows Unity cannot build this case-sensitive WSL worktree. "
                "Pass a new --unity-workspace path on a Windows-mounted drive."
            )
        if workspace.exists():
            raise SystemExit(f"Refusing to overwrite Unity workspace: {workspace}")
        shutil.copytree(unity_root, workspace)
        unity_root = workspace
    project = unity_root / "project"
    run([
        executable,
        "-batchmode",
        "-nographics",
        "-quit",
        "-projectPath",
        engine_path(project, executable),
        "-executeMethod",
        "BuildPrototype.Build",
        "-logFile",
        "-",
    ])
    return project / "Build" / "WebGL"


def build_godot(executable: str) -> None:
    project = ROOT / "godot" / "project"
    project_arg = engine_path(project, executable)
    run([executable, "--headless", "--editor", "--path", project_arg, "--quit-after", "2"])
    export_path = project / "Build" / "Web" / "index.html"
    export_path.parent.mkdir(parents=True, exist_ok=True)
    run([
        executable,
        "--headless",
        "--path",
        project_arg,
        "--export-release",
        "Web",
        engine_path(export_path, executable),
    ])


def verify_export(engine: str, output: Path, expected: dict[str, str]) -> None:
    index = output / "index.html"
    if not index.is_file():
        raise SystemExit(f"{engine} export is missing {index}")
    if "<!-- VERVE_WEBVIEW_CORE_PROTOTYPE -->" not in index.read_text(encoding="utf-8"):
        raise SystemExit(f"{engine} export did not inject the browser Core scripts")
    bundle = output / "VerveWebViewCore"
    for name, digest in expected.items():
        path = bundle / name
        if not path.is_file():
            raise SystemExit(f"{engine} export is missing {path}")
        actual = sha256(path)
        if actual != digest:
            raise SystemExit(f"{engine} changed {name}: {actual} != {digest}")
    print(f"{engine}: injected bundle is byte-identical")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--bazel", default=os.environ.get("VERVE_PROTOTYPE_BAZEL", "bazel"))
    parser.add_argument("--unity", help="Pinned Unity 2021.3 Editor executable")
    parser.add_argument(
        "--unity-workspace",
        type=Path,
        help="New directory on a Windows-mounted drive when --unity is a Windows .exe",
    )
    parser.add_argument("--godot", help="Pinned Godot 4.7.1 executable")
    parser.add_argument("--skip-core-build", action="store_true")
    args = parser.parse_args()

    if not args.skip_core_build and shutil.which(args.bazel) is None and not Path(args.bazel).is_file():
        raise SystemExit(
            "Bazel 8.7.0 is unavailable. Pass --bazel or VERVE_PROTOTYPE_BAZEL; "
            "the runner will not substitute shape fixtures."
        )
    output = ROOT / "bazel-bin" / "core_bindgen"
    if not args.skip_core_build:
        output = build_core(args.bazel)
    elif not all((output / name).is_file() for name in BUNDLE_NAMES[:2]):
        raise SystemExit("--skip-core-build requires an existing bazel-bin/core_bindgen bundle")
    expected = stage_bundle(output)
    print("Core bundle SHA-256:")
    for name, digest in expected.items():
        print(f"  {digest}  {name}")

    built = 0
    if args.unity:
        unity_output = build_unity(args.unity, args.unity_workspace)
        verify_export("Unity", unity_output, expected)
        built += 1
    else:
        print("Unity 2021.3 export: NOT RUN (pass --unity)")
    if args.godot:
        build_godot(args.godot)
        verify_export("Godot", ROOT / "godot" / "project" / "Build" / "Web", expected)
        built += 1
    else:
        print("Godot 4.7.1 export: NOT RUN (pass --godot)")

    if built != 2:
        print("INCOMPLETE: both pinned engine exports are required for a Wayfinder decision.")
        return 2
    print("STATIC EXPORT PROOF COMPLETE: run both exports in a browser before deciding viability.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
