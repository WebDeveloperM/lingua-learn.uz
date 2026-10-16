import os

from django.test import TestCase
from django.urls import reverse

from accounts.models import Role, User

from .models import Category, Course, Exercise, ExerciseResult, Question
from .support import TOTAL_EXERCISES, TempMediaMixin, make_ready_exercise, seed
from .templatetags.practice_tags import inline_bold


class ExerciseFlowTests(TempMediaMixin, TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.course = Course.objects.create(title='Listening', category=Category.LISTENING, short_description='x')
        seed()
        cls.exercise = make_ready_exercise()
        cls.empty_exercise = Exercise.objects.get(part__number=1, number=2)
        cls.student = User.objects.create_user(email='s@t.uz', password='StrongPass123!')
        cls.other = User.objects.create_user(email='o@t.uz', password='StrongPass123!')
        cls.admin = User.objects.create_user(email='a@t.uz', password='StrongPass123!', role=Role.ADMIN)
        cls.questions = list(cls.exercise.questions.all())

    def url(self, name, number=1):
        return reverse(f'courses:{name}', args=[self.course.slug, 1, number])

    def correct_answers(self):
        return {f'q{q.pk}': q.correct for q in self.questions}

    def submit(self, answers):
        return self.client.post(self.url('exercise_submit'), answers)

    def test_tiles_link_to_their_exercise_page(self):
        response = self.client.get(self.course.get_absolute_url())
        self.assertContains(response, f'href="{self.url("exercise_intro")}"')
        self.assertContains(response, f'href="{self.url("exercise_intro", 2)}"')
        self.assertContains(response, 'class="ex-tile"', count=TOTAL_EXERCISES)

    def test_every_exercise_page_needs_a_login(self):
        for name in ('exercise_intro', 'exercise_play'):
            url = self.url(name)
            self.assertRedirects(
                self.client.get(url), f"{reverse('accounts:login')}?next={url}", fetch_redirect_response=False)
        url = self.url('exercise_submit')
        self.assertRedirects(
            self.client.post(url), f"{reverse('accounts:login')}?next={url}", fetch_redirect_response=False)

    def test_intro_of_a_ready_exercise(self):
        self.client.force_login(self.student)
        response = self.client.get(self.url('exercise_intro'))
        self.assertContains(response, 'Listening · Part 1 · Exercise 1')
        self.assertContains(response, 'Ready to start?')
        self.assertContains(response, '1 part · 3 questions · <strong>5 minutes</strong>')
        self.assertContains(response, 'You will see your results after you press <strong>Submit</strong>')
        self.assertContains(response, f'href="{self.url("exercise_play")}"')
        self.assertContains(response, 'Start exercise 🚀')
        self.assertContains(response, f'href="{self.course.get_absolute_url()}"')
        self.assertNotContains(response, 'disabled')

    def test_intro_uses_singular_forms(self):
        exercise = make_ready_exercise(part_number=2, exercise_number=1, questions=1, minutes=1)
        self.client.force_login(self.student)
        response = self.client.get(reverse('courses:exercise_intro', args=[self.course.slug, 2, exercise.number]))
        self.assertContains(response, '1 part · 1 question · <strong>1 minute</strong>')

    def test_intro_of_an_empty_exercise_has_a_disabled_start_button(self):
        self.client.force_login(self.student)
        response = self.client.get(self.url('exercise_intro', 2))
        self.assertContains(response, 'Ready to start?')
        self.assertContains(response, '1 part · 0 questions')
        self.assertContains(response, 'not ready yet')
        self.assertContains(response, 'disabled')
        self.assertNotContains(response, self.url('exercise_play', 2))
        self.assertNotContains(response, 'Add them in the panel')

    def test_admins_get_a_link_to_fill_an_empty_exercise(self):
        self.client.force_login(self.admin)
        response = self.client.get(self.url('exercise_intro', 2))
        self.assertContains(response, reverse('panel:exercise_edit', args=[self.empty_exercise.pk]))

    def test_unknown_exercise_is_a_404(self):
        self.client.force_login(self.student)
        self.assertEqual(self.client.get(self.url('exercise_intro', 99)).status_code, 404)

    def test_play_page_has_timer_audio_and_questions(self):
        self.client.force_login(self.student)
        response = self.client.get(self.url('exercise_play'))
        self.assertContains(response, 'Listening · Part 1 · Exercise 1')
        self.assertContains(response, 'data-duration="300"')
        self.assertContains(response, '>05:00<')
        self.assertContains(response, 'Pause')
        self.assertContains(response, f'src="{reverse("courses:exercise_audio", args=[self.exercise.pk])}"')
        self.assertContains(response, '<strong>Listen</strong> and answer the questions below.')
        self.assertContains(response, '💬 Part 1')
        self.assertContains(response, 'each sentence <strong>twice</strong>')
        self.assertContains(response, 'Where is the library?')
        self.assertContains(response, 'class="q-card"', count=3)
        self.assertContains(response, 'type="radio"', count=9)
        self.assertContains(response, f'name="q{self.questions[0].pk}" value="b"')
        self.assertContains(response, 'Submit')

    def test_play_page_does_not_leak_the_answers(self):
        self.client.force_login(self.student)
        html = self.client.get(self.url('exercise_play')).content.decode()
        for marker in ('is-correct', 'is-wrong', 'checked', 'data-correct'):
            self.assertNotIn(marker, html)

    def test_play_redirects_back_to_the_intro_when_not_ready(self):
        self.client.force_login(self.student)
        response = self.client.get(self.url('exercise_play', 2))
        self.assertRedirects(response, self.url('exercise_intro', 2))

    def test_timer_label_follows_the_duration(self):
        self.exercise.duration_minutes = 12
        self.exercise.save()
        self.client.force_login(self.student)
        response = self.client.get(self.url('exercise_play'))
        self.assertContains(response, 'data-duration="720"')
        self.assertContains(response, '>12:00<')

    def test_submitting_correct_answers_scores_full_marks_and_saves_the_result(self):
        self.client.force_login(self.student)
        response = self.submit(self.correct_answers())
        self.assertTemplateUsed(response, 'courses/exercise_result.html')
        self.assertContains(response, '<span>3</span> / 3')
        self.assertContains(response, 'Perfect score!')
        result = ExerciseResult.objects.get(user=self.student, exercise=self.exercise)
        self.assertEqual((result.score, result.total), (3, 3))

    def test_unanswered_and_invalid_answers_are_wrong(self):
        self.client.force_login(self.student)
        answers = {f'q{self.questions[0].pk}': self.questions[0].correct, f'q{self.questions[1].pk}': 'z'}
        response = self.submit(answers)
        self.assertContains(response, '<span>1</span> / 3')
        self.assertContains(response, 'You did not answer this question.', count=2)
        self.assertContains(response, 'Keep going!')

    def test_answers_for_other_questions_are_ignored(self):
        self.client.force_login(self.student)
        answers = {**self.correct_answers(), 'q99999': 'a', 'unrelated': 'b'}
        self.assertContains(self.submit(answers), '<span>3</span> / 3')

    def test_result_page_shows_the_right_and_the_chosen_wrong_options(self):
        self.client.force_login(self.student)
        wrong = {f'q{q.pk}': 'abc'[('abc'.index(q.correct) + 1) % 3] for q in self.questions}
        response = self.submit(wrong)
        self.assertContains(response, 'class="q-option is-correct"', count=3)
        self.assertContains(response, 'class="q-option is-wrong"', count=3)
        self.assertContains(response, '✓ correct</span>', count=3)
        self.assertContains(response, '✗ your answer</span>', count=3)
        self.assertContains(response, '<span>0</span> / 3')

    def test_the_best_score_is_kept(self):
        self.client.force_login(self.student)
        self.submit(self.correct_answers())
        response = self.submit({})
        self.assertContains(response, '<span>0</span> / 3')
        self.assertContains(response, 'Your best score: ⭐ 3/3')
        self.assertEqual(ExerciseResult.objects.get(user=self.student).score, 3)

        ExerciseResult.objects.filter(user=self.student).update(score=1)
        self.submit(self.correct_answers())
        self.assertEqual(ExerciseResult.objects.get(user=self.student).score, 3)

    def test_changed_question_count_replaces_the_old_result(self):
        self.client.force_login(self.student)
        self.submit(self.correct_answers())
        Question.objects.create(exercise=self.exercise, order=9, option_a='x', option_b='y', option_c='z')
        self.submit({})
        result = ExerciseResult.objects.get(user=self.student)
        self.assertEqual((result.score, result.total), (0, 4))

    def test_results_are_per_student_and_show_on_the_practice_page(self):
        self.client.force_login(self.student)
        self.submit(self.correct_answers())
        self.assertContains(self.client.get(self.course.get_absolute_url()), '⭐ 3/3', count=1)
        self.client.force_login(self.other)
        self.assertNotContains(self.client.get(self.course.get_absolute_url()), '⭐')
        self.assertEqual(ExerciseResult.objects.count(), 1)

    def test_submit_accepts_only_post_and_ready_exercises(self):
        self.client.force_login(self.student)
        self.assertEqual(self.client.get(self.url('exercise_submit')).status_code, 405)
        self.assertEqual(self.client.post(self.url('exercise_submit', 2), {}).status_code, 404)
        self.assertEqual(ExerciseResult.objects.count(), 0)

    def test_draft_course_exercises_are_for_admins_only(self):
        self.course.is_published = False
        self.course.save()
        self.client.force_login(self.student)
        for name in ('exercise_intro', 'exercise_play'):
            self.assertEqual(self.client.get(self.url(name)).status_code, 404)
        self.assertEqual(self.submit(self.correct_answers()).status_code, 404)
        self.client.force_login(self.admin)
        self.assertEqual(self.client.get(self.url('exercise_play')).status_code, 200)


class ExerciseAudioTests(TempMediaMixin, TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.course = Course.objects.create(title='Listening', category=Category.LISTENING, short_description='x')
        seed()
        cls.exercise = make_ready_exercise()
        cls.empty_exercise = Exercise.objects.get(part__number=1, number=2)
        cls.student = User.objects.create_user(email='s@t.uz', password='StrongPass123!')
        cls.url = reverse('courses:exercise_audio', args=[cls.exercise.pk])
        with open(cls.exercise.audio.path, 'rb') as handle:
            cls.content = handle.read()

    def setUp(self):
        self.client.force_login(self.student)

    def fetch(self, **headers):
        response = self.client.get(self.url, **headers)
        body = b''.join(response.streaming_content) if response.streaming else response.content
        response.close()
        return response, body

    def test_login_is_required(self):
        self.client.logout()
        self.assertRedirects(
            self.client.get(self.url), f"{reverse('accounts:login')}?next={self.url}", fetch_redirect_response=False)

    def test_whole_file(self):
        response, body = self.fetch()
        self.assertEqual(response.status_code, 200)
        self.assertEqual(body, self.content)
        self.assertEqual(response['Accept-Ranges'], 'bytes')
        self.assertTrue(response['Content-Type'].startswith('audio/'))

    def test_byte_range_is_served_with_206(self):
        response, body = self.fetch(HTTP_RANGE='bytes=0-99')
        self.assertEqual(response.status_code, 206)
        self.assertEqual(body, self.content[:100])
        self.assertEqual(response['Content-Range'], f'bytes 0-99/{len(self.content)}')
        self.assertEqual(response['Content-Length'], '100')

    def test_open_ended_and_suffix_ranges(self):
        size = len(self.content)
        response, body = self.fetch(HTTP_RANGE='bytes=1000-')
        self.assertEqual((response.status_code, body), (206, self.content[1000:]))
        self.assertEqual(response['Content-Range'], f'bytes 1000-{size - 1}/{size}')
        response, body = self.fetch(HTTP_RANGE='bytes=-50')
        self.assertEqual((response.status_code, body), (206, self.content[-50:]))

    def test_range_end_beyond_the_file_is_clamped(self):
        response, body = self.fetch(HTTP_RANGE=f'bytes=10-{len(self.content) * 5}')
        self.assertEqual((response.status_code, body), (206, self.content[10:]))

    def test_unsatisfiable_range(self):
        response, _ = self.fetch(HTTP_RANGE=f'bytes={len(self.content) + 10}-')
        self.assertEqual(response.status_code, 416)
        self.assertEqual(response['Content-Range'], f'bytes */{len(self.content)}')

    def test_unsupported_range_forms_fall_back_to_the_whole_file(self):
        for header in ('bytes=0-1,5-6', 'items=0-5', 'bytes=-', 'garbage'):
            response, body = self.fetch(HTTP_RANGE=header)
            self.assertEqual((response.status_code, body), (200, self.content), header)

    def test_missing_audio_and_unpublished_courses_are_404(self):
        empty_url = reverse('courses:exercise_audio', args=[self.empty_exercise.pk])
        self.assertEqual(self.client.get(empty_url).status_code, 404)
        self.course.is_published = False
        self.course.save()
        self.assertEqual(self.client.get(self.url).status_code, 404)

    def test_audio_file_missing_on_disk_is_a_404(self):
        path = self.exercise.audio.path
        os.remove(path)
        try:
            self.assertEqual(self.client.get(self.url).status_code, 404)
        finally:
            with open(path, 'wb') as handle:
                handle.write(self.content)


class AudioCleanupTests(TempMediaMixin, TestCase):
    def setUp(self):
        self.course = Course.objects.create(title='Listening', category=Category.LISTENING, short_description='x')
        seed()

    def test_deleting_an_exercise_deletes_its_audio_file(self):
        exercise = make_ready_exercise()
        path = exercise.audio.path
        self.assertTrue(os.path.exists(path))
        exercise.delete()
        self.assertFalse(os.path.exists(path))

    def test_deleting_the_course_deletes_every_audio_file(self):
        paths = [make_ready_exercise(1, 1).audio.path, make_ready_exercise(2, 1).audio.path]
        self.course.delete()
        self.assertFalse(any(os.path.exists(path) for path in paths))


class InlineBoldTests(TestCase):
    def test_bold_markup_is_converted_and_everything_else_is_escaped(self):
        self.assertEqual(inline_bold('hear it **twice** now'), 'hear it <strong>twice</strong> now')
        self.assertEqual(inline_bold('<script>**x**</script>'), '&lt;script&gt;<strong>x</strong>&lt;/script&gt;')
        self.assertEqual(inline_bold('no markup'), 'no markup')
        self.assertEqual(inline_bold('**a** and **b**'), '<strong>a</strong> and <strong>b</strong>')
