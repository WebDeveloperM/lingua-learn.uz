import re

from django.db import connection
from django.test import SimpleTestCase, TestCase
from django.test.utils import CaptureQueriesContext

from accounts.models import User

from . import vocabulary
from .models import Category, Course, KeyWord, Part
from .support import make_key_words
from .vocabulary import parse_key_words

PENCIL = {'word': 'pencil', 'transcription': 'ˈpensl', 'meaning': 'qalam', 'example': 'She borrowed a pencil from her friend.'}
STUDENT = {'word': 'student', 'transcription': 'ˈstjuːdənt', 'meaning': "talaba, o'quvchi", 'example': 'The new student joined our class.'}
TENNIS = {'word': 'tennis', 'transcription': '', 'meaning': 'tennis', 'example': 'They play tennis every weekend.'}
WATER = {'word': 'water', 'transcription': '', 'meaning': 'suv', 'example': ''}


class ParseTests(SimpleTestCase):
    def parse(self, text):
        entries, problems = parse_key_words(text)
        self.assertEqual(problems, [], text)
        return entries

    def test_a_line_reads_the_way_the_card_looks(self):
        self.assertEqual(self.parse('pencil /ˈpensl/ | qalam | She borrowed a pencil from her friend.'), [PENCIL])

    def test_only_the_word_and_its_meaning_are_needed(self):
        self.assertEqual(self.parse('water | suv'), [WATER])
        self.assertEqual(self.parse('tennis | tennis | They play tennis every weekend.'), [TENNIS])
        self.assertEqual(self.parse('pencil /ˈpensl/ | qalam'), [{**PENCIL, 'example': ''}])

    def test_several_lines_keep_their_order_and_blank_lines_are_skipped(self):
        text = (
            "pencil /ˈpensl/ | qalam | She borrowed a pencil from her friend.\r\n\r\n"
            "   \r\n"
            "student /ˈstjuːdənt/ | talaba, o'quvchi | The new student joined our class.\n"
            "tennis | tennis | They play tennis every weekend.\n"
        )
        self.assertEqual(self.parse(text), [PENCIL, STUDENT, TENNIS])

    def test_the_transcription_may_have_its_own_column(self):
        expected = [{'word': 'window', 'transcription': 'ˈwɪndəʊ', 'meaning': 'deraza', 'example': ''}]
        self.assertEqual(self.parse('window | /ˈwɪndəʊ/ | deraza'), expected)
        self.assertEqual(self.parse('window | deraza | /ˈwɪndəʊ/'), expected)

    def test_a_row_copied_from_a_spreadsheet_works(self):
        self.assertEqual(self.parse('pencil\t/ˈpensl/\tqalam\tShe borrowed a pencil from her friend.'), [PENCIL])
        self.assertEqual(self.parse('pencil\tˈpensl\tqalam\tShe borrowed a pencil from her friend.'), [PENCIL])
        self.assertEqual(self.parse('pencil\tˈpensl\tqalam\t'), [{**PENCIL, 'example': ''}])  # an empty last cell
        self.assertEqual(self.parse('tennis\t\ttennis\tThey play tennis every weekend.'), [TENNIS])  # an empty cell
        self.assertEqual(self.parse('water\t\tsuv\t'), [WATER])
        self.assertEqual(self.parse('water\t\tsuv'), [WATER])

    def test_four_columns_typed_with_bars_work_too(self):
        self.assertEqual(self.parse('pencil | /ˈpensl/ | qalam | She borrowed a pencil from her friend.'), [PENCIL])
        self.assertEqual(self.parse('tennis | | tennis | They play tennis every weekend.'), [TENNIS])
        self.assertEqual(self.parse('water | | suv | '), [WATER])

    def test_an_empty_column_between_the_word_and_the_meaning_is_skipped(self):
        self.assertEqual(self.parse('water | | suv'), [WATER])
        self.assertEqual(self.parse('water | suv |'), [WATER])
        self.assertEqual(self.parse('pencil /ˈpensl/ | | qalam'), [{**PENCIL, 'example': ''}])

    def test_words_of_several_words_and_slashes_inside_words(self):
        entries = self.parse('ice cream /aɪs kriːm/ | muzqaymoq | I like ice cream.\nand/or | va/yoki')
        self.assertEqual(entries[0], {
            'word': 'ice cream', 'transcription': 'aɪs kriːm', 'meaning': 'muzqaymoq', 'example': 'I like ice cream.'})
        self.assertEqual(entries[1], {'word': 'and/or', 'transcription': '', 'meaning': 'va/yoki', 'example': ''})

    def test_uzbek_apostrophes_and_other_letters_are_kept_as_typed(self):
        entries = self.parse("headache /ˈhedeɪk/ | bosh og‘rig'i | He has a bad headache today.")
        self.assertEqual(entries[0]['meaning'], "bosh og‘rig'i")

    def test_extra_spaces_are_squeezed_out(self):
        entries = self.parse('  ice   cream  /aɪs  kriːm/  |  muzqaymoq   shirin  |  I  like  it.  ')
        self.assertEqual(entries, [{
            'word': 'ice cream', 'transcription': 'aɪs kriːm', 'meaning': 'muzqaymoq shirin', 'example': 'I like it.'}])

    def test_nothing_typed_is_no_words(self):
        for text in ('', None, '\n\n  \n'):
            self.assertEqual(parse_key_words(text), ([], []))

    def test_what_is_wrong_is_said_with_the_line_number(self):
        entries, problems = parse_key_words('pencil | qalam\n\nwindow\nplane /pleɪn/ |\n | suv\nok | yes')
        self.assertEqual([entry['word'] for entry in entries], ['pencil', 'ok'])
        self.assertEqual(len(problems), 3)
        self.assertTrue(problems[0].startswith("3-qator: «window» uchun o'zbekcha ma'no yozilmagan"))
        self.assertTrue(problems[1].startswith("4-qator: «plane» uchun o'zbekcha ma'no yozilmagan"))
        self.assertTrue(problems[2].startswith("5-qator: so'z yozilmagan"))
        self.assertIn(vocabulary.FORMAT, problems[0])

    def test_too_many_columns_are_refused(self):
        entries, problems = parse_key_words('a | b | c | d | e')
        self.assertEqual(entries, [])
        self.assertTrue(problems[0].startswith("1-qator: ko'pi bilan 4 ta ustun"))

    def test_too_long_texts_are_refused(self):
        for name, line in (
            ('word', 'x' * 101 + ' | meaning'), ('transcription', 'a /' + 'x' * 101 + '/ | meaning'),
            ('meaning', 'a | ' + 'x' * 201), ('example', 'a | b | ' + 'x' * 301),
        ):
            entries, problems = parse_key_words(line)
            self.assertEqual(entries, [], name)
            self.assertEqual(problems, [f"1-qator: {vocabulary.LABELS[name]} {vocabulary.LIMITS[name]} belgidan oshmasligi kerak."], name)
        at_the_limit = f"{'x' * 100} | {'y' * 200} | {'z' * 300}"
        self.assertEqual(len(self.parse(at_the_limit)), 1)

    def test_a_part_cannot_have_more_words_than_the_limit(self):
        many = '\n'.join(f'word{number} | ma\'no' for number in range(vocabulary.MAX_WORDS + 1))
        entries, problems = parse_key_words(many)
        self.assertEqual(len(entries), vocabulary.MAX_WORDS + 1)
        self.assertEqual(problems, [f"Bitta Part'da {vocabulary.MAX_WORDS} tadan ko'p so'z bo'lmaydi (hozir {vocabulary.MAX_WORDS + 1} ta)."])
        self.assertEqual(len(self.parse('\n'.join(many.splitlines()[:vocabulary.MAX_WORDS]))), vocabulary.MAX_WORDS)

    def test_a_long_list_of_mistakes_is_cut_short(self):
        entries, problems = parse_key_words('\n'.join(f'word{number}' for number in range(12)))
        self.assertEqual(entries, [])
        self.assertEqual(len(problems), vocabulary.MAX_PROBLEMS + 1)
        self.assertEqual(problems[-1], f'…va yana {12 - vocabulary.MAX_PROBLEMS} ta xato bor.')


