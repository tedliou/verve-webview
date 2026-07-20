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


def is_static_archive(data: bytes) -> bool:
    if data.startswith(b"!<arch>\n"):
        return True

    fat_formats = {
        b"\xca\xfe\xba\xbe": (">", 20, False),
        b"\xbe\xba\xfe\xca": ("<", 20, False),
        b"\xca\xfe\xba\xbf": (">", 32, True),
        b"\xbf\xba\xfe\xca": ("<", 32, True),
    }
    fat_format = fat_formats.get(data[:4])
    if fat_format is None or len(data) < 8:
        return False

    endian, entry_size, is_64_bit = fat_format
    architecture_count = struct.unpack_from(f"{endian}I", data, 4)[0]
    if architecture_count == 0 or len(data) < 8 + architecture_count * entry_size:
        return False

    offset_format = f"{endian}{'Q' if is_64_bit else 'I'}"
    offset_position = 8 if is_64_bit else 8
    for index in range(architecture_count):
        entry_start = 8 + index * entry_size
        slice_offset = struct.unpack_from(
            offset_format,
            data,
            entry_start + offset_position,
        )[0]
        if not data[slice_offset:].startswith(b"!<arch>\n"):
            return False
    return True


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
            library_path = Path(item["LibraryPath"])
            binary_path = library_path
            if library_path.suffix == ".framework":
                binary_path /= library_path.stem
            binary_name = str(
                Path(archive_path.stem)
                / item["LibraryIdentifier"]
                / binary_path
            )
            if not is_static_archive(archive.read(binary_name)):
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


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("platform", choices=("android", "apple", "windows"))
    platform = parser.parse_args().platform
    {"android": verify_android, "apple": verify_apple, "windows": verify_windows}[platform]()
