import re

from django.test import Client
from django.urls import reverse

from courses.models import Category, Course, Exercise, Part, Question
from courses.support import (
    HEADINGS, MEAT_QUESTIONS, MEAT_TEXT, OLIVIA_ANSWERS, OLIVIA_PASSAGE, PARAGRAPHS, SUMMARY_ANSWERS, SUMMARY_PASSAGE,
    WALK_OPTIONS, WALKS,
)

from .support import PanelTestCase, formset_data, rendered_form_data


class ReadingEditorTests(PanelTestCase):
    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()
        cls.reading = Course.objects.create(title='Reading', category=Category.READING, short_description='x')
        cls.part = Part.objects.create(
            course=cls.reading, number=1, name='Gap filling', icon='✍️', kind='passage_gap', first_question_number=1,
            instructions='Type ONE word for each gap. The word is somewhere in the rest of the text.',
        )

    def setUp(self):
        self.client.force_login(self.admin)
        self.exercise = Exercise.objects.create(part=self.part, number=1)
        self.url = reverse('panel:exercise_edit', args=[self.exercise.pk])

    def save(self, passage=OLIVIA_PASSAGE, **extra):
        data = {'duration_minutes': 8, 'title': 'Olivia', 'instructions': '', 'passage': passage, **extra}
        return self.client.post(self.url, data)

    def test_editor_has_a_title_instructions_and_one_big_text_but_no_audio_or_question_rows(self):
        response = self.client.get(self.url)
        for name in ('title', 'instructions', 'passage', 'duration_minutes'):
            self.assertContains(response, f'name="{name}"')
        for name in ('audio', 'remove_audio', 'transcript', 'options', 'image', 'questions-TOTAL_FORMS'):
            self.assertNotContains(response, f'name="{name}"')
        self.assertContains(response, 'Matn (Passage) · 1-savoldan boshlanadi')
        self.assertContains(response, 'Type ONE word for each gap.')  # the Part text is the fallback hint
        self.assertContains(response, 'ikkita kvadrat qavs')
        self.assertContains(response, '[[town]]')
        self.assertContains(response, "Hali bo'sh joy yo'q")
        self.assertNotContains(response, 'Audio hali yuklanmagan')
        self.assertNotContains(response, 'data-formset')

    def test_saving_the_text_creates_one_question_per_gap(self):
        response = self.save()
        self.assertRedirects(response, self.url)
        self.exercise.refresh_from_db()
        self.assertEqual(self.exercise.passage, OLIVIA_PASSAGE)
        self.assertEqual(self.exercise.title, 'Olivia')
        self.assertEqual(self.exercise.duration_minutes, 8)
        self.assertEqual([q.answer for q in self.exercise.questions.all()], OLIVIA_ANSWERS)
        self.assertEqual([q.order for q in self.exercise.questions.all()], list(range(6)))
        self.assertTrue(self.exercise.is_ready)  # no audio needed

    def test_the_editor_lists_the_gaps_it_found_with_their_question_numbers(self):
        Part.objects.filter(pk=self.part.pk).update(first_question_number=7)
        self.save()
        page = self.client.get(self.url)
        self.assertContains(page, "6 ta bo'sh joy topildi")
        self.assertContains(page, '7-savoldan boshlanadi')
        html = page.content.decode()
        self.assertEqual(re.findall(r'<li value="(\d+)"><span>(.*?)</span></li>', html), [
            (str(7 + index), answer) for index, answer in enumerate(OLIVIA_ANSWERS)
        ])

    def test_editing_the_text_keeps_the_questions_that_still_exist(self):
        self.save()
        before = list(self.exercise.questions.values_list('pk', flat=True))
        self.save(passage=OLIVIA_PASSAGE.replace('[[town]]', 'town').replace('[[flowers]]', 'flowers'))
        remaining = list(self.exercise.questions.values_list('pk', 'answer'))
        self.assertEqual([answer for _, answer in remaining], ['sea', 'foods', 'boat', 'island'])
        self.assertEqual([pk for pk, _ in remaining], before[:4])

    def test_clearing_the_text_empties_the_exercise(self):
        self.save()
        self.save(passage='')
        self.assertEqual(self.exercise.questions.count(), 0)
        self.exercise.refresh_from_db()
        self.assertFalse(self.exercise.is_ready)

    def test_a_broken_text_is_refused_and_nothing_changes(self):
        self.save()
        problems = {
            'unclosed': 'The [[town was small.',
            'unopened': 'The town]] was small.',
            'empty': 'The [[ ]] was small.',
            'also empty': 'The [[]] was small [[sea]].',
            'nested': 'The [[a [[b]] c]] was small.',
        }
        for label, passage in problems.items():
            response = self.save(passage=passage)
            self.assertEqual(response.status_code, 200, label)
            self.assertContains(response, 'Qavslar mos kelmayapti', msg_prefix=label)
        self.exercise.refresh_from_db()
        self.assertEqual(self.exercise.passage, OLIVIA_PASSAGE)
        self.assertEqual([q.answer for q in self.exercise.questions.all()], OLIVIA_ANSWERS)

    def test_a_text_without_any_gap_is_refused(self):
        response = self.save(passage='Just a story with no gaps to fill.')
        self.assertContains(response, "Matnda bo&#x27;sh joy yo&#x27;q")
        self.assertEqual(self.exercise.questions.count(), 0)

    def test_too_many_gaps_and_too_long_answers_are_refused(self):
        response = self.save(passage=' '.join(f'word [[w{i}]]' for i in range(31)))
        self.assertContains(response, 'oshmasligi kerak (hozir 31 ta)')
        response = self.save(passage='A [[' + 'x' * 256 + ']] b')
        self.assertContains(response, 'Bitta javob juda uzun')
        self.assertEqual(self.exercise.questions.count(), 0)
        self.assertEqual(self.save(passage=' '.join(f'word [[w{i}]]' for i in range(30))).status_code, 302)
        self.assertEqual(self.exercise.questions.count(), 30)

    def test_round_trip_posts_back_unchanged(self):
        self.save()
        data = rendered_form_data(self.client.get(self.url))
        self.assertEqual(data['passage'], OLIVIA_PASSAGE)
        self.assertEqual(data['title'], 'Olivia')
        self.assertRedirects(self.client.post(self.url, data), self.url)
        self.assertEqual([q.answer for q in self.exercise.questions.all()], OLIVIA_ANSWERS)

    def test_duration_title_and_instructions_are_saved_with_the_text(self):
        self.save(instructions='Fill the **gaps**.', duration_minutes=10, title='Another story')
        self.exercise.refresh_from_db()
        self.assertEqual((self.exercise.instructions, self.exercise.duration_minutes), ('Fill the **gaps**.', 10))
        self.assertEqual(self.exercise.title, 'Another story')

    def test_part_page_explains_what_makes_the_exercise_ready(self):
        part_url = reverse('panel:part_edit', args=[self.part.pk])
        page = self.client.get(part_url)
        self.assertContains(page, "Bo&#x27;sh")
        self.assertContains(page, 'Mashq matni va kamida 1 ta bo\'sh joy')
        self.save()
        self.assertContains(self.client.get(part_url), 'Tayyor', count=2)
        self.assertContains(self.client.get(part_url), '6 savol')

    def test_the_part_form_offers_the_new_kind(self):
        response = self.client.get(reverse('panel:part_create', args=[self.reading.pk]))
        self.assertContains(response, "Matndagi bo&#x27;sh joylar (so&#x27;zni yozish)")

    def test_admin_builds_it_and_a_student_fills_the_gaps(self):
        self.save()
        student = Client()
        student.force_login(self.alice)
        args = ['reading', 1, 1]
        play = student.get(reverse('courses:exercise_play', args=args))
        html = play.content.decode()
        self.assertEqual(re.findall(r'class="gap-number">(\d+)<', html), ['1', '2', '3', '4', '5', '6'])
        self.assertContains(play, '<h3 class="gap-title">Olivia</h3>')
        self.assertNotContains(play, '[[')

        questions = list(self.exercise.questions.all())
        answers = {f'q{q.pk}': value for q, value in zip(questions, ['town', 'sea', 'food', '', 'island', 'FLOWERS'])}
        result = student.post(reverse('courses:exercise_submit', args=args), answers)
        self.assertContains(result, '<span>4</span> / 6 correct (67%)')


