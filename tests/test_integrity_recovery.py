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

    def test_letter_spaced_minutes_are_not_metres(self):
        source = 'permaneceu a 15 m i n u t o s .'
        self.assertFalse(any(f['check']=='measurements' for f in compare_translation(source, 'remained at 15 minutes.')))
        for target in ['remained at 20 minutes.', 'remained at 15 meters.']:
            self.assertTrue(any(f['check']=='measurements' for f in compare_translation(source, target)))

    def test_enumerated_dates_preserve_middle_days_and_abbreviated_dates(self):
        source = '22, 23 e 24 de janeiro de 1996; 29 Jan 96'
        for target in ['January 22, 23 and 24, 1996; January 29, 1996',
                       'January 22 to 24, 1996; January 29, 1996']:
            self.assertFalse(any(f['check']=='dates' for f in compare_translation(source, target)))
        for target in ['January 22 and 24, 1996; January 29, 1996',
                       'January 22 to 24, 1996; January 28, 1996']:
            self.assertTrue(any(f['check']=='dates' for f in compare_translation(source, target)))

    def test_discrete_weekday_dates_do_not_imply_intermediate_days(self):
        source='20 (sábado) e 22 de janeiro de 1996'
        self.assertFalse(any(f['check']=='dates' for f in compare_translation(source, 'January 20 and 22, 1996')))
        self.assertTrue(any(f['check']=='dates' for f in compare_translation(source, 'January 20 to 22, 1996')))

    def test_portuguese_miles_and_letter_spaced_date_year(self):
        source='entre 10 e 12 milhas; 180 milhas'
        self.assertFalse(any(f['check']=='measurements' for f in compare_translation(source, 'between 10 and 12 miles; 180 miles')))
        self.assertTrue(any(f['check']=='measurements' for f in compare_translation(source, 'between 10 and 15 miles; 180 miles')))
        date='30 de j u n h o de 2 0 0 4'
        self.assertFalse(any(f['check']=='dates' for f in compare_translation(date, 'June 30, 2004')))
        self.assertTrue(any(f['check']=='dates' for f in compare_translation(date, 'June 30, 2005')))

    def test_letter_spaced_abbreviated_date(self):
        source='DE 30 J U N 2 0 0 4'
        self.assertFalse(any(f['check']=='dates' for f in compare_translation(source, 'June 30, 2004')))
        self.assertTrue(any(f['check']=='dates' for f in compare_translation(source, 'July 30, 2004')))

    def test_abbreviated_date_with_portuguese_prepositions(self):
        for source in ['10 de Mai 96', '10 de Mai. de 1996', '10 Mai 1996']:
            self.assertFalse(any(f['check']=='dates' for f in compare_translation(source, 'May 10, 1996')))
            self.assertTrue(any(f['check']=='dates' for f in compare_translation(source, 'May 11, 1996')))
