from __future__ import annotations

import importlib.util
from pathlib import Path
import unittest


SCRIPT = (
    Path(__file__).parents[1]
    / "infra"
    / "buzz"
    / "scripts"
    / "normalize-owner-pubkey.py"
)
SPEC = importlib.util.spec_from_file_location("normalize_owner_pubkey", SCRIPT)
assert SPEC and SPEC.loader
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


class NormalizeOwnerPubkeyTests(unittest.TestCase):
    def test_hex_is_normalized(self) -> None:
        self.assertEqual(MODULE.normalize("AB" * 32), "ab" * 32)

    def test_private_nsec_is_rejected(self) -> None:
        with self.assertRaisesRegex(ValueError, "forbidden"):
            MODULE.normalize("nsec1not-a-public-key")

    def test_invalid_npub_checksum_is_rejected(self) -> None:
        with self.assertRaisesRegex(ValueError, "checksum"):
            MODULE.normalize("npub1" + "q" * 58)

    def test_non_identity_is_rejected(self) -> None:
        with self.assertRaises(ValueError):
            MODULE.normalize("owner")


if __name__ == "__main__":
    unittest.main()
