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
