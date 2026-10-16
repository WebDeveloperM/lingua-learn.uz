import os
from datetime import timedelta
from unittest import mock

from django.db import connection
from django.test import TestCase, override_settings
from django.test.utils import CaptureQueriesContext
from django.urls import reverse
from django.utils import timezone

from accounts.models import Role, User
from courses.models import Category, Course
from courses.support import TempMediaMixin

from . import ai
from .models import SpeakingAnswer, SpeakingAttempt, SpeakingPart, SpeakingPractice, SpeakingQuestion
from .support import FEEDBACK, SET_ONE, SET_TWO, SPOKEN, answers_post, make_attempt, make_set, make_speaking_course, recording

PASSWORD = 'StrongPass123!'
Feedback = SpeakingAttempt.Feedback
GIVEN = {1: FEEDBACK, 2: FEEDBACK, 3: FEEDBACK}
REAL_REQUEST_FEEDBACK = ai.request_feedback  # taken before any test replaces it


def users():
    return (
        User.objects.create_user(email='s@t.uz', password=PASSWORD),
        User.objects.create_user(email='o@t.uz', password=PASSWORD),
        User.objects.create_user(email='a@t.uz', password=PASSWORD, role=Role.ADMIN),
    )


# settings.py reads .env, so a real key there must not make the tests talk to the real service
@override_settings(GROQ_API_KEY='')
class FinishTests(TempMediaMixin, TestCase):
    def setUp(self):
        self.course = make_speaking_course()
        self.set = make_set(self.course)
        self.student, self.other, self.admin = users()
        self.url = reverse('speaking:finish', args=[self.course.slug, 1, self.set.pk])
        self.client.force_login(self.student)
        patcher = mock.patch('speaking.feedback.ai.request_feedback', return_value=GIVEN)
        self.ask_ai = patcher.start()
        self.addCleanup(patcher.stop)

    def finish(self, **kwargs):
        return self.client.post(self.url, answers_post(self.set, **kwargs))

    def test_login_and_post_are_required(self):
        self.assertEqual(self.client.get(self.url).status_code, 405)
        self.client.logout()
        self.assertRedirects(
            self.client.post(self.url, {}), f"{reverse('accounts:login')}?next={self.url}", fetch_redirect_response=False)

    def test_what_was_said_is_saved_with_its_recording(self):
        response = self.finish()
        attempt = SpeakingAttempt.objects.get()
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {'url': reverse('speaking:result', args=[self.course.slug, attempt.pk])})
        self.assertEqual((attempt.user, attempt.set, attempt.coins), (self.student, self.set, 3))
        answers = list(attempt.answers.all())
        self.assertEqual([answer.order for answer in answers], [0, 1, 2])
        self.assertEqual([answer.question for answer in answers], SET_ONE)
        self.assertEqual([answer.transcript for answer in answers], SPOKEN)
        self.assertEqual([(answer.seconds, answer.finished_early, answer.confidence) for answer in answers],
                         [(30.0, False, 0.88)] * 3)
        for answer in answers:
            self.assertTrue(answer.audio.name.startswith('speaking/answers/') and answer.audio.name.endswith('.webm'))
            with open(answer.audio.path, 'rb') as handle:
                self.assertEqual(handle.read(), b'x' * 2000)
        self.assertEqual(len({answer.audio.name for answer in answers}), 3)

    def test_the_set_counts_as_practised(self):
        self.finish()
        self.assertEqual(SpeakingPractice.objects.get().set, self.set)
        self.assertContains(self.client.get(self.course.get_absolute_url()), '✓ 1 / 1 practised')
        part = self.client.get(reverse('speaking:part', args=[self.course.slug, 1]))
        self.assertContains(part, 'Practise this again ✓')

    def test_practising_again_keeps_one_practice_and_both_attempts(self):
        self.finish()
        self.finish()
        self.assertEqual((SpeakingPractice.objects.count(), SpeakingAttempt.objects.count()), (1, 2))

    def test_the_ai_is_asked_about_what_was_said(self):
        self.finish()
        self.ask_ai.assert_called_once()
        items = self.ask_ai.call_args.args[0]
        self.assertEqual([item['number'] for item in items], [1, 2, 3])
        self.assertEqual([item['question'] for item in items], SET_ONE)
        self.assertEqual([item['transcript'] for item in items], SPOKEN)
        self.assertEqual({(item['seconds'], item['allowed'], item['confidence']) for item in items}, {(30.0, 30, 0.88)})

    def test_the_feedback_is_kept_with_each_answer(self):
        self.finish()
        attempt = SpeakingAttempt.objects.get()
        self.assertEqual(attempt.feedback_status, Feedback.READY)
        self.assertEqual([answer.feedback for answer in attempt.answers.all()], [FEEDBACK] * 3)

    def test_only_answers_with_words_go_to_the_ai(self):
        self.ask_ai.return_value = {2: FEEDBACK}
        self.finish(transcripts=['', ' I live in a flat. ', ''])
        self.assertEqual([item['number'] for item in self.ask_ai.call_args.args[0]], [2])
        answers = list(SpeakingAttempt.objects.get().answers.all())
        self.assertEqual([answer.feedback for answer in answers], [{}, FEEDBACK, {}])
        self.assertEqual(answers[1].transcript, 'I live in a flat.')

    def test_silence_is_not_sent_to_the_ai(self):
        response = self.finish(transcripts=['', '  ', ''])
        self.assertEqual(response.status_code, 200)
        self.ask_ai.assert_not_called()
        attempt = SpeakingAttempt.objects.get()
        self.assertEqual(attempt.feedback_status, Feedback.EMPTY)
        self.assertEqual(attempt.answers.count(), 3)

    def test_without_an_ai_key_the_results_are_still_saved(self):
        self.ask_ai.side_effect = ai.FeedbackNotConfigured('no key')
        self.assertEqual(self.finish().status_code, 200)
        attempt = SpeakingAttempt.objects.get()
        self.assertEqual((attempt.feedback_status, attempt.feedback_error), (Feedback.UNCONFIGURED, ''))
        self.assertEqual(attempt.answers.count(), 3)

    def test_with_the_real_settings_and_no_key_nothing_goes_out(self):
        self.ask_ai.side_effect = REAL_REQUEST_FEEDBACK
        with override_settings(ANTHROPIC_API_KEY='', GROQ_API_KEY=''), \
                mock.patch('speaking.ai.urllib.request.urlopen') as urlopen:
            self.assertEqual(self.finish().status_code, 200)
        urlopen.assert_not_called()
        self.assertEqual(SpeakingAttempt.objects.get().feedback_status, Feedback.UNCONFIGURED)

    def test_a_failing_ai_leaves_an_attempt_that_can_be_retried(self):
        self.ask_ai.side_effect = ai.FeedbackError('The AI service answered 529: Overloaded')
        self.assertEqual(self.finish().status_code, 200)
        attempt = SpeakingAttempt.objects.get()
        self.assertEqual(attempt.feedback_status, Feedback.FAILED)
        self.assertEqual(attempt.feedback_error, 'The AI service answered 529: Overloaded')

    def test_coins_are_paid_only_when_every_timer_ran_out(self):
        self.finish(early=(1,))
        attempt = SpeakingAttempt.objects.get()
        self.assertEqual(attempt.coins, 0)
        self.assertEqual([answer.finished_early for answer in attempt.answers.all()], [False, True, False])

    def test_a_practice_that_is_not_complete_earns_no_coins(self):
        data = answers_post(self.set)
        for key in [key for key in data if key.endswith('_2')]:
            del data[key]
        self.assertEqual(self.client.post(self.url, data).status_code, 200)
        attempt = SpeakingAttempt.objects.get()
        self.assertEqual((attempt.answers.count(), attempt.coins), (2, 0))

    def test_a_missing_recording_is_fine(self):
        self.assertEqual(self.finish(audio=False).status_code, 200)
        self.assertEqual([bool(answer.audio) for answer in SpeakingAnswer.objects.all()], [False] * 3)

    def test_recordings_in_the_formats_browsers_make_are_accepted(self):
        for content_type, extension in (
            ('audio/webm', '.webm'), ('video/webm', '.webm'), ('audio/ogg', '.ogg'), ('audio/mp4', '.m4a'),
            ('audio/mpeg', '.mp3'), ('audio/wav', '.wav'),
        ):
            SpeakingAnswer.objects.all().delete()
            SpeakingAttempt.objects.all().delete()
            data = answers_post(self.set, audio=False)
            data['question_0'] = str(self.set.questions.first().pk)
            data['audio_0'] = recording(content_type)
            self.assertEqual(self.client.post(self.url, data).status_code, 200, content_type)
            self.assertTrue(SpeakingAnswer.objects.get(order=0).audio.name.endswith(extension), content_type)

    def test_numbers_are_held_to_what_makes_sense(self):
        data = answers_post(self.set, audio=False)
        data.update({
            'seconds_0': 'abc', 'seconds_1': '999', 'seconds_2': '-4',
            'confidence_0': 'nan', 'confidence_1': '5', 'confidence_2': '-1',
        })
        self.client.post(self.url, data)
        answers = list(SpeakingAnswer.objects.all())
        self.assertEqual([answer.seconds for answer in answers], [0.0, 35.0, 0.0])
        self.assertEqual([answer.confidence for answer in answers], [None, 1.0, 0.0])

    def test_a_missing_confidence_stays_empty(self):
        self.finish(confidence=None)
        self.assertEqual([answer.confidence for answer in SpeakingAnswer.objects.all()], [None] * 3)

    def test_a_very_long_transcript_is_cut(self):
        self.finish(transcripts=['word ' * 1000, 'b', 'c'])
        self.assertEqual(len(SpeakingAnswer.objects.get(order=0).transcript), 1999)  # cut at 2000, trailing space gone

    def test_something_that_is_not_what_the_page_sends_is_refused(self):
        other_set = make_set(self.course, questions=SET_TWO)
        cases = {
            'nothing at all': {},
            'only a transcript': {'transcript_0': 'hello'},
            'an unknown question': {'question_0': '99999'},
            'a question of another set': {'question_0': str(other_set.questions.first().pk)},
            'not a number': {'question_0': 'abc'},
        }
        for name, data in cases.items():
            response = self.client.post(self.url, data)
            self.assertEqual(response.status_code, 400, name)
            self.assertIn('error', response.json(), name)
        data = answers_post(self.set)
        data['question_1'] = data['question_0']
        self.assertEqual(self.client.post(self.url, data).status_code, 400)  # a question answered twice
        data = answers_post(self.set)
        data['question_3'] = data['question_0']
        self.assertEqual(self.client.post(self.url, data).status_code, 400)  # more answers than questions
        self.assertEqual((SpeakingAttempt.objects.count(), SpeakingAnswer.objects.count()), (0, 0))
        self.assertEqual(SpeakingPractice.objects.count(), 0)
        self.ask_ai.assert_not_called()

    def test_files_that_are_not_recordings_are_refused(self):
        for content_type in ('text/html', 'application/octet-stream', 'image/png'):
            data = answers_post(self.set, audio=False)
            data['audio_0'] = recording(content_type)
            self.assertEqual(self.client.post(self.url, data).status_code, 400, content_type)
        self.assertEqual(SpeakingAttempt.objects.count(), 0)

    def test_a_recording_that_is_too_big_is_refused(self):
        with mock.patch('speaking.views.MAX_AUDIO_BYTES', 1000):
            self.assertEqual(self.finish().status_code, 400)
        self.assertEqual(SpeakingAttempt.objects.count(), 0)

    def test_nothing_is_written_to_disk_when_the_answers_are_refused(self):
        def stored():
            return sorted(name for _, _, names in os.walk(self.__class__._media_dir.name) for name in names)

        before = stored()
        data = answers_post(self.set)
        data['question_2'] = 'abc'
        self.assertEqual(self.client.post(self.url, data).status_code, 400)
        self.assertEqual(stored(), before)

    def test_too_many_practices_in_an_hour_are_refused(self):
        for _ in range(30):
            make_attempt(self.student, self.set)
        response = self.finish()
        self.assertEqual(response.status_code, 429)
        self.assertIn('error', response.json())
        self.assertEqual(SpeakingAttempt.objects.count(), 30)
        self.ask_ai.assert_not_called()

    def test_older_practices_and_other_students_do_not_count_against_the_limit(self):
        for _ in range(30):
            make_attempt(self.other, self.set)
        for attempt in [make_attempt(self.student, self.set) for _ in range(30)]:
            SpeakingAttempt.objects.filter(pk=attempt.pk).update(created_at=timezone.now() - timedelta(hours=2))
        self.assertEqual(self.finish().status_code, 200)

    def test_only_part_one_one_has_a_practice(self):
        other_part = make_set(self.course, part=SpeakingPart.PART_12)
        url = reverse('speaking:finish', args=[self.course.slug, 2, other_part.pk])
        self.assertEqual(self.client.post(url, answers_post(other_part)).status_code, 404)
        self.assertEqual(SpeakingAttempt.objects.count(), 0)

    def test_unknown_foreign_and_empty_sets_and_other_courses_are_404(self):
        for url in (
            reverse('speaking:finish', args=[self.course.slug, 1, 9999]),
            reverse('speaking:finish', args=[make_speaking_course().slug, 1, self.set.pk]),
            reverse('speaking:finish', args=[self.course.slug, 1, make_set(self.course, questions=[]).pk]),
            reverse('speaking:finish', args=[Course.objects.create(
                title='Reading', category=Category.READING, short_description='x').slug, 1, self.set.pk]),
            reverse('speaking:finish', args=[self.course.slug, 7, self.set.pk]),
        ):
            self.assertEqual(self.client.post(url, answers_post(self.set)).status_code, 404, url)

    def test_a_draft_course_takes_no_practices_from_students(self):
        Course.objects.filter(pk=self.course.pk).update(is_published=False)
        self.assertEqual(self.finish().status_code, 404)
        self.client.force_login(self.admin)
        self.assertEqual(self.finish().status_code, 200)


