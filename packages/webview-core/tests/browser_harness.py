#!/usr/bin/env python3
"""Run the production browser Core seam in a real headless Chrome process."""

from __future__ import annotations

import html
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile
import threading


def windows_path(path: Path, executable: str) -> str:
    if os.name != "nt" and executable.lower().endswith(".exe"):
        return subprocess.check_output(["wslpath", "-w", str(path)], text=True).strip()
    return str(path)


def main() -> None:
    files = [Path(argument).resolve() for argument in sys.argv[1:]]
    chrome = os.environ.get(
        "CHROME_BIN",
        "/mnt/c/Program Files/Google/Chrome/Application/chrome.exe",
    )
    if not Path(chrome).is_file():
        raise RuntimeError(f"real Chrome executable not found: {chrome}")

    with tempfile.TemporaryDirectory(prefix="verve-browser-core-") as temporary:
        root = Path(temporary)
        required = {
            "verve_webview_core.js",
            "verve_webview_core_bg.wasm",
            "verve_webview_core_test.js",
            "verve_webview_core_test_bg.wasm",
            "verve_webview_core_facade.js",
            "browser_harness.html",
            "browser_harness.js",
            "load_failure_harness.html",
            "load_failure_harness.js",
            "trap_harness.html",
            "trap_harness.js",
            "api-contract.json",
        }
        for source in files:
            if source.name in required:
                shutil.copyfile(source, root / source.name)
        missing = sorted(name for name in required if not (root / name).is_file())
        if missing:
            raise RuntimeError(f"browser harness inputs are missing: {missing}")
        (root / "corrupt.wasm").write_bytes(b"not a WebAssembly module")

        handler = lambda *args, **kwargs: SimpleHTTPRequestHandler(
            *args, directory=root, **kwargs
        )
        server = ThreadingHTTPServer(("127.0.0.1", 0), handler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            profile = root / "chrome-profile"
            command = [
                chrome,
                "--headless=new",
                "--disable-gpu",
                "--no-sandbox",
                "--disable-breakpad",
                "--disable-crash-reporter",
                f"--user-data-dir={windows_path(profile, chrome)}",
                "--virtual-time-budget=10000",
                "--dump-dom",
                f"http://127.0.0.1:{server.server_port}/browser_harness.html",
            ]
            completed = subprocess.run(
                command,
                check=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                timeout=60,
            )
        finally:
            server.shutdown()
            thread.join(timeout=5)

    match = re.search(r'<pre id="result">(.*?)</pre>', completed.stdout, re.DOTALL)
    if match is None:
        raise RuntimeError("Chrome output did not contain the harness result")
    result = json.loads(html.unescape(match.group(1)))
    if result.get("status") != "passed":
        raise RuntimeError(json.dumps(result, indent=2))
    print(json.dumps(result, sort_keys=True))


if __name__ == "__main__":
    main()
