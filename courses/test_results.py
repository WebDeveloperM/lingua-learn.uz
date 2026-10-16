import re

from django.test import SimpleTestCase, TestCase
from django.urls import reverse

from accounts.models import User

from .models import Category, Course, Exercise
from .support import (
    TempMediaMixin, make_extracts_exercise, make_gap_exercise, make_lecture_exercise, make_map_exercise,
    make_matching_exercise, make_ready_exercise, seed,
)
from .templatetags.practice_tags import transcript_html
from .views import _time_used_label

PASSWORD = 'StrongPass123!'
TRANSCRIPT = (
    'Woman: Is this your umbrella?\n'
    'Man: I\'m afraid **not**.\n'
    '\n'
    'Woman: Then whose is it? <script>alert(1)</script>'
)


class SubmitConfirmationMarkupTests(TempMediaMixin, TestCase):
    """Every kind of exercise shares one play page, so each gets the "Submit all parts" confirmation."""

    @classmethod
    def setUpTestData(cls):
        cls.course = Course.objects.create(title='Listening', category=Category.LISTENING, short_description='x')
        seed()
        make_ready_exercise()
        make_gap_exercise()
        make_matching_exercise()
        make_map_exercise()
        make_extracts_exercise()
        make_lecture_exercise()
        cls.student = User.objects.create_user(email='s@t.uz', password=PASSWORD)

    def setUp(self):
        self.client.force_login(self.student)

    def test_every_play_page_has_the_confirmation_card_hidden_until_needed(self):
        for part in range(1, 7):
            response = self.client.get(reverse('courses:exercise_play', args=[self.course.slug, part, 1]))
            html = response.content.decode()
            self.assertContains(response, 'id="submit-confirm"', msg_prefix=f'part {part}')
            self.assertRegex(html, r'<div class="submit-confirm" id="submit-confirm" role="alert" hidden>')
            self.assertContains(response, '>Yes, submit</button>')
            self.assertContains(response, '>Keep working</button>')
            self.assertContains(response, 'Submit all parts')
            self.assertContains(response, 'name="time_used"')
            self.assertContains(response, '/static/js/exercise.js')
            self.assertContains(response, '/static/js/audio-player.js')

    def test_the_confirmation_text_is_filled_in_by_the_script_not_the_server(self):
        html = self.client.get(reverse('courses:exercise_play', args=[self.course.slug, 1, 1])).content.decode()
        self.assertIn('<p id="submit-confirm-text"></p>', html)
        self.assertNotIn('unanswered', html)