class ResultPageTests(TestCase):
    def setUp(self):
        self.course = make_speaking_course()
        self.set = make_set(self.course)
        self.student, self.other, self.admin = users()
        self.client.force_login(self.student)

    def page(self, attempt):
        return self.client.get(reverse('speaking:result', args=[self.course.slug, attempt.pk]))

    def test_the_page_shows_what_was_said_and_the_feedback_on_it(self):
        response = self.page(make_attempt(self.student, self.set, feedback=FEEDBACK))
        self.assertTemplateUsed(response, 'speaking/result.html')
        self.assertContains(response, '🎉</span> Well done!')
        self.assertContains(response, 'You answered 3 questions.')
        self.assertContains(response, 'class="sp-ans-q">1. What do you do on the weekends?</p>')
        self.assertContains(response, 'class="sp-ans-q">3. What kind of movies do you like?</p>')
        self.assertContains(response, '“I usually play football with my friends and sometimes I go to the cinema.”')
        self.assertContains(response, 'You spoke for 30 seconds.')
        self.assertContains(response, 'AI feedback', count=3)
        self.assertContains(response, 'Clear answer with good ideas; add one more detail.', count=3)
        for criterion in ('Grammar', 'Vocabulary', 'Fluency', 'Pronunciation'):
            self.assertContains(response, f'<li><strong>{criterion}</strong> — ', count=3)
        self.assertContains(response, '<strong>Try saying:</strong> At the weekend I usually play football', count=3)

    def test_the_check_yourself_list_is_gone(self):
        response = self.page(make_attempt(self.student, self.set, feedback=FEEDBACK))
        self.assertNotContains(response, 'Check yourself')
        self.assertNotContains(response, 'type="checkbox"')

    def test_the_page_offers_to_try_again_or_go_back_to_the_lesson(self):
        response = self.page(make_attempt(self.student, self.set, feedback=FEEDBACK))
        self.assertContains(response, f'href="{reverse("speaking:ready", args=[self.course.slug, 1, self.set.pk])}">Try again</a>')
        part_url = reverse('speaking:part', args=[self.course.slug, 1])
        self.assertContains(response, f'href="{part_url}">Back to lesson</a>')
        self.assertContains(response, f'href="{part_url}">← Part 1.1</a>')

    def test_coins_are_announced_or_explained(self):
        full = self.page(make_attempt(self.student, self.set, feedback=FEEDBACK))
        self.assertContains(full, 'You earned <strong>3 coins</strong>')
        self.assertNotContains(full, 'No coins this time')
        early = self.page(make_attempt(self.student, self.set, feedback=FEEDBACK, early=(0,)))
        self.assertContains(early, 'No coins this time: you pressed “I’m done” before the timer ended. Speak for the full time to earn coins.')
        self.assertContains(early, 'you pressed “I’m done” early.', count=1)
        self.assertNotContains(early, 'You earned')

    def test_one_coin_is_not_plural(self):
        single = make_set(self.course, questions=['Only one?'])
        self.assertContains(self.page(make_attempt(self.student, single, transcripts=['Yes.'])), '<strong>1 coin</strong>')

    def test_seconds_are_counted_in_the_right_number(self):
        attempt = make_attempt(self.student, self.set, feedback=FEEDBACK)
        for answer, seconds in zip(attempt.answers.all(), (1.0, 0.4, 29.6)):
            SpeakingAnswer.objects.filter(pk=answer.pk).update(seconds=seconds)
        response = self.page(attempt)
        self.assertContains(response, 'You spoke for 1 second.')
        self.assertContains(response, 'You spoke for 0 seconds.')
        self.assertContains(response, 'You spoke for 30 seconds.')

    def test_the_recordings_can_be_played(self):
        attempt = make_attempt(self.student, self.set, feedback=FEEDBACK)
        first = attempt.answers.first()
        SpeakingAnswer.objects.filter(pk=first.pk).update(audio='speaking/answers/x.webm')
        response = self.page(attempt)
        self.assertContains(response, '<audio controls preload="metadata" data-fix-duration', count=1)
        self.assertContains(response, '/static/js/speaking.js')
        self.assertContains(response, f'src="{reverse("speaking:answer_audio", args=[self.course.slug, first.pk])}"')

    def test_an_answer_without_words_says_so(self):
        attempt = make_attempt(self.student, self.set, transcripts=['Words here.', '', 'More words.'], feedback=FEEDBACK)
        SpeakingAnswer.objects.filter(attempt=attempt, order=1).update(feedback={})
        response = self.page(attempt)
        self.assertContains(response, 'We could not hear any words in this answer.', count=1)
        self.assertContains(response, 'AI feedback', count=2)

    def test_the_words_of_a_student_and_of_the_ai_are_escaped(self):
        attempt = make_attempt(self.student, self.set, transcripts=['<script>alert(1)</script>', 'b', 'c'],
                               feedback={**FEEDBACK, 'summary': '<b>bold</b>'})
        response = self.page(attempt)
        self.assertNotContains(response, '<script>alert(1)</script>')
        self.assertContains(response, '&lt;script&gt;alert(1)&lt;/script&gt;')
        self.assertNotContains(response, '<b>bold</b>')

    def test_nothing_is_said_about_the_ai_when_the_feedback_is_there(self):
        response = self.page(make_attempt(self.student, self.set, feedback=FEEDBACK))
        self.assertNotContains(response, 'id="sp-notice"')
        self.assertNotContains(response, 'Get the feedback again')

    def test_when_the_ai_failed_the_student_can_ask_again(self):
        attempt = make_attempt(self.student, self.set, status=Feedback.FAILED)
        SpeakingAttempt.objects.filter(pk=attempt.pk).update(feedback_error='The AI service answered 529: Overloaded')
        response = self.page(attempt)
        self.assertContains(response, 'We could not get the AI feedback just now.')
        self.assertContains(response, 'Get the feedback again')
        self.assertContains(response, f'action="{reverse("speaking:retry_feedback", args=[self.course.slug, attempt.pk])}"')
        self.assertNotContains(response, '529')  # the details are for admins
        self.assertContains(response, '“I usually play football')  # the answers are there all the same

    def test_admins_see_why_it_failed(self):
        attempt = make_attempt(self.student, self.set, status=Feedback.FAILED)
        SpeakingAttempt.objects.filter(pk=attempt.pk).update(feedback_error='The AI service answered 401: invalid x-api-key')
        self.client.force_login(self.admin)
        self.assertContains(self.page(attempt), 'invalid x-api-key')

    @override_settings(ANTHROPIC_API_KEY='', GROQ_API_KEY='')
    def test_without_a_key_students_are_told_and_get_no_useless_button(self):
        attempt = make_attempt(self.student, self.set, status=Feedback.UNCONFIGURED)
        student_page = self.page(attempt)
        self.assertContains(student_page, 'The AI feedback is not turned on on this site yet, so nobody checked these answers.')
        self.assertContains(student_page, 'once your teacher turns the AI on, open this page again')
        self.assertNotContains(student_page, 'ANTHROPIC_API_KEY')
        self.assertNotContains(student_page, reverse('speaking:retry_feedback', args=[self.course.slug, attempt.pk]))
        self.assertNotContains(student_page, '<button type="submit" class="pill-btn is-primary">Get the feedback')
        self.assertNotContains(student_page, 'try again a little later')  # it is not a passing failure

    @override_settings(ANTHROPIC_API_KEY='', GROQ_API_KEY='')
    def test_without_a_key_the_admin_is_told_how_to_turn_it_on(self):
        attempt = make_attempt(self.student, self.set, status=Feedback.UNCONFIGURED)
        self.client.force_login(self.admin)
        admin_page = self.page(attempt)
        self.assertContains(admin_page, '<code>GROQ_API_KEY=gsk_…</code> (a free key from console.groq.com)')
        self.assertContains(admin_page, '<code>ANTHROPIC_API_KEY=sk-ant-…</code>')
        self.assertContains(admin_page, 'console.anthropic.com')
        self.assertContains(admin_page, '<code>docker compose up -d</code>')
        self.assertNotContains(admin_page, '<button type="submit" class="pill-btn is-primary">Get the feedback')

    @override_settings(ANTHROPIC_API_KEY='sk-ant-test', GROQ_API_KEY='')
    def test_once_the_key_is_there_an_old_practice_can_get_its_feedback(self):
        attempt = make_attempt(self.student, self.set, status=Feedback.UNCONFIGURED)
        response = self.page(attempt)
        self.assertContains(response, 'The AI was turned on after this practice.')
        self.assertContains(response, '>Get the feedback</button>')
        self.assertContains(response, f'action="{reverse("speaking:retry_feedback", args=[self.course.slug, attempt.pk])}"')
        self.assertNotContains(response, 'not turned on')

    @override_settings(ANTHROPIC_API_KEY='', GROQ_API_KEY='gsk_test')
    def test_the_free_groq_key_alone_turns_the_feedback_on(self):
        attempt = make_attempt(self.student, self.set, status=Feedback.UNCONFIGURED)
        response = self.page(attempt)
        self.assertContains(response, 'The AI was turned on after this practice.')
        self.assertContains(response, '>Get the feedback</button>')
        self.assertNotContains(response, 'not turned on')

    @override_settings(GROQ_API_KEY='')
    def test_when_nothing_was_heard_the_page_gives_advice_and_no_retry(self):
        attempt = make_attempt(self.student, self.set, transcripts=['', '', ''], status=Feedback.EMPTY)
        response = self.page(attempt)
        self.assertContains(response, 'We could not hear any words, so there was nothing for the AI to check.')
        self.assertContains(response, 'Google Chrome or Microsoft Edge')
        self.assertNotContains(response, 'Get the feedback again')
        self.assertContains(response, 'We could not hear any words in this answer.', count=3)

    @override_settings(GROQ_API_KEY='gsk_test')
    def test_when_the_server_listened_to_the_recordings_the_browser_does_not_matter(self):
        attempt = make_attempt(self.student, self.set, transcripts=['', '', ''], status=Feedback.EMPTY)
        response = self.page(attempt)
        self.assertContains(
            response, 'nothing for the AI to check. Speak a little louder and closer to the microphone.</p>')
        self.assertNotContains(response, 'Google Chrome or Microsoft Edge')

    def test_a_result_belongs_to_its_student_and_to_admins(self):
        attempt = make_attempt(self.student, self.set, feedback=FEEDBACK)
        self.assertEqual(self.page(attempt).status_code, 200)
        self.client.force_login(self.other)
        self.assertEqual(self.page(attempt).status_code, 404)
        self.client.force_login(self.admin)
        self.assertEqual(self.page(attempt).status_code, 200)
        self.client.logout()
        self.assertEqual(self.page(attempt).status_code, 302)

    def test_unknown_results_and_the_wrong_course_are_404(self):
        attempt = make_attempt(self.student, self.set, feedback=FEEDBACK)
        self.assertEqual(self.client.get(reverse('speaking:result', args=[self.course.slug, 9999])).status_code, 404)
        elsewhere = make_speaking_course()
        self.assertEqual(self.client.get(reverse('speaking:result', args=[elsewhere.slug, attempt.pk])).status_code, 404)
        reading = Course.objects.create(title='Reading', category=Category.READING, short_description='x')
        self.assertEqual(self.client.get(reverse('speaking:result', args=[reading.slug, attempt.pk])).status_code, 404)

    def test_the_number_of_queries_does_not_grow_with_the_answers(self):
        small = make_attempt(self.student, self.set, feedback=FEEDBACK)
        big_set = make_set(self.course, questions=[f'Question {number}?' for number in range(10)])
        big = make_attempt(self.student, big_set, transcripts=['Words.'] * 10, feedback=FEEDBACK)
        with CaptureQueriesContext(connection) as few:
            self.page(small)
        with CaptureQueriesContext(connection) as many:
            self.page(big)
        self.assertEqual(len(few), len(many))


