#!/usr/bin/env python3
"""Run the Web Platform Backend seam in a real headless Chrome process."""

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
    sources = [Path(argument).resolve() for argument in sys.argv[1:]]
    chrome = os.environ.get(
        "CHROME_BIN",
        "/mnt/c/Program Files/Google/Chrome/Application/chrome.exe",
    )
    if not Path(chrome).is_file():
        raise RuntimeError(f"real Chrome executable not found: {chrome}")

    required = {
        "verve_webview_core.js",
        "verve_webview_core_bg.wasm",
        "verve_webview_core_facade.js",
        "verve_webview_web_backend.js",
        "web_runtime_backend_harness.html",
        "web_runtime_backend_harness.js",
        "surface_content.html",
    }
    with tempfile.TemporaryDirectory(prefix="verve-browser-backend-") as temporary:
        root = Path(temporary)
        for source in sources:
            if source.name in required:
                shutil.copyfile(source, root / source.name)
        missing = sorted(name for name in required if not (root / name).is_file())
        if missing:
            raise RuntimeError(f"Web Runtime Backend harness inputs are missing: {missing}")

        handler = lambda *args, **kwargs: SimpleHTTPRequestHandler(
            *args, directory=root, **kwargs
        )
        server = ThreadingHTTPServer(("127.0.0.1", 0), handler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            profile = root / "chrome-profile"
            completed = subprocess.run(
                [
                    chrome,
                    "--headless=new",
                    "--disable-gpu",
                    "--no-sandbox",
                    "--disable-breakpad",
                    "--disable-crash-reporter",
                    f"--user-data-dir={windows_path(profile, chrome)}",
                    "--virtual-time-budget=10000",
                    "--dump-dom",
                    f"http://127.0.0.1:{server.server_port}/web_runtime_backend_harness.html",
                ],
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
        raise RuntimeError("Chrome output did not contain the Backend harness result")
    result = json.loads(html.unescape(match.group(1)))
    if result.get("status") != "passed":
        raise RuntimeError(json.dumps(result, indent=2))
    print(json.dumps(result, sort_keys=True))


if __name__ == "__main__":
    main()
