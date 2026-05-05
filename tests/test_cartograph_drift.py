import tempfile
import unittest
from pathlib import Path

from tools.cartograph_drift import build_map, classify_meaning_pressure, import_corpus


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
            self.assertTrue((out / "meaning-pressure.md").exists())
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

    def test_names_likely_meaning_pressure_from_evidence(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "context"
            out = Path(tmp) / "output"
            root.mkdir()
            (root / "2026-01-10-agent.md").write_text(
                "2026-01-10\nAn agent is a loop that wakes up and reads local state.\n",
                encoding="utf-8",
            )
            (root / "2026-02-14-agent.md").write_text(
                "2026-02-14\nAn agent is now a browser controller or desktop operator.\n",
                encoding="utf-8",
            )
            (root / "2026-03-20-agent.md").write_text(
                "2026-03-20\nThe word agent is stretched between pipeline, autonomous loop, and outsourced responsibility.\n",
                encoding="utf-8",
            )

            result = build_map("agent", root, out)
            pressures = {item["pressure"] for item in classify_meaning_pressure(result)}
            report = (out / "meaning-pressure.md").read_text(encoding="utf-8")

            self.assertIn("broadening", pressures)
            self.assertIn("capture", pressures)
            self.assertIn("ambiguity", pressures)
            self.assertIn("# Meaning Pressure: agent", report)
            self.assertIn("This report names likely semantic pressure", report)

    def test_imports_blog_and_knowledge_corpus_with_manifest(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            blog = root / "blog"
            knowledge = root / "knowledge"
            out = root / "context" / "seed-corpus"
            blog.mkdir()
            (knowledge / "research").mkdir(parents=True)
            (blog / "2026-05-01-loop.md").write_text(
                "2026-05-01\nThe loop changed how agent work felt.\n",
                encoding="utf-8",
            )
            (knowledge / "research" / "2026-05-02-loop.txt").write_text(
                "2026-05-02\nKnowledge notes describe agent drift.\n",
                encoding="utf-8",
            )
            (knowledge / "ignore.json").write_text("{}", encoding="utf-8")

            result = import_corpus([blog, knowledge], out)

            self.assertEqual(result["documents_imported"], 2)
            self.assertTrue((out / "blog" / "2026-05-01-loop.md").exists())
            self.assertTrue((out / "knowledge" / "research" / "2026-05-02-loop.txt").exists())
            self.assertFalse((out / "knowledge" / "ignore.json").exists())
            self.assertTrue((out / "import-manifest.json").exists())


if __name__ == "__main__":
    unittest.main()