@override_settings(GROQ_API_KEY='')
class RetryFeedbackTests(TestCase):
    def setUp(self):
        self.course = make_speaking_course()
        self.set = make_set(self.course)
        self.student, self.other, self.admin = users()
        self.client.force_login(self.student)
        self.attempt = make_attempt(self.student, self.set, status=Feedback.FAILED)
        self.url = reverse('speaking:retry_feedback', args=[self.course.slug, self.attempt.pk])

    def test_asking_again_gets_the_feedback(self):
        with mock.patch('speaking.feedback.ai.request_feedback', return_value=GIVEN) as ask:
            response = self.client.post(self.url)
        self.assertRedirects(response, self.attempt.get_absolute_url(), fetch_redirect_response=False)
        ask.assert_called_once()
        self.attempt.refresh_from_db()
        self.assertEqual(self.attempt.feedback_status, Feedback.READY)
        self.assertEqual(self.attempt.answers.first().feedback, FEEDBACK)
        self.assertContains(self.client.get(self.attempt.get_absolute_url()), 'AI feedback')

    def test_a_second_failure_is_explained_on_the_page(self):
        with mock.patch('speaking.feedback.ai.request_feedback', side_effect=ai.FeedbackError('still down')):
            response = self.client.post(self.url, follow=True)
        self.assertContains(response, 'The AI feedback is still not available.')
        self.attempt.refresh_from_db()
        self.assertEqual((self.attempt.feedback_status, self.attempt.feedback_error), (Feedback.FAILED, 'still down'))

    def test_the_key_added_later_makes_it_work(self):
        SpeakingAttempt.objects.filter(pk=self.attempt.pk).update(feedback_status=Feedback.UNCONFIGURED)
        with mock.patch('speaking.feedback.ai.request_feedback', return_value=GIVEN):
            self.client.post(self.url)
        self.attempt.refresh_from_db()
        self.assertEqual(self.attempt.feedback_status, Feedback.READY)

    @override_settings(ANTHROPIC_API_KEY='', GROQ_API_KEY='')
    def test_asking_without_a_key_says_so_instead_of_try_later(self):
        SpeakingAttempt.objects.filter(pk=self.attempt.pk).update(feedback_status=Feedback.UNCONFIGURED)
        with mock.patch('speaking.feedback.ai.urllib.request.urlopen') as urlopen:
            response = self.client.post(self.url, follow=True)
        urlopen.assert_not_called()
        self.assertContains(response, 'The AI feedback is not turned on on this site yet. Your answers are saved')
        self.assertNotContains(response, 'try again a little later')
        self.attempt.refresh_from_db()
        self.assertEqual(self.attempt.feedback_status, Feedback.UNCONFIGURED)

    def test_feedback_that_is_there_is_not_asked_for_again(self):
        SpeakingAttempt.objects.filter(pk=self.attempt.pk).update(feedback_status=Feedback.READY)
        with mock.patch('speaking.feedback.ai.request_feedback') as ask:
            self.assertEqual(self.client.post(self.url).status_code, 302)
        ask.assert_not_called()

    def test_it_needs_a_post_and_the_owner_or_an_admin(self):
        self.assertEqual(self.client.get(self.url).status_code, 405)
        with mock.patch('speaking.feedback.ai.request_feedback', return_value=GIVEN) as ask:
            self.client.force_login(self.other)
            self.assertEqual(self.client.post(self.url).status_code, 404)
            ask.assert_not_called()
            self.client.logout()
            self.assertEqual(self.client.post(self.url).status_code, 302)
            ask.assert_not_called()
            self.client.force_login(self.admin)
            self.assertEqual(self.client.post(self.url).status_code, 302)
            ask.assert_called_once()


