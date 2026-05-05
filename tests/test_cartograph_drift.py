import tempfile
import unittest
from pathlib import Path

from tools.cartograph_drift import build_map


class DriftCartographerTests(unittest.TestCase):
    def test_detects_date_to_date_neighbor_shift(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "context"
            out = Path(tmp) / "output"
            root.mkdir()
            (root / "2026-01-01-agent.md").write_text(
                "2026-01-01\nThe agent reads tasks and writes receipts in a loop.\n",
                encoding="utf-8",
            )
            (root / "2026-02-01-agent.md").write_text(
                "2026-02-01\nThe agent controls browser sessions and desktop tools.\n",
                encoding="utf-8",
            )

            result = build_map("agent", root, out)

            self.assertEqual(result["hit_count"], 2)
            self.assertIn(result["drift_level"], {"medium", "high"})
            self.assertTrue((out / "drift-map.json").exists())
            self.assertTrue((out / "drift-docket.md").exists())
            self.assertTrue((out / "drift-ledger.jsonl").exists())

    def test_detects_phrases_across_common_compound_separators(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "context"
            out = Path(tmp) / "output"
            root.mkdir()
            (root / "2026-03-01-local-ai.md").write_text(
                "2026-03-01\nLocal-AI meant models running on your own machine.\n",
                encoding="utf-8",
            )
            (root / "2026-04-01-local-ai.md").write_text(
                "2026-04-01\nLocal_AI was used for remote services with regional storage.\n",
                encoding="utf-8",
            )

            result = build_map("local AI", root, out)

            self.assertEqual(result["hit_count"], 2)
            self.assertEqual([bucket["date"] for bucket in result["dates"]], ["2026-03-01", "2026-04-01"])
            snippets = [
                example["snippet"]
                for bucket in result["dates"]
                for example in bucket["examples"]
            ]
            self.assertTrue(any("Local-AI" in snippet for snippet in snippets))
            self.assertTrue(any("Local_AI" in snippet for snippet in snippets))


if __name__ == "__main__":
    unittest.main()
