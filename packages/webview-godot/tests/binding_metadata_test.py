#!/usr/bin/env python3
"""Source-of-truth checks for Godot's platform plugin descriptors."""

import configparser
import pathlib
import unittest
import xml.etree.ElementTree as ET


ROOT = pathlib.Path(__file__).parents[1]
ANDROID_NS = "{http://schemas.android.com/apk/res/android}"


class BindingMetadataTest(unittest.TestCase):
    def test_android_v2_manifest_and_export_hook(self):
        manifest = ET.parse(
            ROOT / "src/bindings/android/AndroidManifest.xml"
        ).getroot()
        uses_sdk = manifest.find("uses-sdk")
        self.assertIsNotNone(uses_sdk)
        self.assertEqual(uses_sdk.attrib[ANDROID_NS + "minSdkVersion"], "24")
        metadata = manifest.find("application/meta-data")
        self.assertEqual(
            metadata.attrib[ANDROID_NS + "name"],
            "org.godotengine.plugin.v2.VerveWebView",
        )
        self.assertEqual(
            metadata.attrib[ANDROID_NS + "value"],
            "com.tedliou.verve.webview.godot.VerveWebViewGodotPlugin",
        )
        export_hook = (
            ROOT / "src/bindings/android/android_export_plugin.gd"
        ).read_text(encoding="utf-8")
        self.assertIn("verve-webview-godot.aar", export_hook)
        self.assertIn("verve-webview-backend.aar", export_hook)
        self.assertIn("EditorExportPlatformAndroid", export_hook)

    def test_ios_gdip_selects_debug_and_release_static_xcframeworks(self):
        descriptor = configparser.ConfigParser()
        descriptor.read(
            ROOT / "src/bindings/ios/verve_webview.gdip",
            encoding="utf-8",
        )
        self.assertEqual(
            descriptor["config"]["binary"].strip('"'),
            "VerveWebViewIOS.xcframework",
        )
        build = (ROOT / "BUILD.bazel").read_text(encoding="utf-8")
        rules = (ROOT / "build/godot_adapter.bzl").read_text(encoding="utf-8")
        self.assertIn('commands.add_parser("extract-zip")', (
            ROOT.parents[1] / "build/distribution_tool.py"
        ).read_text(encoding="utf-8"))
        self.assertIn('for profile in ["debug", "release"]', rules)
        self.assertIn('profile + ".xcframework"', rules)
        self.assertIn("device-arm64_simulator-arm64-x86_64", build)

    def test_windows_gdextension_is_release_x86_64_and_webview2_is_fixed(self):
        descriptor = configparser.ConfigParser()
        descriptor.read(
            ROOT / "src/bindings/windows/verve_webview.gdextension",
            encoding="utf-8",
        )
        self.assertEqual(
            descriptor["configuration"]["compatibility_minimum"].strip('"'),
            "4.7",
        )
        self.assertIn("windows.release.x86_64", descriptor["libraries"])
        self.assertIn("windows.debug.editor.x86_64", descriptor["libraries"])
        self.assertIn("linux.debug.editor.x86_64", descriptor["libraries"])
        entry = (
            ROOT / "src/bindings/windows/gdextension_entry.c"
        ).read_text(encoding="utf-8")
        self.assertIn(
            "initialization->initialize = verve_webview_initialize", entry
        )
        self.assertIn(
            "initialization->deinitialize = verve_webview_deinitialize", entry
        )
        self.assertNotIn("initialization->initialize = 0", entry)

    def test_web_hook_lists_the_shared_core_and_backend_payloads(self):
        hook = (
            ROOT / "src/bindings/web/web_export_plugin.gd"
        ).read_text(encoding="utf-8")
        for file_name in (
            "api-contract.js",
            "verve_webview_core.js",
            "verve_webview_core_bg.wasm",
            "verve_webview_core_facade.js",
            "verve_webview_web_backend.js",
        ):
            self.assertIn(f'"{file_name}"', hook)
        self.assertIn("EditorExportPlatformWeb", hook)
        self.assertNotIn("Extension Support", hook)


if __name__ == "__main__":
    unittest.main()
