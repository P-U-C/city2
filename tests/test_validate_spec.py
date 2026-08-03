import tempfile
import unittest
from pathlib import Path

from scripts.validate_spec import validate_markdown


class ValidateSpecTests(unittest.TestCase):
    def test_accepts_local_anchor_and_json(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            target = root / "target.md"
            target.write_text("# Target heading\n")
            source = root / "source.md"
            source.write_text(
                "[target](target.md#target-heading)\n\n"
                "```json\n{\"ok\": true}\n```\n"
            )
            self.assertEqual(validate_markdown(root, source), [])

    def test_rejects_missing_local_link(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "source.md"
            source.write_text("[missing](missing.md)\n")
            self.assertTrue(validate_markdown(root, source))

    def test_rejects_invalid_json(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "source.md"
            source.write_text("```json\n{not-json}\n```\n")
            self.assertTrue(validate_markdown(root, source))


if __name__ == "__main__":
    unittest.main()
