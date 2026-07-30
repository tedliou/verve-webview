import json
import pathlib
import subprocess
import sys
import tempfile
import unittest


class DistributionToolTest(unittest.TestCase):
    def test_unity_merge_keeps_root_metadata_and_validates_package_version(self):
        tool = pathlib.Path(__file__).with_name("distribution_tool.py")
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = pathlib.Path(temporary_directory)
            package = root / "package.json"
            package.write_text(
                json.dumps({"name": "com.tedliou.verve-webview", "version": "1.2.3"}),
                encoding="utf-8",
            )
            compatibility = root / "compatibility.json"
            compatibility.write_text(
                json.dumps({"sdk_version": "1.2.3"}),
                encoding="utf-8",
            )
            spec = root / "entries.tsv"
            spec.write_text(f"package.json\t{package}\n", encoding="utf-8")
            tree = root / "tree"
            subprocess.run(
                [
                    sys.executable,
                    str(tool),
                    "merge",
                    "--engine",
                    "unity",
                    "--spec",
                    str(spec),
                    "--tree",
                    str(tree),
                    "--manifest",
                    str(root / "content-manifest.json"),
                    "--compatibility",
                    str(compatibility),
                    "--release-version",
                    "1.2.3",
                ],
                check=True,
            )
            self.assertTrue((tree / "compatibility.json").is_file())
            self.assertTrue((tree / "content-manifest.json").is_file())
            self.assertFalse((tree / "addons").exists())

    def test_godot_merge_places_metadata_under_addon_root_without_package_json(self):
        tool = pathlib.Path(__file__).with_name("distribution_tool.py")
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = pathlib.Path(temporary_directory)
            addon = root / "plugin.cfg"
            addon.write_text("[plugin]\nname=\"Verve WebView\"\n", encoding="utf-8")
            compatibility = root / "compatibility.json"
            compatibility.write_text(
                json.dumps({"sdk_version": "1.2.3"}),
                encoding="utf-8",
            )
            spec = root / "entries.tsv"
            spec.write_text(
                f"addons/verve_webview/plugin.cfg\t{addon}\n",
                encoding="utf-8",
            )
            tree = root / "tree"
            manifest = root / "content-manifest.json"

            subprocess.run(
                [
                    sys.executable,
                    str(tool),
                    "merge",
                    "--engine",
                    "godot",
                    "--spec",
                    str(spec),
                    "--tree",
                    str(tree),
                    "--manifest",
                    str(manifest),
                    "--compatibility",
                    str(compatibility),
                    "--release-version",
                    "1.2.3",
                ],
                check=True,
            )

            metadata_root = tree / "addons/verve_webview"
            self.assertTrue((metadata_root / "compatibility.json").is_file())
            self.assertTrue((metadata_root / "content-manifest.json").is_file())
            self.assertFalse((tree / "compatibility.json").exists())
            self.assertFalse((tree / "content-manifest.json").exists())
            declared = {
                entry["path"]
                for entry in json.loads(manifest.read_text(encoding="utf-8"))[
                    "entries"
                ]
            }
            self.assertIn("addons/verve_webview/compatibility.json", declared)
            self.assertNotIn("package.json", declared)


if __name__ == "__main__":
    unittest.main()
