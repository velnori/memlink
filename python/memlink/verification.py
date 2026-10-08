"""Offline verification helpers; no pytest or additional runtime dependency."""

from __future__ import annotations

import hashlib
import io
import json
import os
import socket
import sys
from contextlib import ExitStack, contextmanager, redirect_stderr, redirect_stdout
from pathlib import Path
from unittest.mock import patch


def runtime_fingerprint() -> str:
    """Content identity for reuse of measurements on the same installed core."""
    root = Path(__file__).resolve().parent
    files = sorted(p for p in root.rglob("*") if p.is_file() and p.suffix in {".py", ".json", ".md", ".typed"})
    values = {p.relative_to(root).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest() for p in files}
    return hashlib.sha256(json.dumps(values, sort_keys=True).encode()).hexdigest()


@contextmanager
def offline_guard():
    """Block Python network entry points and remove API credentials temporarily.

    This is a measured Python sentinel, not an OS firewall or plugin sandbox.
    A DNS canary proves it is active before the workflow starts.
    """
    evidence = {"canary": False, "attempts": 0}

    def blocked(*args, **kwargs):
        evidence["attempts"] += 1
        raise OSError("MemLink verification blocked a network attempt")

    environment = {
        k: v for k, v in os.environ.items() if not any(s in k.upper() for s in ("API_KEY", "TOKEN", "SECRET"))
    }
    with ExitStack() as stack:
        stack.enter_context(patch.dict(os.environ, environment, clear=True))
        for target in (
            "socket.socket.connect",
            "socket.socket.connect_ex",
            "socket.create_connection",
            "socket.getaddrinfo",
            "socket.gethostbyname",
            "urllib.request.urlopen",
            "http.client.HTTPConnection.connect",
            "http.client.HTTPSConnection.connect",
        ):
            stack.enter_context(patch(target, blocked))
        try:
            socket.getaddrinfo("memlink-canary.invalid", 443)
        except OSError:
            evidence["canary"] = evidence["attempts"] == 1
        evidence["attempts"] = 0
        yield evidence


def invoke_cli(arguments: list[str]) -> tuple[int, str, str]:
    """Exercise the real CLI parser/dispatch/exit codes inside the sentinel."""
    from .cli import main

    out, err = io.StringIO(), io.StringIO()
    with patch.object(sys, "argv", ["memlink", *arguments]), redirect_stdout(out), redirect_stderr(err):
        try:
            main()
            code = 0
        except SystemExit as exc:
            code = int(exc.code or 0)
    return code, out.getvalue(), err.getvalue()


if __name__ == "__main__":
    # A child process uses this launcher for real CLI execution with a sentinel.
    # The first argument is an internal evidence path, never a source/config file.
    evidence_path = Path(sys.argv[1])
    with offline_guard() as network:
        exit_code, stdout, stderr = invoke_cli(sys.argv[2:])
    evidence_path.write_text(json.dumps(network), encoding="utf-8")
    print(stdout, end="")
    print(stderr, end="", file=sys.stderr)
    raise SystemExit(exit_code)