@override_settings(ANTHROPIC_API_KEY='', GROQ_API_KEY='gsk_test')
class TranscriptionTests(TempMediaMixin, TestCase):
    """With a Groq key the recordings are turned into text on the server (Whisper) before the AI reads them."""

    HEARD = [
        'Umm, I usually play football with my friends.',
        'I live in a flat, uh, with my family.',
        'I like comedy movies because they are funny.',
    ]

    def setUp(self):
        self.course = make_speaking_course()
        self.set = make_set(self.course)
        self.student = users()[0]
        self.client.force_login(self.student)
        self.url = reverse('speaking:finish', args=[self.course.slug, 1, self.set.pk])
        self.transcribe = self.patch('speaking.feedback.ai.transcribe', side_effect=[(text, 0.81) for text in self.HEARD])
        self.ask_ai = self.patch('speaking.feedback.ai.request_feedback', return_value=GIVEN)

    def patch(self, target, **kwargs):
        patcher = mock.patch(target, **kwargs)
        self.addCleanup(patcher.stop)
        return patcher.start()

    def finish(self, **kwargs):
        self.assertEqual(self.client.post(self.url, answers_post(self.set, **kwargs)).status_code, 200)
        return SpeakingAttempt.objects.latest('pk')

    def retry(self, attempt):
        return self.client.post(reverse('speaking:retry_feedback', args=[self.course.slug, attempt.pk]))

    def test_what_whisper_hears_is_what_the_ai_checks(self):
        attempt = self.finish()
        answers = list(attempt.answers.all())
        self.assertEqual([call.args for call in self.transcribe.call_args_list],
                         [(answer.audio.path, 'audio/webm') for answer in answers])
        self.assertEqual([answer.transcript for answer in answers], self.HEARD)
        self.assertEqual([answer.confidence for answer in answers], [0.81] * 3)
        items = self.ask_ai.call_args.args[0]
        self.assertEqual([item['transcript'] for item in items], self.HEARD)
        self.assertEqual({item['confidence'] for item in items}, {0.81})
        self.assertEqual(attempt.feedback_status, Feedback.READY)
        self.assertContains(self.client.get(attempt.get_absolute_url()), f'“{self.HEARD[0]}”')

    def test_answers_the_browser_did_not_hear_are_heard_from_the_recording(self):
        attempt = self.finish(transcripts=['', '', ''], confidence=None)
        self.assertEqual([item['number'] for item in self.ask_ai.call_args.args[0]], [1, 2, 3])
        self.assertEqual(attempt.feedback_status, Feedback.READY)
        self.assertEqual(attempt.answers.get(order=2).transcript, self.HEARD[2])

    def test_when_whisper_hears_nothing_the_browser_text_stays(self):
        self.transcribe.side_effect = [('', None), (self.HEARD[1], 0.7), ('', None)]
        answers = list(self.finish().answers.all())
        self.assertEqual([answer.transcript for answer in answers], [SPOKEN[0], self.HEARD[1], SPOKEN[2]])
        self.assertEqual([answer.confidence for answer in answers], [0.88, 0.7, 0.88])

    def test_silence_everywhere_is_nothing_to_check(self):
        self.transcribe.side_effect = None
        self.transcribe.return_value = ('', None)
        attempt = self.finish(transcripts=['', '', ''])
        self.assertEqual(attempt.feedback_status, Feedback.EMPTY)
        self.ask_ai.assert_not_called()

    def test_a_recording_whisper_cannot_use_keeps_the_browser_text(self):
        self.transcribe.side_effect = [
            ai.RecordingRejected('The AI service answered 400: could not process file', 400),
            (self.HEARD[1], 0.8), (self.HEARD[2], 0.8),
        ]
        attempt = self.finish()
        self.assertEqual([answer.transcript for answer in attempt.answers.all()], [SPOKEN[0], *self.HEARD[1:]])
        self.assertEqual(attempt.feedback_status, Feedback.READY)

    def test_a_failing_service_leaves_an_attempt_that_can_be_retried(self):
        self.transcribe.side_effect = ai.FeedbackError('The AI service answered 429: Rate limit reached', 429)
        attempt = self.finish()
        self.assertEqual(attempt.feedback_status, Feedback.FAILED)
        self.assertEqual(attempt.feedback_error,
                         'Answer 1 could not be turned into text: The AI service answered 429: Rate limit reached')
        self.assertEqual(self.transcribe.call_count, 1)  # the other recordings are not tried while it is failing
        self.ask_ai.assert_not_called()
        self.assertEqual([answer.transcript for answer in attempt.answers.all()], SPOKEN)

        self.transcribe.side_effect = [(text, 0.81) for text in self.HEARD]
        self.assertRedirects(self.retry(attempt), attempt.get_absolute_url(), fetch_redirect_response=False)
        attempt.refresh_from_db()
        self.assertEqual((attempt.feedback_status, attempt.feedback_error), (Feedback.READY, ''))
        self.assertEqual([answer.transcript for answer in attempt.answers.all()], self.HEARD)
        self.ask_ai.assert_called_once()

    def test_answers_without_a_recording_keep_the_browser_text(self):
        attempt = self.finish(audio=False)
        self.transcribe.assert_not_called()
        self.assertEqual([answer.transcript for answer in attempt.answers.all()], SPOKEN)
        self.assertEqual(attempt.feedback_status, Feedback.READY)

    def test_recordings_that_are_gone_are_skipped(self):
        attempt = self.finish()
        for answer in attempt.answers.all():
            os.remove(answer.audio.path)
        SpeakingAttempt.objects.filter(pk=attempt.pk).update(feedback_status=Feedback.FAILED)
        self.transcribe.reset_mock()
        self.retry(attempt)
        self.transcribe.assert_not_called()
        attempt.refresh_from_db()
        self.assertEqual(attempt.feedback_status, Feedback.READY)

    def test_a_very_long_transcript_is_cut(self):
        self.transcribe.side_effect = [('word ' * 1000, 0.9), (self.HEARD[1], 0.8), (self.HEARD[2], 0.8)]
        attempt = self.finish()
        self.assertEqual(len(attempt.answers.get(order=0).transcript), 1999)  # cut at 2000, trailing space gone

    @override_settings(GROQ_API_KEY='')
    def test_without_a_groq_key_the_recordings_stay_on_this_computer(self):
        attempt = self.finish()
        self.transcribe.assert_not_called()
        self.assertEqual([answer.transcript for answer in attempt.answers.all()], SPOKEN)