class ReadingMatchingEditorTests(PanelTestCase):
    """Reading Part 2 (statements) and Part 3 (headings): the list-matching editor without any audio."""

    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()
        cls.reading = Course.objects.create(title='Reading', category=Category.READING, short_description='x')
        cls.statements = Part.objects.create(
            course=cls.reading, number=2, name='Matching', icon='🔗', kind='matching', first_question_number=7,
            questions_count=8, instructions='Each statement is used once. Two are extra!',
        )
        cls.headings = Part.objects.create(
            course=cls.reading, number=3, name='Headings', icon='🏷️', kind='matching', first_question_number=15,
            questions_count=6,
        )

    def setUp(self):
        self.client.force_login(self.admin)
        self.exercise = Exercise.objects.create(part=self.statements, number=1)
        self.url = reverse('panel:exercise_edit', args=[self.exercise.pk])

    def statement_rows(self):
        return [{'label': '', 'text': text, 'correct': correct} for text, correct in WALKS]

    def save_statements(self, **extra):
        data = {
            'duration_minutes': 10, 'options': '\n'.join(WALK_OPTIONS),
            **formset_data('questions', self.statement_rows()), **extra,
        }
        return self.client.post(self.url, data)

    def test_editor_has_options_a_title_labelled_long_text_rows_and_no_audio(self):
        response = self.client.get(self.url)
        self.assertEqual(len(response.context['questions'].forms), 8)
        for name in ('options', 'title', 'instructions', 'questions-0-label', 'questions-0-text', 'questions-7-correct'):
            self.assertContains(response, f'name="{name}"')
        for name in ('audio', 'transcript', 'passage', 'questions-0-option_a'):
            self.assertNotContains(response, f'name="{name}"')
        self.assertContains(response, 'counter-reset: qrow 6;')
        self.assertContains(response, '7-savoldan boshlanadi')
        self.assertContains(response, '<textarea name="questions-0-text"')  # room for a whole paragraph
        self.assertContains(response, 'Each statement is used once. Two are extra!')  # the Part text as the fallback hint

    def test_saving_a_statements_exercise_makes_it_ready_without_audio(self):
        self.assertRedirects(self.save_statements(), self.url)
        self.exercise.refresh_from_db()
        self.assertEqual(len(self.exercise.option_list), 10)
        self.assertEqual([q.correct for q in self.exercise.questions.all()], [correct for _, correct in WALKS])
        self.assertTrue(self.exercise.is_ready)
        self.assertContains(self.client.get(reverse('panel:part_edit', args=[self.statements.pk])), 'Tayyor', count=2)

    def test_a_paragraph_longer_than_five_hundred_characters_is_kept_whole(self):
        long_text = ' '.join(f'Sentence number {i} of a long paragraph.' for i in range(30))
        self.assertGreater(len(long_text), 900)
        rows = [{'label': '', 'text': long_text, 'correct': 'a'}, {'label': '', 'text': 'Short.', 'correct': 'b'}]
        response = self.client.post(self.url, {
            'duration_minutes': 10, 'options': 'One\nTwo', **formset_data('questions', rows),
        })
        self.assertRedirects(response, self.url)
        self.assertEqual(self.exercise.questions.first().text, long_text)

    def test_the_title_the_label_and_the_paragraph_of_a_headings_exercise_are_saved_and_shown(self):
        exercise = Exercise.objects.create(part=self.headings, number=1)
        url = reverse('panel:exercise_edit', args=[exercise.pk])
        rows = [{'label': label, 'text': text, 'correct': correct} for label, text, correct in PARAGRAPHS]
        response = self.client.post(url, {
            'duration_minutes': 10, 'title': 'Pedestrian Zones and Their Growth', 'options': '\n'.join(HEADINGS),
            **formset_data('questions', rows),
        })
        self.assertRedirects(response, url)
        exercise.refresh_from_db()
        self.assertEqual(exercise.title, 'Pedestrian Zones and Their Growth')
        self.assertEqual(
            [(q.label, q.correct) for q in exercise.questions.all()],
            [(label, correct) for label, _, correct in PARAGRAPHS],
        )

        student = Client()
        student.force_login(self.alice)
        play = student.get(reverse('courses:exercise_play', args=['reading', 3, 1]))
        self.assertContains(play, '<h3 class="gap-title">Pedestrian Zones and Their Growth</h3>')
        self.assertContains(play, '<strong>15. Paragraph I</strong>')
        self.assertContains(play, 'class="match-select"', count=6)

    def test_round_trip_keeps_the_labels_and_the_title(self):
        exercise = Exercise.objects.create(part=self.headings, number=1, title='Heading text')
        Exercise.objects.filter(pk=exercise.pk).update(options='\n'.join(HEADINGS))
        for index, (label, text, correct) in enumerate(PARAGRAPHS):
            Question.objects.create(exercise=exercise, order=index, label=label, text=text, correct=correct)
        url = reverse('panel:exercise_edit', args=[exercise.pk])
        data = rendered_form_data(self.client.get(url))
        self.assertEqual(data['title'], 'Heading text')
        self.assertEqual(data['questions-0-label'], 'Paragraph I')
        self.assertEqual(data['questions-0-text'], PARAGRAPHS[0][1])
        self.assertRedirects(self.client.post(url, data), url)
        self.assertEqual([q.label for q in exercise.questions.all()], [label for label, _, _ in PARAGRAPHS])

    def test_a_letter_beyond_the_list_is_still_refused(self):
        rows = [{'label': '', 'text': 'Text', 'correct': 'h'}]
        response = self.client.post(self.url, {
            'duration_minutes': 10, 'options': 'One\nTwo\nThree', **formset_data('questions', rows),
        })
        self.assertContains(response, 'variantlar ro&#x27;yxatidan tashqarida')

    def test_the_listening_speakers_editor_gets_the_same_optional_fields(self):
        listening = Course.objects.create(title='Listening', category=Category.LISTENING, short_description='x')
        part = Part.objects.create(course=listening, number=3, name='Speakers', kind='matching', first_question_number=15)
        speaker = Exercise.objects.create(part=part, number=1)
        response = self.client.get(reverse('panel:exercise_edit', args=[speaker.pk]))
        self.assertContains(response, 'name="audio"')
        self.assertContains(response, 'name="title"')
        self.assertContains(response, 'name="questions-0-label"')

    def test_map_rows_do_not_offer_a_label(self):
        listening = Course.objects.create(title='Listening', category=Category.LISTENING, short_description='x')
        part = Part.objects.create(course=listening, number=4, name='Map', kind='map', first_question_number=19)
        exercise = Exercise.objects.create(part=part, number=1)
        response = self.client.get(reverse('panel:exercise_edit', args=[exercise.pk]))
        self.assertContains(response, 'name="questions-0-text"')
        self.assertNotContains(response, 'name="questions-0-label"')
        self.assertContains(response, '<input type="text" name="questions-0-text"')  # still a one-line input


