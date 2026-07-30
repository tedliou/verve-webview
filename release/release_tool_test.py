#!/usr/bin/env python3
"""Behavior tests for candidate identity and forward-only promotion."""

import hashlib
import io
import json
import pathlib
import subprocess
import sys
import tarfile
import tempfile
import unittest
import zipfile


ROOT = pathlib.Path(__file__).resolve().parents[1]
TOOL = ROOT / "release" / "release_tool.py"
SOURCE_SHA = "a" * 40
BOUNDARIES = [
    "upm_commit",
    "draft_release",
    "release_assets",
    "source_tag",
    "upm_tag",
    "published_release",
    "upm_branch",
]


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def write_tree(root: pathlib.Path, files: dict[str, bytes]) -> None:
    for name, content in files.items():
        path = root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(content)


def content_manifest(files: dict[str, bytes]) -> bytes:
    return (
        json.dumps(
            {
                "entries": [
                    {"path": name, "sha256": digest(content), "size": len(content)}
                    for name, content in sorted(files.items())
                ],
                "schema_version": 1,
            },
            indent=2,
            sort_keys=True,
        )
        + "\n"
    ).encode()


class ReleaseToolTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.root = pathlib.Path(self.temporary.name)
        self.bundle = self.root / "bundle"
        self.bundle.mkdir()
        compatibility = (
            json.dumps(
                {
                    "schema_version": 1,
                    "sdk_version": "1.2.3",
                    "verification_profiles": [],
                    "supported": [],
                    "verified": [],
                },
                indent=2,
                sort_keys=True,
            )
            + "\n"
        ).encode()
        (self.bundle / "compatibility.json").write_bytes(compatibility)

        unity_files = {
            "package.json": b'{"name":"com.tedliou.verve-webview","version":"1.2.3"}\n',
            "compatibility.json": compatibility,
            "Runtime/sdk.txt": b"verified unity bytes\n",
        }
        unity_files["content-manifest.json"] = content_manifest(unity_files)
        self.upm_tree = self.bundle / "upm-package"
        write_tree(self.upm_tree, unity_files)

        with tarfile.open(
            self.bundle / "com.tedliou.verve-webview-1.2.3.tgz", "w:gz"
        ) as archive:
            for name, content in sorted(unity_files.items()):
                info = tarfile.TarInfo("package/" + name)
                info.size = len(content)
                info.mtime = 0
                archive.addfile(info, io.BytesIO(content))
        with zipfile.ZipFile(
            self.bundle / "com.tedliou.verve-webview-1.2.3.zip", "w"
        ) as archive:
            for name, content in sorted(unity_files.items()):
                archive.writestr("com.tedliou.verve-webview/" + name, content)

        godot_files = {
            "addons/verve_webview/plugin.cfg": b"[plugin]\nname=\"Verve WebView\"\n",
            "addons/verve_webview/compatibility.json": compatibility,
        }
        godot_files["addons/verve_webview/content-manifest.json"] = content_manifest(
            godot_files
        )
        with zipfile.ZipFile(
            self.bundle / "verve-webview-godot-1.2.3.zip", "w"
        ) as archive:
            for name, content in sorted(godot_files.items()):
                archive.writestr(name, content)

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def run_tool(self, *arguments: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [sys.executable, str(TOOL), *arguments],
            cwd=ROOT,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
        )

    def create_candidate(
        self, *, version: str = "1.2.3", channel: str = "stable"
    ) -> pathlib.Path:
        candidate = self.bundle / "candidate.json"
        result = self.run_tool(
            "candidate",
            "create",
            "--output",
            str(candidate),
            "--bundle",
            str(self.bundle),
            "--version",
            version,
            "--channel",
            channel,
            "--source-sha",
            SOURCE_SHA,
            "--compatibility",
            str(self.bundle / "compatibility.json"),
            "--upm-tree",
            str(self.upm_tree),
            "--artifact",
            "unity.tgz=com.tedliou.verve-webview-1.2.3.tgz",
            "--artifact",
            "unity.zip=com.tedliou.verve-webview-1.2.3.zip",
            "--artifact",
            "godot.zip=verve-webview-godot-1.2.3.zip",
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        return candidate

    def test_candidate_manifest_binds_complete_identity_and_final_bytes(self) -> None:
        candidate = self.create_candidate()
        manifest = json.loads(candidate.read_text(encoding="utf-8"))
        self.assertEqual(manifest["schema_version"], 1)
        self.assertEqual(
            set(manifest["identity"]),
            {
                "version",
                "channel",
                "source_sha",
                "compatibility_sha256",
                "artifact_sha256",
            },
        )
        self.assertRegex(manifest["candidate_id"], r"^[0-9a-f]{64}$")
        result = self.run_tool(
            "candidate",
            "verify",
            "--candidate",
            str(candidate),
            "--bundle",
            str(self.bundle),
        )
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_host_fragment_envelope_binds_source_toolchain_and_payload_bytes(
        self,
    ) -> None:
        fragment = self.root / "fragment"
        tree = fragment / "tree"
        tree.mkdir(parents=True)
        payload = b"host-owned payload\n"
        (tree / "binding.bin").write_bytes(payload)
        (fragment / "content-manifest.json").write_bytes(
            content_manifest({"binding.bin": payload})
        )
        (fragment / "fragment-manifest.json").write_text(
            json.dumps(
                {
                    "architecture": "x86_64",
                    "fragment_id": "binding_windows",
                    "platform": "windows",
                    "release_version": "1.2.3",
                    "schema_version": 1,
                }
            ),
            encoding="utf-8",
        )
        envelope = fragment / "release-fragment.json"
        recorded = self.run_tool(
            "fragment",
            "record",
            "--fragment",
            str(fragment),
            "--output",
            str(envelope),
            "--source-sha",
            SOURCE_SHA,
            "--compatibility",
            str(self.bundle / "compatibility.json"),
            "--toolchain",
            "runner=windows-2022",
            "--toolchain",
            "msvc=14.44",
            "--toolchain",
            "windows_sdk=10.0.26100.0",
        )
        self.assertEqual(recorded.returncode, 0, recorded.stderr)
        value = json.loads(envelope.read_text(encoding="utf-8"))
        self.assertEqual(value["source_sha"], SOURCE_SHA)
        self.assertEqual(
            value["toolchain"],
            {
                "msvc": "14.44",
                "runner": "windows-2022",
                "windows_sdk": "10.0.26100.0",
            },
        )
        self.assertEqual(value["payloads"][0]["sha256"], digest(payload))
        verified = self.run_tool(
            "fragment",
            "verify",
            "--fragment",
            str(fragment),
            "--compatibility",
            str(self.bundle / "compatibility.json"),
            "--source-sha",
            SOURCE_SHA,
        )
        self.assertEqual(verified.returncode, 0, verified.stderr)
        (tree / "binding.bin").write_bytes(b"tampered\n")
        rejected = self.run_tool(
            "fragment",
            "verify",
            "--fragment",
            str(fragment),
            "--compatibility",
            str(self.bundle / "compatibility.json"),
            "--source-sha",
            SOURCE_SHA,
        )
        self.assertNotEqual(rejected.returncode, 0)
        self.assertIn("payload", rejected.stderr)

    def test_candidate_verification_rejects_changed_final_bytes(self) -> None:
        candidate = self.create_candidate()
        with (self.bundle / "verve-webview-godot-1.2.3.zip").open("ab") as output:
            output.write(b"rebuilt")
        result = self.run_tool(
            "candidate",
            "verify",
            "--candidate",
            str(candidate),
            "--bundle",
            str(self.bundle),
        )
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("digest mismatch", result.stderr)

    def test_candidate_requires_equivalent_unity_archives_and_upm_tree(self) -> None:
        (self.upm_tree / "Runtime/sdk.txt").write_bytes(b"different package tree\n")
        result = self.run_tool(
            "candidate",
            "create",
            "--output",
            str(self.bundle / "candidate.json"),
            "--bundle",
            str(self.bundle),
            "--version",
            "1.2.3",
            "--channel",
            "stable",
            "--source-sha",
            SOURCE_SHA,
            "--compatibility",
            str(self.bundle / "compatibility.json"),
            "--upm-tree",
            str(self.upm_tree),
            "--artifact",
            "unity.tgz=com.tedliou.verve-webview-1.2.3.tgz",
            "--artifact",
            "unity.zip=com.tedliou.verve-webview-1.2.3.zip",
            "--artifact",
            "godot.zip=verve-webview-godot-1.2.3.zip",
        )
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("Unity distributions differ", result.stderr)

    def test_candidate_rejects_public_artifact_name_drift(self) -> None:
        wrong = self.bundle / "renamed-unity.tgz"
        wrong.write_bytes(
            (self.bundle / "com.tedliou.verve-webview-1.2.3.tgz").read_bytes()
        )
        result = self.run_tool(
            "candidate",
            "create",
            "--output",
            str(self.bundle / "candidate.json"),
            "--bundle",
            str(self.bundle),
            "--version",
            "1.2.3",
            "--channel",
            "stable",
            "--source-sha",
            SOURCE_SHA,
            "--compatibility",
            str(self.bundle / "compatibility.json"),
            "--upm-tree",
            str(self.upm_tree),
            "--artifact",
            "unity.tgz=renamed-unity.tgz",
            "--artifact",
            "unity.zip=com.tedliou.verve-webview-1.2.3.zip",
            "--artifact",
            "godot.zip=verve-webview-godot-1.2.3.zip",
        )
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("artifact filename", result.stderr)

    def test_retry_converges_after_every_partial_promotion_boundary(self) -> None:
        candidate = self.create_candidate()
        for boundary in BOUNDARIES:
            with self.subTest(boundary=boundary):
                state = self.root / f"{boundary}.json"
                state.write_text(
                    json.dumps({"schema_version": 1}), encoding="utf-8"
                )
                first = self.run_tool(
                    "promotion",
                    "simulate",
                    "--candidate",
                    str(candidate),
                    "--state",
                    str(state),
                    "--output",
                    str(state),
                    "--stop-after",
                    boundary,
                )
                self.assertEqual(first.returncode, 0, first.stderr)
                retry = self.run_tool(
                    "promotion",
                    "simulate",
                    "--candidate",
                    str(candidate),
                    "--state",
                    str(state),
                    "--output",
                    str(state),
                )
                self.assertEqual(retry.returncode, 0, retry.stderr)
                final = json.loads(state.read_text(encoding="utf-8"))
                self.assertEqual(final["status"], "promoted")
                self.assertEqual(final["source_tag"], SOURCE_SHA)
                self.assertEqual(final["upm_branch"], final["upm_tag"])
                self.assertFalse(final["release"]["draft"])

    def test_conflicting_destination_fails_without_mutation(self) -> None:
        candidate = self.create_candidate()
        state = self.root / "conflict.json"
        original = {
            "schema_version": 1,
            "source_tag": "b" * 40,
        }
        state.write_text(json.dumps(original, sort_keys=True), encoding="utf-8")
        result = self.run_tool(
            "promotion",
            "simulate",
            "--candidate",
            str(candidate),
            "--state",
            str(state),
            "--output",
            str(state),
        )
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("conflicting", result.stderr)
        self.assertEqual(
            json.loads(state.read_text(encoding="utf-8")),
            original,
        )

    def test_prerelease_never_advances_upm_branch(self) -> None:
        version = "1.2.3-pre.1"
        compatibility = json.loads(
            (self.bundle / "compatibility.json").read_text(encoding="utf-8")
        )
        compatibility["sdk_version"] = version
        compatibility_bytes = (
            json.dumps(compatibility, indent=2, sort_keys=True) + "\n"
        ).encode()
        (self.bundle / "compatibility.json").write_bytes(compatibility_bytes)
        unity_files = {
            "package.json": (
                '{"name":"com.tedliou.verve-webview","version":"'
                + version
                + '"}\n'
            ).encode(),
            "compatibility.json": compatibility_bytes,
            "Runtime/sdk.txt": b"verified unity bytes\n",
        }
        unity_files["content-manifest.json"] = content_manifest(unity_files)
        write_tree(self.upm_tree, unity_files)
        unity_tgz = self.bundle / f"com.tedliou.verve-webview-{version}.tgz"
        with tarfile.open(unity_tgz, "w:gz") as archive:
            for name, content in sorted(unity_files.items()):
                info = tarfile.TarInfo("package/" + name)
                info.size = len(content)
                info.mtime = 0
                archive.addfile(info, io.BytesIO(content))
        unity_zip = self.bundle / f"com.tedliou.verve-webview-{version}.zip"
        with zipfile.ZipFile(unity_zip, "w") as archive:
            for name, content in sorted(unity_files.items()):
                archive.writestr("com.tedliou.verve-webview/" + name, content)
        godot_files = {
            "addons/verve_webview/plugin.cfg": b"[plugin]\nname=\"Verve WebView\"\n",
            "addons/verve_webview/compatibility.json": compatibility_bytes,
        }
        godot_files["addons/verve_webview/content-manifest.json"] = content_manifest(
            godot_files
        )
        godot_zip = self.bundle / f"verve-webview-godot-{version}.zip"
        with zipfile.ZipFile(godot_zip, "w") as archive:
            for name, content in sorted(godot_files.items()):
                archive.writestr(name, content)
        candidate = self.bundle / "candidate.json"
        created = self.run_tool(
            "candidate",
            "create",
            "--output",
            str(candidate),
            "--bundle",
            str(self.bundle),
            "--version",
            version,
            "--channel",
            "prerelease",
            "--source-sha",
            SOURCE_SHA,
            "--compatibility",
            str(self.bundle / "compatibility.json"),
            "--upm-tree",
            str(self.upm_tree),
            "--artifact",
            f"unity.tgz={unity_tgz.name}",
            "--artifact",
            f"unity.zip={unity_zip.name}",
            "--artifact",
            f"godot.zip={godot_zip.name}",
        )
        self.assertEqual(created.returncode, 0, created.stderr)
        state = self.root / "prerelease.json"
        previous_upm = "c" * 40
        state.write_text(
            json.dumps({"schema_version": 1, "upm_branch": previous_upm}),
            encoding="utf-8",
        )
        promoted = self.run_tool(
            "promotion",
            "simulate",
            "--candidate",
            str(candidate),
            "--state",
            str(state),
            "--output",
            str(state),
        )
        self.assertEqual(promoted.returncode, 0, promoted.stderr)
        final = json.loads(state.read_text(encoding="utf-8"))
        self.assertEqual(final["upm_branch"], previous_upm)
        self.assertTrue(final["release"]["prerelease"])
        self.assertEqual(final["status"], "promoted")

    def test_withdrawal_preserves_objects_and_requires_newer_corrective_version(
        self,
    ) -> None:
        candidate = self.create_candidate()
        state = self.root / "promoted.json"
        state.write_text(json.dumps({"schema_version": 1}), encoding="utf-8")
        promoted = self.run_tool(
            "promotion",
            "simulate",
            "--candidate",
            str(candidate),
            "--state",
            str(state),
            "--output",
            str(state),
        )
        self.assertEqual(promoted.returncode, 0, promoted.stderr)
        before = json.loads(state.read_text(encoding="utf-8"))
        result = self.run_tool(
            "withdrawal",
            "record",
            "--state",
            str(state),
            "--version",
            "1.2.3",
            "--corrective-version",
            "1.2.4",
            "--reason",
            "security defect",
            "--output",
            str(state),
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        after = json.loads(state.read_text(encoding="utf-8"))
        self.assertEqual(after["source_tag"], before["source_tag"])
        self.assertEqual(after["upm_tag"], before["upm_tag"])
        self.assertEqual(after["release"]["assets"], before["release"]["assets"])
        self.assertEqual(after["withdrawn"]["1.2.3"]["corrective_version"], "1.2.4")


if __name__ == "__main__":
    unittest.main()
