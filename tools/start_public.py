#!/usr/bin/env python
"""Start Vivid and a free Cloudflare quick tunnel, then print the temporary public URL.

Use start_public.bat, or: .venv312\\Scripts\\python.exe tools\\start_public.py

The local site works even if the tunnel doesn't. Keep the window open; Ctrl+C stops both.
"""
from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from weight_store import _download, sha256_of  # noqa: E402

PORT = int(os.environ.get("PORT", "7860"))
LOCAL = f"http://127.0.0.1:{PORT}"
BIN = ROOT / "tools" / "bin" / "cloudflared.exe"
VERSION = "2026.11.2"
URL = f"https://github.com/cloudflare/cloudflared/releases/download/{VERSION}/cloudflared-windows-amd64.exe"
SHA256 = "555b46c85582461d189cac30d14ad05480d612613801be9f110b8ce08c5b2113"
STARTUP_TIMEOUT = 120
TUNNEL_TIMEOUT = 60
DNS_TIMEOUT = 30


def say(text: str = "") -> None:
    print(text, flush=True)


def healthy(base: str, timeout: float = 5) -> bool:
    request = urllib.request.Request(f"{base}/api/health", headers={"User-Agent": "vivid-start"})
    try:
        with urllib.request.urlopen(request, timeout=timeout) as r:
            return json.load(r).get("status") == "ok"
    except (OSError, ValueError):
        return False


def port_taken() -> bool:
    try:
        urllib.request.urlopen(LOCAL, timeout=3)
    except urllib.error.HTTPError:
        return True
    except OSError:
        return False
    return True


def published(host: str) -> bool:
    """Does Cloudflare's public DNS know the new address yet?

    Asked over HTTPS, never through this machine's own DNS: looking a brand-new name up too early makes
    the router cache "not found", and then no browser on the network can open the link for minutes.
    """
    request = urllib.request.Request(
        f"https://1.1.1.1/dns-query?name={host}&type=A", headers={"Accept": "application/dns-json", "User-Agent": "vivid-start"}
    )
    try:
        with urllib.request.urlopen(request, timeout=5) as response:
            return any(a.get("type") == 1 for a in json.load(response).get("Answer", []))
    except (OSError, ValueError):
        return False


def wait_until_public(url: str) -> bool:
    host = url.removeprefix("https://")
    deadline = time.time() + DNS_TIMEOUT
    while time.time() < deadline and not published(host):
        time.sleep(2)
    time.sleep(5)  # let other resolvers catch up before the first real lookup
    deadline = time.time() + TUNNEL_TIMEOUT
    while time.time() < deadline:
        if healthy(url, timeout=10):
            return True
        time.sleep(5)
    return False


def find_cloudflared() -> str:
    if BIN.exists() and sha256_of(BIN) == SHA256:
        return str(BIN)
    if installed := shutil.which("cloudflared"):
        return installed
    say("Downloading cloudflared (once, about 60 MB)...")
    BIN.parent.mkdir(parents=True, exist_ok=True)
    tmp = BIN.with_suffix(".download")
    _download(URL, tmp, say)
    if sha256_of(tmp) != SHA256:
        tmp.unlink()
        raise RuntimeError("the cloudflared download didn't match its published SHA-256")
    os.replace(tmp, BIN)
    return str(BIN)


def start_server() -> subprocess.Popen | None:
    if healthy(LOCAL):
        say(f"Vivid is already running on {LOCAL}, using that one.")
        return None
    if port_taken():
        raise SystemExit(f"Another program is using port {PORT}. Close it, then try again.")
    say("Starting Vivid (about 25 seconds)...")
    server = subprocess.Popen([sys.executable, "server.py"], cwd=ROOT, env={**os.environ, "PORT": str(PORT)})
    deadline = time.time() + STARTUP_TIMEOUT
    while time.time() < deadline:
        if server.poll() is not None:
            raise SystemExit("Vivid stopped while starting. The reason is in the lines above.")
        if healthy(LOCAL):
            return server
        time.sleep(1)
    server.terminate()
    raise SystemExit("Vivid took too long to start.")


def start_tunnel(exe: str) -> tuple[subprocess.Popen, str | None]:
    tunnel = subprocess.Popen(
        [exe, "tunnel", "--no-autoupdate", "--url", LOCAL],
        stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, text=True, encoding="utf-8", errors="replace",
    )
    found: list[str] = []
    recent: list[str] = []

    def read() -> None:  # keeps draining the pipe for as long as the tunnel runs
        for line in tunnel.stderr:
            recent.append(line.rstrip())
            del recent[:-12]
            # api.trycloudflare.com appears in error messages; it's never the public address.
            if not found and (m := re.search(r"https://(?!api\.)[a-z0-9-]+\.trycloudflare\.com", line)):
                found.append(m.group())

    threading.Thread(target=read, daemon=True).start()
    deadline = time.time() + TUNNEL_TIMEOUT
    while time.time() < deadline and not found and tunnel.poll() is None:
        time.sleep(0.5)
    if not found:
        say("\ncloudflared said:")
        for line in recent:
            say("  " + line)
        if tunnel.poll() is None:
            tunnel.terminate()
        return tunnel, None
    return tunnel, found[0]


def banner(public: str | None, verified: bool) -> None:
    say("\n" + "=" * 64)
    say(f"  LOCAL   {LOCAL}")
    if public:
        say(f"  PUBLIC  {public}")
        if not verified:
            say("          (not reachable from this laptop yet; wait 2 minutes, then try it)")
    else:
        say("  PUBLIC  not available. The local site above still works.")
    say("=" * 64)
    say("Keep this window open. Ctrl+C stops everything.\n")


def main() -> None:
    server = tunnel = None
    try:
        server = start_server()
        public, verified = None, False
        try:
            say("Opening the public link...")
            tunnel, public = start_tunnel(find_cloudflared())
            verified = bool(public) and wait_until_public(public)
        except Exception as e:  # no internet, blocked download: the local demo must go on
            say(f"The public link couldn't be set up: {e}")
        banner(public, verified)
        while True:
            if server and server.poll() is not None:
                say("Vivid has stopped. Run start_public.bat again.")
                break
            if public and tunnel.poll() is not None:
                say(f"The public link has closed. The local site still works: {LOCAL}")
                public = None
            time.sleep(1)
    except KeyboardInterrupt:
        say("\nStopping...")
    finally:
        for process in (tunnel, server):
            if process and process.poll() is None:
                process.terminate()


if __name__ == "__main__":
    main()
