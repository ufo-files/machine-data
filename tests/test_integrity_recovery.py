import unittest
from portuguese_pipeline.qa import mask_protected, restore_protected, compare_translation

class IntegrityRecoveryTests(unittest.TestCase):
    def test_measurement_units_survive_printed_line_breaks(self):
        for source, target in [('26 me-\ntros', '26 meters'), ('30 quiló-\nmetros', '30 kilometres'), ('35 mi-\nlhas', '35 miles')]:
            self.assertFalse(any(f['check'] == 'measurements' for f in compare_translation(source, target)))
            self.assertTrue(any(f['check'] == 'measurements' for f in compare_translation(source, target.replace('26', '27').replace('30', '31').replace('35', '36'))))
        self.assertTrue(any(f['check'] == 'measurements' for f in compare_translation('26 me-\ntros', '26 miles')))

    def test_british_distance_units_preserve_measurements(self):
        for source, target in [('700 metros', '700 metres'), ('20 quilómetros', '20 kilometers')]:
            self.assertFalse(any(f['check'] == 'measurements' for f in compare_translation(source, target)))
        self.assertTrue(any(f['check'] == 'measurements' for f in compare_translation('700 metros', '700 kilometres')))

    def test_separate_page_number_does_not_start_measurement_range(self):
        source = '18\n a 55mm de distância focal'
        self.assertFalse(any(f['check'] == 'measurements' for f in compare_translation(source, '18\n at a focal length of 55mm')))
        self.assertTrue(any(f['check'] == 'measurements' for f in compare_translation('18 a\n55mm', '55mm')))

    def test_letter_spaced_months_are_not_distances(self):
        for source, target in [('28 M a i 84', '28 May 84'), ('25 J u l\n78', '25 Jul 78')]:
            self.assertFalse(any(f['severity'] == 'error' for f in compare_translation(source, target)))
            self.assertTrue(any(f['check'] == 'dates' for f in compare_translation(source, target.replace('84', '85').replace('78', '79'))))
        self.assertTrue(any(f['check'] == 'measurements' for f in compare_translation('28 m', '28 May 84')))

    def test_reference_suffix_is_not_an_enumerated_calendar_day(self):
        for suffix in ('91', '17'):
            source = f'NEFP.GEU/003/{suffix},\n26 de abril de 1991'
            target = f'NEFP.GEU/003/{suffix},\nApril 26, 1991'
            self.assertFalse(any(f['check'] == 'dates' for f in compare_translation(source, target)))
            self.assertTrue(any(f['check'] == 'dates' for f in compare_translation(source, target.replace('April 26', 'April 25'))))
        self.assertTrue(any(f['check'] == 'dates' for f in compare_translation('17, 26 de abril de 1991', 'April 26, 1991')))

    def test_para_date_range_preserves_all_days(self):
        source = 'CODA de 17 para 19 de julho de 1991.'
        self.assertFalse(any(f['check'] == 'dates' for f in compare_translation(source, 'CODA from July 17 to 19, 1991.')))
        for target in ('July 18 to 19, 1991', 'July 17 and 19, 1991', 'July 17 to 20, 1991'):
            self.assertTrue(any(f['check'] == 'dates' for f in compare_translation(source, target)))

    def test_spaced_words_do_not_invent_gram_measurements(self):
        examples = [
            ('4 g r a n d e s plotes', '4 large plots'),
            ('210 g r a u s', '210 degrees'),
            ('1\nG o s t a r i a de novos contatos', '1\nI would like new contacts'),
            ('2 0 0 4\nM O D E L O DE FICHA', '2004\nFORM TEMPLATE'),
        ]
        for source, target in examples:
            with self.subTest(source=source):
                self.assertFalse(any(f['check'] == 'measurements' for f in compare_translation(source, target)))
                self.assertTrue(any(f['check'] == 'measurements' for f in compare_translation(source, target + '; 4 g')))
        for target in ('4 plots', '5 g'):
            self.assertTrue(any(f['check'] == 'measurements' for f in compare_translation('4 g', target)))
        self.assertTrue(any(f['check'] == 'measurements' for f in compare_translation('4 m', '5 meters')))

    def test_spaced_miles_still_protect_distance(self):
        source = '35 m i l h a s'
        self.assertFalse(any(f['check'] == 'measurements' for f in compare_translation(source, '35 miles')))
        for target in ('35 meters', '30 miles'):
            self.assertTrue(any(f['check'] == 'measurements' for f in compare_translation(source, target)))

    def test_measurement_ranges_survive_page_line_wrapping(self):
        for source, target in [('500 to\n 600 meters', '500 to 600 meters'),
                               ('1.20 a\n 1.40 metros', '1.20 to 1.40 meters'),
                               ('1,800 and\n 2,000 meters', '1,800 and 2,000 meters')]:
            self.assertFalse(any(f['check'] == 'measurements' for f in compare_translation(source, target)))
            changed = target.replace('600', '900').replace('1.40', '1.50').replace('2,000', '3,000')
            self.assertTrue(any(f['check'] == 'measurements' for f in compare_translation(source, changed)))

    def test_ocr_feet_units_retain_value_and_unit(self):
        for source in ['150 pes', '150 pês', '150 pés', '150 pe']:
            self.assertFalse(any(f['check'] == 'measurements' for f in compare_translation(source, '150 feet')))
            for changed in ['150 meters', '250 feet']:
                self.assertTrue(any(f['check'] == 'measurements' for f in compare_translation(source, changed)))

    def test_nothing_preserves_portuguese_negative_concord(self):
        for source, target in [('Sem nada a relatar.', 'Nothing to report.'),
                               ('Na 180 não tem nada.', 'At 180 there is nothing.')]:
            self.assertFalse(any(f['check'] == 'negation' for f in compare_translation(source, target)))
            self.assertTrue(any(f['check'] == 'negation' for f in compare_translation(source, target.replace('nothing', 'something').replace('Nothing', 'Something'))))
        self.assertTrue(any(f['check'] == 'negation' for f in compare_translation('sem confirmação', 'nothing confirmed')))

    def test_numeric_identifier_does_not_split_an_alphanumeric_fragment(self):
        for source in ['359/25MM', '0&79/33HH', 'LUPORMACNO B?.)892/329C405/27']:
            masked, replacements = mask_protected(source)
            self.assertEqual(restore_protected(masked, replacements), (source, []))
            self.assertEqual(restore_protected(source, replacements), (source, []))
        masked, replacements = mask_protected('File 405/27')
        self.assertEqual(restore_protected(masked, replacements), ('File 405/27', []))
        self.assertEqual(restore_protected('File 405/28', replacements)[1], ['405/27'])

    def test_full_ocr_dates_preserve_values_across_missing_or_extra_spaces(self):
        examples = [('06 de Marçode 1997', 'March 6, 1997'),
                    ('MG,10de marçode 1997', 'MG, March 10, 1997'),
                    ('Brasília, 21 de junho de 1 978', 'Brasília, June 21, 1978'),
                    ('São Paulo 17 d e o u t u b r o d e 19 89', 'São Paulo, October 17, 1989'),
                    ('No dia 19 de j a\nn e i r o de 1968', 'On January 19, 1968'),
                    ('Rio, 2 3 de fevereiro de 1980', 'Rio, February 23, 1980')]
        for source, target in examples:
            with self.subTest(source=source):
                self.assertFalse(any(f['check'] == 'dates' for f in compare_translation(source, target)))
                changed = target.replace('1997', '1998').replace('1978', '1979').replace('1989', '1990').replace('1968', '1969').replace('1980', '1981')
                self.assertTrue(any(f['check'] == 'dates' for f in compare_translation(source, changed)))

    def test_date_followed_by_time_does_not_invent_a_year(self):
        for source, target in [('29 de abril, 22h', 'April 29, 10:00 PM'),
                               ('8 de maio, 11h', 'May 8, 11 a.m.')]:
            self.assertFalse(any(f['check'] == 'dates' for f in compare_translation(source, target)))
        self.assertTrue(any(f['check'] == 'dates' for f in compare_translation('29 de abril de 2010', 'April 29, 10:00 PM')))

    def test_attributive_measurement_retains_value(self):
        self.assertFalse(any(f['check'] == 'measurements' for f in compare_translation('entrevista de 45 minutos', 'a 45-minute interview')))
        self.assertTrue(any(f['check'] == 'measurements' for f in compare_translation('entrevista de 45 minutos', 'a 15-minute interview')))

    def test_margo_ocr_month_requires_full_portuguese_date_context(self):
        self.assertFalse(any(f['check'] == 'dates' for f in compare_translation('10 de Margo de 1997', 'March 10, 1997')))
        self.assertTrue(any(f['check'] == 'dates' for f in compare_translation('10 de Margo de 1997', 'March 11, 1997')))

    def test_sem_can_translate_to_explicit_negative_or_negative_adjective(self):
        for source, target, changed in [('sem confirmação', 'unconfirmed', 'confirmed'),
                                        ('sem identificação', 'unidentified', 'identified'),
                                        ('sem saber', 'did not know', 'did know'),
                                        ('sem nenhum pelo', 'with no hair', 'with hair')]:
            self.assertFalse(any(f['check'] == 'negation' for f in compare_translation(source, target)))
            self.assertTrue(any(f['check'] == 'negation' for f in compare_translation(source, changed)))

    def test_italian_correspondence_date_preserves_its_calendar_value(self):
        source = 'Roma, 3 dicembre 1975'
        self.assertFalse(any(f['check'] == 'dates' for f in compare_translation(source, 'Rome, December 3, 1975')))
        self.assertTrue(any(f['check'] == 'dates' for f in compare_translation(source, 'Rome, December 4, 1975')))

    def test_unmanned_and_nothing_ever_preserve_explicit_negation(self):
        pairs = [('Aeronave não-tripulada.', 'Unmanned aircraft.', 'Manned aircraft.'),
                 ('Nada nunca acontece.', 'Nothing ever happens.', 'Things happen.')]
        for source, correct, changed in pairs:
            self.assertFalse(any(f['check'] == 'negation' for f in compare_translation(source, correct)))
            self.assertTrue(any(f['check'] == 'negation' for f in compare_translation(source, changed)))

    def test_urls_are_preserved_as_literals_and_changes_are_rejected(self):
        url = 'https://example.gov.br/gestao-de-pessoas/COMDABRA.pdf?id=12&lang=pt#secao'
        source = f'Consulte ({url}).'
        masked, replacements = mask_protected(source)
        self.assertEqual(list(replacements.values()), [url])
        self.assertEqual(restore_protected(masked, replacements), (source, []))
        self.assertFalse(any(f['check'] == 'urls' for f in compare_translation(source, f'See ({url}).')))
        for target in [url.replace('pessoas', 'people'), url.replace('id=12', 'id=13'), 'See the website.']:
            self.assertTrue(any(f['check'] == 'urls' for f in compare_translation(source, target)))

    def test_urls_keep_balanced_parentheses_and_repeated_occurrences(self):
        url = 'https://example.org/Arquivo_(Brasil)'
        masked, replacements = mask_protected(f'{url}; ({url}).')
        self.assertEqual(list(replacements.values()), [url])
        self.assertEqual(restore_protected(masked, replacements)[0], f'{url}; ({url}).')
        self.assertTrue(any(f['check'] == 'urls' for f in compare_translation(f'{url} {url}', url)))

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

    def test_cannot_preserves_negation_and_negative_concord(self):
        pairs = [('Não pode observar.', 'Cannot observe.'),
                 ('Não pode observar nenhum objeto.', 'Cannot observe any object.')]
        for source, target in pairs:
            self.assertFalse(any(f['check']=='negation' for f in compare_translation(source, target)))
            self.assertTrue(any(f['check']=='negation' for f in compare_translation(source, target.replace('Cannot', 'Can'))))

    def test_english_day_first_dates_and_short_years(self):
        source = '13 Mai 96'
        for target in ['May 13, 96', '13 May 96', '13 May 1996', 'May 13, 1996']:
            self.assertFalse(any(f['check']=='dates' for f in compare_translation(source, target)))
            self.assertTrue(any(f['check']=='dates' for f in compare_translation(source, target.replace('13', '14'))))
        self.assertFalse(any(f['check']=='dates' for f in compare_translation('13 Ago 96', '13 Aug. 1996')))

    def test_polite_pois_nao_is_affirmative_without_hiding_factual_negation(self):
        self.assertFalse(any(f['severity']=='error' for f in compare_translation('Pois não, vamos lá.', "Certainly, let's go ahead.")))
        self.assertTrue(any(f['severity']=='error' for f in compare_translation('Pois não, vamos lá.', "No, let's go ahead.")))
        self.assertTrue(any(f['check']=='negation' for f in compare_translation('Pois não havia tempo.', 'Because there was time.')))

    def test_exception_phrase_preserves_exception_and_independent_negation(self):
        source = 'Não houve explicação, a não ser para o tremor.'
        self.assertFalse(any(f['severity'] == 'error' for f in compare_translation(
            source, 'There was no explanation, except for the tremor.')))
        self.assertTrue(any(f['check'] == 'idiomatic-exception' for f in compare_translation(
            source, 'There was no explanation for the tremor.')))
        self.assertTrue(any(f['check'] == 'negation' for f in compare_translation(
            source, 'There was an explanation, except for the tremor.')))
