import json
import os
import pathlib
import subprocess
import sys
import tempfile
import unittest


class GenerateFragmentRepositoryTest(unittest.TestCase):
    def test_generated_directory_is_a_bazel_repository(self):
        generator = pathlib.Path(__file__).with_name(
            "generate_fragment_repository.py"
        )
        if not generator.is_file():
            runfiles = pathlib.Path(os.environ["RUNFILES_DIR"])
            generator = (
                runfiles
                / os.environ.get("TEST_WORKSPACE", "_main")
                / "build/generate_fragment_repository.py"
            )

        with tempfile.TemporaryDirectory() as temporary_directory:
            root = pathlib.Path(temporary_directory)
            downloads = root / "downloads"
            output = root / "fragments"
            for platform in ("android", "ios", "windows", "web"):
                fragment = downloads / platform
                tree = fragment / "tree"
                tree.mkdir(parents=True)
                (tree / "binding.txt").write_text(platform, encoding="utf-8")
                (fragment / "content-manifest.json").write_text(
                    json.dumps(
                        {
                            "entries": [
                                {
                                    "path": "binding.txt",
                                }
                            ]
                        }
                    ),
                    encoding="utf-8",
                )
                (fragment / "fragment-manifest.json").write_text(
                    "{}",
                    encoding="utf-8",
                )

            subprocess.run(
                [
                    sys.executable,
                    os.fspath(generator),
                    "--downloads",
                    os.fspath(downloads),
                    "--output",
                    os.fspath(output),
                ],
                check=True,
            )

            self.assertTrue((output / "BUILD.bazel").is_file())
            self.assertTrue(
                any(
                    (output / marker).is_file()
                    for marker in ("MODULE.bazel", "REPO.bazel", "WORKSPACE")
                )
            )


if __name__ == "__main__":
    unittest.main()
