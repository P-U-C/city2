#!/usr/bin/env python3
import argparse
import json
import re
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CONFIG = ROOT / "config/workstreams.json"
SLUG = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")


def load_config(path: Path) -> dict:
    data = json.loads(path.read_text())
    if data.get("schema_version") != 1:
        raise ValueError("schema_version must be 1")
    policy = data.get("policy")
    workstreams = data.get("workstreams")
    if not isinstance(policy, dict) or not isinstance(workstreams, list) or not workstreams:
        raise ValueError("policy and non-empty workstreams are required")

    ids: set[str] = set()
    channels: set[str] = set()
    required = {"id", "channel", "state", "agent", "agent_mode", "purpose", "task_sources"}
    for item in workstreams:
        if not isinstance(item, dict) or not required.issubset(item):
            raise ValueError("every workstream must contain the required fields")
        if not SLUG.fullmatch(item["id"]) or not SLUG.fullmatch(item["channel"]):
            raise ValueError("workstream ids and channels must be slugs")
        if item["id"] in ids or item["channel"] in channels:
            raise ValueError("workstream ids and channels must be unique")
        if item["state"] not in {"active", "proposed", "parked"}:
            raise ValueError("invalid workstream state")
        if item["agent_mode"] not in {"coordinator-session", "dedicated"}:
            raise ValueError("invalid agent_mode")
        if not isinstance(item["task_sources"], list) or not item["task_sources"]:
            raise ValueError("task_sources must be a non-empty list")
        ids.add(item["id"])
        channels.add(item["channel"])
    return data


def print_table(data: dict) -> None:
    print("WORKSTREAM     STATE     CHANNEL        AGENT MODE")
    for item in data["workstreams"]:
        print(
            f"{item['id']:<14} {item['state']:<9} "
            f"#{item['channel']:<14} {item['agent_mode']}"
        )
    print("\nTask unit: one forum thread per task")
    print("Default: one isolated coordinator session per channel; dedicated agents stay gated")


def print_plan(data: dict, workstream_id: str) -> None:
    item = next((item for item in data["workstreams"] if item["id"] == workstream_id), None)
    if item is None:
        raise ValueError(f"unknown workstream: {workstream_id}")
    print(f"Workstream: {item['id']} -> #{item['channel']}")
    print(f"Purpose: {item['purpose']}")
    print(f"Initial agent: {item['agent']} via {item['agent_mode']}")
    print(f"Import sources: {', '.join(item['task_sources'])}")
    if item["state"] == "active":
        print("Active channel:")
        print("  1. Keep one top-level thread per task with source links and current state.")
        print("  2. Use the existing isolated coordinator session for this channel.")
        print("  3. Promote to a dedicated agent only after the isolation gate is reviewed.")
    elif item["state"] == "proposed":
        print("Activation:")
        print("  1. Create a private Buzz forum channel with this slug.")
        print("  2. Add the City2 Coordinator as Bot; keep Chad as sole Owner.")
        print("  3. Add the channel UUID to the coordinator routing config and restart it.")
        print("  4. Seed one top-level thread per open task with source links and current state.")
        print("  5. Promote to a dedicated agent only after the isolation gate is reviewed.")
    else:
        print("Parked:")
        print("  No channel or agent activation is authorized.")
        print("  Require a new evidence-backed decision before changing this state.")


def main() -> int:
    parser = argparse.ArgumentParser(description="Inspect the City2 workstream plan")
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--plan", metavar="WORKSTREAM")
    args = parser.parse_args()
    try:
        data = load_config(args.config)
        if args.json:
            print(json.dumps(data, indent=2, sort_keys=True))
        elif args.plan:
            print_plan(data, args.plan)
        else:
            print_table(data)
        return 0
    except (OSError, json.JSONDecodeError, ValueError) as error:
        print(f"workstreams: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
