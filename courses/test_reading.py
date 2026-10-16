import re
from types import SimpleNamespace

from django.core.management import CommandError, call_command
from django.test import SimpleTestCase, TestCase
from django.urls import reverse

from accounts.models import User

from .models import Category, Course, Exercise, ExerciseResult, KeyWord, Part, Question
from .passages import build_passage_blocks, passage_answers, sync_passage_questions
from .support import (
    HEADINGS, MEAT_QUESTIONS, MEAT_TEXT, OLIVIA_ANSWERS, OLIVIA_PASSAGE, PARAGRAPHS, SUMMARY_ANSWERS, SUMMARY_PASSAGE,
    WALK_OPTIONS, WALKS, make_headings_exercise, make_meat_exercise, make_passage_exercise, make_statements_exercise,
    make_summary_exercise, seed, seed_reading,
)

PASSWORD = 'StrongPass123!'


class ReadingSeedTests(TestCase):
    def setUp(self):
        self.course = Course.objects.create(title='Reading', category=Category.READING, short_description='x')

    def test_five_parts_with_ten_exercises_each(self):
        seed_reading()
        parts = list(self.course.parts.all())
        self.assertEqual(
            [(p.number, p.icon, p.name, p.exercises.count()) for p in parts],
            [
                (1, '✍️', 'Gap filling', 10),
                (2, '🔗', 'Matching', 10),
                (3, '🏷️', 'Headings', 10),
                (4, '✅', 'Multiple choice & True / False', 10),
                (5, '🧩', 'Summary & questions', 10),
            ],
        )
        self.assertEqual(Exercise.objects.count(), 50)
        self.assertFalse(KeyWord.objects.exists())  # the words of a Part are typed by an admin, never invented

    def test_the_formats_known_so_far(self):
        seed_reading()
        formats = {p.number: (p.kind, p.first_question_number, p.questions_count) for p in Part.objects.all()}
        self.assertEqual(formats[1], ('passage_gap', 1, 0))  # its questions are the [[gaps]] of the text
        self.assertEqual(formats[2], ('matching', 7, 8))     # questions 7–14
        self.assertEqual(formats[3], ('matching', 15, 6))    # questions 15–20
        self.assertEqual(formats[4], ('choice', 21, 9))      # a text, then questions 21–29
        self.assertEqual(formats[5], ('passage_mixed', 30, 2))  # gaps 30–33 from the text, then 2 test rows (34–35)

    def test_instructions_of_the_known_parts(self):
        seed_reading()
        text = {p.number: p.instructions for p in Part.objects.all()}
        self.assertEqual(text[1], 'Type ONE word for each gap. The word is somewhere in the rest of the text.')
        self.assertEqual(text[2], 'Each statement is used once. Two are extra!')
        self.assertEqual(
            text[3],
            'Choose the correct heading for each paragraph. There are more headings than paragraphs, '
            'and you cannot use a heading more than once.')
        self.assertEqual(text[4], 'Read the following text for questions 21-29.')
        self.assertEqual(text[5], '')  # Part 5's instruction was not sent yet: the admin writes it in the panel

    def test_exercises_get_the_time_shown_in_the_references(self):
        seed_reading()
        minutes = {}
        for exercise in Exercise.objects.all():
            minutes.setdefault(exercise.part.number, set()).add(exercise.duration_minutes)
        self.assertEqual(minutes, {1: {8}, 2: {10}, 3: {10}, 4: {15}, 5: {5}})

    def test_empty_exercises_seeded_earlier_with_the_standard_time_get_the_new_one(self):
        seed_reading()
        Exercise.objects.filter(part__number=2).update(duration_minutes=5)  # as an older seed left them
        Exercise.objects.filter(part__number=2, number=1).update(duration_minutes=7)  # edited by the admin
        question_holder = Exercise.objects.get(part__number=2, number=2)
        Question.objects.create(exercise=question_holder, text='x', correct='a')
        seed_reading()
        minutes = {e.number: e.duration_minutes for e in Exercise.objects.filter(part__number=2)}
        self.assertEqual(minutes[1], 7)   # edited: kept
        self.assertEqual(minutes[2], 5)   # already holds a question: kept
        self.assertEqual({m for n, m in minutes.items() if n > 2}, {10})

    def test_rerun_is_idempotent_and_keeps_edits(self):
        seed_reading()
        Exercise.objects.filter(part__number=1, number=1).update(duration_minutes=12, title='Kept')
        Part.objects.filter(number=1).update(instructions='Edited in the panel')
        seed_reading()
        self.assertEqual((Part.objects.count(), Exercise.objects.count()), (5, 50))
        self.assertEqual(Exercise.objects.get(part__number=1, number=1).duration_minutes, 12)
        self.assertEqual(Part.objects.get(number=1).instructions, 'Edited in the panel')

    def test_a_part_created_earlier_with_the_defaults_is_upgraded_unless_it_holds_questions(self):
        Part.objects.create(course=self.course, number=1, name='Old')
        seed_reading()
        self.assertEqual(Part.objects.get(number=1).kind, 'passage_gap')

        other = Course.objects.create(title='Reading two', category=Category.READING, short_description='y')
        part = Part.objects.create(course=other, number=1, name='Old')
        Question.objects.create(exercise=Exercise.objects.create(part=part, number=1), option_a='a', option_b='b', option_c='c')
        seed_reading(course=other.slug)
        self.assertEqual(Part.objects.get(pk=part.pk).kind, 'choice')

    def test_needs_a_reading_course_and_never_touches_the_listening_one(self):
        Course.objects.all().delete()
        with self.assertRaises(CommandError):
            seed_reading()
        listening = Course.objects.create(title='Listening', category=Category.LISTENING, short_description='x')
        with self.assertRaises(CommandError):
            seed_reading()
        self.assertEqual(listening.parts.count(), 0)

    def test_both_skills_can_be_seeded_side_by_side(self):
        Course.objects.create(title='Listening', category=Category.LISTENING, short_description='x')
        seed()
        seed_reading()
        self.assertEqual(Part.objects.filter(course__category='listening').count(), 6)
        self.assertEqual(Part.objects.filter(course__category='reading').count(), 5)
        self.assertEqual(Part.objects.get(course__category='listening', number=6).kind, 'gap_fill')
        self.assertEqual(Part.objects.get(course__category='reading', number=1).kind, 'passage_gap')


