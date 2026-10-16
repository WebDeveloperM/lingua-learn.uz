import re

from django.urls import reverse

from courses.models import KeyWord, Part
from courses.support import make_key_words
from courses.vocabulary import MAX_WORDS

from .support import PanelTestCase, formset_data, rendered_form_data

PENCIL = {'word': 'pencil', 'transcription': 'ˈpensl', 'meaning': 'qalam', 'example': 'She borrowed a pencil from her friend.'}
STUDENT = {'word': 'student', 'transcription': 'ˈstjuːdənt', 'meaning': "talaba, o'quvchi", 'example': 'The new student joined our class.'}
WATER = {'word': 'water', 'transcription': '', 'meaning': 'suv', 'example': ''}
BLANK = {'word': '', 'transcription': '', 'meaning': '', 'example': ''}


def stored(part):
    return [
        {name: getattr(word, name) for name in ('word', 'transcription', 'meaning', 'example')}
        for word in part.key_words.all()
    ]


class PartPageVocabularyCardTests(PanelTestCase):
    """The Part page only summarises the words; they are edited on their own page."""

    def setUp(self):
        self.client.force_login(self.admin)
        self.part = Part.objects.create(course=self.course1, number=1, name='Short replies', icon='💬')
        self.url = reverse('panel:part_edit', args=[self.part.pk])
        self.words_url = reverse('panel:part_words', args=[self.part.pk])

    def test_a_part_without_words_offers_to_add_some(self):
        response = self.client.get(self.url)
        self.assertContains(response, 'Key vocabulary')
        self.assertContains(response, f'href="{self.words_url}" class="btn btn-primary btn-sm">➕ So\'z qo\'shish</a>')
        self.assertContains(response, "hali so'z yo'q")
        self.assertNotContains(response, "ta so'z</small>")

    def test_the_old_ways_of_entering_the_words_are_gone(self):
        response = self.client.get(self.url)
        self.assertNotContains(response, 'name="vocabulary"')
        self.assertNotContains(response, 'key_words_count')
        self.assertNotContains(response, "so'zlari soni")
        self.assertNotContains(response, 'so&#x27;zlari soni')

    def test_a_part_with_words_lists_some_of_them_and_links_to_the_editor(self):
        make_key_words(self.part, [{**WATER, 'word': f'word{number}'} for number in range(15)])
        response = self.client.get(self.url)
        self.assertContains(response, "15 ta so'z</small>")
        self.assertContains(response, f'href="{self.words_url}" class="btn btn-primary btn-sm">✏️ So\'zlarni tahrirlash</a>')
        self.assertContains(response, '<li>word0</li>')
        self.assertContains(response, '<li>word11</li>')
        self.assertNotContains(response, '<li>word12</li>')
        self.assertContains(response, 'va yana 3 ta')

    def test_few_words_are_all_shown_without_a_remainder(self):
        make_key_words(self.part, [PENCIL, STUDENT])
        response = self.client.get(self.url)
        self.assertContains(response, '<li>pencil</li>')
        self.assertContains(response, '<li>student</li>')
        self.assertNotContains(response, 'va yana')

    def test_a_part_that_does_not_exist_yet_has_no_vocabulary_card(self):
        response = self.client.get(reverse('panel:part_create', args=[self.course1.pk]))
        self.assertNotContains(response, 'Key vocabulary')

    def test_saving_the_part_does_not_touch_its_words(self):
        make_key_words(self.part, [PENCIL, STUDENT])
        data = {'number': 1, 'name': 'Renamed', 'icon': '💬', 'kind': 'choice', 'first_question_number': 1, 'instructions': ''}
        self.assertRedirects(self.client.post(self.url, data), self.url)
        self.assertEqual(stored(self.part), [PENCIL, STUDENT])


