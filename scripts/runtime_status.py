#!/usr/bin/env python3
"""Content-free, read-only status for live City2 activation dependencies."""

from __future__ import annotations

import argparse
import json
import os
import pwd
import shutil
import subprocess
from typing import Callable


Run = Callable[..., subprocess.CompletedProcess[str]]
Which = Callable[[str], str | None]


def tailscale_state(*, run: Run = subprocess.run, which: Which = shutil.which) -> str:
    if not which("tailscale"):
        return "missing"
    result = run(
        ["tailscale", "status", "--json"],
        capture_output=True,
        text=True,
        check=False,
    )
    try:
        backend = json.loads(result.stdout).get("BackendState")
    except json.JSONDecodeError:
        backend = None
    return {
        "Running": "connected",
        "NeedsLogin": "logged-out",
        "Stopped": "stopped",
        "NoState": "stopped",
    }.get(backend, "unavailable")


def coordinator_state(
    unit: str, *, run: Run = subprocess.run, which: Which = shutil.which
) -> str:
    if not which("systemctl"):
        return "missing"
    result = run(
        [
            "systemctl",
            "show",
            unit,
            "--property=LoadState",
            "--property=ActiveState",
            "--property=SubState",
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode:
        return "unavailable"
    values = {}
    for line in result.stdout.splitlines():
        key, separator, value = line.partition("=")
        if separator:
            values[key] = value
    if values.get("LoadState") == "not-found":
        return "not-installed"
    if values.get("ActiveState") == "active" and values.get("SubState") == "running":
        return "active"
    return values.get("ActiveState") or "unknown"


def default_unit() -> str:
    instance = os.environ.get("CITY2_COORDINATOR_INSTANCE")
    if not instance:
        instance = pwd.getpwuid(os.getuid()).pw_name
    return f"city2-buzz-agent@{instance}.service"


def snapshot() -> dict[str, str]:
    return {
        "tailscale": tailscale_state(),
        "coordinator": coordinator_state(default_unit()),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--format", choices=("doctor", "status", "json"), default="status"
    )
    args = parser.parse_args()
    values = snapshot()
    if args.format == "doctor":
        for key, value in values.items():
            print(f"{key:<18} {value}")
    elif args.format == "json":
        print(json.dumps(values, sort_keys=True, separators=(",", ":")))
    else:
        for key, value in values.items():
            print(f"{key}={value}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