def choice_rows(questions):
    return [
        {'intro': intro, 'text': text, 'option_a': options[0], 'option_b': options[1], 'option_c': options[2],
         'option_d': options[3] if len(options) > 3 else '', 'correct': correct}
        for intro, text, options, correct in questions
    ]


class ReadingTextWithQuestionsEditorTests(PanelTestCase):
    """Reading Part 4: a text to read (title + paragraphs) and A–D / True-False questions under it."""

    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()
        cls.reading = Course.objects.create(title='Reading', category=Category.READING, short_description='x')
        cls.part = Part.objects.create(
            course=cls.reading, number=4, name='Multiple choice & True / False', icon='✅', kind='choice',
            first_question_number=21, questions_count=9, instructions='Read the following text for questions 21-29.',
        )

    def setUp(self):
        self.client.force_login(self.admin)
        self.exercise = Exercise.objects.create(part=self.part, number=1)
        self.url = reverse('panel:exercise_edit', args=[self.exercise.pk])

    def save(self, rows=None, **extra):
        data = {
            'duration_minutes': 15, 'title': 'Eating meat', 'passage': MEAT_TEXT,
            **formset_data('questions', rows if rows is not None else choice_rows(MEAT_QUESTIONS)), **extra,
        }
        return self.client.post(self.url, data)

    def test_editor_has_the_text_fields_nine_rows_numbered_from_21_and_a_fourth_option(self):
        response = self.client.get(self.url)
        self.assertEqual(len(response.context['questions'].forms), 9)
        for name in ('title', 'passage', 'questions-0-intro', 'questions-0-option_d', 'questions-8-correct'):
            self.assertContains(response, f'name="{name}"')
        for name in ('audio', 'transcript', 'options', 'image'):
            self.assertNotContains(response, f'name="{name}"')
        self.assertContains(response, 'counter-reset: qrow 20;')
        self.assertContains(response, '21-savoldan boshlanadi')
        self.assertContains(response, 'Read the following text for questions 21-29.')  # the Part text as the fallback hint
        self.assertNotContains(response, "Bo'sh joylar")  # a plain text has no gaps summary
        self.assertContains(response, 'D variant (ixtiyoriy)')

    def test_saving_the_text_and_the_questions_makes_the_exercise_ready_without_audio(self):
        self.assertRedirects(self.save(), self.url)
        self.exercise.refresh_from_db()
        self.assertEqual((self.exercise.title, self.exercise.passage), ('Eating meat', MEAT_TEXT))
        questions = list(self.exercise.questions.all())
        self.assertEqual(len(questions), 9)
        self.assertEqual([q.order for q in questions], list(range(9)))
        self.assertEqual((questions[0].option_d, questions[0].correct), ("for people who don't like meat", 'a'))
        self.assertEqual((questions[4].option_d, questions[4].intro[:20]), ('', '**Questions 25-29:**'))
        self.assertTrue(self.exercise.is_ready)

    def test_a_text_with_double_brackets_is_saved_as_typed_and_creates_no_gaps(self):
        self.save(passage='Plain [[text]] with brackets.', rows=choice_rows(MEAT_QUESTIONS[:1]))
        self.exercise.refresh_from_db()
        self.assertEqual(self.exercise.passage, 'Plain [[text]] with brackets.')
        self.assertEqual(self.exercise.questions.count(), 1)

    def test_the_correct_letter_d_needs_a_d_option(self):
        rows = choice_rows(MEAT_QUESTIONS[:1])
        rows[0].update(option_d='', correct='d')
        response = self.save(rows=rows)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'D variant yozilmagan')
        self.assertEqual(self.exercise.questions.count(), 0)

    def test_three_options_are_still_required_and_the_fourth_is_optional(self):
        rows = choice_rows(MEAT_QUESTIONS[4:5])
        rows[0]['option_c'] = ''
        self.assertEqual(self.save(rows=rows).status_code, 200)
        self.assertEqual(self.exercise.questions.count(), 0)
        self.assertEqual(self.save(rows=choice_rows(MEAT_QUESTIONS[4:5])).status_code, 302)

    def test_round_trip_keeps_the_text_the_options_and_the_cards(self):
        self.save()
        data = rendered_form_data(self.client.get(self.url))
        self.assertEqual(data['title'], 'Eating meat')
        self.assertEqual(data['passage'], MEAT_TEXT.replace('\n', '\r\n') if '\r' in data['passage'] else MEAT_TEXT)
        self.assertEqual(data['questions-0-option_d'], "for people who don't like meat")
        self.assertEqual(data['questions-0-intro'], MEAT_QUESTIONS[0][0])
        self.assertRedirects(self.client.post(self.url, data), self.url)
        self.assertEqual(self.exercise.questions.count(), 9)

    def test_admin_builds_it_and_a_student_answers_with_d(self):
        self.save()
        student = Client()
        student.force_login(self.alice)
        args = ['reading', 4, 1]
        play = student.get(reverse('courses:exercise_play', args=args))
        self.assertContains(play, '<h3 class="gap-title">Eating meat</h3>')
        self.assertContains(play, 'type="radio"', count=4 * 4 + 5 * 3)
        questions = list(self.exercise.questions.all())
        answers = {f'q{q.pk}': q.correct for q in questions}
        answers[f'q{questions[2].pk}'] = 'd'  # question 23's right answer is D
        result = student.post(reverse('courses:exercise_submit', args=args), answers)
        self.assertContains(result, '<span>9</span> / 9 correct (100%)')

    def test_listening_choice_editors_offer_the_fourth_option_but_no_text(self):
        listening = Course.objects.create(title='Listening', category=Category.LISTENING, short_description='x')
        part = Part.objects.create(course=listening, number=1, name='Short replies')
        exercise = Exercise.objects.create(part=part, number=1)
        response = self.client.get(reverse('panel:exercise_edit', args=[exercise.pk]))
        self.assertContains(response, 'name="questions-0-option_d"')
        self.assertNotContains(response, 'name="passage"')
        self.assertNotContains(response, 'name="title"')