class PartWordsEditorTests(PanelTestCase):
    def setUp(self):
        self.client.force_login(self.admin)
        self.part = Part.objects.create(course=self.course1, number=1, name='Short replies', icon='💬')
        self.url = reverse('panel:part_words', args=[self.part.pk])

    def post(self, rows=(), initial=0, follow=False, **extra):
        return self.client.post(self.url, {**formset_data('words', list(rows), initial=initial), **extra}, follow=follow)

    def row(self, entry, word=None, **extra):
        """A posted row; for a word that is already saved pass it as `word`."""
        return {**({'id': word.pk} if word else {}), **entry, **extra}

    # ---------- the page ----------
    def test_a_part_without_words_opens_five_rows_to_type_in(self):
        response = self.client.get(self.url)
        self.assertTemplateUsed(response, 'panel/part_words.html')
        self.assertEqual(len(response.context['words'].forms), 5)
        self.assertContains(response, 'class="kw-row"', count=6)  # five rows and the template for "+"
        self.assertContains(response, 'Key vocabulary')
        self.assertContains(response, '💬 Part 1 · Short replies')

    def test_the_page_has_the_plus_button_and_the_row_machinery(self):
        response = self.client.get(self.url)
        self.assertContains(response, 'data-formset data-prefix="words" data-enter-next')
        self.assertContains(response, 'name="words-TOTAL_FORMS" value="5"')
        self.assertContains(response, '<template data-empty>')
        self.assertContains(response, '__prefix__')
        self.assertContains(response, "data-add>+ So'z qo'shish</button>")
        self.assertContains(response, 'data-remove', count=6)
        self.assertContains(response, '<button type="submit" class="btn btn-primary">Saqlash</button>')
        self.assertContains(response, f'href="{reverse("panel:part_edit", args=[self.part.pk])}" class="back-link"')
        self.assertContains(response, f'href="{self.course1.get_absolute_url()}#part-1"')

    def test_every_row_has_the_four_boxes_each_with_a_label_for_screen_readers(self):
        html = self.client.get(self.url).content.decode()
        for name, label in (('word', 'So&#x27;z'), ('transcription', 'Talaffuz'), ('meaning', 'Ma&#x27;no'), ('example', 'Misol')):
            self.assertIn(f'name="words-0-{name}"', html)
            self.assertRegex(html, rf'aria-label="{label}"[^>]*name="words-0-{name}"|name="words-0-{name}"[^>]*aria-label="{label}"')

    def test_the_saved_words_are_the_rows_with_one_spare_row_after_them(self):
        make_key_words(self.part, [PENCIL, STUDENT, WATER])
        response = self.client.get(self.url)
        words = response.context['words']
        self.assertEqual((words.initial_form_count(), len(words.forms)), (3, 4))
        self.assertEqual([form.initial['word'] for form in words.forms[:3]], ['pencil', 'student', 'water'])
        self.assertContains(response, 'value="ˈstjuːdənt"')
        self.assertContains(response, "3 ta so'z")

    def test_the_box_for_many_words_is_closed_until_it_is_needed(self):
        response = self.client.get(self.url)
        self.assertContains(response, '<details class="kw-bulk">')
        self.assertContains(response, 'name="bulk"')
        self.assertContains(response, "Ko'p so'zni birdaniga qo'shish")

    def test_unknown_parts_and_non_admins_are_turned_away(self):
        self.assertEqual(self.client.get(reverse('panel:part_words', args=[9999])).status_code, 404)
        make_key_words(self.part, [PENCIL])
        self.client.force_login(self.alice)
        self.assertNotEqual(self.client.get(self.url).status_code, 200)
        self.assertNotEqual(self.post([self.row(WATER)]).status_code, 200)
        self.assertEqual(stored(self.part), [PENCIL])
        self.client.logout()
        self.assertEqual(self.client.get(self.url).status_code, 302)

    # ---------- adding words with the rows ----------
    def test_new_rows_become_words_in_the_order_they_are_on_the_page(self):
        response = self.post([self.row(PENCIL), self.row(STUDENT), self.row(WATER)])
        self.assertRedirects(response, self.url)
        self.assertEqual(stored(self.part), [PENCIL, STUDENT, WATER])
        self.assertEqual([word.order for word in self.part.key_words.all()], [0, 1, 2])

    def test_saving_says_how_many_words_the_part_has(self):
        response = self.client.post(self.url, {**formset_data('words', [self.row(PENCIL), self.row(WATER)])}, follow=True)
        self.assertContains(response, "So&#x27;zlar saqlandi: Part 1 da jami 2 ta so&#x27;z.")

    def test_empty_rows_are_ignored(self):
        self.post([self.row(BLANK), self.row(PENCIL), self.row(BLANK), self.row(WATER), self.row(BLANK)])
        self.assertEqual(stored(self.part), [PENCIL, WATER])

    def test_only_the_word_and_its_meaning_are_needed(self):
        self.post([self.row({'word': 'tennis', 'transcription': '', 'meaning': 'tennis', 'example': ''})])
        self.assertEqual(stored(self.part), [{'word': 'tennis', 'transcription': '', 'meaning': 'tennis', 'example': ''}])

    def test_the_transcription_may_be_typed_with_its_slashes_and_spaces_are_squeezed(self):
        self.post([self.row({
            'word': '  ice   cream ', 'transcription': ' / aɪs  kriːm / ', 'meaning': 'muzqaymoq   shirin',
            'example': 'I  like   it.',
        })])
        self.assertEqual(stored(self.part), [{
            'word': 'ice cream', 'transcription': 'aɪs kriːm', 'meaning': 'muzqaymoq shirin', 'example': 'I like it.'}])

    def test_a_word_without_a_meaning_or_a_meaning_without_a_word_is_refused_and_says_which(self):
        for row, message in (
            ({**PENCIL, 'meaning': ''}, "O&#x27;zbekcha ma&#x27;no yozilmagan."),
            ({**PENCIL, 'word': ''}, "So&#x27;z yozilmagan."),
        ):
            response = self.post([self.row(WATER), self.row(row)])
            self.assertEqual(response.status_code, 200)
            self.assertContains(response, message, count=1)
            self.assertNotContains(response, 'This field is required.')
            self.assertEqual(KeyWord.objects.count(), 0)  # nothing is saved, not even the good row
        self.assertContains(response, 'value="water"')  # what was typed is still in the rows

    def test_too_long_texts_are_refused_and_say_which(self):
        for name, limit, message in (
            ('word', 100, 'So&#x27;z 100 belgidan oshmasligi kerak.'),
            ('transcription', 100, 'Talaffuz 100 belgidan oshmasligi kerak.'),
            ('meaning', 200, 'Ma&#x27;no 200 belgidan oshmasligi kerak.'),
            ('example', 300, 'Misol 300 belgidan oshmasligi kerak.'),
        ):
            response = self.post([self.row({**WATER, name: 'x' * (limit + 1)})])
            self.assertEqual(response.status_code, 200, name)
            self.assertContains(response, message, msg_prefix=name)
        self.assertEqual(KeyWord.objects.count(), 0)

    def test_a_row_that_was_added_and_removed_again_causes_no_error(self):
        self.post([self.row(PENCIL), self.row(BLANK, DELETE='on'), self.row(WATER)])
        self.assertEqual(stored(self.part), [PENCIL, WATER])

    def test_a_removed_row_does_not_have_to_be_valid(self):
        self.post([self.row(PENCIL), self.row({**WATER, 'meaning': ''}, DELETE='on')])
        self.assertEqual(stored(self.part), [PENCIL])

    # ---------- changing, removing and moving words ----------
    def test_saved_words_can_be_changed_and_keep_their_rows(self):
        first, second = make_key_words(self.part, [PENCIL, STUDENT])
        response = self.post(
            [self.row({**PENCIL, 'meaning': 'ruchka'}, first), self.row(STUDENT, second)], initial=2)
        self.assertRedirects(response, self.url)
        self.assertEqual([word.pk for word in self.part.key_words.all()], [first.pk, second.pk])
        self.assertEqual(stored(self.part)[0]['meaning'], 'ruchka')

    def test_a_removed_word_is_deleted_and_the_others_close_ranks(self):
        first, second, third = make_key_words(self.part, [PENCIL, STUDENT, WATER])
        self.post([self.row(PENCIL, first), self.row(STUDENT, second, DELETE='on'), self.row(WATER, third)], initial=3)
        self.assertEqual(stored(self.part), [PENCIL, WATER])
        self.assertEqual([word.order for word in self.part.key_words.all()], [0, 1])

    def test_a_new_word_goes_after_the_saved_ones(self):
        first, second = make_key_words(self.part, [PENCIL, STUDENT])
        self.post([self.row(PENCIL, first), self.row(STUDENT, second), self.row(WATER)], initial=2)
        self.assertEqual([word['word'] for word in stored(self.part)], ['pencil', 'student', 'water'])

    def test_rows_dragged_into_another_order_are_saved_in_that_order(self):
        first, second = make_key_words(self.part, [PENCIL, STUDENT])
        self.post([self.row(STUDENT, second), self.row(PENCIL, first)], initial=2)
        self.assertEqual([word['word'] for word in stored(self.part)], ['student', 'pencil'])

    def test_a_word_cannot_be_emptied_without_removing_it(self):
        first, = make_key_words(self.part, [PENCIL])
        response = self.post([self.row(BLANK, first)], initial=1)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(stored(self.part), [PENCIL])

    def test_the_page_posted_back_unchanged_changes_nothing(self):
        make_key_words(self.part, [PENCIL, STUDENT, WATER])
        before = list(self.part.key_words.values_list('pk', 'order', 'word', 'meaning'))
        self.assertRedirects(self.client.post(self.url, rendered_form_data(self.client.get(self.url))), self.url)
        self.assertEqual(list(self.part.key_words.values_list('pk', 'order', 'word', 'meaning')), before)

    def test_another_parts_words_cannot_be_changed_from_here(self):
        other = Part.objects.create(course=self.course1, number=2, name='Other')
        foreign, = make_key_words(other, [STUDENT])
        make_key_words(self.part, [PENCIL])
        # a row that names a word of another Part is not that word's edit: it can only become a new word of THIS Part
        self.post([self.row({**STUDENT, 'meaning': 'hacked'}, foreign)], initial=1)
        self.post([self.row({**STUDENT, 'meaning': 'hacked'}, foreign, DELETE='on')], initial=1)
        self.assertEqual(stored(other), [STUDENT])
        self.assertEqual(other.key_words.get().pk, foreign.pk)
        self.assertEqual(KeyWord.objects.get(pk=foreign.pk).meaning, STUDENT['meaning'])
        self.assertEqual(stored(self.part)[0], PENCIL)

    def test_other_parts_keep_their_words_when_this_one_is_saved(self):
        other = Part.objects.create(course=self.course1, number=2, name='Other')
        make_key_words(other, [STUDENT])
        self.post([self.row(PENCIL)])
        self.assertEqual(stored(other), [STUDENT])
        self.assertEqual(stored(self.part), [PENCIL])

    def test_there_is_a_limit_to_the_words_of_a_part(self):
        rows = [self.row({**WATER, 'word': f'w{number}'}) for number in range(MAX_WORDS + 1)]
        response = self.post(rows)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, f"Bitta Part&#x27;da {MAX_WORDS} tadan ko&#x27;p so&#x27;z bo&#x27;lmaydi (hozir {MAX_WORDS + 1} ta)")
        self.assertEqual(KeyWord.objects.count(), 0)
        self.assertEqual(self.post(rows[:MAX_WORDS]).status_code, 302)
        self.assertEqual(KeyWord.objects.count(), MAX_WORDS)

    # ---------- the box for many words ----------
    def test_a_pasted_list_is_added_after_the_rows(self):
        first, = make_key_words(self.part, [PENCIL])
        pasted = "student /ˈstjuːdənt/ | talaba, o'quvchi | The new student joined our class.\nwater | suv"
        response = self.post([self.row(PENCIL, first), self.row(BLANK)], initial=1, bulk=pasted)
        self.assertRedirects(response, self.url)
        self.assertEqual(stored(self.part), [PENCIL, STUDENT, WATER])
        self.assertEqual([word.order for word in self.part.key_words.all()], [0, 1, 2])

    def test_the_pasted_list_and_the_rows_are_both_saved_in_one_go(self):
        response = self.post([self.row(PENCIL)], bulk='water | suv', follow=True)
        self.assertEqual([word['word'] for word in stored(self.part)], ['pencil', 'water'])
        self.assertContains(response, 'jami 2 ta so&#x27;z')
        self.assertContains(response, 'value="water"')  # now a row of its own

    def test_a_list_pasted_from_a_spreadsheet_works(self):
        self.post([], bulk='pencil\t/ˈpensl/\tqalam\tShe borrowed a pencil from her friend.\nwater\t\tsuv')
        self.assertEqual(stored(self.part), [PENCIL, WATER])

    def test_a_mistake_in_the_pasted_list_is_explained_and_nothing_is_saved(self):
        first, = make_key_words(self.part, [PENCIL])
        response = self.post(
            [self.row({**PENCIL, 'meaning': 'changed'}, first)], initial=1, bulk='book | kitob\nwindow\n| deraza')
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "2-qator: «window» uchun o&#x27;zbekcha ma&#x27;no yozilmagan")
        self.assertContains(response, "3-qator: so&#x27;z yozilmagan")
        self.assertContains(response, '<details class="kw-bulk" open>')  # opened so the mistake is seen
        self.assertContains(response, 'book | kitob')  # what was pasted is still there
        self.assertEqual(stored(self.part), [PENCIL])

    def test_the_pasted_list_counts_towards_the_limit(self):
        make_key_words(self.part, [{**WATER, 'word': f'w{number}'} for number in range(MAX_WORDS - 1)])
        words = list(self.part.key_words.all())
        rows = [self.row({**WATER, 'word': word.word}, word) for word in words]
        response = self.post(rows, initial=len(words), bulk='one | bir\ntwo | ikki')
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, f'{MAX_WORDS + 1} ta bo&#x27;lib qoladi')
        self.assertEqual(self.part.key_words.count(), MAX_WORDS - 1)
        self.assertEqual(self.post(rows, initial=len(words), bulk='one | bir').status_code, 302)
        self.assertEqual(self.part.key_words.count(), MAX_WORDS)

    # ---------- what students see ----------
    def test_the_student_page_shows_what_was_typed(self):
        self.post([self.row(PENCIL), self.row(WATER)])
        self.client.logout()
        response = self.client.get(self.course1.get_absolute_url())
        self.assertContains(response, 'Key vocabulary · 2 words')
        self.assertContains(response, '<strong>pencil</strong> <span class="vocab-ipa">/ˈpensl/</span>')
        self.assertContains(response, '<p class="vocab-meaning">suv</p>')

    def test_removing_every_word_takes_the_button_away_from_students(self):
        words = make_key_words(self.part, [PENCIL, STUDENT])
        self.post([self.row(PENCIL, words[0], DELETE='on'), self.row(STUDENT, words[1], DELETE='on')], initial=2)
        self.assertEqual(KeyWord.objects.count(), 0)
        self.assertNotContains(self.client.get(self.course1.get_absolute_url()), 'Key vocabulary')

    def test_the_rows_get_their_numbers_from_the_page_not_from_the_server(self):
        make_key_words(self.part, [PENCIL, STUDENT])
        html = self.client.get(self.url).content.decode()
        self.assertEqual(len(re.findall(r'<span class="kw-num" aria-hidden="true"></span>', html)), 4)  # 3 rows + template