class KeyWordModelTests(TestCase):
    def setUp(self):
        course = Course.objects.create(title='Listening', category=Category.LISTENING, short_description='x')
        self.part = Part.objects.create(course=course, number=1, name='One')
        self.other = Part.objects.create(course=course, number=2, name='Two')

    def test_the_words_come_in_the_order_they_were_given(self):
        make_key_words(self.part, [PENCIL, STUDENT, TENNIS])
        self.assertEqual([word.word for word in self.part.key_words.all()], ['pencil', 'student', 'tennis'])

    def test_words_that_share_an_order_number_keep_the_order_they_were_made_in(self):
        KeyWord.objects.create(part=self.part, order=0, **STUDENT)
        KeyWord.objects.create(part=self.part, order=0, **PENCIL)
        self.assertEqual([word.word for word in self.part.key_words.all()], ['student', 'pencil'])

    def test_a_word_is_known_by_its_word_and_meaning(self):
        self.assertEqual(str(make_key_words(self.part, [PENCIL])[0]), 'pencil — qalam')

    def test_deleting_a_part_deletes_its_words_and_only_its_own(self):
        make_key_words(self.part, [PENCIL])
        make_key_words(self.other, [WATER])
        self.part.delete()
        self.assertEqual(KeyWord.objects.get().word, 'water')