class ReadingTextWithGapsAndTestEditorTests(PanelTestCase):
    """Reading Part 5: a text with [[gaps]] (generated rows) followed by ordinary test questions."""

    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()
        cls.reading = Course.objects.create(title='Reading', category=Category.READING, short_description='x')
        cls.part = Part.objects.create(
            course=cls.reading, number=5, name='Summary & questions', icon='🧩', kind='passage_mixed',
            first_question_number=30, questions_count=2,
        )

    def setUp(self):
        self.client.force_login(self.admin)
        self.exercise = Exercise.objects.create(part=self.part, number=1)
        self.url = reverse('panel:exercise_edit', args=[self.exercise.pk])
        self.tests = choice_rows([
            ('**Questions 34-35:** choose the correct answer A, B, C or D.', 'First test?', ['a1', 'b1', 'c1', 'd1'], 'b'),
            ('', 'Second test?', ['a2', 'b2', 'c2', 'd2'], 'd'),
        ])

    def save(self, passage=SUMMARY_PASSAGE, rows=None, **extra):
        data = {
            'duration_minutes': 12, 'title': 'Riverton', 'passage': passage,
            **formset_data('questions', self.tests if rows is None else rows), **extra,
        }
        return self.client.post(self.url, data)

    def test_the_editor_has_the_text_and_two_blank_test_rows(self):
        response = self.client.get(self.url)
        self.assertEqual(len(response.context['questions'].forms), 2)
        for name in ('title', 'passage', 'questions-0-intro', 'questions-1-option_d'):
            self.assertContains(response, f'name="{name}"')
        for name in ('audio', 'transcript', 'questions-2-text'):
            self.assertNotContains(response, f'name="{name}"')
        self.assertContains(response, 'Test savollar (30-savoldan boshlanadi)')
        self.assertContains(response, "Hali bo'sh joy yo'q")

    def test_saving_makes_four_gap_rows_first_and_the_test_rows_after_them(self):
        self.assertRedirects(self.save(), self.url)
        self.exercise.refresh_from_db()
        rows = list(self.exercise.questions.all())
        self.assertEqual([(q.order, q.is_choice) for q in rows], [(0, False)] * 1 + [(1, False), (2, False), (3, False), (4, True), (5, True)])
        self.assertEqual([q.answer for q in rows[:4]], SUMMARY_ANSWERS)
        self.assertEqual([q.correct for q in rows[4:]], ['b', 'd'])
        self.assertTrue(self.exercise.is_ready)

        page = self.client.get(self.url)
        self.assertContains(page, "4 ta bo'sh joy topildi")
        self.assertContains(page, 'Test savollar (34-savoldan boshlanadi)')
        self.assertContains(page, 'counter-reset: qrow 33;')
        self.assertEqual(len(page.context['questions'].forms), 2)  # the two saved tests, no spare row
        html = page.content.decode()
        self.assertEqual(re.findall(r'<li value="(\d+)"><span>(.*?)</span></li>', html), [
            (str(30 + index), answer) for index, answer in enumerate(SUMMARY_ANSWERS)])

    def test_adding_a_gap_moves_the_test_questions_down_and_keeps_them(self):
        self.save()
        before = list(self.exercise.questions.filter(option_a__gt='').values_list('pk', flat=True))
        page = self.client.get(self.url)
        data = rendered_form_data(page)
        data['passage'] = SUMMARY_PASSAGE.replace('old [[tower]].', 'old [[tower]] and a [[gate]].')
        self.assertRedirects(self.client.post(self.url, data), self.url)
        rows = list(self.exercise.questions.all())
        self.assertEqual([q.answer for q in rows if not q.is_choice], SUMMARY_ANSWERS + ['gate'])
        self.assertEqual([q.order for q in rows], list(range(7)))
        self.assertEqual([q.pk for q in rows if q.is_choice], before)
        self.assertContains(self.client.get(self.url), 'Test savollar (35-savoldan boshlanadi)')

    def test_a_test_question_can_be_deleted_and_the_rest_keep_their_place(self):
        self.save()
        data = rendered_form_data(self.client.get(self.url))
        data['questions-0-DELETE'] = 'on'
        self.assertRedirects(self.client.post(self.url, data), self.url)
        rows = list(self.exercise.questions.all())
        self.assertEqual([(q.order, q.is_choice) for q in rows], [(0, False), (1, False), (2, False), (3, False), (4, True)])
        self.assertEqual(rows[-1].text, 'Second test?')

    def test_a_broken_text_is_refused_before_anything_is_saved(self):
        self.save()
        response = self.save(passage='A [[broken gap and no end.')
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Qavslar mos kelmayapti')
        self.assertEqual(self.exercise.questions.count(), 6)

    def test_text_alone_without_tests_is_still_a_ready_exercise(self):
        self.save(rows=[])
        self.exercise.refresh_from_db()
        self.assertEqual(self.exercise.questions.count(), 4)
        self.assertTrue(self.exercise.is_ready)

    def test_round_trip_posts_back_unchanged(self):
        self.save()
        data = rendered_form_data(self.client.get(self.url))
        self.assertEqual(data['questions-INITIAL_FORMS'], '2')
        self.assertEqual(data['questions-1-correct'], 'd')
        self.assertRedirects(self.client.post(self.url, data), self.url)
        self.assertEqual([q.answer for q in self.exercise.questions.all()][:4], SUMMARY_ANSWERS)
        self.assertEqual(self.exercise.questions.count(), 6)

    def test_a_student_fills_the_gaps_and_answers_the_test(self):
        self.save()
        student = Client()
        student.force_login(self.alice)
        args = ['reading', 5, 1]
        play = student.get(reverse('courses:exercise_play', args=args))
        self.assertContains(play, 'class="gap-input"', count=4)
        self.assertContains(play, 'type="radio"', count=8)
        questions = list(self.exercise.questions.all())
        values = ['port', 'bridge', 'market', 'tower', 'b', 'd']
        result = student.post(
            reverse('courses:exercise_submit', args=args), {f'q{q.pk}': value for q, value in zip(questions, values)})
        self.assertContains(result, '<span>6</span> / 6 correct (100%)')

    def test_the_part_form_offers_the_new_kind_and_the_part_page_explains_readiness(self):
        response = self.client.get(reverse('panel:part_create', args=[self.reading.pk]))
        self.assertContains(response, 'Matn: bo&#x27;sh joylar va undan keyin test savollari')
        page = self.client.get(reverse('panel:part_edit', args=[self.part.pk]))
        self.assertContains(page, "Mashq matni va kamida 1 ta bo'sh joy")


