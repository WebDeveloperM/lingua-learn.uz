import os
import re

from django.test import SimpleTestCase, TestCase
from django.urls import reverse

from accounts.models import Role, User

from .grading import accepted_answers, normalize_answer
from .models import Category, Course, Exercise, ExerciseResult, Part, Question
from .support import (
    LECTURE_NOTE, MAP_PLACES, MATCHING_OPTIONS, TempMediaMixin, make_extracts_exercise, make_gap_exercise,
    make_lecture_exercise, make_map_exercise, make_matching_exercise, make_ready_exercise, seed,
)

PASSWORD = 'StrongPass123!'


def numbers_in(html, css_class):
    return re.findall(rf'class="{css_class}">(\d+)<', html)


def question_numbers(html):
    """The bold "24." style numbers written before a question's text."""
    return re.findall(r'class="q-number">(\d+)\.<', html)


class PartFormatSeedTests(TestCase):
    def setUp(self):
        self.course = Course.objects.create(title='Listening', category=Category.LISTENING, short_description='x')

    def formats(self):
        return {p.number: (p.kind, p.first_question_number) for p in Part.objects.all()}

    def test_formats_of_the_known_parts(self):
        seed()
        formats = self.formats()
        self.assertEqual(formats[1], ('choice', 1))
        self.assertEqual(formats[2], ('gap_fill', 9))
        self.assertEqual(formats[3], ('matching', 15))
        self.assertEqual(formats[4], ('map', 19))
        self.assertEqual(formats[5], ('choice', 24))
        self.assertEqual(formats[6], ('gap_fill', 30))

    def test_parts_with_a_known_format_get_their_instructions(self):
        seed()
        self.assertIn('**ONE WORD and / or A NUMBER**', Part.objects.get(number=2).instructions)
        self.assertIn('(19–23) on the map (A–I)', Part.objects.get(number=4).instructions)
        self.assertIn('**FOUR extra**', Part.objects.get(number=4).instructions)
        self.assertIn('three extracts', Part.objects.get(number=5).instructions)
        self.assertIn('(24–29)', Part.objects.get(number=5).instructions)
        self.assertIn('part of a lecture', Part.objects.get(number=6).instructions)
        self.assertIn('**ONE WORD and / or A NUMBER**', Part.objects.get(number=6).instructions)
        self.assertEqual(Part.objects.get(number=3).instructions, '')

    def test_parts_created_before_their_format_was_known_are_upgraded(self):
        for number in (2, 3, 4, 5, 6):
            Part.objects.create(course=self.course, number=number, name=f'Old {number}')
        seed()
        self.assertEqual(self.formats()[2], ('gap_fill', 9))
        self.assertEqual(self.formats()[3], ('matching', 15))
        self.assertEqual(self.formats()[4], ('map', 19))
        self.assertEqual(self.formats()[5], ('choice', 24))
        self.assertEqual(self.formats()[6], ('gap_fill', 30))

    def test_every_part_opens_its_editor_with_its_own_number_of_rows(self):
        seed()
        counts = {p.number: p.questions_count for p in Part.objects.all()}
        self.assertEqual(counts, {1: 8, 2: 6, 3: 4, 4: 5, 5: 6, 6: 6})
        # the rows match the question numbers each Part spans: 1–8, 9–14, 15–18, 19–23, 24–29, 30–35
        parts = list(Part.objects.order_by('number'))
        for part, following in zip(parts, parts[1:]):
            self.assertEqual(part.first_question_number + part.questions_count, following.first_question_number)

    def test_rerun_keeps_a_question_count_edited_in_the_panel(self):
        seed()
        Part.objects.filter(number=5).update(questions_count=7)
        seed()
        self.assertEqual(Part.objects.get(number=5).questions_count, 7)

    def test_existing_parts_without_a_question_count_get_one(self):
        part = Part.objects.create(course=self.course, number=5, name='Extracts', first_question_number=24)
        self.assertEqual(part.questions_count, 0)
        self.assertEqual(part.expected_questions, 8)  # still the by-kind default until the seed runs
        seed()
        part.refresh_from_db()
        self.assertEqual((part.questions_count, part.expected_questions), (6, 6))

    def test_a_part_that_already_holds_questions_keeps_its_format(self):
        part = Part.objects.create(course=self.course, number=4, name='Old 4')
        exercise = Exercise.objects.create(part=part, number=1)
        Question.objects.create(exercise=exercise, order=0, option_a='a', option_b='b', option_c='c')
        seed()
        self.assertEqual(self.formats()[4], ('choice', 1))

    def test_edited_parts_are_left_alone(self):
        seed()
        Part.objects.filter(number=3).update(kind='choice', first_question_number=20)
        Part.objects.filter(number=2).update(first_question_number=10)
        seed()
        self.assertEqual(self.formats()[3], ('choice', 20))
        self.assertEqual(self.formats()[2], ('gap_fill', 10))


