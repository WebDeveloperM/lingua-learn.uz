import os
from unittest import mock

from django.core.files.base import ContentFile
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import Client
from django.urls import reverse

from courses.models import Category, Course, Exercise, ExerciseResult, Part, Question
from courses.support import TempMediaMixin, make_wav

from .support import COURSE_BASE, PanelTestCase, formset_data, rendered_form_data


def wav_upload(name='lesson.wav'):
    return SimpleUploadedFile(name, make_wav(), content_type='audio/wav')


def question_rows(count=8, blank_from=None):
    rows = []
    for index in range(count):
        if blank_from is not None and index >= blank_from:
            rows.append({'text': '', 'option_a': '', 'option_b': '', 'option_c': '', 'correct': ''})
        else:
            rows.append({
                'text': '', 'option_a': f'A{index}', 'option_b': f'B{index}', 'option_c': f'C{index}',
                'correct': 'abc'[index % 3],
            })
    return rows


def add_ready_exercise(part, number=1):
    exercise = Exercise.objects.create(part=part, number=number)
    exercise.audio.save('ready.wav', ContentFile(make_wav()), save=True)
    Question.objects.create(exercise=exercise, option_a='a', option_b='b', option_c='c')
    return exercise


class CourseFormPracticeSectionTests(TempMediaMixin, PanelTestCase):
    def setUp(self):
        self.client.force_login(self.admin)

    def test_new_course_form_asks_to_save_the_course_first(self):
        response = self.client.get(reverse('panel:course_create'))
        self.assertContains(response, 'Mashqlar (Practice)')
        self.assertContains(response, 'avval kursni saqlang')
        self.assertNotContains(response, "Part qo'shish")

    def test_saving_a_new_course_lands_on_its_edit_page_with_the_practice_section(self):
        data = {**COURSE_BASE, **formset_data('outcomes', []), **formset_data('tags', [])}
        response = self.client.post(reverse('panel:course_create'), data, follow=True)
        course = Course.objects.get(title=COURSE_BASE['title'])
        self.assertRedirects(response, reverse('panel:course_edit', args=[course.pk]))
        self.assertContains(response, 'kursi yaratildi')
        self.assertContains(response, reverse('panel:part_create', args=[course.pk]))

    def test_edit_form_without_parts_shows_an_empty_hint(self):
        response = self.client.get(reverse('panel:course_edit', args=[self.course1.pk]))
        self.assertContains(response, "Hali Part yo'q")
        self.assertContains(response, reverse('panel:part_create', args=[self.course1.pk]))

    def test_edit_form_lists_the_parts_and_how_many_exercises_are_ready(self):
        part = Part.objects.create(course=self.course1, number=1, name='Short replies', icon='💬')
        add_ready_exercise(part, 1)
        Exercise.objects.create(part=part, number=2)
        response = self.client.get(reverse('panel:course_edit', args=[self.course1.pk]))
        self.assertContains(response, '💬 Part 1 · Short replies')
        self.assertContains(response, '2 ta mashq · 1 tasi tayyor')
        self.assertContains(response, reverse('panel:part_edit', args=[part.pk]))


