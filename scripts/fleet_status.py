#!/usr/bin/env python3
"""Read-only City2 fleet inventory and health evaluation."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import re
import subprocess
import sys
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_MANIFEST = ROOT / "config" / "fleet.json"
ID_PATTERN = re.compile(r"^[a-z0-9-]+$")


class ManifestError(ValueError):
    pass


def load_json(path: Path) -> dict[str, Any]:
    with path.open(encoding="utf-8") as handle:
        value = json.load(handle)
    if not isinstance(value, dict):
        raise ManifestError(f"{path} must contain a JSON object")
    return value


def validate_manifest(manifest: dict[str, Any]) -> None:
    if manifest.get("schema_version") != 1:
        raise ManifestError("schema_version must be 1")
    hosts = manifest.get("hosts")
    producers = manifest.get("producers")
    if not isinstance(hosts, list) or not hosts:
        raise ManifestError("hosts must be a non-empty list")
    if not isinstance(producers, list) or not producers:
        raise ManifestError("producers must be a non-empty list")

    host_ids: set[str] = set()
    for host in hosts:
        if not isinstance(host, dict) or not ID_PATTERN.fullmatch(str(host.get("id", ""))):
            raise ManifestError("every host needs a valid id")
        host_id = host["id"]
        if host_id in host_ids:
            raise ManifestError(f"duplicate host id: {host_id}")
        host_ids.add(host_id)
        access = host.get("access")
        if not isinstance(access, dict) or access.get("type") not in {"local", "ssh"}:
            raise ManifestError(f"{host_id}: invalid access")
        if access["type"] == "ssh" and not access.get("alias"):
            raise ManifestError(f"{host_id}: SSH alias is required")

    producer_ids: set[str] = set()
    for producer in producers:
        if not isinstance(producer, dict) or not ID_PATTERN.fullmatch(str(producer.get("id", ""))):
            raise ManifestError("every producer needs a valid id")
        producer_id = producer["id"]
        if producer_id in producer_ids:
            raise ManifestError(f"duplicate producer id: {producer_id}")
        producer_ids.add(producer_id)
        if producer.get("host") not in host_ids:
            raise ManifestError(f"{producer_id}: unknown host")
        if producer.get("state") not in {"active", "parked"}:
            raise ManifestError(f"{producer_id}: invalid state")
        for field in ("unix_user", "runtime_root", "database"):
            if not isinstance(producer.get(field), str) or not producer[field]:
                raise ManifestError(f"{producer_id}: missing {field}")
        if not producer["runtime_root"].startswith("/") or not producer["database"].startswith("/"):
            raise ManifestError(f"{producer_id}: paths must be absolute")
        if producer["state"] == "active":
            if not isinstance(producer.get("freshness_hours"), (int, float)) or producer["freshness_hours"] <= 0:
                raise ManifestError(f"{producer_id}: invalid freshness_hours")
            cron = producer.get("cron")
            if not isinstance(cron, dict) or cron.get("type") not in {"system", "user"}:
                raise ManifestError(f"{producer_id}: invalid cron contract")


REMOTE_PROBE = r'''
import json, os, pathlib, pwd, shutil
from datetime import datetime, timezone

manifest = json.loads(__MANIFEST__)

def file_state(value):
    if not value:
        return None
    path = pathlib.Path(value)
    try:
        stat = path.stat()
    except OSError:
        return {"path": value, "exists": False}
    return {"path": value, "exists": True, "bytes": stat.st_size, "mtime": stat.st_mtime}

rows = []
for producer in manifest["producers"]:
    try:
        user_exists = pwd.getpwnam(producer["unix_user"]) is not None
    except KeyError:
        user_exists = False
    cron = producer.get("cron")
    cron_ok = None
    if cron:
        if cron["type"] == "system":
            cron_ok = pathlib.Path(cron["path"]).is_file()
        else:
            spool = pathlib.Path("/var/spool/cron/crontabs") / producer["unix_user"]
            try:
                lines = spool.read_text(errors="replace").splitlines()
            except OSError:
                lines = []
            match = cron["match"]
            cron_ok = any(match in line for line in lines if line.strip() and not line.lstrip().startswith("#"))
    rows.append({
        "id": producer["id"],
        "unix_user_exists": user_exists,
        "runtime_root_exists": pathlib.Path(producer["runtime_root"]).is_dir(),
        "database": file_state(producer.get("database")),
        "aggregate_log": file_state(producer.get("aggregate_log")),
        "cron_ok": cron_ok,
    })

disk = shutil.disk_usage("/")
print(json.dumps({
    "checked_at": datetime.now(timezone.utc).isoformat(),
    "disk_free_bytes": disk.free,
    "producers": rows,
}))
'''


def probe_host(host: dict[str, Any], producers: list[dict[str, Any]]) -> dict[str, Any]:
    payload = {"producers": producers}
    program = REMOTE_PROBE.replace("__MANIFEST__", repr(json.dumps(payload, separators=(",", ":"))))
    access = host["access"]
    if access["type"] == "local":
        command = ["sudo", "-n", "python3", "-"]
    else:
        command = ["ssh", "-o", "BatchMode=yes", access["alias"], "sudo", "-n", "python3", "-"]
    try:
        completed = subprocess.run(
            command,
            input=program,
            text=True,
            capture_output=True,
            timeout=30,
            check=False,
        )
    except subprocess.TimeoutExpired:
        return {"error": "probe timed out after 30s"}
    except OSError as error:
        return {"error": f"probe could not start: {error}"}
    if completed.returncode != 0:
        message = completed.stderr.strip().splitlines()[-1] if completed.stderr.strip() else "probe failed"
        return {"error": message}
    try:
        return json.loads(completed.stdout)
    except json.JSONDecodeError:
        return {"error": "probe returned invalid JSON"}


def collect_snapshot(manifest: dict[str, Any]) -> dict[str, Any]:
    hosts: dict[str, Any] = {}
    for host in manifest["hosts"]:
        producers = [item for item in manifest["producers"] if item["host"] == host["id"]]
        if not producers:
            continue
        hosts[host["id"]] = probe_host(host, producers)
    return {"checked_at": datetime.now(timezone.utc).isoformat(), "hosts": hosts}


def evaluate(manifest: dict[str, Any], snapshot: dict[str, Any], *, now: datetime | None = None) -> dict[str, Any]:
    now = now or datetime.now(timezone.utc)
    hosts_by_id = {host["id"]: host for host in manifest["hosts"]}
    snapshot_hosts = snapshot.get("hosts", {})
    host_results: list[dict[str, Any]] = []
    producer_results: list[dict[str, Any]] = []

    for host_id, host in hosts_by_id.items():
        if not any(item["host"] == host_id for item in manifest["producers"]):
            continue
        raw = snapshot_hosts.get(host_id, {})
        if raw.get("error"):
            host_results.append({"id": host_id, "status": "critical", "detail": raw["error"]})
            continue
        free_gib = raw.get("disk_free_bytes", 0) / (1024**3)
        minimum = float(host.get("minimum_free_gib", 0))
        status = "warn" if minimum and free_gib < minimum else "ok"
        detail = f"disk_free={free_gib:.1f}GiB"
        if status == "warn":
            detail += f" (<{minimum:g}GiB)"
        host_results.append({"id": host_id, "status": status, "detail": detail})

    for producer in manifest["producers"]:
        if producer["state"] == "parked":
            producer_results.append({"id": producer["id"], "status": "parked", "detail": producer.get("note", "")})
            continue
        host_raw = snapshot_hosts.get(producer["host"], {})
        if host_raw.get("error"):
            producer_results.append({"id": producer["id"], "status": "critical", "detail": "host unavailable"})
            continue
        raw = next((item for item in host_raw.get("producers", []) if item.get("id") == producer["id"]), None)
        if raw is None:
            producer_results.append({"id": producer["id"], "status": "critical", "detail": "missing from probe"})
            continue
        failures: list[str] = []
        if not raw.get("unix_user_exists"):
            failures.append("user missing")
        if not raw.get("runtime_root_exists"):
            failures.append("runtime missing")
        if raw.get("cron_ok") is not True:
            failures.append("cron missing")
        database = raw.get("database") or {}
        age_hours = None
        if not database.get("exists") or database.get("bytes", 0) <= 0:
            failures.append("database missing/empty")
        else:
            age_hours = max(0.0, (now.timestamp() - float(database["mtime"])) / 3600)
            if age_hours > float(producer["freshness_hours"]):
                failures.append(f"database stale {age_hours:.1f}h")
        aggregate = raw.get("aggregate_log") or {}
        if producer.get("aggregate_log") and not aggregate.get("exists"):
            failures.append("aggregate log missing")
        detail = ", ".join(failures) if failures else f"database_age={age_hours:.1f}h"
        producer_results.append({
            "id": producer["id"],
            "status": "critical" if failures else "ok",
            "detail": detail,
        })

    statuses = [item["status"] for item in host_results + producer_results]
    overall = "critical" if "critical" in statuses else "warn" if "warn" in statuses else "ok"
    return {
        "checked_at": snapshot.get("checked_at", now.isoformat()),
        "overall": overall,
        "hosts": host_results,
        "producers": producer_results,
    }


def print_human(report: dict[str, Any]) -> None:
    print(f"City2 fleet: {report['overall'].upper()} ({report['checked_at']})")
    for host in report["hosts"]:
        print(f"  host     {host['id']:<18} {host['status']:<8} {host['detail']}")
    for producer in report["producers"]:
        print(f"  producer {producer['id']:<18} {producer['status']:<8} {producer['detail']}")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    parser.add_argument("--snapshot", type=Path, help="evaluate a saved probe snapshot")
    parser.add_argument("--offline", action="store_true", help="validate inventory without host access")
    parser.add_argument("--json", action="store_true", dest="as_json")
    args = parser.parse_args()

    try:
        manifest = load_json(args.manifest)
        validate_manifest(manifest)
    except (OSError, json.JSONDecodeError, ManifestError) as error:
        print(f"fleet: invalid manifest: {error}", file=sys.stderr)
        return 2

    if args.offline:
        active = sum(item["state"] == "active" for item in manifest["producers"])
        parked = sum(item["state"] == "parked" for item in manifest["producers"])
        result = {"manifest": "valid", "hosts": len(manifest["hosts"]), "active": active, "parked": parked}
        print(json.dumps(result, indent=2) if args.as_json else f"fleet manifest: valid; hosts={len(manifest['hosts'])}; active={active}; parked={parked}")
        return 0

    try:
        snapshot = load_json(args.snapshot) if args.snapshot else collect_snapshot(manifest)
    except (OSError, json.JSONDecodeError, ManifestError) as error:
        print(f"fleet: invalid snapshot: {error}", file=sys.stderr)
        return 2
    report = evaluate(manifest, snapshot)
    if args.as_json:
        print(json.dumps(report, indent=2))
    else:
        print_human(report)
    return 2 if report["overall"] == "critical" else 1 if report["overall"] == "warn" else 0


if __name__ == "__main__":
    raise SystemExit(main())