class AnswerNormalisationTests(SimpleTestCase):
    def test_normalize_answer(self):
        self.assertEqual(normalize_answer('  Space   STATION '), 'space station')
        self.assertEqual(normalize_answer(None), '')

    def test_accepted_answers_are_split_on_slashes(self):
        self.assertEqual(accepted_answers('space station / futuristic city'), ['space station', 'futuristic city'])
        self.assertEqual(accepted_answers(' a/b/ '), ['a', 'b'])
        self.assertEqual(accepted_answers(''), [])


class ExerciseHelpersTests(TestCase):
    def setUp(self):
        course = Course.objects.create(title='Listening', category=Category.LISTENING, short_description='x')
        self.part = Part.objects.create(course=course, number=1, name='P', instructions='Part text')
        self.exercise = Exercise.objects.create(part=self.part, number=1)

    def test_option_list_assigns_letters_and_skips_blank_lines(self):
        self.exercise.options = '  First  \n\n Second\n   \nThird'
        self.assertEqual(self.exercise.option_list, [('a', 'First'), ('b', 'Second'), ('c', 'Third')])

    def test_option_list_stops_at_ten(self):
        self.exercise.options = '\n'.join(f'Option {i}' for i in range(15))
        self.assertEqual(len(self.exercise.option_list), 10)
        self.assertEqual(self.exercise.option_list[-1][0], 'j')

    def test_exercise_text_overrides_the_part_text(self):
        self.assertEqual(self.exercise.effective_instructions, 'Part text')
        self.exercise.instructions = 'Own text'
        self.assertEqual(self.exercise.effective_instructions, 'Own text')


class PartHelpersTests(TestCase):
    def setUp(self):
        self.course = Course.objects.create(title='Listening', category=Category.LISTENING, short_description='x')

    def test_expected_questions_follow_the_kind_until_the_part_sets_its_own(self):
        usual = {'choice': 8, 'gap_fill': 6, 'matching': 4, 'map': 5, 'passage_gap': 6, 'passage_mixed': 2}
        for number, (kind, expected) in enumerate(usual.items(), start=1):
            part = Part.objects.create(course=self.course, number=number, name=kind, kind=kind)
            self.assertEqual(part.expected_questions, expected, kind)
            part.questions_count = 3
            self.assertEqual(part.expected_questions, 3, kind)
        self.assertEqual(set(usual), {kind for kind, _ in Part.Kind.choices})