class ResultPageTests(TempMediaMixin, TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.course = Course.objects.create(title='Listening', category=Category.LISTENING, short_description='x')
        seed()
        cls.exercise = make_ready_exercise(questions=10, minutes=5)
        cls.student = User.objects.create_user(email='s@t.uz', password=PASSWORD)
        cls.questions = list(cls.exercise.questions.all())

    def setUp(self):
        self.client.force_login(self.student)

    def url(self, name, part=1, number=1):
        return reverse(f'courses:{name}', args=[self.course.slug, part, number])

    def submit(self, correct=0, **extra):
        """Answer `correct` questions right (the first ones) and give a wrong option for the others."""
        answers = {}
        for index, question in enumerate(self.questions):
            right = question.correct
            answers[f'q{question.pk}'] = right if index < correct else 'abc'[('abc'.index(right) + 1) % 3]
        return self.client.post(self.url('exercise_submit'), {**answers, **extra})

    def test_summary_line_has_the_mood_the_score_the_percent_and_the_time_used(self):
        response = self.submit(correct=3, time_used='65')
        self.assertContains(response, '💪</span> Keep going!')
        self.assertContains(response, '<span>3</span> / 10 correct (30%)')
        self.assertContains(response, '· Time used: 01:05')

    def test_the_mood_follows_the_percent(self):
        self.assertContains(self.submit(correct=7), '👏</span> Well done!')
        self.assertContains(self.submit(correct=6), 'Keep going!')
        perfect = self.submit(correct=10)
        self.assertContains(perfect, '🎉</span> Perfect score!')
        self.assertContains(perfect, '<span>10</span> / 10 correct (100%)')

    def test_time_used_is_optional_and_never_trusted_beyond_the_exercise_time(self):
        self.assertNotContains(self.submit(correct=1), 'Time used')
        for garbage in ('', 'abc', '1.5', '12s'):
            self.assertNotContains(self.submit(correct=1, time_used=garbage), 'Time used', msg_prefix=garbage)
        self.assertContains(self.submit(correct=1, time_used='999999'), 'Time used: 05:00')  # 5 minute exercise
        self.assertContains(self.submit(correct=1, time_used='-20'), 'Time used: 00:00')
        self.assertContains(self.submit(correct=1, time_used='0'), 'Time used: 00:00')

    def test_buttons_note_and_best_score(self):
        response = self.submit(correct=10)
        self.assertContains(response, f'href="{self.url("exercise_intro")}">Try again</a>')
        self.assertContains(response, f'href="{self.course.get_absolute_url()}">More exercises</a>')
        self.assertContains(
            response,
            'Green = correct, red = your wrong answer. Your best score is shown on the Listening practice page.')
        self.assertNotContains(response, 'Your best score: ⭐')
        self.assertContains(self.submit(correct=2), 'Your best score: ⭐ 10/10')

    def test_answers_table_lists_every_question_with_both_answers(self):
        response = self.submit(correct=4)
        html = response.content.decode()
        self.assertContains(response, '<details class="ex-card fold-card" open>')
        self.assertContains(response, '<th>#</th><th>Your answer</th><th>Correct answer</th>')
        rows = re.findall(r'<tr class="(is-correct|is-wrong)">\s*<td>(\d+)</td>\s*<td>(.*?)</td>\s*<td>(.*?)</td>', html)
        self.assertEqual([row[1] for row in rows], [str(n) for n in range(1, 11)])
        self.assertEqual([row[0] for row in rows], ['is-correct'] * 4 + ['is-wrong'] * 6)
        for (state, _, given, correct), question in zip(rows, self.questions):
            self.assertEqual(correct, question.correct.upper())
            if state == 'is-correct':
                self.assertEqual(given, correct)
            else:
                self.assertNotEqual(given, correct)

    def test_unanswered_questions_show_a_dash_in_the_table(self):
        response = self.client.post(self.url('exercise_submit'), {})
        self.assertContains(response, '<td>–</td>', count=10)
        self.assertContains(response, '<tr class="is-wrong">', count=10)

    def test_question_cards_repeat_the_options_and_mark_the_correct_one(self):
        response = self.submit(correct=10)
        self.assertContains(response, 'class="q-card"', count=10)
        self.assertContains(response, 'class="q-option is-correct"', count=10)
        self.assertContains(response, '✓ correct</span>', count=10)
        self.assertNotContains(response, 'type="radio"')

    def test_audio_player_and_instructions_come_back_on_the_result_page(self):
        response = self.submit(correct=1)
        audio_url = reverse('courses:exercise_audio', args=[self.exercise.pk])
        self.assertContains(response, 'data-audio-player')
        self.assertContains(response, f'src="{audio_url}"')
        self.assertContains(response, '💬 Part 1')
        self.assertContains(response, '/static/js/audio-player.js')
        self.assertNotContains(response, '/static/js/exercise.js')  # no timer or confirmation here
        self.assertNotContains(response, 'id="exercise-form"')

    def test_no_transcript_card_without_a_transcript(self):
        self.assertNotContains(self.submit(correct=1), 'Transcript')

    def test_transcript_card_is_closed_by_default_with_the_answers_highlighted(self):
        Exercise.objects.filter(pk=self.exercise.pk).update(transcript=TRANSCRIPT)
        response = self.submit(correct=1)
        self.assertContains(response, '<details class="ex-card fold-card transcript-card">')
        self.assertContains(response, '<strong class="fold-accent">Transcript</strong>')
        self.assertContains(response, '(answers are highlighted)')
        self.assertContains(response, '<mark>not</mark>')
        self.assertContains(response, '<p>Woman: Is this your umbrella?<br>Man: I&#x27;m afraid <mark>not</mark>.</p>')
        self.assertContains(response, '<p>Woman: Then whose is it? &lt;script&gt;alert(1)&lt;/script&gt;</p>')
        self.assertNotContains(response, '<script>alert(1)</script>')

    def test_transcript_never_reaches_the_exercise_page(self):
        Exercise.objects.filter(pk=self.exercise.pk).update(transcript=TRANSCRIPT)
        play = self.client.get(self.url('exercise_play'))
        self.assertNotContains(play, 'Transcript')
        self.assertNotContains(play, 'umbrella')
        self.assertNotContains(self.client.get(self.url('exercise_intro')), 'umbrella')

    def test_a_blank_transcript_counts_as_none(self):
        Exercise.objects.filter(pk=self.exercise.pk).update(transcript='  \n \n')
        self.assertNotContains(self.submit(correct=1), 'Transcript')


class ResultPagesOfEveryKindTests(TempMediaMixin, TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.course = Course.objects.create(title='Listening', category=Category.LISTENING, short_description='x')
        seed()
        cls.student = User.objects.create_user(email='s@t.uz', password=PASSWORD)

    def setUp(self):
        self.client.force_login(self.student)

    def result(self, part, answers):
        exercise = Exercise.objects.get(part__number=part, number=1)
        data = {f'q{q.pk}': answer for q, answer in zip(exercise.questions.all(), answers)}
        return self.client.post(
            reverse('courses:exercise_submit', args=[self.course.slug, part, 1]), {**data, 'time_used': '30'})

    def table_rows(self, response):
        return re.findall(
            r'<tr class="(is-correct|is-wrong)">\s*<td>(\d+)</td>\s*<td>(.*?)</td>\s*<td>(.*?)</td>',
            response.content.decode())

    def test_gap_fill_table_shows_what_was_typed_and_the_accepted_answers(self):
        make_gap_exercise()
        response = self.result(2, ['Space Station', '', 'wrong'])
        self.assertEqual(self.table_rows(response), [
            ('is-correct', '9', 'Space Station', 'space station / futuristic city'),
            ('is-wrong', '10', '–', 'history'),
            ('is-wrong', '11', 'wrong', 'gamingworld'),
        ])
        self.assertContains(response, 'Time used: 00:30')

    def test_matching_table_shows_letters(self):
        make_matching_exercise()
        response = self.result(3, ['d', 'b', '', 'c'])
        self.assertEqual(self.table_rows(response), [
            ('is-correct', '15', 'D', 'D'), ('is-wrong', '16', 'B', 'A'),
            ('is-wrong', '17', '–', 'E'), ('is-correct', '18', 'C', 'C'),
        ])
        self.assertContains(response, '<li>A) Arriving late for everything.</li>')  # the options stay visible

    def test_map_table_shows_letters_and_the_map_stays_visible(self):
        make_map_exercise()
        response = self.result(4, ['c', 'b', 'h', '', 'b'])
        self.assertEqual([(row[1], row[2], row[3]) for row in self.table_rows(response)], [
            ('19', 'C', 'C'), ('20', 'B', 'A'), ('21', 'H', 'H'), ('22', '–', 'E'), ('23', 'B', 'B'),
        ])
        self.assertContains(response, 'class="map-figure"', count=1)

    def test_extract_cards_stay_between_the_question_cards(self):
        make_extracts_exercise()
        response = self.result(5, ['a', 'b', 'c', 'a', 'b', 'c'])
        html = response.content.decode()
        self.assertContains(response, '<span>6</span> / 6 correct (100%)')
        self.assertContains(response, 'class="q-intro"', count=3)
        self.assertTrue(html.index('Extract Two') < html.index('q-number">26.'))

    def test_lecture_notes_keep_their_plain_line_and_the_table_numbers_30_to_35(self):
        make_lecture_exercise()
        response = self.result(6, ['puzzle', 'confusion', 'worship', 'rocks', 'coins', 'tree'])
        self.assertContains(response, '<span>6</span> / 6 correct (100%)')
        self.assertEqual([row[1] for row in self.table_rows(response)], [str(n) for n in range(30, 36)])
        self.assertContains(response, 'class="gap-note"', count=1)
        self.assertContains(response, '<h3 class="gap-title">Labyrinths</h3>')


class TranscriptFilterTests(SimpleTestCase):
    def test_paragraphs_line_breaks_and_highlights(self):
        self.assertEqual(
            transcript_html('One **two** three\nfour\n\nfive'),
            '<p>One <mark>two</mark> three<br>four</p>\n\n<p>five</p>')

    def test_html_is_escaped_before_the_markup_is_applied(self):
        self.assertEqual(transcript_html('<b>x</b> **<i>y</i>**'), '<p>&lt;b&gt;x&lt;/b&gt; <mark>&lt;i&gt;y&lt;/i&gt;</mark></p>')

    def test_empty_values(self):
        self.assertEqual(transcript_html(''), '')
        self.assertEqual(transcript_html(None), '')


class TimeUsedLabelTests(SimpleTestCase):
    def test_formats_and_clamps_to_the_exercise_time(self):
        self.assertEqual(_time_used_label('65', 300), '01:05')
        self.assertEqual(_time_used_label('0', 300), '00:00')
        self.assertEqual(_time_used_label('301', 300), '05:00')
        self.assertEqual(_time_used_label('9' * 30, 300), '05:00')
        self.assertEqual(_time_used_label('-1', 300), '00:00')

    def test_unusable_values_are_ignored(self):
        for raw in (None, '', 'abc', '1.5', '1e3', ' '):
            self.assertIsNone(_time_used_label(raw, 300), raw)