class KeyVocabularyPageTests(TestCase):
    """What a student sees under the exercises of a Part: the "Key vocabulary" button and the words it opens."""

    @classmethod
    def setUpTestData(cls):
        cls.student = User.objects.create_user(email='s@t.uz', password='StrongPass123!')
        cls.listening = Course.objects.create(title='Listening', category=Category.LISTENING, short_description='x')
        cls.reading = Course.objects.create(title='Reading', category=Category.READING, short_description='y')
        cls.part = Part.objects.create(course=cls.listening, number=1, name='Short replies', icon='💬')
        cls.bare = Part.objects.create(course=cls.listening, number=2, name='Gap filling', icon='✍️')
        make_key_words(cls.part, [PENCIL, STUDENT, TENNIS, WATER])

    def page(self, course=None):
        return self.client.get((course or self.listening).get_absolute_url())

    def test_the_button_says_how_many_words_there_are(self):
        response = self.page()
        self.assertContains(response, '<details class="vocab">', count=1)
        self.assertContains(response, '<summary class="vocab-pill">', count=1)
        self.assertContains(response, 'Key vocabulary · 4 words', count=1)
        self.assertContains(response, 'Hide vocabulary · 4 words', count=1)
        self.assertContains(response, '📚</span> Key vocabulary')
        self.assertContains(response, '📖</span> Hide vocabulary')

    def test_one_word_is_not_plural(self):
        make_key_words(self.bare, [WATER])
        response = self.page()
        self.assertContains(response, 'Key vocabulary · 1 word</span>')
        self.assertNotContains(response, '1 words')

    def test_a_part_without_words_has_no_button(self):
        response = self.page()
        html = response.content.decode()
        gap_filling = html.split('Part 2 · Gap filling')[1]
        self.assertNotIn('vocab', gap_filling.split('</section>')[0])

    def test_every_word_is_a_card_with_its_transcription_meaning_and_example(self):
        html = self.page().content.decode()
        cards = re.findall(r'<li class="vocab-card">(.*?)</li>', html, re.S)
        self.assertEqual(len(cards), 4)
        self.assertIn('<strong>pencil</strong> <span class="vocab-ipa">/ˈpensl/</span>', cards[0])
        self.assertIn('<p class="vocab-meaning">qalam</p>', cards[0])
        self.assertIn('<p class="vocab-example">She borrowed a pencil from her friend.</p>', cards[0])
        self.assertIn("talaba, o&#x27;quvchi", cards[1])

    def test_a_word_without_a_transcription_or_an_example_shows_neither(self):
        html = self.page().content.decode()
        water = re.findall(r'<li class="vocab-card">(.*?)</li>', html, re.S)[3]
        self.assertIn('<strong>water</strong></p>', water)
        self.assertNotIn('vocab-ipa', water)
        self.assertNotIn('vocab-example', water)
        self.assertNotIn('//', water)

    def test_the_words_come_in_the_order_the_admin_typed_them(self):
        html = self.page().content.decode()
        words = re.findall(r'<li class="vocab-card">\s*<p class="vocab-word"><strong>(.*?)</strong>', html)
        self.assertEqual(words, ['pencil', 'student', 'tennis', 'water'])

    def test_there_is_a_search_box_that_the_script_shows(self):
        response = self.page()
        self.assertContains(response, 'placeholder="Search a word, Uzbek meaning or example…"')
        self.assertRegex(response.content.decode(), r'<input type="search" class="vocab-search"[^>]* hidden>')
        self.assertContains(response, 'aria-label="Search the key vocabulary of Part 1"')
        self.assertContains(response, 'class="vocab-status"')
        self.assertContains(response, '/static/js/vocabulary.js')

    def test_the_script_is_loaded_only_when_there_are_words(self):
        KeyWord.objects.all().delete()
        response = self.page()
        self.assertNotContains(response, 'vocabulary.js')
        self.assertNotContains(response, 'Key vocabulary')

    def test_it_works_the_same_in_reading(self):
        part = Part.objects.create(course=self.reading, number=1, name='Gap filling', icon='✍️')
        make_key_words(part, [PENCIL, STUDENT])
        response = self.page(self.reading)
        self.assertTemplateUsed(response, 'courses/practice.html')
        self.assertContains(response, 'Key vocabulary · 2 words', count=1)
        self.assertContains(response, '<li class="vocab-card">', count=2)

    def test_the_words_of_one_part_stay_in_its_card(self):
        make_key_words(self.bare, [{**WATER, 'word': 'unique-word'}])
        html = self.page().content.decode()
        first, second = html.split('Part 2 · Gap filling')
        self.assertNotIn('unique-word', first)
        self.assertIn('unique-word', second)
        self.assertNotIn('pencil', second)

    def test_what_the_admin_typed_cannot_change_the_page(self):
        make_key_words(self.bare, [{
            'word': '<script>alert(1)</script>', 'transcription': '<b>x</b>', 'meaning': '"><img src=x>',
            'example': '<i>italic</i>',
        }])
        response = self.page()
        self.assertNotContains(response, '<script>alert(1)</script>')
        self.assertNotContains(response, '<img src=x>')
        self.assertNotContains(response, '<b>x</b>')
        self.assertContains(response, '&lt;script&gt;alert(1)&lt;/script&gt;')

    def test_students_see_it_too_when_logged_in(self):
        self.client.force_login(self.student)
        self.assertContains(self.page(), 'Key vocabulary · 4 words')

    def test_the_number_of_queries_does_not_grow_with_the_words(self):
        with CaptureQueriesContext(connection) as few:
            self.page()
        make_key_words(self.bare, [{**WATER, 'word': f'w{number}'} for number in range(40)])
        make_key_words(self.part, [{**WATER, 'word': f'v{number}'} for number in range(40)])
        with CaptureQueriesContext(connection) as many:
            self.page()
        self.assertEqual(len(few), len(many))
