#!/usr/bin/env python3
"""Repository-level invariants for final-distribution Example Apps."""

import json
import pathlib
import unittest


ROOT = pathlib.Path(__file__).resolve().parents[1]


class ExampleAppsTest(unittest.TestCase):
    def test_shared_suites_cover_every_authority_owned_behavior(self) -> None:
        corpus = json.loads(
            (ROOT / "verification/shared-suites.json").read_text(encoding="utf-8")
        )
        self.assertEqual(
            corpus["required_suites"],
            [
                "conformance",
                "security",
                "smoke",
                "lifecycle_stress",
                "host_loss",
                "surface_lease",
                "malformed_distribution",
            ],
        )
        scenario_suites = {scenario["suite"] for scenario in corpus["scenarios"]}
        self.assertEqual(scenario_suites, set(corpus["required_suites"]))

    def test_example_targets_depend_only_on_their_engine_sdk(self) -> None:
        build = (ROOT / "examples/BUILD.bazel").read_text(encoding="utf-8")
        self.assertIn('"//packages/webview-unity:sdk"', build)
        self.assertIn('"//packages/webview-godot:sdk"', build)
        for forbidden in (
            "//packages/webview-core:",
            "//packages/webview-android:",
            "//packages/webview-ios:",
            "//packages/webview-windows:",
            "//packages/webview-web:",
            "//packages/webview-unity:adapter",
            "//packages/webview-godot:adapter",
        ):
            self.assertNotIn(forbidden, build)

    def test_both_apps_demonstrate_the_same_public_lifecycle(self) -> None:
        unity = (
            ROOT / "examples/unity/Assets/VerveWebViewExample.cs"
        ).read_text(encoding="utf-8")
        godot = (ROOT / "examples/godot/main.gd").read_text(encoding="utf-8")
        for operation in ("initialize", "open", "close", "dispose"):
            self.assertIn(operation, unity.lower())
            self.assertIn(operation, godot.lower())
        for behavior in ("navigate", "rectangle", "reopen", "error"):
            self.assertIn(behavior, unity.lower())
            self.assertIn(behavior, godot.lower())


if __name__ == "__main__":
    unittest.main()