class ReadingHubTests(TestCase):
    def setUp(self):
        self.course = Course.objects.create(title='Reading', category=Category.READING, short_description='x')
        seed_reading()
        self.student = User.objects.create_user(email='s@t.uz', password=PASSWORD)
        self.client.force_login(self.student)

    def test_the_reading_course_opens_the_practice_page(self):
        response = self.client.get(self.course.get_absolute_url())
        self.assertTemplateUsed(response, 'courses/practice.html')
        self.assertContains(response, '📖 Reading practice')
        self.assertContains(
            response, 'Choose a part, then pick an exercise. Each one is short and you get your score straight away.')
        for text in ('✍️ Part 1 · Gap filling', '🔗 Part 2 · Matching', '🏷️ Part 3 · Headings',
                     '✅ Part 4 · Multiple choice &amp; True / False', '🧩 Part 5 · Summary &amp; questions'):
            self.assertContains(response, text)
        self.assertContains(response, 'class="ex-tile"', count=50)
        self.assertContains(response, '10 ready', count=5)
        self.assertNotContains(response, 'Key vocabulary')  # no words typed yet
        self.assertNotContains(response, 'Paid')
        self.assertNotContains(response, 'Free')

    def test_a_course_without_parts_keeps_its_old_page(self):
        other = Course.objects.create(title='Plain', category=Category.GRAMMAR, short_description='x')
        self.assertTemplateUsed(self.client.get(other.get_absolute_url()), 'courses/course_detail.html')


class PassageHelpersTests(SimpleTestCase):
    def test_answers_come_out_in_order_and_are_trimmed(self):
        self.assertEqual(passage_answers('A [[ one ]] b [[two / deux]] c [[three]]'), ['one', 'two / deux', 'three'])
        self.assertEqual(passage_answers(''), [])
        self.assertEqual(passage_answers(None), [])
        self.assertEqual(passage_answers('no gaps [here] or [[ ]]'), [''])

    def test_the_text_is_cut_around_the_gaps(self):
        blocks = build_passage_blocks('Start [[a]] middle [[b]].\n\nSecond [[c]]', ['Q1', 'Q2', 'Q3'])
        self.assertEqual(blocks, [
            [{'text': 'Start '}, {'item': 'Q1'}, {'text': ' middle '}, {'item': 'Q2'}, {'text': '.'}],
            [{'text': 'Second '}, {'item': 'Q3'}],
        ])

    def test_a_gap_without_an_item_is_dropped_never_shown_as_its_answer(self):
        blocks = build_passage_blocks('Before [[secret]] after', [])
        self.assertEqual(blocks, [[{'text': 'Before '}, {'text': ' after'}]])
        self.assertNotIn('secret', str(blocks))

    def test_blank_lines_split_paragraphs_and_single_line_breaks_read_as_spaces(self):
        blocks = build_passage_blocks('One\ntwo\r\nthree\n\n\n  \nFour', [])
        self.assertEqual(blocks, [[{'text': 'One two three'}], [{'text': 'Four'}]])
        self.assertEqual(build_passage_blocks('', []), [])
        blocks = build_passage_blocks('wrapped\n[[word]]\nagain', ['Q1'])
        self.assertEqual(blocks, [[{'text': 'wrapped '}, {'item': 'Q1'}, {'text': ' again'}]])

    def test_a_typed_number_before_a_gap_is_left_out_because_the_gap_prints_its_own(self):
        items = [SimpleNamespace(number=n) for n in (1, 2, 3)]
        blocks = build_passage_blocks(
            'At first the 1.[[shop]] sold. Then\n2) [[meaning]] came. (Q3) [[toys]].', items,
            number_of=lambda item: item.number)
        self.assertEqual(blocks, [[
            {'text': 'At first the '}, {'item': items[0]}, {'text': ' sold. Then '}, {'item': items[1]},
            {'text': ' came. '}, {'item': items[2]}, {'text': '.'},
        ]])

    def test_only_the_gaps_own_number_in_that_exact_form_is_removed(self):
        items = [SimpleNamespace(number=1), SimpleNamespace(number=2), SimpleNamespace(number=3)]
        number_of = lambda item: item.number
        blocks = build_passage_blocks('In room 3. [[a]] and page 22 [[b]] in 1932 [[c]]', items, number_of=number_of)
        texts = [piece['text'] for piece in blocks[0] if 'text' in piece]
        self.assertEqual(texts, ['In room 3. ', ' and page 22 ', ' in 1932 '])
        # without number_of nothing is touched, whatever the text says
        blocks = build_passage_blocks('1. [[a]]', items[:1])
        self.assertEqual(blocks, [[{'text': '1. '}, {'item': items[0]}]])

    def test_a_text_that_was_only_the_number_disappears(self):
        item = SimpleNamespace(number=1)
        blocks = build_passage_blocks('1. [[a]] rest', [item], number_of=lambda i: i.number)
        self.assertEqual(blocks, [[{'item': item}, {'text': ' rest'}]])


