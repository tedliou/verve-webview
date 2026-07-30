#!/usr/bin/env python3
"""Behavior tests for the public Release Evidence verification seam."""

import hashlib
import json
import pathlib
import subprocess
import sys
import tempfile
import unittest


ROOT = pathlib.Path(__file__).resolve().parents[1]
TOOL = ROOT / "verification" / "release_evidence.py"
COMPATIBILITY = ROOT / "compatibility" / "compatibility.json"
SUITES = ROOT / "verification" / "shared-suites.json"
SOURCE_SHA = "a" * 40


def sha256(path: pathlib.Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


class ReleaseEvidenceTest(unittest.TestCase):
    def setUp(self) -> None:
        self.directory = tempfile.TemporaryDirectory()
        self.root = pathlib.Path(self.directory.name)
        self.artifacts = {}
        for name in ("unity.tgz", "unity.zip", "godot.zip"):
            path = self.root / name
            path.write_bytes(("final artifact " + name).encode("utf-8"))
            self.artifacts[name] = path

    def tearDown(self) -> None:
        self.directory.cleanup()

    def run_tool(self, *arguments: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [sys.executable, str(TOOL), *arguments],
            cwd=ROOT,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
        )

    def write_evidence(self, *, result: str = "passed") -> pathlib.Path:
        compatibility = json.loads(COMPATIBILITY.read_text(encoding="utf-8"))
        suites = json.loads(SUITES.read_text(encoding="utf-8"))
        evidence = {
            "schema_version": 1,
            "candidate": {
                "sdk_version": compatibility["sdk_version"],
                "artifacts": [
                    {
                        "id": artifact_id,
                        "sha256": sha256(path),
                    }
                    for artifact_id, path in sorted(self.artifacts.items())
                ],
            },
            "environment": {
                "engine": "godot",
                "engine_version": "4.7.1",
                "profile": "web-windows-chrome",
                "platform": "web",
                "architecture": "wasm32",
                "os": "windows-11",
                "toolchain": {
                    "godot_editor": "4.7.1.stable.official.a13da4feb"
                },
                "runtime": {"name": "chrome", "version": "exact-test-version"},
            },
            "suite_version": suites["suite_version"],
            "results": [
                {"suite": suite, "result": result}
                for suite in suites["required_suites"]
            ],
        }
        path = self.root / "evidence.json"
        path.write_text(json.dumps(evidence), encoding="utf-8")
        return path

    def write_candidate(self) -> pathlib.Path:
        compatibility_digest = sha256(COMPATIBILITY)
        identity = {
            "version": json.loads(COMPATIBILITY.read_text(encoding="utf-8"))[
                "sdk_version"
            ],
            "channel": "prerelease",
            "source_sha": SOURCE_SHA,
            "compatibility_sha256": compatibility_digest,
            "artifact_sha256": {
                artifact_id: sha256(path)
                for artifact_id, path in sorted(self.artifacts.items())
            },
        }
        candidate = {
            "schema_version": 1,
            "candidate_id": hashlib.sha256(
                json.dumps(
                    identity,
                    ensure_ascii=True,
                    separators=(",", ":"),
                    sort_keys=True,
                ).encode("utf-8")
            ).hexdigest(),
            "identity": identity,
            "artifacts": [
                {
                    "id": artifact_id,
                    "name": path.name,
                    "sha256": sha256(path),
                    "size": path.stat().st_size,
                }
                for artifact_id, path in sorted(self.artifacts.items())
            ],
            "upm_package": {"sha256": "b" * 64, "entries": []},
        }
        path = self.root / "candidate.json"
        path.write_text(json.dumps(candidate), encoding="utf-8")
        return path

    def candidate_binding(self, candidate_path: pathlib.Path) -> dict:
        candidate = json.loads(candidate_path.read_text(encoding="utf-8"))
        return {
            "candidate_id": candidate["candidate_id"],
            **candidate["identity"],
        }

    def verify_arguments(
        self, evidence: pathlib.Path, candidate: pathlib.Path | None = None
    ) -> list[str]:
        arguments = [
            "verify",
            "--evidence",
            str(evidence),
            "--compatibility",
            str(COMPATIBILITY),
            "--suites",
            str(SUITES),
            "--artifact",
            f"unity.tgz={self.artifacts['unity.tgz']}",
            "--artifact",
            f"unity.zip={self.artifacts['unity.zip']}",
            "--artifact",
            f"godot.zip={self.artifacts['godot.zip']}",
        ]
        if candidate is not None:
            arguments.extend(["--candidate", str(candidate)])
        return arguments

    def test_exact_artifacts_and_all_shared_suites_are_accepted(self) -> None:
        result = self.run_tool(*self.verify_arguments(self.write_evidence()))
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("verified Release Evidence", result.stdout)

    def test_changed_final_artifact_fails_closed(self) -> None:
        evidence = self.write_evidence()
        self.artifacts["godot.zip"].write_bytes(b"rebuilt after verification")
        result = self.run_tool(*self.verify_arguments(evidence))
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("artifact digest mismatch", result.stderr)

    def test_complete_candidate_identity_is_required_when_candidate_is_supplied(
        self,
    ) -> None:
        candidate = self.write_candidate()
        evidence_path = self.write_evidence()
        evidence = json.loads(evidence_path.read_text(encoding="utf-8"))
        evidence["candidate"] = self.candidate_binding(candidate)
        evidence_path.write_text(json.dumps(evidence), encoding="utf-8")
        result = self.run_tool(
            *self.verify_arguments(evidence_path, candidate)
        )
        self.assertEqual(result.returncode, 0, result.stderr)

        evidence["candidate"]["source_sha"] = "c" * 40
        evidence_path.write_text(json.dumps(evidence), encoding="utf-8")
        result = self.run_tool(
            *self.verify_arguments(evidence_path, candidate)
        )
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("candidate identity mismatch", result.stderr)

    def test_unverified_required_suite_fails_closed(self) -> None:
        result = self.run_tool(
            *self.verify_arguments(self.write_evidence(result="unverified"))
        )
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("required suite is not passed", result.stderr)

    def test_success_without_exact_runtime_version_fails_closed(self) -> None:
        evidence_path = self.write_evidence()
        evidence = json.loads(evidence_path.read_text(encoding="utf-8"))
        evidence["environment"]["runtime"] = {"mode": "browser"}
        evidence_path.write_text(json.dumps(evidence), encoding="utf-8")
        result = self.run_tool(*self.verify_arguments(evidence_path))
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("exact runtime version", result.stderr)

    def test_missing_supported_combination_fails_release_gate(self) -> None:
        evidence = self.write_evidence()
        manifest = self.root / "manifest.json"
        manifest.write_text(
            json.dumps({"schema_version": 1, "evidence": [str(evidence)]}),
            encoding="utf-8",
        )
        result = self.run_tool(
            "gate",
            "--manifest",
            str(manifest),
            "--compatibility",
            str(COMPATIBILITY),
            "--suites",
            str(SUITES),
            "--artifact",
            f"unity.tgz={self.artifacts['unity.tgz']}",
            "--artifact",
            f"unity.zip={self.artifacts['unity.zip']}",
            "--artifact",
            f"godot.zip={self.artifacts['godot.zip']}",
        )
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("missing successful Release Evidence", result.stderr)

    def test_plan_expands_exact_declared_engine_platform_matrix(self) -> None:
        result = self.run_tool(
            "plan",
            "--compatibility",
            str(COMPATIBILITY),
            "--suites",
            str(SUITES),
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        plan = json.loads(result.stdout)
        self.assertEqual(plan["schema_version"], 1)
        self.assertEqual(len(plan["required_environments"]), 75)
        versions = {
            (item["engine"], item["engine_version"])
            for item in plan["required_environments"]
        }
        self.assertEqual(
            versions,
            {
                ("unity", "2021.3.45f2"),
                ("unity", "2022.3.62f1"),
                ("unity", "6000.0.80f1"),
                ("unity", "6000.3.20f1"),
                ("godot", "4.7.1"),
            },
        )
        web_profiles = {
            (item["os_requirement"], item["runtime"])
            for item in plan["required_environments"]
            if item["engine"] == "godot" and item["platform"] == "web"
        }
        self.assertEqual(
            web_profiles,
            {
                ("windows-11", "chrome"),
                ("windows-11", "edge"),
                ("windows-11", "firefox"),
                ("macos", "chrome"),
                ("macos", "edge"),
                ("macos", "firefox"),
                ("macos", "safari"),
                ("linux", "chrome"),
                ("linux", "edge"),
                ("linux", "firefox"),
            },
        )

    def test_record_binds_digests_and_defaults_missing_suites_to_unverified(
        self,
    ) -> None:
        output = self.root / "recorded.json"
        result = self.run_tool(
            "record",
            "--output",
            str(output),
            "--compatibility",
            str(COMPATIBILITY),
            "--suites",
            str(SUITES),
            "--engine",
            "godot",
            "--engine-version",
            "4.7.1",
            "--profile",
            "web-windows-chrome",
            "--platform",
            "web",
            "--architecture",
            "wasm32",
            "--os",
            "windows-11",
            "--toolchain",
            "godot_editor=4.7.1.stable.official.a13da4feb",
            "--runtime",
            "name=chrome",
            "--runtime",
            "version=unverified",
            "--result",
            "malformed_distribution=passed",
            "--artifact",
            f"unity.tgz={self.artifacts['unity.tgz']}",
            "--artifact",
            f"unity.zip={self.artifacts['unity.zip']}",
            "--artifact",
            f"godot.zip={self.artifacts['godot.zip']}",
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        evidence = json.loads(output.read_text(encoding="utf-8"))
        by_suite = {
            item["suite"]: item["result"] for item in evidence["results"]
        }
        self.assertEqual(by_suite["malformed_distribution"], "passed")
        self.assertEqual(by_suite["security"], "unverified")
        self.assertEqual(
            {item["id"]: item["sha256"] for item in evidence["candidate"]["artifacts"]},
            {
                artifact_id: sha256(path)
                for artifact_id, path in self.artifacts.items()
            },
        )


if __name__ == "__main__":
    unittest.main()
