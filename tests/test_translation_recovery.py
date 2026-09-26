import unittest
from portuguese_pipeline.qa import compare_translation
from portuguese_pipeline.translation import translate_text


class TranslationRecoveryTests(unittest.TestCase):
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