class GapFillExerciseTests(TempMediaMixin, TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.course = Course.objects.create(title='Listening', category=Category.LISTENING, short_description='x')
        seed()
        cls.exercise = make_gap_exercise()
        cls.student = User.objects.create_user(email='s@t.uz', password=PASSWORD)
        cls.questions = list(cls.exercise.questions.all())

    def setUp(self):
        self.client.force_login(self.student)

    def url(self, name):
        return reverse(f'courses:{name}', args=[self.course.slug, 2, 1])

    def answers(self, *values):
        return {f'q{q.pk}': value for q, value in zip(self.questions, values)}

    def submit(self, *values):
        return self.client.post(self.url('exercise_submit'), self.answers(*values))

    def test_intro_counts_the_gaps_and_uses_the_exercise_duration(self):
        response = self.client.get(self.url('exercise_intro'))
        self.assertContains(response, 'Listening · Part 2 · Exercise 1')
        self.assertContains(response, '1 part · 3 questions · <strong>6 minutes</strong>')

    def test_play_page_is_a_note_with_inputs_numbered_from_nine(self):
        response = self.client.get(self.url('exercise_play'))
        html = response.content.decode()
        self.assertContains(response, '✍️ Part 2')
        self.assertContains(response, '>06:00<')
        self.assertContains(response, 'Video game review')
        self.assertContains(response, 'fill in the missing information')
        self.assertContains(response, '<strong>ONE WORD and / or A NUMBER</strong>')
        self.assertContains(response, 'Action takes place in:')
        self.assertContains(response, 'www.')
        self.assertContains(response, '.com')
        self.assertEqual(numbers_in(html, 'gap-number'), ['9', '10', '11'])
        self.assertContains(response, 'class="gap-input"', count=3)
        self.assertContains(response, 'Submit all parts')
        self.assertNotContains(response, 'type="radio"')
        self.assertNotContains(response, '<select')

    def test_play_page_does_not_leak_the_answers(self):
        html = self.client.get(self.url('exercise_play')).content.decode()
        for answer in ('space station', 'futuristic city', 'history', 'gamingworld'):
            self.assertNotIn(answer, html)

    def test_answers_ignore_case_and_extra_spaces(self):
        response = self.submit('  SPACE   Station ', 'History', 'GamingWorld')
        self.assertContains(response, '<span>3</span> / 3')
        self.assertEqual(ExerciseResult.objects.get().score, 3)

    def test_any_listed_alternative_is_accepted(self):
        self.assertContains(self.submit('Futuristic City', 'history', 'gamingworld'), '<span>3</span> / 3')

    def test_partial_wrong_and_blank_answers_are_marked_wrong(self):
        response = self.submit('space', '', 'gaming world')
        self.assertContains(response, '<span>0</span> / 3')

    def test_result_page_shows_what_was_typed_and_the_correct_answers(self):
        response = self.submit('Space Station', '', 'wrong')
        html = response.content.decode()
        self.assertContains(response, '<span>1</span> / 3')
        self.assertEqual(numbers_in(html, 'gap-number'), ['9', '10', '11'])
        self.assertContains(response, 'gap-answer is-correct">Space Station<')
        self.assertContains(response, 'gap-answer is-wrong">—<')
        self.assertContains(response, 'gap-answer is-wrong">wrong<')
        self.assertContains(response, 'Correct answer: <strong>history</strong>')
        self.assertContains(response, 'Correct answer: <strong>gamingworld</strong>')
        self.assertNotContains(response, 'Correct answer: <strong>space station')

    def test_typed_text_is_escaped(self):
        response = self.submit('<script>alert(1)</script>', '', '')
        self.assertNotContains(response, '<script>alert(1)</script>')
        self.assertContains(response, '&lt;script&gt;alert(1)&lt;/script&gt;')


class LectureNotesExerciseTests(TempMediaMixin, TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.course = Course.objects.create(title='Listening', category=Category.LISTENING, short_description='x')
        seed()
        cls.exercise = make_lecture_exercise()
        cls.student = User.objects.create_user(email='s@t.uz', password=PASSWORD)
        cls.questions = list(cls.exercise.questions.all())

    def setUp(self):
        self.client.force_login(self.student)

    def url(self, name):
        return reverse(f'courses:{name}', args=[self.course.slug, 6, 1])

    def submit(self, *values):
        return self.client.post(
            self.url('exercise_submit'), {f'q{q.pk}': value for q, value in zip(self.questions, values)})

    def test_intro_counts_the_six_gaps_and_uses_the_exercise_duration(self):
        response = self.client.get(self.url('exercise_intro'))
        self.assertContains(response, 'Listening · Part 6 · Exercise 1')
        self.assertContains(response, '1 part · 6 questions · <strong>8 minutes</strong>')

    def test_play_page_is_a_note_with_gaps_numbered_30_to_35(self):
        response = self.client.get(self.url('exercise_play'))
        html = response.content.decode()
        self.assertContains(response, '>08:00<')
        self.assertContains(response, 'You will hear a part of a lecture.')
        self.assertContains(response, '<strong>ONE WORD and / or A NUMBER</strong>')
        self.assertContains(response, '<h3 class="gap-title">Labyrinths</h3>')
        self.assertEqual(numbers_in(html, 'gap-number'), [str(n) for n in range(30, 36)])
        self.assertContains(response, 'class="gap-input"', count=6)
        self.assertContains(response, '<span class="gap-text">Mazes are a type of</span>')
        self.assertContains(response, '<span class="gap-text">and prayer.</span>')
        self.assertContains(response, 'Submit all parts')
        self.assertNotContains(response, 'type="radio"')
        self.assertNotContains(response, '<select')

    def test_the_plain_line_sits_between_gaps_31_and_32_and_is_not_a_question(self):
        response = self.client.get(self.url('exercise_play'))
        html = response.content.decode()
        self.assertContains(response, f'<p class="gap-note">{LECTURE_NOTE}</p>', count=1)
        self.assertTrue(
            html.index('gap-number">31<') < html.index('class="gap-note"') < html.index('gap-number">32<'))
        self.assertEqual(html.count('class="gap-input"'), 6)
        # the plain line takes no number: the gaps are still 30..35
        self.assertEqual(numbers_in(html, 'gap-number'), [str(n) for n in range(30, 36)])

    def test_play_page_does_not_leak_the_answers(self):
        html = self.client.get(self.url('exercise_play')).content.decode()
        for answer in ('puzzle', 'confusion', 'meditation', 'worship', 'rocks', 'coins', 'tree'):
            self.assertNotIn(answer, html)

    def test_result_keeps_the_plain_line_and_marks_each_gap(self):
        response = self.submit('Puzzle', 'fear', 'WORSHIP', ' rocks ', '', 'tree')
        html = response.content.decode()
        self.assertContains(response, '<span>4</span> / 6')
        self.assertEqual(numbers_in(html, 'gap-number'), [str(n) for n in range(30, 36)])
        self.assertContains(response, f'<p class="gap-note">{LECTURE_NOTE}</p>', count=1)
        self.assertTrue(
            html.index('gap-number">31<') < html.index('class="gap-note"') < html.index('gap-number">32<'))
        self.assertContains(response, 'Correct answer: <strong>confusion</strong>')
        self.assertContains(response, 'Correct answer: <strong>coins</strong>')
        self.assertContains(response, 'gap-answer is-correct">WORSHIP<')

    def test_plain_line_is_escaped_but_keeps_bold(self):
        Question.objects.filter(pk=self.questions[2].pk).update(intro='<b>x</b> and **bold**')
        response = self.client.get(self.url('exercise_play'))
        self.assertNotContains(response, '<b>x</b>')
        self.assertContains(response, '<p class="gap-note">&lt;b&gt;x&lt;/b&gt; and <strong>bold</strong></p>')

    def test_gaps_without_a_plain_line_have_no_note(self):
        Question.objects.update(intro='')
        self.assertNotContains(self.client.get(self.url('exercise_play')), 'gap-note')


class MatchingExerciseTests(TempMediaMixin, TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.course = Course.objects.create(title='Listening', category=Category.LISTENING, short_description='x')
        seed()
        cls.exercise = make_matching_exercise()
        cls.student = User.objects.create_user(email='s@t.uz', password=PASSWORD)
        cls.admin = User.objects.create_user(email='a@t.uz', password=PASSWORD, role=Role.ADMIN)
        cls.questions = list(cls.exercise.questions.all())

    def setUp(self):
        self.client.force_login(self.student)

    def url(self, name):
        return reverse(f'courses:{name}', args=[self.course.slug, 3, 1])

    def submit(self, letters):
        return self.client.post(
            self.url('exercise_submit'), {f'q{q.pk}': letter for q, letter in zip(self.questions, letters)},
        )

    def test_play_page_lists_the_options_and_a_dropdown_per_speaker(self):
        response = self.client.get(self.url('exercise_play'))
        html = response.content.decode()
        self.assertContains(response, '🗣️ Part 3')
        self.assertContains(response, 'habits they find difficult to control')
        self.assertContains(response, '<strong>TWO extra</strong>')
        for letter, text in zip('ABCDEF', MATCHING_OPTIONS):
            self.assertContains(response, f'<li>{letter}) {text}</li>', count=1)
            self.assertContains(response, f'>{letter}) {text}</option>', count=4)
        self.assertContains(response, 'class="match-select"', count=4)
        self.assertContains(response, 'Choose an answer...', count=4)
        for number in (15, 16, 17, 18):
            self.assertContains(response, f'<strong>{number}.</strong> Speaker {number - 14}')
        self.assertContains(response, 'Submit all parts')
        self.assertNotContains(response, 'type="radio"')
        self.assertNotContains(response, 'gap-input')
        self.assertTrue(html.index('<li>A)') < html.index('<select'))

    def test_play_page_does_not_leak_the_correct_letters(self):
        html = self.client.get(self.url('exercise_play')).content.decode()
        self.assertNotIn('selected', html)
        self.assertNotIn('is-correct', html)

    def test_part_text_is_used_when_the_exercise_has_none(self):
        Exercise.objects.filter(pk=self.exercise.pk).update(instructions='')
        Part.objects.filter(pk=self.exercise.part_id).update(instructions='Part level **text**')
        response = self.client.get(self.url('exercise_play'))
        self.assertContains(response, 'Part level <strong>text</strong>')
        self.assertNotContains(response, 'habits they find difficult')

    def test_all_correct_letters_score_full_marks(self):
        response = self.submit('daec')
        self.assertContains(response, '<span>4</span> / 4')
        self.assertContains(response, 'Perfect score!')

    def test_result_shows_the_chosen_and_the_correct_option_for_mistakes(self):
        response = self.submit('baec')
        self.assertContains(response, '<span>3</span> / 4')
        self.assertContains(response, 'Your answer: B) Doing too much exercise.')
        self.assertContains(response, 'Correct answer: <strong>D) Watching too much television.</strong>')
        self.assertContains(response, 'class="q-option review-answer is-correct"', count=3)
        self.assertContains(response, 'class="q-option review-answer is-wrong"', count=1)
        for number in (15, 16, 17, 18):
            self.assertContains(response, f'<strong>{number}.</strong>')

    def test_blank_and_out_of_range_choices_are_unanswered(self):
        response = self.submit(['', 'z', 'j', 'c'])
        self.assertContains(response, '<span>1</span> / 4')
        self.assertContains(response, 'You did not answer this question.', count=3)

    def test_exercise_without_enough_options_is_not_ready(self):
        for options in ('', 'Only one'):
            Exercise.objects.filter(pk=self.exercise.pk).update(options=options)
            intro = self.client.get(self.url('exercise_intro'))
            self.assertContains(intro, 'not ready yet')
            self.assertRedirects(self.client.get(self.url('exercise_play')), self.url('exercise_intro'))
            self.assertEqual(self.client.post(self.url('exercise_submit'), {}).status_code, 404)


class MapExerciseTests(TempMediaMixin, TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.course = Course.objects.create(title='Listening', category=Category.LISTENING, short_description='x')
        seed()
        cls.exercise = make_map_exercise()
        cls.student = User.objects.create_user(email='s@t.uz', password=PASSWORD)
        cls.questions = list(cls.exercise.questions.all())

    def setUp(self):
        self.client.force_login(self.student)

    def url(self, name):
        return reverse(f'courses:{name}', args=[self.course.slug, 4, 1])

    def submit(self, letters):
        return self.client.post(
            self.url('exercise_submit'), {f'q{q.pk}': letter for q, letter in zip(self.questions, letters)},
        )

    def test_play_page_shows_the_map_and_a_row_of_letters_per_place(self):
        response = self.client.get(self.url('exercise_play'))
        html = response.content.decode()
        image_url = reverse('courses:exercise_image', args=[self.exercise.pk])
        self.assertContains(response, '🗺️ Part 4')
        self.assertContains(response, 'Label the places (19–23) on the map (A–I)')
        self.assertContains(response, '<strong>FOUR extra</strong>')
        self.assertContains(response, '<figure class="map-figure">')
        self.assertContains(response, f'<img src="{image_url}" alt="Map">')
        for number, place in zip(range(19, 24), MAP_PLACES):
            self.assertContains(response, f'<strong>{number}.</strong> {place}')
        self.assertContains(response, 'class="chip-row"', count=5)
        self.assertContains(response, 'type="radio"', count=5 * 9)
        self.assertEqual(re.findall(r'<span>([A-Z])</span>', html), list('ABCDEFGHI') * 5)
        self.assertContains(response, 'Submit all parts')
        self.assertNotContains(response, '<select')
        self.assertNotContains(response, 'gap-input')
        self.assertTrue(html.index('map-figure') < html.index('chip-row'))

    def test_play_page_does_not_leak_the_correct_letters(self):
        html = self.client.get(self.url('exercise_play')).content.decode()
        self.assertNotIn('checked', html)
        self.assertNotIn('is-correct', html)

    def test_number_of_letters_follows_the_exercise_setting(self):
        Exercise.objects.filter(pk=self.exercise.pk).update(letters_count=6)
        response = self.client.get(self.url('exercise_play'))
        self.assertContains(response, 'type="radio"', count=5 * 6)
        self.assertNotContains(response, '<span>G</span>')

    def test_all_correct_letters_score_full_marks(self):
        response = self.submit('caheb')
        self.assertContains(response, '<span>5</span> / 5')
        self.assertContains(response, 'Perfect score!')
        self.assertEqual(ExerciseResult.objects.get().score, 5)

    def test_result_shows_the_chosen_and_the_correct_letter_for_mistakes(self):
        response = self.submit('cbhab')
        self.assertContains(response, '<span>3</span> / 5')
        self.assertContains(response, 'Your answer: B')
        self.assertContains(response, 'Correct answer: <strong>A</strong>')
        self.assertContains(response, 'Correct answer: <strong>E</strong>')
        self.assertContains(response, 'class="q-option review-answer is-correct"', count=3)
        self.assertContains(response, 'class="q-option review-answer is-wrong"', count=2)
        for number, place in zip(range(19, 24), MAP_PLACES):
            self.assertContains(response, f'<strong>{number}.</strong> {place}')

    def test_result_page_shows_the_map_again_for_review(self):
        response = self.submit('caheb')
        image_url = reverse('courses:exercise_image', args=[self.exercise.pk])
        self.assertContains(response, '<figure class="map-figure">', count=1)
        self.assertContains(response, f'<img src="{image_url}" alt="Map">', count=1)

    def test_blank_and_out_of_range_letters_are_unanswered(self):
        Exercise.objects.filter(pk=self.exercise.pk).update(letters_count=6)
        response = self.submit(['', 'z', 'h', 'e', 'b'])
        self.assertContains(response, '<span>2</span> / 5')
        self.assertContains(response, 'You did not answer this question.', count=3)

    def test_image_is_served_to_logged_in_users_only(self):
        url = reverse('courses:exercise_image', args=[self.exercise.pk])
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response['Content-Type'], 'image/png')
        body = b''.join(response.streaming_content)
        response.close()
        with open(self.exercise.image.path, 'rb') as handle:
            self.assertEqual(body, handle.read())
        self.client.logout()
        self.assertRedirects(
            self.client.get(url), f"{reverse('accounts:login')}?next={url}", fetch_redirect_response=False)

    def test_image_of_an_exercise_without_one_or_of_a_hidden_course_is_404(self):
        other = Exercise.objects.get(part__number=4, number=2)
        self.assertEqual(self.client.get(reverse('courses:exercise_image', args=[other.pk])).status_code, 404)
        url = reverse('courses:exercise_image', args=[self.exercise.pk])
        Course.objects.filter(pk=self.course.pk).update(is_published=False)
        self.assertEqual(self.client.get(url).status_code, 404)

    def test_exercise_is_ready_only_with_audio_questions_picture_and_letters(self):
        self.assertTrue(Exercise.objects.get(pk=self.exercise.pk).is_ready)
        for field, value in (('image', ''), ('letters_count', 1), ('letters_count', 0)):
            Exercise.objects.filter(pk=self.exercise.pk).update(**{field: value})
            self.assertFalse(Exercise.objects.get(pk=self.exercise.pk).is_ready, (field, value))
            self.assertContains(self.client.get(self.url('exercise_intro')), 'not ready yet')
            self.assertRedirects(self.client.get(self.url('exercise_play')), self.url('exercise_intro'))
            self.assertEqual(self.client.post(self.url('exercise_submit'), {}).status_code, 404)
            Exercise.objects.filter(pk=self.exercise.pk).update(image=self.exercise.image.name, letters_count=9)

    def test_deleting_the_exercise_deletes_the_picture_and_the_audio(self):
        extra = make_map_exercise(exercise_number=2)
        paths = [extra.image.path, extra.audio.path]
        self.assertTrue(all(os.path.exists(path) for path in paths))
        extra.delete()
        self.assertFalse(any(os.path.exists(path) for path in paths))
        self.assertTrue(os.path.exists(self.exercise.image.path))


class ExtractsExerciseTests(TempMediaMixin, TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.course = Course.objects.create(title='Listening', category=Category.LISTENING, short_description='x')
        seed()
        cls.exercise = make_extracts_exercise()
        cls.student = User.objects.create_user(email='s@t.uz', password=PASSWORD)
        cls.questions = list(cls.exercise.questions.all())

    def setUp(self):
        self.client.force_login(self.student)

    def url(self, name):
        return reverse(f'courses:{name}', args=[self.course.slug, 5, 1])

    def submit(self, letters):
        return self.client.post(
            self.url('exercise_submit'), {f'q{q.pk}': letter for q, letter in zip(self.questions, letters)},
        )

    def test_play_page_numbers_the_questions_from_24_with_the_number_beside_the_text(self):
        response = self.client.get(self.url('exercise_play'))
        html = response.content.decode()
        self.assertContains(response, '🎙️ Part 5')
        self.assertContains(response, 'You will hear three extracts.')
        self.assertContains(response, '<strong>TWO</strong> questions for each extract.')
        self.assertEqual(question_numbers(html), [str(n) for n in range(24, 30)])
        self.assertContains(
            response, '<p class="q-line"><strong class="q-number">24.</strong> How does speaker 1 feel?</p>')
        self.assertContains(response, 'type="radio"', count=18)
        self.assertContains(response, 'Submit all parts')

    def test_extract_cards_come_before_the_first_question_of_each_extract(self):
        response = self.client.get(self.url('exercise_play'))
        html = response.content.decode()
        self.assertContains(response, 'class="q-intro"', count=3)
        self.assertContains(response, '<strong>Extract One</strong> · You hear part of an interview with Fiona')
        self.assertContains(response, '<strong>Extract Two</strong> · You hear two friends talking about a film.')
        positions = [
            html.index('Extract One'), html.index('q-number">24.'), html.index('q-number">25.'),
            html.index('Extract Two'), html.index('q-number">26.'), html.index('q-number">27.'),
            html.index('Extract Three'), html.index('q-number">28.'), html.index('q-number">29.'),
        ]
        self.assertEqual(positions, sorted(positions))

    def test_intro_card_is_escaped_but_keeps_bold(self):
        Question.objects.filter(pk=self.questions[0].pk).update(intro='<script>x()</script> **Bold** text')
        response = self.client.get(self.url('exercise_play'))
        self.assertNotContains(response, '<script>x()</script>')
        self.assertContains(response, '&lt;script&gt;x()&lt;/script&gt; <strong>Bold</strong> text')

    def test_play_page_does_not_leak_the_correct_options(self):
        html = self.client.get(self.url('exercise_play')).content.decode()
        self.assertNotIn('checked', html)
        self.assertNotIn('is-correct', html)

    def test_scoring_and_result_page_keep_the_extract_cards(self):
        response = self.submit('abcabb')
        html = response.content.decode()
        self.assertContains(response, '<span>5</span> / 6')
        self.assertEqual(question_numbers(html), [str(n) for n in range(24, 30)])
        self.assertContains(response, 'class="q-intro"', count=3)
        self.assertTrue(html.index('Extract Two') < html.index('q-number">26.'))
        self.assertEqual(ExerciseResult.objects.get().score, 5)

    def test_questions_without_an_intro_have_no_card(self):
        Question.objects.update(intro='')
        self.assertNotContains(self.client.get(self.url('exercise_play')), 'q-intro')


class QuestionNumberingTests(TempMediaMixin, TestCase):
    def test_numbers_continue_from_the_parts_first_question_number(self):
        course = Course.objects.create(title='Listening', category=Category.LISTENING, short_description='x')
        seed()
        Part.objects.filter(number=1).update(first_question_number=5)
        make_ready_exercise(questions=3)
        student = User.objects.create_user(email='s@t.uz', password=PASSWORD)
        self.client.force_login(student)
        url = lambda name: reverse(f'courses:{name}', args=[course.slug, 1, 1])

        html = self.client.get(url('exercise_play')).content.decode()
        self.assertEqual(re.findall(r'class="q-number">(\d+)\.<', html), ['5', '6', '7'])

        questions = list(Exercise.objects.get(part__number=1, number=1).questions.all())
        result = self.client.post(url('exercise_submit'), {f'q{q.pk}': q.correct for q in questions})
        self.assertEqual(re.findall(r'class="q-number">(\d+)\.<', result.content.decode()), ['5', '6', '7'])
