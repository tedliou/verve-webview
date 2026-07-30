#!/usr/bin/env python3
"""Cross-engine checks against the canonical generated API Contract."""

import json
import pathlib
import re
import unittest


ROOT = pathlib.Path(__file__).resolve().parents[1]


def unity_name(canonical: str) -> str:
    return "".join(word.title() for word in canonical.lower().split("_"))


class ContractMatrixTest(unittest.TestCase):
    def test_engine_error_enums_match_canonical_wire_ids(self) -> None:
        contract = json.loads(
            (
                ROOT
                / "packages/webview-core/generated/conformance/api-contract.json"
            ).read_text(encoding="utf-8")
        )
        expected = {
            error["name"]: error["id"] for error in contract["public_error_codes"]
        }
        unity_text = (
            ROOT / "packages/webview-core/generated/unity/WebViewContract.g.cs"
        ).read_text(encoding="utf-8")
        godot_text = (
            ROOT / "packages/webview-core/generated/godot/webview_contract.gd"
        ).read_text(encoding="utf-8")
        unity = {
            name: int(wire)
            for name, wire in re.findall(r"^\s+(\w+) = (\d+),$", unity_text, re.M)
        }
        godot = {
            name: int(wire)
            for name, wire in re.findall(r"^\s+([A-Z_]+) = (\d+),$", godot_text, re.M)
        }
        self.assertEqual(
            unity,
            {unity_name(name): wire for name, wire in expected.items()},
        )
        self.assertEqual(
            godot,
            {name.upper(): wire for name, wire in expected.items()},
        )

    def test_shared_scenarios_use_only_canonical_public_error_codes(self) -> None:
        contract = json.loads(
            (
                ROOT
                / "packages/webview-core/generated/conformance/api-contract.json"
            ).read_text(encoding="utf-8")
        )
        errors = {
            error["name"].lower() for error in contract["public_error_codes"]
        }
        scenarios = json.loads(
            (ROOT / "verification/shared-suites.json").read_text(encoding="utf-8")
        )["scenarios"]
        used = {
            token
            for scenario in scenarios
            for step in scenario["steps"]
            for token in step.split(":")
            if token in errors
        }
        self.assertEqual(
            used,
            {
                "ok",
                "disposed",
                "host_lost",
                "surface_in_use",
                "distribution_invalid",
            },
        )


if __name__ == "__main__":
    unittest.main()