class ReadingPartsWithoutAudioTests(PanelTestCase):
    """The other Reading Parts use the ordinary kinds (until their formats arrive) — they just have no audio."""

    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()
        cls.reading = Course.objects.create(title='Reading', category=Category.READING, short_description='x')
        cls.part = Part.objects.create(course=cls.reading, number=4, name='Multiple choice', kind='choice')

    def setUp(self):
        self.client.force_login(self.admin)
        self.exercise = Exercise.objects.create(part=self.part, number=1)
        self.url = reverse('panel:exercise_edit', args=[self.exercise.pk])

    def test_the_editor_has_no_audio_and_no_transcript_but_offers_a_text_to_read(self):
        response = self.client.get(self.url)
        for name in ('audio', 'remove_audio', 'transcript'):
            self.assertNotContains(response, f'name="{name}"')
        for name in ('title', 'passage'):
            self.assertContains(response, f'name="{name}"')
        self.assertContains(response, 'name="questions-0-option_a"')
        self.assertContains(response, 'name="questions-0-option_d"')
        self.assertContains(response, 'name="duration_minutes"')
        self.assertNotContains(response, 'Audio yuklash')
        self.assertContains(response, 'Matn, savollar va')  # the delete warning no longer mentions audio

    def test_questions_alone_make_the_exercise_ready(self):
        rows = [{'intro': '', 'text': 'True or false?', 'option_a': 'True', 'option_b': 'False', 'option_c': 'Not given',
                 'correct': 'b'}]
        response = self.client.post(self.url, {'duration_minutes': 5, **formset_data('questions', rows)})
        self.assertRedirects(response, self.url)
        self.exercise.refresh_from_db()
        self.assertTrue(self.exercise.is_ready)
        part_page = self.client.get(reverse('panel:part_edit', args=[self.part.pk]))
        self.assertContains(part_page, 'Mashq kamida 1 ta savol kiritilgach')
        self.assertNotContains(part_page, '🎧')

    def test_a_listening_editor_is_unchanged(self):
        listening = Course.objects.create(title='Listening', category=Category.LISTENING, short_description='x')
        part = Part.objects.create(course=listening, number=1, name='Short replies')
        exercise = Exercise.objects.create(part=part, number=1)
        response = self.client.get(reverse('panel:exercise_edit', args=[exercise.pk]))
        for name in ('audio', 'transcript'):
            self.assertContains(response, f'name="{name}"')
        self.assertNotContains(response, 'name="passage"')
        self.assertContains(response, 'Audio yuklash')


class CourseListShowsReadingPartsTests(PanelTestCase):
    def test_course_edit_page_lists_the_reading_parts_with_ready_counts(self):
        reading = Course.objects.create(title='Reading', category=Category.READING, short_description='x')
        part = Part.objects.create(course=reading, number=1, name='Gap filling', icon='✍️', kind='passage_gap')
        ready = Exercise.objects.create(part=part, number=1, passage='A [[b]]')
        Question.objects.create(exercise=ready, answer='b')
        Exercise.objects.create(part=part, number=2)
        self.client.force_login(self.admin)
        response = self.client.get(reverse('panel:course_edit', args=[reading.pk]))
        self.assertContains(response, '✍️ Part 1 · Gap filling')
        self.assertContains(response, '2 ta mashq · 1 tasi tayyor')
