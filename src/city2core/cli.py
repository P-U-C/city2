"""Operator CLI for the City2 Core ledger."""

from __future__ import annotations

import argparse
from pathlib import Path
import sys

from .archive import (
    create_backup,
    generate_checkpoint_key,
    restore_backup,
    verify_backup,
)
from .core import Core, CoreError
from .model import canonical_json
from .store import Store, StoreError


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="city2-core")
    sub = parser.add_subparsers(dest="command", required=True)

    init = sub.add_parser("init", help="initialize a new Core database")
    init.add_argument("--db", required=True)

    status = sub.add_parser("status", help="verify and report Core state")
    status.add_argument("--db", required=True)

    migrate = sub.add_parser("migrate", help="apply reviewed forward-only migrations")
    migrate.add_argument("--db", required=True)

    export = sub.add_parser("export", help="write a deterministic event JSONL export")
    export.add_argument("--db", required=True)
    export.add_argument("--output", required=True)

    keygen = sub.add_parser(
        "keygen", help="generate a local Ed25519 checkpoint keypair"
    )
    keygen.add_argument("--private-key", required=True)
    keygen.add_argument("--public-key", required=True)

    backup = sub.add_parser("backup", help="create a signed local backup proof")
    backup.add_argument("--db", required=True)
    backup.add_argument("--output", required=True)
    backup.add_argument("--signing-key", required=True)
    backup.add_argument("--key-version", required=True)

    verify = sub.add_parser(
        "verify-backup", help="verify a local backup and checkpoint"
    )
    verify.add_argument("--archive", required=True)
    verify.add_argument("--trusted-key", required=True)

    restore = sub.add_parser("restore", help="restore into an empty directory")
    restore.add_argument("--archive", required=True)
    restore.add_argument("--output-dir", required=True)
    restore.add_argument("--trusted-key", required=True)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        if args.command == "init":
            with Store.initialize(args.db) as store:
                result = Core(store).status()
        elif args.command == "status":
            with Store.open(args.db) as store:
                result = Core(store).status()
        elif args.command == "migrate":
            with Store.migrate(args.db) as store:
                result = Core(store).status()
        elif args.command == "export":
            output = Path(args.output)
            if output.exists():
                raise StoreError(f"refusing to overwrite export: {output}")
            output.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
            with Store.open(args.db) as store:
                output.write_text(
                    "".join(canonical_json(event) + "\n" for event in store.events()),
                    encoding="utf-8",
                )
                result = {
                    "events": int(store.meta("global_sequence")),
                    "output": str(output),
                    "sha256": __import__("hashlib")
                    .sha256(output.read_bytes())
                    .hexdigest(),
                }
        elif args.command == "keygen":
            generate_checkpoint_key(args.private_key, args.public_key)
            result = {"private_key": args.private_key, "public_key": args.public_key}
        elif args.command == "backup":
            with Store.open(args.db) as store:
                result = create_backup(
                    store,
                    args.output,
                    signing_key=args.signing_key,
                    key_version=args.key_version,
                )
        elif args.command == "verify-backup":
            checkpoint, manifest = verify_backup(
                args.archive, trusted_public_key=args.trusted_key
            )
            result = {"verified": True, "checkpoint": checkpoint, "manifest": manifest}
        elif args.command == "restore":
            result = restore_backup(
                args.archive, args.output_dir, trusted_public_key=args.trusted_key
            )
        else:  # pragma: no cover
            raise AssertionError(args.command)
    except (CoreError, StoreError, ValueError) as error:
        print(canonical_json({"ok": False, "error": str(error)}), file=sys.stderr)
        return 1
    print(canonical_json({"ok": True, "result": result}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
