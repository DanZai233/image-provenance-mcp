#!/usr/bin/env python3
"""Minimal MCP client probe — checks a server end to end without any SDK.

    python examples/probe_mcp.py image-provenance-mcp
    python examples/probe_mcp.py --call image_provenance /path/to/photo.jpg

It speaks raw JSON-RPC over stdio, so if this works then the server works and any
remaining problem is in the client's config, not in the server.
"""

from __future__ import annotations

import json
import subprocess
import sys
import threading
import time

DEFAULT_CMD = ["image-provenance-mcp"]


class Probe:
    def __init__(self, cmd: list[str]):
        self.proc = subprocess.Popen(
            cmd, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
            text=True, bufsize=1,
        )
        self.replies: dict = {}
        threading.Thread(target=self._reader, daemon=True).start()

    def _reader(self) -> None:
        for line in self.proc.stdout:
            line = line.strip()
            if not line:
                continue
            try:
                msg = json.loads(line)
            except json.JSONDecodeError:
                continue
            self.replies[msg.get("id")] = msg

    def send(self, payload: dict) -> None:
        self.proc.stdin.write(json.dumps(payload) + "\n")
        self.proc.stdin.flush()

    def wait(self, req_id: int, timeout: float = 180.0) -> dict:
        deadline = time.time() + timeout
        while req_id not in self.replies:
            if time.time() > deadline:
                raise TimeoutError(f"no reply to request {req_id}")
            if self.proc.poll() is not None:
                raise RuntimeError(f"server exited with code {self.proc.returncode}")
            time.sleep(0.05)
        return self.replies[req_id]

    def close(self) -> None:
        try:
            self.proc.stdin.close()
            self.proc.wait(timeout=5)
        except Exception:
            self.proc.kill()


def main(argv: list[str]) -> int:
    if argv and argv[0] == "--call":
        tool, path = argv[1], argv[2]
        cmd = argv[3:] or DEFAULT_CMD
        call_only = True
    else:
        tool, path = None, None
        cmd = argv or DEFAULT_CMD
        call_only = False

    probe = Probe(cmd)
    try:
        probe.send({"jsonrpc": "2.0", "id": 1, "method": "initialize",
                    "params": {"protocolVersion": "2024-11-05", "capabilities": {},
                               "clientInfo": {"name": "probe", "version": "1"}}})
        init = probe.wait(1, timeout=30)["result"]
        print("server:", init.get("serverInfo"))

        probe.send({"jsonrpc": "2.0", "method": "notifications/initialized"})
        probe.send({"jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {}})
        tools = [t["name"] for t in probe.wait(2, timeout=30)["result"]["tools"]]
        print("tools:", ", ".join(tools))

        if call_only:
            probe.send({"jsonrpc": "2.0", "id": 3, "method": "tools/call",
                        "params": {"name": tool, "arguments": {"image_path": path}}})
            result = probe.wait(3)["result"]
            print("".join(c.get("text", "") for c in result.get("content", [])))
        return 0
    finally:
        probe.close()


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
