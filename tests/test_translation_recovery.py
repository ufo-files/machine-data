import unittest
import tempfile
from pathlib import Path
from unittest.mock import patch
from portuguese_pipeline.extract import command
from portuguese_pipeline.qa import compare_translation
from portuguese_pipeline.translation import translate_text


class TranslationRecoveryTests(unittest.TestCase):
    def test_extraction_finds_tools_in_worker_virtualenv(self):
        with tempfile.TemporaryDirectory() as directory:
            tool = Path(directory) / "ocrmypdf"
            tool.write_text("#!/bin/sh\nexit 0\n")
            tool.chmod(0o700)
            with patch("portuguese_pipeline.extract.sys.executable", str(Path(directory) / "python")):
                self.assertEqual(command("ocrmypdf"), str(tool))

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