class PassageSyncTests(TestCase):
    def setUp(self):
        self.course = Course.objects.create(title='Reading', category=Category.READING, short_description='x')
        seed_reading()
        self.exercise = Exercise.objects.get(part__number=1, number=1)

    def sync(self, passage):
        self.exercise.passage = passage
        self.exercise.save()
        sync_passage_questions(self.exercise)
        return list(self.exercise.questions.values_list('pk', 'order', 'answer'))

    def test_questions_follow_the_gaps(self):
        rows = self.sync('A [[one]] b [[two]]')
        self.assertEqual([(order, answer) for _, order, answer in rows], [(0, 'one'), (1, 'two')])

    def test_editing_the_text_keeps_the_rows_and_changes_only_what_differs(self):
        first = self.sync('A [[one]] b [[two]] c [[three]]')
        second = self.sync('A [[uno]] b [[two]]')
        self.assertEqual([pk for pk, _, _ in second], [pk for pk, _, _ in first][:2])
        self.assertEqual([answer for _, _, answer in second], ['uno', 'two'])

        third = self.sync('X [[a]] [[b]] [[c]] [[d]]')
        self.assertEqual([pk for pk, _, _ in third][:2], [pk for pk, _, _ in second])
        self.assertEqual([answer for _, _, answer in third], ['a', 'b', 'c', 'd'])
        self.assertEqual([order for _, order, _ in third], [0, 1, 2, 3])

    def test_an_empty_passage_removes_every_question(self):
        self.sync('A [[one]]')
        self.assertEqual(self.sync(''), [])


class ReadingModelTests(TestCase):
    def setUp(self):
        self.reading = Course.objects.create(title='Reading', category=Category.READING, short_description='x')
        self.listening = Course.objects.create(title='Listening', category=Category.LISTENING, short_description='x')

    def test_only_listening_needs_audio(self):
        reading = Part.objects.create(course=self.reading, number=1, name='R')
        listening = Part.objects.create(course=self.listening, number=1, name='L')
        self.assertFalse(reading.needs_audio)
        self.assertTrue(listening.needs_audio)

    def test_a_reading_exercise_is_ready_without_audio(self):
        part = Part.objects.create(course=self.reading, number=1, name='R', kind='choice')
        exercise = Exercise.objects.create(part=part, number=1)
        self.assertFalse(exercise.is_ready)
        Question.objects.create(exercise=exercise, option_a='a', option_b='b', option_c='c')
        self.assertTrue(Exercise.objects.get(pk=exercise.pk).is_ready)

    def test_a_listening_exercise_still_needs_its_audio(self):
        part = Part.objects.create(course=self.listening, number=1, name='L', kind='choice')
        exercise = Exercise.objects.create(part=part, number=1)
        Question.objects.create(exercise=exercise, option_a='a', option_b='b', option_c='c')
        self.assertFalse(Exercise.objects.get(pk=exercise.pk).is_ready)

    def test_a_passage_exercise_needs_text_and_gaps(self):
        part = Part.objects.create(course=self.reading, number=1, name='R', kind='passage_gap')
        exercise = Exercise.objects.create(part=part, number=1)
        Question.objects.create(exercise=exercise, answer='town')
        self.assertFalse(Exercise.objects.get(pk=exercise.pk).is_ready)  # questions but no text
        Exercise.objects.filter(pk=exercise.pk).update(passage='A [[town]]')
        self.assertTrue(Exercise.objects.get(pk=exercise.pk).is_ready)
        Exercise.objects.filter(pk=exercise.pk).update(passage='   ')
        self.assertFalse(Exercise.objects.get(pk=exercise.pk).is_ready)


class ReadingExerciseTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.course = Course.objects.create(title='Reading', category=Category.READING, short_description='x')
        seed_reading()
        cls.exercise = make_passage_exercise()
        cls.student = User.objects.create_user(email='s@t.uz', password=PASSWORD)
        cls.questions = list(cls.exercise.questions.all())

    def setUp(self):
        self.client.force_login(self.student)

    def url(self, name, number=1):
        return reverse(f'courses:{name}', args=[self.course.slug, 1, number])

    def submit(self, *values, **extra):
        data = {f'q{q.pk}': value for q, value in zip(self.questions, values)}
        return self.client.post(self.url('exercise_submit'), {**data, **extra})

    def test_intro_counts_the_gaps_and_uses_the_exercise_duration(self):
        response = self.client.get(self.url('exercise_intro'))
        self.assertContains(response, 'Reading · Part 1 · Exercise 1')
        self.assertContains(response, '1 part · 6 questions · <strong>8 minutes</strong>')
        self.assertContains(response, f'href="{self.url("exercise_play")}"')

    def test_play_page_has_no_audio_and_shows_the_title_instructions_and_text(self):
        response = self.client.get(self.url('exercise_play'))
        self.assertContains(response, 'Reading · Part 1 · Exercise 1')
        self.assertContains(response, '>08:00<')
        self.assertContains(response, '✍️ Part 1')
        self.assertContains(response, 'Type ONE word for each gap. The word is somewhere in the rest of the text.')
        self.assertContains(response, '<h3 class="gap-title">Olivia</h3>')
        self.assertContains(response, 'Olivia likes traveling and visiting new places.')
        self.assertNotContains(response, '<audio')
        self.assertNotContains(response, 'Listen</strong>')
        self.assertContains(response, 'Submit all parts')
        self.assertContains(response, 'id="submit-confirm"')

    def test_every_gap_is_a_numbered_input_inside_the_sentence(self):
        html = self.client.get(self.url('exercise_play')).content.decode()
        self.assertEqual(re.findall(r'class="gap-number">(\d+)<', html), ['1', '2', '3', '4', '5', '6'])
        self.assertEqual(re.findall(r'class="gap-ref">\(Q(\d+)\)<', html), ['1', '2', '3', '4', '5', '6'])
        self.assertEqual(html.count('class="gap-input"'), 6)
        for question in self.questions:
            self.assertIn(f'name="q{question.pk}"', html)
        self.assertIn('Although the <span class="gap-ref">(Q1)</span> <span class="gap-number">1</span> <input', html)
        self.assertRegex(html, r'aria-label="Question 1"> was small, it was really wonderful\.')
        self.assertRegex(html, r'aria-label="Question 6">\.</p>')  # the full stop hugs the last gap

    def test_the_markers_and_answers_never_reach_the_exercise_page(self):
        html = self.client.get(self.url('exercise_play')).content.decode()
        self.assertNotIn('[[', html)
        self.assertNotIn(']]', html)
        self.assertNotIn('is-correct', html)
        self.assertEqual(html.count('swimming in the'), 1)
        self.assertNotIn('swimming in the sea', html)  # the gap hides the word
        self.assertNotIn('The foods were', html)

    def test_all_correct_answers_ignoring_case_and_spaces(self):
        response = self.submit('Town', ' SEA ', 'foods', 'boat', 'Island', 'flowers', time_used='125')
        self.assertContains(response, '🎉</span> Perfect score!')
        self.assertContains(response, '<span>6</span> / 6 correct (100%)')
        self.assertContains(response, 'Time used: 02:05')
        self.assertEqual(ExerciseResult.objects.get().score, 6)

    def test_result_page_has_the_table_and_the_text_with_corrections(self):
        response = self.submit('town', '', 'food', 'boat', '', 'flowers')
        html = response.content.decode()
        self.assertContains(response, '<span>3</span> / 6 correct (50%)')
        rows = re.findall(
            r'<tr class="(is-correct|is-wrong)">\s*<td>(\d+)</td>\s*<td>(.*?)</td>\s*<td>(.*?)</td>', html)
        self.assertEqual(rows, [
            ('is-correct', '1', 'town', 'town'), ('is-wrong', '2', '–', 'sea'), ('is-wrong', '3', 'food', 'foods'),
            ('is-correct', '4', 'boat', 'boat'), ('is-wrong', '5', '–', 'island'), ('is-correct', '6', 'flowers', 'flowers'),
        ])
        self.assertContains(response, '<h3 class="gap-title">Olivia</h3>')
        self.assertContains(response, 'Olivia likes traveling and visiting new places.')
        self.assertContains(response, 'gap-answer is-correct">town</span>')
        self.assertContains(
            response, 'gap-answer is-wrong">&nbsp;</span> <span class="gap-fix">→ <strong>sea</strong></span>')
        self.assertContains(
            response, 'gap-answer is-wrong">food</span> <span class="gap-fix">→ <strong>foods</strong></span>')
        self.assertEqual(html.count('class="gap-fix"'), 3)
        self.assertNotContains(response, '<audio')
        self.assertNotContains(response, 'Transcript')
        self.assertNotContains(response, 'audio-player.js')
        self.assertContains(response, f'href="{self.url("exercise_intro")}">Try again</a>')

    def test_typed_text_is_escaped(self):
        response = self.submit('<script>alert(1)</script>')
        self.assertNotContains(response, '<script>alert(1)</script>')
        self.assertContains(response, '&lt;script&gt;alert(1)&lt;/script&gt;')

    def test_alternative_answers_are_accepted(self):
        Exercise.objects.filter(pk=self.exercise.pk).update(passage=OLIVIA_PASSAGE.replace('[[town]]', '[[town / city]]'))
        sync_passage_questions(Exercise.objects.get(pk=self.exercise.pk))
        self.assertContains(self.submit('CITY'), 'gap-answer is-correct">CITY</span>')

    def test_blank_lines_make_paragraphs_and_single_line_breaks_flow_on(self):
        Exercise.objects.filter(pk=self.exercise.pk).update(passage='First [[one]] line\nsecond line.\n\nNew [[two]] paragraph.')
        sync_passage_questions(Exercise.objects.get(pk=self.exercise.pk))
        html = self.client.get(self.url('exercise_play')).content.decode()
        self.assertEqual(html.count('class="passage-p"'), 2)
        self.assertIn(' line second line.</p>', html)
        self.assertNotIn('<br>', html.split('class="passage"')[1].split('</section>')[0])

    def test_numbers_typed_before_the_gaps_do_not_show_twice(self):
        passage = 'At first the 1.[[shop]] sold toys.\nLater the original\n2. [[meaning]] changed. In 1932 it grew.'
        Exercise.objects.filter(pk=self.exercise.pk).update(passage=passage)
        sync_passage_questions(Exercise.objects.get(pk=self.exercise.pk))
        play = self.client.get(self.url('exercise_play')).content.decode()
        self.assertIn('At first the <span class="gap-ref">(Q1)</span> <span class="gap-number">1</span>', play)
        self.assertIn('Later the original <span class="gap-ref">(Q2)</span>', play)
        self.assertNotIn('1.<span', play)
        self.assertIn('In 1932 it grew.', play)  # other numbers stay

        questions = list(Exercise.objects.get(pk=self.exercise.pk).questions.all())
        result = self.client.post(self.url('exercise_submit'), {f'q{q.pk}': 'x' for q in questions}).content.decode()
        self.assertIn('At first the <span class="gap-ref">(Q1)</span>', result)
        self.assertNotIn('1.<span', result)

    def test_the_passage_text_is_escaped(self):
        Exercise.objects.filter(pk=self.exercise.pk).update(passage='<b>Bold?</b> [[one]]')
        sync_passage_questions(Exercise.objects.get(pk=self.exercise.pk))
        response = self.client.get(self.url('exercise_play'))
        self.assertNotContains(response, '<b>Bold?</b>')
        self.assertContains(response, '&lt;b&gt;Bold?&lt;/b&gt;')

    def test_an_exercise_without_a_text_is_not_ready(self):
        empty = Exercise.objects.get(part__course=self.course, part__number=1, number=2)
        intro = self.client.get(self.url('exercise_intro', 2))
        self.assertContains(intro, 'not ready yet')
        self.assertContains(intro, 'its text and questions have not been added')
        self.assertRedirects(self.client.get(self.url('exercise_play', 2)), self.url('exercise_intro', 2))
        self.assertEqual(self.client.post(self.url('exercise_submit', 2), {}).status_code, 404)
        self.assertFalse(empty.is_ready)

    def test_the_tile_shows_the_best_score(self):
        self.submit('town', 'sea')
        self.assertContains(self.client.get(self.course.get_absolute_url()), '⭐ 2/6')


