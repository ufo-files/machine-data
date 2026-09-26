import unittest
from portuguese_pipeline.qa import mask_protected, restore_protected, compare_translation

class IntegrityRecoveryTests(unittest.TestCase):
    def test_numbered_placeholder_format_damage_is_recoverable(self):
        for damaged in ['UFO_PROTECTED_001__', '__UFO_PROTECTED_01__', 'UFO-PROTECTED-001', '__UFO PROTECTED 001__']:
            with self.subTest(damaged=damaged):
                self.assertEqual(restore_protected(damaged, {'__UFO_PROTECTED_001__':'COMDABRA'}), ('COMDABRA', []))

    def test_original_literal_can_be_preserved_without_a_placeholder(self):
        self.assertEqual(restore_protected('COMDABRA', {'__UFO_PROTECTED_000__':'COMDABRA'}), ('COMDABRA', []))

    def test_missing_literal_cannot_match_inside_another_word(self):
        self.assertEqual(restore_protected('GEIPAN', {'__UFO_PROTECTED_000__':'PAN'})[1], ['PAN'])

    def test_unknown_number_cannot_be_guessed(self):
        text, missing = restore_protected('UFO_PROTECTED_099__', {'__UFO_PROTECTED_000__':'COMDABRA'})
        self.assertIn('099', text)
        self.assertEqual(missing, ['COMDABRA'])

    def test_unchanged_numeric_date_keeps_its_source_locale(self):
        errors = [x for x in compare_translation('04/05/1969', '04/05/1969') if x['check']=='dates']
        self.assertEqual(errors, [])

    def test_changed_numeric_date_is_still_rejected(self):
        errors = [x for x in compare_translation('04/05/1969', '05/05/1969') if x['check']=='dates']
        self.assertTrue(errors)

    def test_dot_separated_date_is_recognized(self):
        errors = [x for x in compare_translation('24.09.1986', 'September 24, 1986') if x['check']=='dates']
        self.assertEqual(errors, [])

    def test_masking_nested_tokens_is_single_pass(self):
        source='COMDABRA.pdf'
        masked, replacements=mask_protected(source)
        self.assertEqual(len(replacements), 1)
        self.assertEqual(restore_protected(masked,replacements), (source, []))

    def test_explicit_negative_contraction_is_not_lost_negation(self):
        self.assertFalse(any(x['check']=='negation' for x in compare_translation('Não era visível.', "It wasn't visible.")))
