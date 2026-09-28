from __future__ import annotations

import base64
import io
import json
import subprocess
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path

from portuguese_pipeline.entities import extract_entities, extract_events
from portuguese_pipeline.ids import stable_id
from portuguese_pipeline.language import detect_language
from portuguese_pipeline.pipeline import PIPELINE_VERSION, build_canonical, build_translation, process_source, retranslate_existing, sha256_file
from portuguese_pipeline.qa import compare_translation, mask_protected, restore_protected
from portuguese_pipeline.translation import TranslationResult, translate_text
from portuguese_pipeline.extract import Extraction, ExtractedUnit
from scripts.portuguese_ssh_worker import REMOTE_DISCOVER, REMOTE_FINALIZE, REMOTE_MARK, REMOTE_READ_REVIEW


FIXTURES = Path(__file__).parent / "fixtures" / "portuguese"
RELATIVE_PATH = "Camara-dos-Deputados/RIC-3515-2018/representative.txt"


class FakeBackend:
    method = "fixture"
    model = "deterministic-fixture-translator"
    model_revision = "1"
    runtime_version = "fixture-1"

    def translate_raw(self, prompt: str) -> str:
        source = prompt.split("\n\n", 1)[1]
        replacements = {
            "RELATÓRIO OFICIAL": "OFFICIAL REPORT",
            "Em ": "On ",
            "o Capitão João da Silva observou um OVNI a": "Captain João da Silva observed a UFO at",
            "nas coordenadas": "at coordinates",
            "O objeto não pousou e nunca foi identificado pela Força Aérea Brasileira.":
                "The object did not land and was never identified by Força Aérea Brasileira.",
            "Tabela": "Table",
            "Unidade": "Unit",
            "Medida": "Measurement",
            "Altura": "Height",
        }
        for old, new in replacements.items():
            source = source.replace(old, new)
        return source


class FailingBackend(FakeBackend):
    def translate_raw(self, prompt: str) -> str:
        if "objeto" in prompt:
            raise RuntimeError("fixture failure")
        return super().translate_raw(prompt)


class UpdatedFakeBackend(FakeBackend):
    model_revision = "2"


def fixture_manifest(source: Path) -> dict:
    manifest = json.loads((FIXTURES / "manifest.json").read_text(encoding="utf-8"))
    record = manifest["items"][0]
    record["bytes"] = source.stat().st_size
    record["sha256"] = sha256_file(source)
    return manifest