class ReadingStatementsTests(TestCase):
    """Part 2: ten statements (A–J), eight paragraphs (7–14), a dropdown under each paragraph."""

    @classmethod
    def setUpTestData(cls):
        cls.course = Course.objects.create(title='Reading', category=Category.READING, short_description='x')
        seed_reading()
        cls.exercise = make_statements_exercise()
        cls.student = User.objects.create_user(email='s@t.uz', password=PASSWORD)
        cls.questions = list(cls.exercise.questions.all())

    def setUp(self):
        self.client.force_login(self.student)

    def url(self, name):
        return reverse(f'courses:{name}', args=[self.course.slug, 2, 1])

    def submit(self, letters, **extra):
        data = {f'q{q.pk}': letter for q, letter in zip(self.questions, letters)}
        return self.client.post(self.url('exercise_submit'), {**data, **extra})

    def test_intro_counts_eight_questions_and_ten_minutes(self):
        response = self.client.get(self.url('exercise_intro'))
        self.assertContains(response, 'Reading · Part 2 · Exercise 1')
        self.assertContains(response, '1 part · 8 questions · <strong>10 minutes</strong>')

    def test_play_page_lists_the_statements_once_and_offers_them_under_every_paragraph(self):
        response = self.client.get(self.url('exercise_play'))
        html = response.content.decode()
        self.assertContains(response, '>10:00<')
        self.assertContains(response, '🔗 Part 2')
        self.assertContains(response, 'Each statement is used once. Two are extra!')
        self.assertNotContains(response, '<audio')
        for letter, text in zip('ABCDEFGHIJ', WALK_OPTIONS):
            self.assertContains(response, f'<li>{letter}) {text}</li>', count=1)
            self.assertContains(response, f'>{letter}) {text}</option>', count=8)
        self.assertContains(response, 'class="match-select"', count=8)
        self.assertContains(response, 'Choose an answer...', count=8)
        self.assertEqual(re.findall(r'<p class="q-line"><strong>(\d+)\.</strong>', html), [str(n) for n in range(7, 15)])
        self.assertContains(response, '<strong>7.</strong> Willow Farm is perfect for families.')
        self.assertNotContains(response, 'gap-title')  # Part 2 has no heading above the list
        self.assertTrue(html.index('<li>A)') < html.index('<select'))
        self.assertNotContains(response, 'selected')

    def test_a_paragraph_without_a_label_keeps_its_number_inline(self):
        html = self.client.get(self.url('exercise_play')).content.decode()
        self.assertNotIn('class="q-text"', html)

    def test_all_correct_letters_score_full_marks(self):
        response = self.submit('bcfjgihd', time_used='300')
        self.assertContains(response, '<span>8</span> / 8 correct (100%)')
        self.assertContains(response, 'Time used: 05:00')

    def test_result_shows_the_chosen_and_the_correct_statement_and_the_letters_table(self):
        response = self.submit('bc', time_used='45')  # q9 onwards unanswered
        html = response.content.decode()
        self.assertContains(response, '<span>2</span> / 8 correct (25%)')
        rows = re.findall(r'<tr class="(is-correct|is-wrong)">\s*<td>(\d+)</td>\s*<td>(.*?)</td>\s*<td>(.*?)</td>', html)
        self.assertEqual(rows[:3], [('is-correct', '7', 'B', 'B'), ('is-correct', '8', 'C', 'C'), ('is-wrong', '9', '–', 'F')])
        self.assertContains(response, 'Your answer: B) You want your kids to have outdoor fun and see animals.')
        self.assertContains(
            response, 'Correct answer: <strong>F) You prefer a quiet walk with a chance to explore rivers and wildlife.</strong>')
        self.assertContains(response, '<li>J) You want to walk in flower gardens with short guided tours.</li>')
        self.assertContains(response, 'Each statement is used once. Two are extra!')
        self.assertNotContains(response, '<audio')