class PartManagementTests(TempMediaMixin, PanelTestCase):
    def setUp(self):
        self.client.force_login(self.admin)

    def part_data(self, **overrides):
        return {'number': 1, 'name': 'Short replies', 'icon': '💬', 'kind': 'choice', 'first_question_number': 1,
                'instructions': 'Listen **twice**.', **overrides}

    def test_new_part_form_suggests_the_next_number(self):
        Part.objects.create(course=self.course1, number=1, name='One')
        Part.objects.create(course=self.course1, number=4, name='Four')
        response = self.client.get(reverse('panel:part_create', args=[self.course1.pk]))
        self.assertEqual(response.context['form'].initial['number'], 5)
        self.assertContains(response, "Yangi Part qo'shish")

    def test_create_part(self):
        response = self.client.post(reverse('panel:part_create', args=[self.course1.pk]), self.part_data())
        part = Part.objects.get(course=self.course1)
        self.assertRedirects(response, reverse('panel:part_edit', args=[part.pk]))
        self.assertEqual((part.number, part.name, part.icon), (1, 'Short replies', '💬'))
        self.assertEqual(part.instructions, 'Listen **twice**.')

    def test_part_numbers_are_unique_within_a_course_only(self):
        Part.objects.create(course=self.course1, number=1, name='One')
        response = self.client.post(reverse('panel:part_create', args=[self.course1.pk]), self.part_data())
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Bu raqamli Part allaqachon mavjud')
        self.assertEqual(Part.objects.filter(course=self.course1).count(), 1)

        self.client.post(reverse('panel:part_create', args=[self.course2.pk]), self.part_data())
        self.assertEqual(Part.objects.filter(course=self.course2).count(), 1)

    def test_part_number_must_be_positive(self):
        response = self.client.post(reverse('panel:part_create', args=[self.course1.pk]), self.part_data(number=0))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(Part.objects.count(), 0)

    def test_part_name_is_required(self):
        response = self.client.post(reverse('panel:part_create', args=[self.course1.pk]), self.part_data(name=''))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(Part.objects.count(), 0)

    def test_edit_part_and_keep_its_own_number(self):
        part = Part.objects.create(course=self.course1, number=2, name='Old')
        url = reverse('panel:part_edit', args=[part.pk])
        response = self.client.post(url, self.part_data(number=2, name='New name'))
        self.assertRedirects(response, url)
        part.refresh_from_db()
        self.assertEqual((part.number, part.name), (2, 'New name'))

    def test_part_page_lists_exercises_with_their_status(self):
        part = Part.objects.create(course=self.course1, number=1, name='One')
        add_ready_exercise(part, 1)
        Exercise.objects.create(part=part, number=2)
        response = self.client.get(reverse('panel:part_edit', args=[part.pk]))
        self.assertContains(response, 'Tayyor', count=2)  # one badge + one explanatory sentence
        self.assertContains(response, "Bo'sh", count=1)
        self.assertContains(response, '1 savol')
        self.assertContains(response, '0 savol')
        for exercise in part.exercises.all():
            self.assertContains(response, reverse('panel:exercise_edit', args=[exercise.pk]))

    def test_deleting_a_part_removes_its_exercises_and_returns_to_the_course(self):
        part = Part.objects.create(course=self.course1, number=1, name='One')
        Exercise.objects.create(part=part, number=1)
        response = self.client.post(reverse('panel:part_delete', args=[part.pk]))
        self.assertRedirects(response, reverse('panel:course_edit', args=[self.course1.pk]))
        self.assertEqual((Part.objects.count(), Exercise.objects.count()), (0, 0))

    def test_missing_objects_are_404(self):
        self.assertEqual(self.client.get(reverse('panel:part_edit', args=[999])).status_code, 404)
        self.assertEqual(self.client.get(reverse('panel:part_create', args=[999])).status_code, 404)
        self.assertEqual(self.client.get(reverse('panel:exercise_edit', args=[999])).status_code, 404)


