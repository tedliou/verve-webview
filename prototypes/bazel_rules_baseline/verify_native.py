#!/usr/bin/env python3
"""Verify the smallest real platform artifacts emitted by Bazel."""

from __future__ import annotations

import argparse
import plistlib
import struct
import zipfile
from pathlib import Path


ROOT = Path(__file__).resolve().parent
OUTPUT = ROOT / "bazel-bin" / "native"


def only(pattern: str) -> Path:
    matches = list(OUTPUT.glob(pattern))
    if len(matches) != 1:
        raise SystemExit(f"Expected one {pattern}, found: {matches}")
    return matches[0]


def verify_android() -> None:
    aar = only("android/*.aar")
    with zipfile.ZipFile(aar) as archive:
        names = set(archive.namelist())
        missing = {"AndroidManifest.xml", "classes.jar"} - names
        if missing:
            raise SystemExit(f"AAR missing {sorted(missing)}")
        manifest = archive.read("AndroidManifest.xml").decode()
    if 'android:minSdkVersion="24"' not in manifest:
        raise SystemExit("AAR does not preserve minSdk 24")
    print(f"Verified real Android AAR: {aar}")


def verify_apple() -> None:
    archive_path = only("apple/*.xcframework.zip")
    with zipfile.ZipFile(archive_path) as archive:
        plist_name = next(name for name in archive.namelist() if name.endswith("/Info.plist"))
        info = plistlib.loads(archive.read(plist_name))
        libraries = info["AvailableLibraries"]
        device = [item for item in libraries if item["SupportedPlatform"] == "ios" and "SupportedPlatformVariant" not in item]
        simulator = [item for item in libraries if item.get("SupportedPlatformVariant") == "simulator"]
        if len(device) != 1 or device[0]["SupportedArchitectures"] != ["arm64"]:
            raise SystemExit(f"Unexpected device slice: {device}")
        if len(simulator) != 1 or set(simulator[0]["SupportedArchitectures"]) != {"arm64", "x86_64"}:
            raise SystemExit(f"Unexpected simulator slice: {simulator}")
        for item in libraries:
            binary_name = f"{archive_path.stem}/{item['LibraryIdentifier']}/{item['LibraryPath']}"
            if not archive.read(binary_name).startswith(b"!<arch>\n"):
                raise SystemExit(f"Not a static archive: {binary_name}")
    print(f"Verified real Apple static XCFramework: {archive_path}")


def verify_windows() -> None:
    dll = only("windows/*.dll")
    data = dll.read_bytes()
    if data[:2] != b"MZ":
        raise SystemExit("Windows output is not a PE image")
    pe_offset = struct.unpack_from("<I", data, 0x3C)[0]
    if data[pe_offset:pe_offset + 4] != b"PE\0\0":
        raise SystemExit("Windows output lacks a PE signature")
    machine = struct.unpack_from("<H", data, pe_offset + 4)[0]
    if machine != 0x8664:
        raise SystemExit(f"Expected x86_64 PE machine 0x8664, got {machine:#x}")
    print(f"Verified real Windows x86_64 DLL: {dll}")


parser = argparse.ArgumentParser()
parser.add_argument("platform", choices=("android", "apple", "windows"))
platform = parser.parse_args().platform
{"android": verify_android, "apple": verify_apple, "windows": verify_windows}[platform]()