class ReadingHeadingsTests(TestCase):
    """Part 3: a titled list of headings (A–H) and labelled paragraphs (15–20) to match them with."""

    @classmethod
    def setUpTestData(cls):
        cls.course = Course.objects.create(title='Reading', category=Category.READING, short_description='x')
        seed_reading()
        cls.exercise = make_headings_exercise()
        cls.student = User.objects.create_user(email='s@t.uz', password=PASSWORD)
        cls.questions = list(cls.exercise.questions.all())

    def setUp(self):
        self.client.force_login(self.student)

    def url(self, name):
        return reverse(f'courses:{name}', args=[self.course.slug, 3, 1])

    def submit(self, letters, **extra):
        data = {f'q{q.pk}': letter for q, letter in zip(self.questions, letters)}
        return self.client.post(self.url('exercise_submit'), {**data, **extra})

    def test_play_page_shows_the_title_between_the_instructions_and_the_headings(self):
        response = self.client.get(self.url('exercise_play'))
        html = response.content.decode()
        self.assertContains(response, '🏷️ Part 3')
        self.assertContains(response, '>10:00<')
        self.assertContains(response, 'Choose the correct heading for each paragraph.')
        self.assertContains(response, '<h3 class="gap-title">Pedestrian Zones and Their Growth</h3>')
        self.assertTrue(
            html.index('Choose the correct heading') < html.index('Pedestrian Zones and Their Growth')
            < html.index('<li>A)'))
        for letter, text in zip('ABCDEFGH', HEADINGS):
            self.assertContains(response, f'<li>{letter}) {text}</li>', count=1)
            self.assertContains(response, f'>{letter}) {text}</option>', count=6)

    def test_every_paragraph_has_a_bold_number_and_label_then_its_text_then_the_dropdown(self):
        response = self.client.get(self.url('exercise_play'))
        html = response.content.decode()
        for number, (label, text, _) in zip(range(15, 21), PARAGRAPHS):
            self.assertContains(response, f'<p class="q-line"><strong>{number}. {label}</strong></p>')
        self.assertContains(
            response, '<p class="q-text">Modern traffic-free shopping streets may seem like a new idea, but they actually have a long history.')
        first = html.index('<strong>15. Paragraph I</strong>')
        self.assertTrue(first < html.index('class="q-text"') < html.index('<select', first))
        self.assertContains(response, 'class="match-select"', count=6)

    def test_scoring_and_the_result_page_keep_the_labels(self):
        response = self.submit('dhfecg')  # correct: d, h, f, e, c, g
        self.assertContains(response, '<span>6</span> / 6 correct (100%)')
        response = self.submit('dxfxcg', time_used='200')
        html = response.content.decode()
        self.assertContains(response, '<span>4</span> / 6 correct (67%)')
        self.assertContains(response, '<strong>16. Paragraph II</strong>')
        self.assertContains(response, 'Correct answer: <strong>H) When the modern idea began</strong>')
        self.assertContains(response, '<h3 class="gap-title">Pedestrian Zones and Their Growth</h3>')
        rows = re.findall(r'<tr class="(is-correct|is-wrong)">\s*<td>(\d+)</td>\s*<td>(.*?)</td>\s*<td>(.*?)</td>', html)
        self.assertEqual([(row[1], row[2], row[3]) for row in rows], [
            ('15', 'D', 'D'), ('16', '–', 'H'), ('17', 'F', 'F'), ('18', '–', 'E'), ('19', 'C', 'C'), ('20', 'G', 'G'),
        ])

    def test_label_and_text_are_escaped_and_line_breaks_kept(self):
        Question.objects.filter(pk=self.questions[0].pk).update(label='<i>Paragraph I</i>', text='First line\nSecond <b>line</b>')
        response = self.client.get(self.url('exercise_play'))
        self.assertNotContains(response, '<i>Paragraph I</i>')
        self.assertContains(response, '<strong>15. &lt;i&gt;Paragraph I&lt;/i&gt;</strong>')
        self.assertContains(response, 'First line<br>Second &lt;b&gt;line&lt;/b&gt;')

    def test_a_label_without_a_text_still_shows_the_number_and_label(self):
        Question.objects.filter(pk=self.questions[0].pk).update(text='')
        response = self.client.get(self.url('exercise_play'))
        self.assertContains(response, '<strong>15. Paragraph I</strong>')


