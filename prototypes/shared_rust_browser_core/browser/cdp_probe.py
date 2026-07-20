#!/usr/bin/env python3
"""PROTOTYPE ONLY: wait for an engine result through Chrome DevTools Protocol."""

from __future__ import annotations

import argparse
import base64
import json
from pathlib import Path
import os
import socket
import struct
import subprocess
import time
import urllib.parse
import urllib.request


def native_path(path: Path, executable: str) -> str:
    if os.name != "nt" and executable.lower().endswith(".exe"):
        return subprocess.check_output(["wslpath", "-w", str(path)], text=True).strip()
    return str(path)


class WebSocket:
    def __init__(self, url: str):
        parsed = urllib.parse.urlparse(url)
        self.socket = socket.create_connection((parsed.hostname, parsed.port), timeout=10)
        key = base64.b64encode(os.urandom(16)).decode()
        target = parsed.path + (("?" + parsed.query) if parsed.query else "")
        request = (
            f"GET {target} HTTP/1.1\r\n"
            f"Host: {parsed.hostname}:{parsed.port}\r\n"
            "Upgrade: websocket\r\nConnection: Upgrade\r\n"
            f"Sec-WebSocket-Key: {key}\r\nSec-WebSocket-Version: 13\r\n"
            "Origin: http://localhost\r\n\r\n"
        )
        self.socket.sendall(request.encode())
        response = b""
        while b"\r\n\r\n" not in response:
            response += self.socket.recv(4096)
        if not response.startswith(b"HTTP/1.1 101"):
            raise RuntimeError(response.decode(errors="replace"))

    def send(self, payload: dict) -> None:
        data = json.dumps(payload).encode()
        mask = os.urandom(4)
        header = bytearray([0x81])
        length = len(data)
        if length < 126:
            header.append(0x80 | length)
        elif length < 65536:
            header.append(0x80 | 126)
            header.extend(struct.pack("!H", length))
        else:
            header.append(0x80 | 127)
            header.extend(struct.pack("!Q", length))
        header.extend(mask)
        masked = bytes(value ^ mask[index % 4] for index, value in enumerate(data))
        self.socket.sendall(header + masked)

    def receive(self) -> dict:
        first, second = self._read(2)
        opcode = first & 0x0F
        length = second & 0x7F
        if length == 126:
            length = struct.unpack("!H", self._read(2))[0]
        elif length == 127:
            length = struct.unpack("!Q", self._read(8))[0]
        if second & 0x80:
            mask = self._read(4)
        else:
            mask = None
        payload = self._read(length)
        if mask:
            payload = bytes(value ^ mask[index % 4] for index, value in enumerate(payload))
        if opcode == 0x9:
            return self.receive()
        if opcode == 0x8:
            raise RuntimeError("Chrome closed the DevTools socket")
        return json.loads(payload)

    def _read(self, length: int) -> bytes:
        chunks = bytearray()
        while len(chunks) < length:
            chunk = self.socket.recv(length - len(chunks))
            if not chunk:
                raise RuntimeError("Unexpected end of DevTools socket")
            chunks.extend(chunk)
        return bytes(chunks)


def request_json(url: str, method: str = "GET") -> dict:
    with urllib.request.urlopen(urllib.request.Request(url, method=method), timeout=5) as response:
        return json.load(response)


def command(ws: WebSocket, identifier: int, method: str, params: dict | None = None) -> dict:
    ws.send({"id": identifier, "method": method, "params": params or {}})
    while True:
        message = ws.receive()
        if message.get("id") == identifier:
            return message


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("url")
    parser.add_argument("--chrome", required=True)
    parser.add_argument("--profile", type=Path, required=True)
    parser.add_argument("--timeout", type=float, default=120.0)
    parser.add_argument("--port", type=int, default=9223)
    args = parser.parse_args()
    args.profile.mkdir(parents=True, exist_ok=True)
    process = subprocess.Popen([
        args.chrome,
        "--headless=new",
        "--disable-gpu",
        "--no-sandbox",
        "--remote-allow-origins=*",
        f"--remote-debugging-port={args.port}",
        f"--user-data-dir={native_path(args.profile, args.chrome)}",
        "about:blank",
    ])
    try:
        endpoint = f"http://127.0.0.1:{args.port}"
        deadline = time.monotonic() + args.timeout
        while True:
            try:
                request_json(endpoint + "/json/version")
                break
            except Exception:
                if time.monotonic() >= deadline:
                    raise TimeoutError("Chrome DevTools endpoint did not start")
                time.sleep(0.2)
        page = request_json(endpoint + "/json/new?" + urllib.parse.quote(args.url, safe=""), "PUT")
        ws = WebSocket(page["webSocketDebuggerUrl"])
        identifier = 1
        command(ws, identifier, "Runtime.enable")
        expression = "document.querySelector('#verve-prototype-result')?.textContent || null"
        while time.monotonic() < deadline:
            identifier += 1
            response = command(ws, identifier, "Runtime.evaluate", {
                "expression": expression,
                "returnByValue": True,
            })
            value = response.get("result", {}).get("result", {}).get("value")
            if value:
                print(value)
                return
            time.sleep(0.5)
        identifier += 1
        body = command(ws, identifier, "Runtime.evaluate", {
            "expression": "document.body?.innerText || ''",
            "returnByValue": True,
        })
        visible = body.get("result", {}).get("result", {}).get("value", "")
        raise TimeoutError("No prototype result before timeout. Visible page text:\n" + visible)
    finally:
        process.terminate()


if __name__ == "__main__":
    main()