class PortuguesePipelineTests(unittest.TestCase):
    def test_aircraft_model_and_spelled_out_speed(self):
        source = "F-16 a 2.400 quilômetros por hora; mais de 12 mil quilômetros por hora."
        target = "F-16 at 2,400 km/h; more than 12,000 km/h."
        self.assertFalse([f for f in compare_translation(source, target) if f["severity"] == "error"])
        for changed in (target.replace("2,400", "3,400"), target.replace("12,000", "12"), target.replace("km/h", "km")):
            self.assertTrue([f for f in compare_translation(source, changed) if f["check"] == "measurements"])
        self.assertTrue([f for f in compare_translation("F-16: de 16 a 2400 km/h", "F-16: 2400 km/h") if f["check"] == "measurements"])
        self.assertFalse([f for f in compare_translation("30 kms de Natal", "30 km from Natal") if f["severity"] == "error"])
        self.assertTrue([f for f in compare_translation("30 kms de Natal", "40 km from Natal") if f["check"] == "measurements"])

    def test_radio_flight_number_is_not_distance_range(self):
        source = "QD-460: Ciente. ACC: O 460 a 32 milhas, cruzando 175."
        target = "QD-460: Roger. ACC: 460 at 32 miles, passing through 175."
        self.assertFalse([f for f in compare_translation(source, target) if f["severity"] == "error"])
        self.assertTrue([f for f in compare_translation(source, target.replace("32 miles", "42 miles")) if f["check"] == "measurements"])
        self.assertTrue([f for f in compare_translation("QD-460: de 460 a 500 milhas", "QD-460: 500 miles") if f["check"] == "measurements"])
        self.assertTrue([f for f in compare_translation("460 a 500 milhas", "500 miles") if f["check"] == "measurements"])

    def test_radio_bearing_is_not_distance_range(self):
        source = "Tá na 240 a 40 m i l h a s"
        self.assertFalse([f for f in compare_translation(source, "On bearing 240 at 40 miles") if f["severity"] == "error"])
        self.assertTrue([f for f in compare_translation(source, "On bearing 240 at 50 miles") if f["check"] == "measurements"])
        self.assertTrue([f for f in compare_translation("de 240 a 400 milhas", "400 miles") if f["check"] == "measurements"])
        self.assertFalse([f for f in compare_translation("de 240 a 400 milhas", "240 to 400 miles") if f["severity"] == "error"])

    def test_original_spanish_dates_in_portuguese_collections(self):
        for source, target in [("11 de j u l i o de 1989", "July 11, 1989"),
                               ("12 de junio de 1989", "June 12, 1989"),
                               ("11 de julho de 1989", "July 11, 1989")]:
            self.assertFalse([f for f in compare_translation(source, target) if f["severity"] == "error"])
        self.assertTrue([f for f in compare_translation("11 de julio de 1989", "June 11, 1989") if f["check"] == "dates"])

    def test_spaced_unit_abbreviations_and_nautical_distances(self):
        for source, target in [("2.000 f t", "2,000 ft"), ("5 k m", "5 km"),
                               ("83 m i l h a s náuticas", "83 nautical miles")]:
            self.assertFalse([f for f in compare_translation(source, target) if f["severity"] == "error"])
        for source, target in [("83 milhas náuticas", "83 miles"), ("5 k m", "6 km")]:
            self.assertTrue([f for f in compare_translation(source, target) if f["check"] == "measurements"])

    def test_original_note_heading_is_not_added_translator_commentary(self):
        self.assertFalse([f for f in compare_translation("NOTA: objeto azul", "NOTE: blue object") if f["severity"] == "error"])
        self.assertTrue([f for f in compare_translation("objeto azul", "NOTE: blue object") if f["check"] == "translator-commentary"])
        self.assertTrue([f for f in compare_translation("NOTA: objeto azul", "NOTE: blue object\nNOTE: invented explanation") if f["check"] == "translator-commentary"])

    def test_embedded_remote_worker_scripts_compile(self):
        for name, source in (
            ("discover", REMOTE_DISCOVER),
            ("finalize", REMOTE_FINALIZE),
            ("mark", REMOTE_MARK),
            ("read-review", REMOTE_READ_REVIEW),
        ):
            compile(source, f"<{name}>", "exec")

    def test_launch_agent_supports_mlx_subprocesses_and_filters_web_chrome(self):
        template = (Path(__file__).parents[1] / "launchd" / "com.ufo-files.portuguese-worker.plist.template").read_text()
        self.assertIn("<key>KeepAlive</key>", template)
        self.assertIn("<integer>300</integer>", template)
        self.assertNotIn("NumberOfProcesses", template)
        self.assertNotIn("NumberOfFiles", template)
        self.assertIn('name.startswith("favicon")', REMOTE_DISCOVER)
        self.assertIn("info.st_size < 16384", REMOTE_DISCOVER)

    def test_remote_publish_swaps_a_complete_artifact_directory(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            output_rel = Path("Brazil-Government-UAP/paired/source/item")
            final_root = root / "transcripts" / output_rel
            final_root.mkdir(parents=True)
            (final_root / "old.txt").write_text("old", encoding="utf-8")
            upload = root / ".state/mac-processor-portuguese/uploads/claim-test"
            upload.mkdir(parents=True)
            first = upload / "00-document.json"
            second = upload / "01-canonical.txt"
            first.write_text('{"new": true}\n', encoding="utf-8")
            second.write_text("português\n", encoding="utf-8")
            items = [
                {
                    "temporary": str(first),
                    "final": str(final_root / "document.json"),
                    "sha256": sha256_file(first),
                },
                {
                    "temporary": str(second),
                    "final": str(final_root / "pt-BR/canonical.txt"),
                    "sha256": sha256_file(second),
                },
            ]
            payload = base64.urlsafe_b64encode(json.dumps(items).encode()).decode()
            previous_argv = sys.argv
            try:
                sys.argv = ["remote-finalize", str(root), "claim-test", str(output_rel), payload]
                exec(REMOTE_FINALIZE, {})
            finally:
                sys.argv = previous_argv
            self.assertFalse((final_root / "old.txt").exists())
            self.assertEqual((final_root / "pt-BR/canonical.txt").read_text(encoding="utf-8"), "português\n")
            self.assertFalse(upload.exists())

    def test_language_routing_prefers_portuguese(self):
        detected = detect_language("O objeto não foi identificado pela equipe.")
        self.assertEqual(detected["code"], "pt-BR")

    def test_protected_identifiers_and_markers_round_trip(self):
        text = "RIC-3515/2018 arquivo.pdf [ILEGÍVEL] 23°33'00\" S"
        masked, replacements = mask_protected(text, ["RIC-3515/2018"])
        self.assertNotIn("RIC-3515/2018", masked)
        restored, missing = restore_protected(masked, replacements)
        self.assertEqual(restored, text)
        self.assertEqual(missing, [])

    def test_official_codes_and_abbreviations_are_protected_but_ovni_is_translatable(self):
        text = "RIC 4470/2009 da FAB registrou um OVNI."
        masked, replacements = mask_protected(text)
        protected = set(replacements.values())
        self.assertIn("RIC 4470/2009", protected)
        self.assertIn("FAB", protected)
        self.assertIn("OVNI", masked)
        restored, missing = restore_protected(masked, replacements)
        self.assertEqual(restored, text)
        self.assertEqual(missing, [])

    def test_quality_checks_cover_dates_numbers_coordinates_negation_and_redaction(self):
        source = 'Em 19/05/1986, não estava a 12 m em 23°33\'00" S. [ILEGÍVEL]'
        good = 'On 19/05/1986, it was not at 12 m at 23°33\'00" S. [ILEGÍVEL]'
        self.assertEqual(compare_translation(source, good), [])
        checks = {item["check"] for item in compare_translation(source, "It was present.")}
        self.assertTrue({"dates", "measurements", "coordinates", "numbers", "negation", "redactions"} <= checks)

    def test_named_dates_and_translated_measurement_units_compare_semantically(self):
        source = "Em 4 de julho de 2011, estava a 1600 metros."
        target = "On July 4, 2011, it was at 1600 meters."
        self.assertEqual(compare_translation(source, target), [])

    def test_confirmation_question_is_distinct_from_polite_affirmation(self):
        source = "Qualquer um entende, pois não?"
        self.assertFalse([f for f in compare_translation(source, "Anyone understands, right?") if f["severity"] == "error"])
        self.assertFalse([f for f in compare_translation(source, "Anyone understands, isn't that so?") if f["severity"] == "error"])
        for target in ("Anyone understands.", "Certainly! Anyone understands."):
            self.assertTrue([f for f in compare_translation(source, target) if f["check"] == "confirmation-question"])
        self.assertTrue([f for f in compare_translation("Pois não!", "Right?") if f["check"] == "idiomatic-affirmation"])

    def test_more_than_ever_preserves_comparison_and_separate_negation(self):
        for phrase in ("mais do que nunca", "mais que nunca"):
            source = f"Agora {phrase}, precisamos observar. Nunca vi isso."
            correct = "Now more than ever, we need to observe. I never saw this."
            self.assertFalse([f for f in compare_translation(source, correct) if f["severity"] == "error"])
            missing_negation = "Now more than ever, we need to observe. I saw this."
            self.assertTrue([f for f in compare_translation(source, missing_negation) if f["check"] == "negation"])
            missing_comparison = "Now we need to observe. I never saw this."
            self.assertTrue([f for f in compare_translation(source, missing_comparison) if f["check"] == "idiomatic-comparison"])

    def test_historical_and_bibliographic_dates_preserve_actual_days(self):
        pairs = [
            ("1º de junho de 1850", "June 1, 1850", "June 2, 1850"),
            ("22/09/1881", "September 22, 1881", "September 23, 1881"),
            ("14 de abril, 1914", "April 14, 1914", "April 15, 1914"),
            ("p.\n8, 14 de abril, 1914", "p. 8, April 14, 1914", "p. 8, April 15, 1914"),
            ("January 20. 1996", "January 20, 1996", "January 21, 1996"),
        ]
        for source, correct, changed in pairs:
            with self.subTest(source=source):
                self.assertFalse([f for f in compare_translation(source, correct) if f["check"] == "dates"])
                self.assertTrue([f for f in compare_translation(source, changed) if f["check"] == "dates"])

    def test_embedded_french_dates_preserve_each_day(self):
        pairs = [
            ("25 avril 1977", "April 25, 1977", "April 26, 1977"),
            ("du 4 décembre 1949 au 14 avril 1950", "from December 4, 1949 to April 14, 1950",
             "from December 4, 1949 to April 15, 1950"),
            ("19 et 20 mai 1986", "May 19 and 20, 1986", "May 20, 1986"),
        ]
        for source, correct, changed in pairs:
            with self.subTest(source=source):
                self.assertFalse([f for f in compare_translation(source, correct) if f["check"] == "dates"])
                self.assertTrue([f for f in compare_translation(source, changed) if f["check"] == "dates"])

    def test_quality_checks_distinguish_ordinals_coordinates_and_semantic_negation(self):
        source = "Art. 14º. Objetos voadores não identificados em 20° 30' O."
        target = "Article 14. Unidentified flying objects at 20° 30' W."
        self.assertEqual(compare_translation(source, target), [])

    def test_quality_checks_accept_english_numeric_date_order_and_ignore_am_times(self):
        source = "Em 13/01/1996 às 8:30h, mediu 01,50 metros."
        target = "On 1/13/1996 at 8:30 am, it measured 1.5 meters."
        self.assertEqual(compare_translation(source, target), [])

    def test_quality_checks_normalize_translated_ordinals(self):
        self.assertEqual(compare_translation("Captura 1º e 2º criatura", "Capture 1st and 2nd creature"), [])

    def test_name_check_tracks_people_without_flagging_translated_titles(self):
        self.assertEqual(compare_translation("O Sr. Chico Alencar falou.", "Mr. Chico Alencar spoke."), [])
        checks = {
            item["check"]
            for item in compare_translation("O Sr. Chico Alencar falou.", "Mr. Charles spoke.")
        }
        self.assertIn("names", checks)
        self.assertEqual(compare_translation("Senhor Presidente", "Mr. President"), [])

    def test_translator_commentary_is_flagged(self):
        findings = compare_translation("4", "4\n\n(Translation: four)")
        self.assertIn("translator-commentary", {item["check"] for item in findings})

    def test_paired_ids_and_partial_failure_are_explicit(self):
        extraction = Extraction(
            medium="document",
            mode="fixture",
            engine="fixture",
            units=(ExtractedUnit(1, "Primeiro trecho.\n\nO objeto não pousou."),),
        )
        canonical = build_canonical("doc-fixture", {"country": "BR"}, extraction, "2026-01-01T00:00:00Z")
        translation, qa = build_translation(canonical, FailingBackend(), "2026-01-01T00:00:00Z")
        source_ids = [item["segment_id"] for item in canonical["pages"][0]["segments"]]
        target_ids = [item["segment_id"] for item in translation["pages"][0]["segments"]]
        self.assertEqual(source_ids, target_ids)
        self.assertEqual(translation["translation"]["review_status"], "partial")
        self.assertEqual(translation["pages"][0]["segments"][1]["status"], "failed")
        self.assertTrue(qa["segment_count_match"])

    def test_large_translation_reports_content_free_progress(self):
        extraction = Extraction(
            medium="media",
            mode="fixture",
            engine="fixture",
            units=tuple(
                ExtractedUnit(index, "Trecho de áudio.", start_ms=index * 1000, end_ms=(index + 1) * 1000)
                for index in range(25)
            ),
        )
        canonical = build_canonical("doc-media", {"country": "BR"}, extraction, "2026-01-01T00:00:00Z")
        output = io.StringIO()
        with redirect_stdout(output):
            build_translation(canonical, FakeBackend(), "2026-01-01T00:00:00Z")
        self.assertIn("translation working: 25/25 segment(s)", output.getvalue())
        self.assertNotIn("Trecho de áudio", output.getvalue())

    def test_partial_translation_is_resumable_processing_state(self):
        source = FIXTURES / "representative.txt"
        manifest = fixture_manifest(source)
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            result = process_source(
                source,
                relative_path=RELATIVE_PATH,
                manifest=manifest,
                output_root=root / "output",
                work_root=root / "work",
                backend=FailingBackend(),
            )
            self.assertEqual(result["status"], "partial")
            output = Path(result["output_dir"])
            provenance = json.loads((output / "provenance.json").read_text(encoding="utf-8"))
            document = json.loads((output / "document.json").read_text(encoding="utf-8"))
            self.assertEqual(provenance["status"], "partial")
            self.assertEqual(document["processing_status"], "partial")

    def test_entities_and_events_do_not_double_count_translation(self):
        extraction = Extraction(
            medium="document",
            mode="fixture",
            engine="fixture",
            units=(ExtractedUnit(1, "Em 19/05/1986, observou um OVNI em Varginha."),),
        )
        canonical = build_canonical("doc-fixture", {"country": "BR"}, extraction, "2026-01-01T00:00:00Z")
        translation, _ = build_translation(canonical, FakeBackend(), "2026-01-01T00:00:00Z")
        entities = extract_entities(canonical, translation)
        ufo = next(item for item in entities["entities"] if item["name"] == "UFO")
        self.assertEqual(ufo["mention_count"], 1)
        self.assertEqual(ufo["evidence_languages"], ["en", "pt-BR"])
        events = extract_events(canonical, translation)["events"]
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0]["document_origin_country"], "BR")
        self.assertEqual(events[0]["event_location"], "Varginha")

    def test_events_dedupe_equivalent_portuguese_and_english_date_order(self):
        extraction = Extraction(
            medium="document",
            mode="fixture",
            engine="fixture",
            units=(ExtractedUnit(1, "Em 13/01/1996, observou um OVNI em Varginha."),),
        )
        canonical = build_canonical("doc-fixture", {"country": "BR"}, extraction, "2026-01-01T00:00:00Z")
        translation, _ = build_translation(canonical, FakeBackend(), "2026-01-01T00:00:00Z")
        translated = translation["pages"][0]["segments"][0]
        translated["text"] = "On 1/13/1996, they observed a UFO in Varginha."
        events = extract_events(canonical, translation)["events"]
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0]["normalized_date"], "1996-01-13")
        self.assertEqual(events[0]["evidence_languages"], ["en", "pt-BR"])

    def test_end_to_end_output_is_idempotent_and_preserves_canonical_text(self):
        source = FIXTURES / "representative.txt"
        manifest = fixture_manifest(source)
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            first = process_source(
                source,
                relative_path=RELATIVE_PATH,
                manifest=manifest,
                output_root=root / "output",
                work_root=root / "work",
                backend=FakeBackend(),
            )
            self.assertEqual(first["status"], "complete")
            output = Path(first["output_dir"])
            canonical = json.loads((output / "pt-BR" / "canonical.json").read_text(encoding="utf-8"))
            translation = json.loads((output / "en" / "translation.json").read_text(encoding="utf-8"))
            self.assertIn("OVNI", (output / "pt-BR" / "canonical.txt").read_text(encoding="utf-8"))
            self.assertIn("UFO", (output / "en" / "translation.txt").read_text(encoding="utf-8"))
            self.assertEqual(sha256_file(source), manifest["items"][0]["sha256"])
            self.assertEqual(canonical["detected_language"]["code"], "pt-BR")
            self.assertEqual(
                [s["segment_id"] for s in canonical["pages"][0]["segments"]],
                [s["segment_id"] for s in translation["pages"][0]["segments"]],
            )
            checked = subprocess.run(
                [
                    sys.executable,
                    str(Path(__file__).parents[1] / "scripts" / "check_portuguese_outputs.py"),
                    str(output),
                ],
                check=False,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
            )
            self.assertEqual(checked.returncode, 0, checked.stdout + checked.stderr)
            portuguese_before = (output / "pt-BR" / "canonical.txt").read_bytes()
            segment_id = canonical["pages"][0]["segments"][0]["segment_id"]
            subprocess.run(
                [
                    sys.executable,
                    str(Path(__file__).parents[1] / "scripts" / "review_portuguese_translation.py"),
                    str(output),
                    "--segment-id", segment_id,
                    "--decision", "reviewed",
                    "--reviewer", "fixture-reviewer",
                    "--note", "Fixture review completed.",
                ],
                check=True,
                stdout=subprocess.PIPE,
                text=True,
            )
            self.assertEqual((output / "pt-BR" / "canonical.txt").read_bytes(), portuguese_before)
            audit = json.loads((output / "translation-reviews.json").read_text(encoding="utf-8"))
            self.assertEqual(audit["reviews"][0]["segment_id"], segment_id)
            second = process_source(
                source,
                relative_path=RELATIVE_PATH,
                manifest=manifest,
                output_root=root / "output",
                work_root=root / "work",
                backend=FakeBackend(),
            )
            self.assertEqual(second["status"], "skipped-complete")
            retranslate_existing(output, UpdatedFakeBackend())
            self.assertEqual((output / "pt-BR" / "canonical.txt").read_bytes(), portuguese_before)
            updated = json.loads((output / "en" / "translation.json").read_text(encoding="utf-8"))
            self.assertEqual(updated["translation"]["model_revision"], "2")
            updated_provenance = json.loads((output / "provenance.json").read_text(encoding="utf-8"))
            self.assertEqual(updated_provenance["pipeline_version"], PIPELINE_VERSION)
            process_source(
                source,
                relative_path=RELATIVE_PATH,
                manifest=manifest,
                output_root=root / "output",
                work_root=root / "work",
                backend=UpdatedFakeBackend(),
                force=True,
            )
            preserved_audit = json.loads((output / "translation-reviews.json").read_text(encoding="utf-8"))
            self.assertEqual(preserved_audit["reviews"][0]["reviewer"], "fixture-reviewer")

    def test_source_hash_mismatch_stops_processing(self):
        source = FIXTURES / "representative.txt"
        manifest = fixture_manifest(source)
        manifest["items"][0]["sha256"] = "0" * 64
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            with self.assertRaisesRegex(RuntimeError, "SHA-256"):
                process_source(
                    source,
                    relative_path=RELATIVE_PATH,
                    manifest=manifest,
                    output_root=root / "output",
                    work_root=root / "work",
                    backend=FakeBackend(),
                )


if __name__ == "__main__":
    unittest.main()
