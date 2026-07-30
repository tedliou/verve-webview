#!/usr/bin/env python3
"""Static contract tests for the trusted candidate and promotion workflows."""

import pathlib
import re
import unittest


ROOT = pathlib.Path(__file__).resolve().parents[1]
CANDIDATE = ROOT / ".github/workflows/release-candidate.yml"
PROMOTION = ROOT / ".github/workflows/release-promotion.yml"
FULL_SHA_USE = re.compile(r"uses:\s+[^@\s]+@([0-9a-f]{40})(?:\s|$)")


class WorkflowPolicyTest(unittest.TestCase):
    def test_candidate_uses_resolved_topology_and_immutable_actions(self) -> None:
        text = CANDIDATE.read_text(encoding="utf-8")
        for runner in ("ubuntu-24.04", "macos-15", "windows-2022"):
            self.assertIn(f"runs-on: {runner}", text)
        uses = [line for line in text.splitlines() if "uses:" in line]
        self.assertTrue(uses)
        for line in uses:
            self.assertRegex(line, FULL_SHA_USE)
        self.assertIn("permissions:\n  contents: read", text)
        self.assertNotIn("contents: write", text)
        self.assertIn("persist-credentials: false", text)
        self.assertIn('repos/$GITHUB_REPOSITORY/releases', text)

    def test_promotion_is_serialized_human_approved_and_least_privilege(
        self,
    ) -> None:
        text = PROMOTION.read_text(encoding="utf-8")
        self.assertIn("group: verve-release-promotion", text)
        self.assertIn("cancel-in-progress: false", text)
        self.assertIn("environment: release", text)
        self.assertIn("actions: read", text)
        self.assertIn("contents: write", text)
        self.assertNotIn("pull-requests: write", text)
        self.assertNotIn("issues: write", text)
        self.assertIn("github.ref == 'refs/heads/main'", text)
        uses = [line for line in text.splitlines() if "uses:" in line]
        self.assertTrue(uses)
        for line in uses:
            self.assertRegex(line, FULL_SHA_USE)

    def test_promotion_verifies_existing_bytes_without_build_commands(self) -> None:
        text = PROMOTION.read_text(encoding="utf-8")
        for forbidden in ("bazel build", "bazel test", "cargo build", "dotnet build"):
            self.assertNotIn(forbidden, text)
        self.assertIn("candidate verify", text)
        self.assertIn("release_evidence.py gate", text)
        self.assertIn("promotion apply", text)


if __name__ == "__main__":
    unittest.main()