class ReadingTextWithQuestionsTests(TestCase):
    """Part 4: a titled text to read, then A–D questions (21–24) and True / False / Not given questions (25–29)."""

    @classmethod
    def setUpTestData(cls):
        cls.course = Course.objects.create(title='Reading', category=Category.READING, short_description='x')
        seed_reading()
        cls.exercise = make_meat_exercise()
        cls.student = User.objects.create_user(email='s@t.uz', password=PASSWORD)
        cls.questions = list(cls.exercise.questions.all())

    def setUp(self):
        self.client.force_login(self.student)

    def url(self, name):
        return reverse(f'courses:{name}', args=[self.course.slug, 4, 1])

    def submit(self, letters, **extra):
        data = {f'q{q.pk}': letter for q, letter in zip(self.questions, letters)}
        return self.client.post(self.url('exercise_submit'), {**data, **extra})

    def test_intro_counts_nine_questions_and_fifteen_minutes(self):
        response = self.client.get(self.url('exercise_intro'))
        self.assertContains(response, '1 part · 9 questions · <strong>15 minutes</strong>')

    def test_play_page_shows_the_instruction_title_and_the_text_in_paragraphs(self):
        response = self.client.get(self.url('exercise_play'))
        html = response.content.decode()
        self.assertContains(response, '>15:00<')
        self.assertContains(response, '✅ Part 4')
        self.assertContains(response, 'Read the following text for questions 21-29.')
        self.assertContains(response, '<h3 class="gap-title">Eating meat</h3>')
        self.assertContains(response, 'class="passage-p"', count=4)
        self.assertContains(response, '<p class="passage-p">Do you hate the idea of animal-free meat?')
        self.assertNotContains(response, '<audio')
        self.assertNotContains(response, 'gap-input')  # nothing to type inside the text
        text_end = html.index('Meat is consuming the planet.')
        self.assertTrue(
            html.index('Read the following text') < html.index('Eating meat') < text_end
            < html.index('Questions 21-24:') < html.index('class="q-number">21.<'))

    def test_the_questions_have_intro_cards_and_four_or_three_options(self):
        response = self.client.get(self.url('exercise_play'))
        html = response.content.decode()
        self.assertContains(response, 'class="q-intro"', count=2)
        self.assertContains(response, '<strong>Questions 21-24:</strong> choose the correct answer A, B, C or D.')
        self.assertContains(response, '<strong>Questions 25-29:</strong> write True, False or Not given.')
        self.assertEqual(re.findall(r'class="q-number">(\d+)\.<', html), [str(n) for n in range(21, 30)])
        self.assertContains(response, '<strong class="q-number">21.</strong> New type of meat is ....')
        self.assertContains(response, 'type="radio"', count=4 * 4 + 5 * 3)
        self.assertContains(response, f'name="q{self.questions[0].pk}" value="d"')
        self.assertNotContains(response, f'name="q{self.questions[4].pk}" value="d"')  # a True/False question has no D
        self.assertContains(response, '<span class="q-label">for people who don&#x27;t like meat</span>')

    def test_a_text_is_shown_as_it_is_without_gap_processing(self):
        Exercise.objects.filter(pk=self.exercise.pk).update(passage='A [[bracketed]] word.\n\nSecond <b>paragraph</b>.')
        response = self.client.get(self.url('exercise_play'))
        self.assertContains(response, '<p class="passage-p">A [[bracketed]] word.</p>')
        self.assertContains(response, '<p class="passage-p">Second &lt;b&gt;paragraph&lt;/b&gt;.</p>')
        self.assertEqual(Exercise.objects.get(pk=self.exercise.pk).questions.count(), 9)  # nothing was re-generated

    def test_an_exercise_without_a_text_still_plays_when_it_has_questions(self):
        Exercise.objects.filter(pk=self.exercise.pk).update(passage='', title='')
        response = self.client.get(self.url('exercise_play'))
        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, 'passage-p')

    def test_answers_a_to_d_are_graded_and_d_counts_only_when_it_is_offered(self):
        correct = ''.join(q.correct for q in self.questions)
        response = self.submit(correct, time_used='400')
        self.assertContains(response, '<span>9</span> / 9 correct (100%)')
        self.assertContains(response, 'Time used: 06:40')
        answers = list(correct)
        answers[4] = 'd'  # question 25 offers only A–C: D is not an answer
        response = self.submit(''.join(answers))
        self.assertContains(response, '<span>8</span> / 9 correct (89%)')
        self.assertContains(response, 'You did not answer this question.', count=1)

    def test_result_page_repeats_the_text_and_marks_every_option_including_d(self):
        response = self.submit('abdc' + 'a' * 5)  # q22 wrong (b), q23 right (d), q24 right (c)
        html = response.content.decode()
        self.assertContains(response, '<h3 class="gap-title">Eating meat</h3>')
        self.assertContains(response, 'class="passage-p"', count=4)
        rows = re.findall(r'<tr class="(is-correct|is-wrong)">\s*<td>(\d+)</td>\s*<td>(.*?)</td>\s*<td>(.*?)</td>', html)
        self.assertEqual([(r[1], r[2], r[3]) for r in rows[:4]], [('21', 'A', 'A'), ('22', 'B', 'C'), ('23', 'D', 'D'), ('24', 'C', 'C')])
        self.assertContains(response, 'class="q-card"', count=9)
        self.assertContains(response, 'class="q-intro"', count=2)
        self.assertContains(response, '✗ your answer</span>')
        self.assertContains(response, '<span class="q-letter">D</span>', count=4)


