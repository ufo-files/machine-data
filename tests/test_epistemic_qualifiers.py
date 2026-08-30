import json
import subprocess
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "annotate_epistemic_qualifiers.py"


class EpistemicQualifierTests(unittest.TestCase):
    def annotate(self, lines):
        with tempfile.TemporaryDirectory(dir=ROOT) as directory:
            folder = Path(directory)
            transcript = folder / "example.tsv"
            transcript.write_text("start\tend\ttext\n" + "\n".join(f"{start}\t{end}\t{text}" for start, end, text in lines) + "\n", encoding="utf-8")
            output = folder / "annotations.jsonl"
            subprocess.run(["python3", str(SCRIPT), "--repository-root", str(ROOT), "--output", str(output), str(transcript)], check=True, capture_output=True, text=True)
            return [json.loads(line) for line in output.read_text(encoding="utf-8").splitlines()]

    def test_preserves_explicit_conjecture_and_binds_the_following_claim(self):
        rows = self.annotate([(0, 5000, "What I was told, and again, I'll preface this as conjecture, is that two craft were housed there.")])
        conjecture = next(row for row in rows if row["category"] == "explicit_conjecture")
        self.assertEqual(conjecture["scope"], "same_segment")
        self.assertIn("two craft", conjecture["claim_text"])
        self.assertEqual(conjecture["review_status"], "candidate")

    def test_marks_evidence_gap_without_removing_the_statement(self):
        rows = self.annotate([(0, 5000, "I haven't seen any evidence to suggest that there were functional craft.")])
        gap = next(row for row in rows if row["category"] == "evidence_not_reviewed")
        self.assertIn("functional craft", gap["claim_text"])
        self.assertEqual(gap["evidence_text"], "I haven't seen any evidence to suggest that there were functional craft.")

    def test_distinguishes_unknown_provenance_from_bare_belief(self):
        rows = self.annotate([(0, 4000, "I don't know how he got this intel, but he states the sites are connected."), (5000, 8000, "I think the documents combine fact and disinformation.")])
        self.assertEqual(rows[0]["category"], "knowledge_gap")
        self.assertEqual(rows[0]["confidence"], .94)
        belief = next(row for row in rows if row["category"] == "speaker_inference")
        self.assertEqual(belief["confidence"], .72)

    def test_cross_segment_scope_is_candidate_not_asserted(self):
        rows = self.annotate([(0, 900, "I'm not sure."), (1000, 5000, "Perhaps both facilities were involved.")])
        self.assertEqual(rows[0]["scope"], "next_segment_candidate")
        self.assertEqual(rows[0]["speaker_attribution"], "unresolved")
        self.assertLessEqual(rows[0]["confidence"], .82)
        self.assertEqual(rows[0]["claim_line"], 3)
        self.assertEqual((rows[0]["claim_start_ms"], rows[0]["claim_end_ms"]), (1000, 5000))

    def test_clause_final_qualifier_binds_to_preceding_claim(self):
        rows = self.annotate([(0, 4000, "So this is footage from Utah, I believe."), (4100, 7000, "And it was recorded in 4K.")])
        self.assertEqual(rows[0]["scope"], "preceding_clause")
        self.assertEqual(rows[0]["claim_text"], "So this is footage from Utah")

    def test_generic_sight_and_reported_commands_are_not_qualifiers(self):
        rows = self.annotate([(0, 3000, "I haven't seen Jake since last summer."), (3100, 6000, "I was told to close my eyes.")])
        self.assertEqual(rows, [])

    def test_evidence_gap_still_covers_explicit_source_material(self):
        rows = self.annotate([(0, 3000, "I haven't read the book, but the account sounds inconsistent.")])
        self.assertEqual(rows[0]["category"], "evidence_not_reviewed")

    def test_cli_rejects_missing_roots_and_input_overwrite(self):
        with tempfile.TemporaryDirectory(dir=ROOT) as directory:
            folder = Path(directory)
            missing = subprocess.run(["python3", str(SCRIPT), "--output", str(folder / "out.jsonl"), str(folder / "missing")], capture_output=True, text=True)
            self.assertNotEqual(missing.returncode, 0)
            transcript = folder / "example.tsv"
            original = "start\tend\ttext\n0\t1000\tI think this is a claim.\n"
            transcript.write_text(original, encoding="utf-8")
            overwrite = subprocess.run(["python3", str(SCRIPT), "--output", str(transcript), str(transcript)], capture_output=True, text=True)
            self.assertNotEqual(overwrite.returncode, 0)
            self.assertEqual(transcript.read_text(encoding="utf-8"), original)

    def test_non_claim_usage_is_left_unresolved(self):
        rows = self.annotate([(0, 3000, "I don't know how to pronounce this word.")])
        self.assertEqual(rows[0]["scope"], "unresolved")
        self.assertEqual(rows[0]["confidence"], .55)


if __name__ == "__main__":
    unittest.main()