@override_settings(GROQ_API_KEY='')
class AnswerAudioTests(TempMediaMixin, TestCase):
    def setUp(self):
        self.course = make_speaking_course()
        self.set = make_set(self.course)
        self.student, self.other, self.admin = users()
        self.client.force_login(self.student)
        with mock.patch('speaking.feedback.ai.request_feedback', return_value=GIVEN):
            self.client.post(
                reverse('speaking:finish', args=[self.course.slug, 1, self.set.pk]), answers_post(self.set))
        self.answer = SpeakingAnswer.objects.get(order=0)
        self.url = reverse('speaking:answer_audio', args=[self.course.slug, self.answer.pk])

    def test_the_owner_hears_the_recording(self):
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response['Content-Type'], 'audio/webm')
        self.assertEqual(response['Accept-Ranges'], 'bytes')
        self.assertEqual(b''.join(response.streaming_content), b'x' * 2000)

    def test_the_player_can_jump_around(self):
        response = self.client.get(self.url, HTTP_RANGE='bytes=100-199')
        self.assertEqual(response.status_code, 206)
        self.assertEqual(response['Content-Range'], 'bytes 100-199/2000')
        self.assertEqual(len(b''.join(response.streaming_content)), 100)

    def test_admins_may_listen_but_other_students_may_not(self):
        self.client.force_login(self.admin)
        self.assertEqual(self.client.get(self.url).status_code, 200)
        self.client.force_login(self.other)
        self.assertEqual(self.client.get(self.url).status_code, 404)
        self.client.logout()
        self.assertEqual(self.client.get(self.url).status_code, 302)

    def test_a_recording_that_is_gone_or_never_was_is_404(self):
        os.remove(self.answer.audio.path)
        self.assertEqual(self.client.get(self.url).status_code, 404)
        SpeakingAnswer.objects.filter(pk=self.answer.pk).update(audio='')
        self.assertEqual(self.client.get(self.url).status_code, 404)
        self.assertEqual(self.client.get(reverse('speaking:answer_audio', args=[self.course.slug, 9999])).status_code, 404)

    def test_the_wrong_course_is_404(self):
        elsewhere = make_speaking_course()
        self.assertEqual(
            self.client.get(reverse('speaking:answer_audio', args=[elsewhere.slug, self.answer.pk])).status_code, 404)

    def test_recordings_are_deleted_with_their_answers(self):
        paths = [answer.audio.path for answer in SpeakingAnswer.objects.all()]
        self.assertTrue(all(os.path.exists(path) for path in paths))
        SpeakingAttempt.objects.get().delete()
        self.assertFalse(any(os.path.exists(path) for path in paths))

    def test_recordings_are_deleted_with_their_set(self):
        paths = [answer.audio.path for answer in SpeakingAnswer.objects.all()]
        self.set.delete()
        self.assertFalse(any(os.path.exists(path) for path in paths))
        self.assertEqual((SpeakingAttempt.objects.count(), SpeakingQuestion.objects.count()), (0, 0))