class ExerciseEditorTests(TempMediaMixin, PanelTestCase):
    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()
        cls.listening = Course.objects.create(title='Listening', category=Category.LISTENING, short_description='x')
        cls.part = Part.objects.create(
            course=cls.listening, number=1, name='Short replies', icon='💬',
            instructions='You will hear each sentence **twice**.',
        )

    def setUp(self):
        self.client.force_login(self.admin)
        self.exercise = Exercise.objects.create(part=self.part, number=1)
        self.url = reverse('panel:exercise_edit', args=[self.exercise.pk])

    def post_content(self, rows=None, audio=None, **extra):
        data = {'duration_minutes': 5, **formset_data('questions', rows if rows is not None else question_rows())}
        if audio is not None:
            data['audio'] = audio
        data.update(extra)
        return self.client.post(self.url, data)

    def test_adding_an_exercise_takes_the_next_number_and_opens_its_editor(self):
        response = self.client.post(reverse('panel:exercise_add', args=[self.part.pk]))
        added = Exercise.objects.get(part=self.part, number=2)
        self.assertRedirects(response, reverse('panel:exercise_edit', args=[added.pk]))

    def test_new_exercise_editor_offers_eight_empty_question_rows(self):
        response = self.client.get(self.url)
        self.assertEqual(len(response.context['questions'].forms), 8)
        self.assertContains(response, 'Audio hali yuklanmagan')
        self.assertContains(response, 'Listening · Part 1 · Exercise 1')
        self.assertContains(response, 'enctype="multipart/form-data"')

    def test_editor_only_adds_the_rows_that_are_still_missing(self):
        for index in range(3):
            Question.objects.create(exercise=self.exercise, order=index, option_a='a', option_b='b', option_c='c')
        response = self.client.get(self.url)
        questions = response.context['questions']
        self.assertEqual((questions.initial_form_count(), len(questions.forms)), (3, 8))

    def test_a_complete_exercise_has_no_spare_row(self):
        for index in range(8):
            Question.objects.create(exercise=self.exercise, order=index, option_a='a', option_b='b', option_c='c')
        questions = self.client.get(self.url).context['questions']
        self.assertEqual((questions.initial_form_count(), len(questions.forms)), (8, 8))
        self.assertContains(self.client.get(self.url), "+ Savol qo'shish")  # more can still be added with the button

    def test_the_part_decides_how_many_rows_a_new_exercise_opens_with(self):
        Part.objects.filter(pk=self.part.pk).update(questions_count=6)
        self.assertEqual(len(self.client.get(self.url).context['questions'].forms), 6)

    def test_more_questions_than_expected_are_all_kept_without_a_spare_row(self):
        for index in range(9):
            Question.objects.create(exercise=self.exercise, order=index, option_a='a', option_b='b', option_c='c')
        questions = self.client.get(self.url).context['questions']
        self.assertEqual((questions.initial_form_count(), len(questions.forms)), (9, 9))

    def test_upload_audio_and_eight_questions(self):
        response = self.post_content(audio=wav_upload(), duration_minutes=7)
        self.assertRedirects(response, self.url)

        self.exercise.refresh_from_db()
        self.assertTrue(os.path.exists(self.exercise.audio.path))
        self.assertEqual(self.exercise.duration_minutes, 7)
        questions = list(self.exercise.questions.all())
        self.assertEqual([q.order for q in questions], list(range(8)))
        self.assertEqual([q.correct for q in questions], list('abcabcab'))
        self.assertEqual((questions[0].option_a, questions[7].option_c), ('A0', 'C7'))
        self.assertTrue(self.exercise.is_ready)

    def test_blank_question_rows_are_ignored(self):
        self.post_content(rows=question_rows(8, blank_from=3), audio=wav_upload())
        self.assertEqual(self.exercise.questions.count(), 3)

    def test_the_correct_answer_must_be_chosen_for_every_filled_row(self):
        rows = question_rows(2)
        rows[1]['correct'] = ''
        response = self.post_content(rows=rows, audio=wav_upload())
        self.assertEqual(response.status_code, 200)
        self.assertEqual(self.exercise.questions.count(), 0)
        self.exercise.refresh_from_db()
        self.assertFalse(self.exercise.audio)

    def test_all_three_options_are_required(self):
        rows = question_rows(1)
        rows[0]['option_c'] = ''
        response = self.post_content(rows=rows)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(self.exercise.questions.count(), 0)

    def test_only_audio_files_are_accepted(self):
        bad = SimpleUploadedFile('notes.txt', b'not audio', content_type='text/plain')
        response = self.post_content(audio=bad)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Faqat audio fayl yuklash mumkin')
        self.exercise.refresh_from_db()
        self.assertFalse(self.exercise.audio)

    def test_extension_check_ignores_case(self):
        self.post_content(rows=question_rows(1), audio=wav_upload('SONG.WAV'))
        self.exercise.refresh_from_db()
        self.assertTrue(self.exercise.audio)

    def test_too_large_audio_is_rejected(self):
        with mock.patch('panel.forms.MAX_AUDIO_MB', 0):
            response = self.post_content(audio=wav_upload())
        self.assertContains(response, 'Fayl hajmi')
        self.exercise.refresh_from_db()
        self.assertFalse(self.exercise.audio)

    def test_replacing_the_audio_removes_the_old_file(self):
        self.post_content(rows=question_rows(1), audio=wav_upload('first.wav'))
        self.exercise.refresh_from_db()
        old_path = self.exercise.audio.path

        self.client.post(self.url, {
            'duration_minutes': 5, 'audio': wav_upload('second.wav'),
            **formset_data('questions', [], initial=0),
        })
        self.exercise.refresh_from_db()
        self.assertNotEqual(self.exercise.audio.path, old_path)
        self.assertTrue(os.path.exists(self.exercise.audio.path))
        self.assertFalse(os.path.exists(old_path))

    def test_remove_audio_checkbox_clears_the_field_and_the_file(self):
        self.post_content(rows=question_rows(1), audio=wav_upload())
        self.exercise.refresh_from_db()
        path = self.exercise.audio.path

        question = self.exercise.questions.get()
        rows = [{'id': question.pk, 'text': '', 'option_a': 'A0', 'option_b': 'B0', 'option_c': 'C0', 'correct': 'a'}]
        self.client.post(self.url, {
            'duration_minutes': 5, 'remove_audio': 'on', **formset_data('questions', rows, initial=1),
        })
        self.exercise.refresh_from_db()
        self.assertFalse(self.exercise.audio)
        self.assertFalse(os.path.exists(path))
        self.assertFalse(self.exercise.is_ready)

    def test_editing_deleting_and_adding_questions(self):
        first = Question.objects.create(exercise=self.exercise, order=0, option_a='a0', option_b='b0', option_c='c0')
        second = Question.objects.create(exercise=self.exercise, order=1, option_a='a1', option_b='b1', option_c='c1')
        rows = [
            {'id': first.pk, 'text': 'Changed', 'option_a': 'a0', 'option_b': 'b0', 'option_c': 'c0', 'correct': 'c'},
            {'id': second.pk, 'text': '', 'option_a': 'a1', 'option_b': 'b1', 'option_c': 'c1', 'correct': 'a',
             'DELETE': 'on'},
            {'text': '', 'option_a': 'new-a', 'option_b': 'new-b', 'option_c': 'new-c', 'correct': 'b'},
        ]
        response = self.client.post(self.url, {'duration_minutes': 5, **formset_data('questions', rows, initial=2)})
        self.assertRedirects(response, self.url)

        questions = list(self.exercise.questions.all())
        self.assertEqual([(q.text, q.option_a, q.correct, q.order) for q in questions],
                         [('Changed', 'a0', 'c', 0), ('', 'new-a', 'b', 1)])

    def test_duration_limits(self):
        for minutes in (0, 121):
            response = self.post_content(rows=question_rows(1), duration_minutes=minutes)
            self.assertEqual(response.status_code, 200)
        self.exercise.refresh_from_db()
        self.assertEqual(self.exercise.duration_minutes, 5)

    def test_editor_links_to_the_student_page_and_plays_the_audio(self):
        self.post_content(rows=question_rows(1), audio=wav_upload())
        response = self.client.get(self.url)
        self.assertContains(response, reverse('courses:exercise_intro', args=['listening', 1, 1]))
        self.assertContains(response, reverse('courses:exercise_audio', args=[self.exercise.pk]))
        self.assertContains(response, 'Audioni almashtirish')
        self.assertContains(response, 'name="remove_audio"')

    def test_editor_round_trip_posts_back_unchanged(self):
        self.post_content(rows=question_rows(3), audio=wav_upload(), duration_minutes=9)
        data = rendered_form_data(self.client.get(self.url))
        self.assertEqual(data['questions-INITIAL_FORMS'], '3')
        self.assertEqual(data['duration_minutes'], '9')
        self.assertNotIn('audio', data)

        self.assertRedirects(self.client.post(self.url, data), self.url)
        self.assertEqual(
            list(self.exercise.questions.values_list('option_a', 'correct', 'order')),
            [('A0', 'a', 0), ('A1', 'b', 1), ('A2', 'c', 2)],
        )
        self.exercise.refresh_from_db()
        self.assertTrue(self.exercise.audio)

    def test_editor_has_an_optional_transcript_box(self):
        response = self.client.get(self.url)
        self.assertContains(response, 'name="transcript"')
        self.assertContains(response, '<h2>Transcript</h2>')
        self.assertContains(response, 'ikkita yulduzcha')

    def test_transcript_is_saved_cleared_and_round_trips(self):
        text = 'Woman: Is this yours?\nMan: I\'m afraid **not**.'
        self.assertRedirects(self.post_content(rows=question_rows(2), audio=wav_upload(), transcript=text), self.url)
        self.exercise.refresh_from_db()
        self.assertEqual(self.exercise.transcript, text)

        data = rendered_form_data(self.client.get(self.url))
        self.assertEqual(data['transcript'], text)
        self.assertRedirects(self.client.post(self.url, data), self.url)
        self.exercise.refresh_from_db()
        self.assertEqual(self.exercise.transcript, text)

        data['transcript'] = ''
        self.client.post(self.url, data)
        self.exercise.refresh_from_db()
        self.assertEqual(self.exercise.transcript, '')

    def test_every_kind_of_part_offers_the_transcript_box(self):
        for number, kind in enumerate(('gap_fill', 'matching', 'map'), start=2):
            part = Part.objects.create(course=self.listening, number=number, name=kind, kind=kind)
            exercise = Exercise.objects.create(part=part, number=1)
            response = self.client.get(reverse('panel:exercise_edit', args=[exercise.pk]))
            self.assertContains(response, 'name="transcript"', msg_prefix=kind)

    def test_students_see_the_transcript_only_on_the_result_page(self):
        text = 'Woman: Is this yours?\nMan: I\'m afraid **not**.'
        self.post_content(audio=wav_upload(), transcript=text)
        questions = list(self.exercise.questions.all())

        student = Client()
        student.force_login(self.alice)
        args = ['listening', 1, 1]
        self.assertNotContains(student.get(reverse('courses:exercise_play', args=args)), 'Transcript')
        result = student.post(reverse('courses:exercise_submit', args=args), {f'q{q.pk}': q.correct for q in questions})
        self.assertContains(result, '(answers are highlighted)')
        self.assertContains(result, '<mark>not</mark>')

    def test_deleting_an_exercise_removes_its_audio_and_results(self):
        self.post_content(rows=question_rows(1), audio=wav_upload())
        self.exercise.refresh_from_db()
        path = self.exercise.audio.path
        ExerciseResult.objects.create(user=self.alice, exercise=self.exercise, score=1, total=1)

        response = self.client.post(reverse('panel:exercise_delete', args=[self.exercise.pk]))
        self.assertRedirects(response, reverse('panel:part_edit', args=[self.part.pk]))
        self.assertFalse(Exercise.objects.filter(pk=self.exercise.pk).exists())
        self.assertFalse(os.path.exists(path))
        self.assertEqual(ExerciseResult.objects.count(), 0)

    def test_admin_builds_an_exercise_and_a_student_completes_it(self):
        self.post_content(audio=wav_upload(), duration_minutes=5)
        questions = list(self.exercise.questions.all())

        student = Client()
        student.force_login(self.alice)
        play = student.get(reverse('courses:exercise_play', args=['listening', 1, 1]))
        self.assertContains(play, 'class="q-card"', count=8)
        self.assertContains(play, '>05:00<')
        self.assertContains(play, 'each sentence <strong>twice</strong>')

        answers = {f'q{q.pk}': q.correct for q in questions[:6]}
        result = student.post(reverse('courses:exercise_submit', args=['listening', 1, 1]), answers)
        self.assertContains(result, '<span>6</span> / 8')

        listing = student.get(self.listening.get_absolute_url())
        self.assertContains(listing, '⭐ 6/8')
