import json
import tempfile
import unittest
from pathlib import Path

from scripts.build_catalog import build, classify_phrase, comparison_key


class ClassificationTests(unittest.TestCase):
    def test_normalizes_identity_keys(self):
        self.assertEqual(comparison_key("Dr. J. Allen Hynek"), "j allen hynek")

    def test_rejects_document_heading_as_person(self):
        self.assertIsNone(classify_phrase("CONGRESSIONAL TRAVEL REQUEST"))
        self.assertIsNone(classify_phrase("Additional Details"))

    def test_classifies_strong_shapes(self):
        self.assertEqual(classify_phrase("Holloman Air Force Base")[0], "location")
        self.assertEqual(classify_phrase("University of Colorado")[0], "organization")
        self.assertEqual(classify_phrase("Kelly Johnson")[0], "person")


class CatalogTests(unittest.TestCase):
    def test_reads_supported_sources_and_keeps_evidence(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            collection = root / "Example"
            collection.mkdir()
            for number in (1, 2):
                metadata = {"schema": "ufo-files-archive-ocr/v1", "source_file": f"source-{number}.pdf", "source_bytes": 100}
                body = "Federal Bureau of Investigation worked with Kelly Johnson.\nKelly Johnson discussed UFO reports.\n"
                (collection / f"source-{number}.txt").write_text(json.dumps(metadata) + "\n\n" + body, encoding="utf-8")
            output = root / "catalog.json"
            catalog = build(root, output, 100, 100)
            self.assertEqual(catalog["counts"]["documents"], 2)
            self.assertTrue(any(entity["canonicalName"] == "Kelly Johnson" for entity in catalog["entities"]))
            self.assertTrue(all(edge["evidence"] for edge in catalog["edges"]))
            self.assertTrue(output.exists())


if __name__ == "__main__":
    unittest.main()
