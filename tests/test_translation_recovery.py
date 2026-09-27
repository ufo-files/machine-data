import unittest
import tempfile
from pathlib import Path
from unittest.mock import patch
from portuguese_pipeline.extract import command
from portuguese_pipeline.qa import compare_translation
from portuguese_pipeline.translation import MLXBackend, translate_text


class TranslationRecoveryTests(unittest.TestCase):
    def test_generation_budget_tracks_source_size_and_respects_cap(self):
        class Tokenizer:
            def encode(self, text): return list(text)
            def apply_chat_template(self, messages, **kwargs): return messages[-1]['content']
        backend = MLXBackend.__new__(MLXBackend)
        backend._tokenizer = Tokenizer()
        backend._model = backend._sampler = None
        backend.max_tokens = 2048
        observed = []
        def generate(*args, **kwargs):
            observed.append(kwargs['max_tokens'])
            return "translated"
        backend._generate = generate
        backend.translate_raw("Translate:\n\nÁ")
        backend.translate_raw("Translate:\n\n" + "x" * 2000)
        self.assertEqual(observed, [128, 2048])

    def test_invented_placeholder_is_an_integrity_error(self):
        self.assertTrue([f for f in compare_translation("Texto", "__UFO_PROTECTED_012__") if f['check'] == 'unresolved-placeholder'])
        self.assertFalse([f for f in compare_translation("__UFO_PROTECTED_012__", "__UFO_PROTECTED_012__") if f['check'] == 'unresolved-placeholder'])

    def test_formal_certificate_date_preserves_day_month_and_year(self):
        source = "Aos 16 dias do mês de julho do ano de 1997"
        self.assertFalse([f for f in compare_translation(source, "On July 16, 1997") if f['check'] == 'dates'])
        self.assertTrue([f for f in compare_translation(source, "On July 15, 1997") if f['check'] == 'dates'])

    def test_ordinal_and_notification_dates_preserve_values(self):
        for source, target in [("1º de junho de 2017", "June 1, 2017"), ("dia 09 do mês de julho do ano de 1997", "July 9, 1997")]:
            self.assertFalse([f for f in compare_translation(source, target) if f['check'] == 'dates'])
            self.assertTrue([f for f in compare_translation(source, target.replace('2017', '2018').replace('1997', '1998')) if f['check'] == 'dates'])

    def test_shared_month_date_range_checks_both_ends(self):
        source = "no período de 02 a 31 de julho de 1997"
        target = "from July 2 to 31, 1997"
        self.assertFalse([f for f in compare_translation(source, target) if f['check'] == 'dates'])
        self.assertTrue([f for f in compare_translation(source, target.replace('2 to', '3 to')) if f['check'] == 'dates'])

    def test_date_ranges_with_weekday_and_ordinals_preserve_both_ends(self):
        source = "20 (sábado) a 22 de janeiro de 1996"
        target = "January 20th to 22nd, 1996"
        self.assertFalse([f for f in compare_translation(source, target) if f['check'] == 'dates'])
        self.assertTrue([f for f in compare_translation(source, target.replace('20th', '21st')) if f['check'] == 'dates'])

    def test_negative_concord_accepts_not_any_in_same_clause(self):
        source = "A testemunha não confirmou a presença de nenhum objeto."
        for target in ["The witness did not confirm the presence of any object.",
                       "The witness didn't confirm any object."]:
            self.assertFalse([f for f in compare_translation(source, target) if f['check'] == 'negation'])
        for target in ["The witness confirmed the presence of an object.",
                       "The witness did not return. Any object was confirmed.",
                       "The witness did not return; any object was confirmed."]:
            self.assertTrue([f for f in compare_translation(source, target) if f['check'] == 'negation'])

    def test_typed_ordinal_and_ocr_colon_dates_preserve_values(self):
        for source, target, changed in [
            ("1o de novembro de 1957", "November 1, 1957", "November 10, 1957"),
            ("20 de janeiro de: 1996", "January 20, 1996", "January 21, 1996"),
        ]:
            self.assertFalse([f for f in compare_translation(source, target) if f['check'] == 'dates'])
            self.assertTrue([f for f in compare_translation(source, changed) if f['check'] == 'dates'])

    def test_historical_august_spelling_preserves_date(self):
        source = "No dia 20 de agôsto de 1948"
        self.assertFalse([f for f in compare_translation(source, "On August 20, 1948") if f['check'] == 'dates'])
        self.assertTrue([f for f in compare_translation(source, "On August 21, 1948") if f['check'] == 'dates'])

    def test_measurement_range_checks_both_endpoints(self):
        source = "a 25 a 30 metros"
        for target in ["at 25 to 30 meters", "at 25–30 m"]:
            self.assertFalse([f for f in compare_translation(source, target) if f['check'] == 'measurements'])
        for target in ["at 25 to 90 meters", "at 26 to 30 meters", "at 25 meters"]:
            self.assertTrue([f for f in compare_translation(source, target) if f['check'] == 'measurements'])

    def test_ocr_spaced_dates_keep_exact_values(self):
        examples = [("São Paulo, 13 de A b r i l de 2.004", "São Paulo, April 13, 2004"), ("2 0 / 0 8 / 1 9 6 9 e 0 6 / 0 1 / 7 7", "20/08/1969 and 06/01/77")]
        for source, target in examples:
            self.assertFalse([f for f in compare_translation(source, target) if f['check'] == 'dates'])
        self.assertTrue([f for f in compare_translation(examples[0][0], "April 14, 2004") if f['check'] == 'dates'])

    def test_extraction_finds_tools_in_worker_virtualenv(self):
        with tempfile.TemporaryDirectory() as directory:
            tool = Path(directory) / "ocrmypdf"
            tool.write_text("#!/bin/sh\nexit 0\n")
            tool.chmod(0o700)
            with patch("portuguese_pipeline.extract.sys.executable", str(Path(directory) / "python")):
                self.assertEqual(command("ocrmypdf"), str(tool))

    def test_literal_retry_preserves_identifiers_without_markers(self):
        class Backend:
            def translate_raw(self, prompt):
                return "RIC 4.470/2009" if prompt.startswith("Translate the following") else "UFO"
        result = translate_text(Backend(), "RIC 4.470/2009", official_identifiers=["RIC 4.470/2009"])
        self.assertEqual(result.text, "RIC 4.470/2009")
        self.assertEqual(result.status, "machine-unreviewed")

    def test_literal_retry_repairs_changed_measurement_without_missing_tokens(self):
        class Backend:
            def translate_raw(self, prompt):
                return "It was 50 m away." if prompt.startswith("Translate the following") else "It was 900 m away."
        result = translate_text(Backend(), "Estava a 50 m.")
        self.assertEqual(result.text, "It was 50 m away.")

    def test_literal_retry_does_not_accept_new_integrity_errors(self):
        class Backend:
            def translate_raw(self, prompt):
                return "RIC 4.470/2009 at 900 m" if prompt.startswith("Translate the following") else "UFO at 50 m"
        result = translate_text(Backend(), "RIC 4.470/2009 50 m", official_identifiers=["RIC 4.470/2009"])
        self.assertEqual(result.status, "failed-protected-token-check")

    def test_long_translation_retries_without_losing_protected_text(self):
        text = ('A FAB permanece visível. ' * 50).strip()
        class Backend:
            def translate_raw(self, prompt):
                source = prompt.split('\n\n', 1)[1]
                return 'Summary.' if len(source) > 800 else source
        result = translate_text(Backend(), text)
        self.assertEqual(result.text, text)
        self.assertEqual(result.status, 'machine-unreviewed')

    def test_retry_does_not_accept_missing_protected_text(self):
        class Backend:
            def translate_raw(self, prompt):
                return 'Summary.'
        result = translate_text(Backend(), ('A FAB permanece visível. ' * 50).strip())
        self.assertEqual(result.status, 'failed-protected-token-check')


if __name__ == '__main__':
    unittest.main()