class ReadingTextWithGapsAndTestTests(TestCase):
    """Part 5: a text with gaps 30–33 inside it, then two test questions (34–35)."""

    @classmethod
    def setUpTestData(cls):
        cls.course = Course.objects.create(title='Reading', category=Category.READING, short_description='x')
        seed_reading()
        cls.exercise = make_summary_exercise()
        cls.student = User.objects.create_user(email='s@t.uz', password=PASSWORD)
        cls.questions = list(cls.exercise.questions.all())

    def setUp(self):
        self.client.force_login(self.student)

    def url(self, name):
        return reverse(f'courses:{name}', args=[self.course.slug, 5, 1])

    def submit(self, answers, **extra):
        data = {f'q{q.pk}': value for q, value in zip(self.questions, answers)}
        return self.client.post(self.url('exercise_submit'), {**data, **extra})

    def test_the_part_is_the_combined_kind_and_the_exercise_is_ready_without_audio(self):
        self.assertEqual(self.exercise.part.kind, 'passage_mixed')
        self.assertTrue(Exercise.objects.get(pk=self.exercise.pk).is_ready)
        self.assertEqual([q.is_choice for q in self.questions], [False] * 4 + [True] * 2)
        self.assertEqual([q.order for q in self.questions], list(range(6)))

    def test_intro_counts_all_six_questions(self):
        self.assertContains(self.client.get(self.url('exercise_intro')), '1 part · 6 questions · <strong>12 minutes</strong>')

    def test_play_page_has_the_gaps_in_the_text_and_the_test_questions_under_it(self):
        response = self.client.get(self.url('exercise_play'))
        html = response.content.decode()
        self.assertContains(response, '<h3 class="gap-title">Riverton</h3>')
        self.assertEqual(re.findall(r'class="gap-number">(\d+)<', html), ['30', '31', '32', '33'])
        self.assertEqual(re.findall(r'class="q-number">(\d+)\.<', html), ['34', '35'])
        self.assertEqual(html.count('class="gap-input"'), 4)
        self.assertContains(response, 'type="radio"', count=2 * 4)
        self.assertContains(response, 'class="q-intro"', count=1)
        self.assertContains(response, '<strong>Questions 34-35:</strong> choose the correct answer A, B, C or D.')
        self.assertTrue(
            html.index('gap-number">33<') < html.index('class="q-intro"') < html.index('class="q-number">34.<'))
        self.assertNotContains(response, '<audio')
        self.assertNotContains(response, '[[')
        self.assertNotContains(response, 'checked')

    def test_the_gap_inputs_and_the_radios_belong_to_the_right_questions(self):
        html = self.client.get(self.url('exercise_play')).content.decode()
        for question in self.questions[:4]:
            self.assertIn(f'<input type="text" class="gap-input" name="q{question.pk}"', html)
        for question in self.questions[4:]:
            self.assertIn(f'type="radio" name="q{question.pk}" value="d"', html)
            self.assertNotIn(f'<input type="text" class="gap-input" name="q{question.pk}"', html)

    def test_mixed_answers_are_graded_by_the_kind_of_each_question(self):
        response = self.submit(['PORT', 'bridge', 'market', 'tower', 'b', 'd'], time_used='90')
        self.assertContains(response, '<span>6</span> / 6 correct (100%)')
        response = self.submit(['port', 'bridge', 'wrong', '', 'b', 'a'])
        self.assertContains(response, '<span>3</span> / 6 correct (50%)')
        html = response.content.decode()
        rows = re.findall(r'<tr class="(is-correct|is-wrong)">\s*<td>(\d+)</td>\s*<td>(.*?)</td>\s*<td>(.*?)</td>', html)
        self.assertEqual([(r[1], r[2], r[3]) for r in rows], [
            ('30', 'port', 'port'), ('31', 'bridge', 'bridge'), ('32', 'wrong', 'market'), ('33', '–', 'tower'),
            ('34', 'B', 'B'), ('35', 'A', 'D'),
        ])

    def test_result_page_shows_the_text_review_and_cards_for_the_test_questions_only(self):
        response = self.submit(['port', 'bridge', 'wrong', '', 'b', 'a'])
        self.assertContains(response, '<h3 class="gap-title">Riverton</h3>')
        self.assertContains(response, 'gap-answer is-wrong">wrong</span> <span class="gap-fix">→ <strong>market</strong></span>')
        self.assertContains(response, 'gap-answer is-wrong">&nbsp;</span> <span class="gap-fix">→ <strong>tower</strong></span>')
        self.assertContains(response, 'class="q-card"', count=2)
        self.assertContains(response, 'class="q-intro"', count=1)
        self.assertContains(response, '✓ correct</span>', count=2)
        self.assertContains(response, '✗ your answer</span>', count=1)

    def test_a_letter_typed_into_a_gap_or_a_word_into_a_test_question_is_just_wrong(self):
        response = self.submit(['b', 'b', 'b', 'b', 'port', 'zzz'])
        self.assertContains(response, '<span>0</span> / 6 correct (0%)')

    def test_an_exercise_with_gaps_but_no_text_is_not_ready(self):
        Exercise.objects.filter(pk=self.exercise.pk).update(passage='')
        self.assertFalse(Exercise.objects.get(pk=self.exercise.pk).is_ready)


class MixedExerciseSyncTests(TestCase):
    def setUp(self):
        self.course = Course.objects.create(title='Reading', category=Category.READING, short_description='x')
        seed_reading()
        self.exercise = make_summary_exercise()

    def rows(self):
        return list(self.exercise.questions.values_list('pk', 'order', 'answer', 'option_a'))

    def change(self, passage):
        self.exercise.passage = passage
        self.exercise.save()
        sync_passage_questions(self.exercise)

    def test_more_gaps_push_the_test_questions_further_down_without_touching_them(self):
        before = self.rows()
        tests_before = [row for row in before if row[3]]
        self.change(SUMMARY_PASSAGE + ' And a fifth [[gate]] too.')
        after = self.rows()
        self.assertEqual([row[2] for row in after[:5]], SUMMARY_ANSWERS + ['gate'])
        self.assertEqual([row[1] for row in after], list(range(7)))
        self.assertEqual([row for row in after if row[3]][0][0], tests_before[0][0])  # same question rows
        self.assertEqual([row[0] for row in after if row[3]], [row[0] for row in tests_before])
        self.assertTrue(all(row[3] for row in after[5:]))

    def test_fewer_gaps_pull_them_back_and_drop_only_the_gap_rows(self):
        self.change('Just one [[gap]] left.')
        rows = self.rows()
        self.assertEqual([(row[1], row[2]) for row in rows[:1]], [(0, 'gap')])
        self.assertEqual([row[1] for row in rows], [0, 1, 2])
        self.assertEqual([bool(row[3]) for row in rows], [False, True, True])

    def test_no_gaps_at_all_leaves_the_test_questions(self):
        self.change('')
        self.assertEqual([bool(row[3]) for row in self.rows()], [True, True])
        self.assertEqual([row[1] for row in self.rows()], [0, 1])


class ReadingAudioFreePagesTests(TestCase):
    """Reading Parts that still use a plain kind (until their formats arrive) must work without audio too."""

    def test_a_choice_exercise_of_a_reading_course_plays_without_audio(self):
        course = Course.objects.create(title='Reading', category=Category.READING, short_description='x')
        seed_reading()
        exercise = Exercise.objects.get(part__course=course, part__number=4, number=1)
        Question.objects.create(
            exercise=exercise, text='Is it true?', option_a='True', option_b='False', option_c='Not given', correct='b')
        student = User.objects.create_user(email='s@t.uz', password=PASSWORD)
        self.client.force_login(student)

        play = self.client.get(reverse('courses:exercise_play', args=[course.slug, 4, 1]))
        self.assertContains(play, 'Is it true?')
        self.assertNotContains(play, '<audio')
        question = exercise.questions.get()
        result = self.client.post(reverse('courses:exercise_submit', args=[course.slug, 4, 1]), {f'q{question.pk}': 'b'})
        self.assertContains(result, '<span>1</span> / 1 correct (100%)')
        self.assertNotContains(result, '<audio')
