import os
import re

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import Client
from django.urls import reverse

from courses.models import Category, Course, Exercise, Part, Question
from courses.support import (
    LECTURE_LINES, LECTURE_NOTE, MAP_PLACES, MATCHING_OPTIONS, TempMediaMixin, make_png, make_wav,
)

from .support import PanelTestCase, formset_data, rendered_form_data


def wav_upload():
    return SimpleUploadedFile('talk.wav', make_wav(), content_type='audio/wav')


def png_upload(name='map.png'):
    return SimpleUploadedFile(name, make_png(), content_type='image/png')


def map_rows(letters='caheb'):
    return [{'text': place, 'correct': letter} for place, letter in zip(MAP_PLACES, letters)]


def gap_rows(count=6):
    return [
        {
            'text': f'Label {i}', 'text_before': 'a' if i == 0 else '', 'text_after': '.com' if i == count - 1 else '',
            'answer': f'answer{i} / alt{i}',
        }
        for i in range(count)
    ]


def match_rows(letters='daec'):
    return [{'text': f'Speaker {i + 1}', 'correct': letter} for i, letter in enumerate(letters)]


class PartKindFormTests(PanelTestCase):
    def setUp(self):
        self.client.force_login(self.admin)

    def part_data(self, **overrides):
        return {'number': 2, 'name': 'Gap filling', 'icon': '✍️', 'kind': 'gap_fill', 'first_question_number': 9,
                'instructions': '', **overrides}

    def test_first_part_suggests_question_one(self):
        response = self.client.get(reverse('panel:part_create', args=[self.course1.pk]))
        self.assertEqual(response.context['form'].initial['first_question_number'], 1)

    def test_next_part_continues_after_the_longest_exercise_of_the_previous_one(self):
        part = Part.objects.create(course=self.course1, number=1, name='One', first_question_number=1)
        short = Exercise.objects.create(part=part, number=1)
        long = Exercise.objects.create(part=part, number=2)
        for exercise, count in ((short, 3), (long, 8)):
            for index in range(count):
                Question.objects.create(exercise=exercise, order=index, option_a='a', option_b='b', option_c='c')
        response = self.client.get(reverse('panel:part_create', args=[self.course1.pk]))
        self.assertEqual(response.context['form'].initial['first_question_number'], 9)
        self.assertEqual(response.context['form'].initial['number'], 2)

    def test_part_form_offers_the_four_kinds(self):
        response = self.client.get(reverse('panel:part_create', args=[self.course1.pk]))
        for label in ('Variantlardan tanlash (A, B, C)', "Eshitib yozish (bo&#x27;sh joyni to&#x27;ldirish)",
                      "Ro&#x27;yxatdan tanlash (moslashtirish)", 'Xaritada belgilash (rasmdagi harfni tanlash)'):
            self.assertContains(response, label)
        self.assertContains(response, 'Birinchi savol raqami')

    def test_create_and_edit_a_part_with_a_kind(self):
        response = self.client.post(reverse('panel:part_create', args=[self.course1.pk]), self.part_data())
        part = Part.objects.get(course=self.course1)
        self.assertRedirects(response, reverse('panel:part_edit', args=[part.pk]))
        self.assertEqual((part.kind, part.first_question_number), ('gap_fill', 9))

        self.client.post(reverse('panel:part_edit', args=[part.pk]), self.part_data(kind='matching', first_question_number=15))
        part.refresh_from_db()
        self.assertEqual((part.kind, part.first_question_number), ('matching', 15))

    def test_kind_cannot_change_while_the_part_has_questions(self):
        part = Part.objects.create(course=self.course1, number=2, name='Gap filling', kind='gap_fill', first_question_number=9)
        exercise = Exercise.objects.create(part=part, number=1)
        Question.objects.create(exercise=exercise, order=0, text='Label', answer='x')
        url = reverse('panel:part_edit', args=[part.pk])

        response = self.client.post(url, self.part_data(kind='choice'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'savollar bor')
        part.refresh_from_db()
        self.assertEqual(part.kind, 'gap_fill')

        # other fields can still be edited, and an empty part can change kind freely
        self.client.post(url, self.part_data(name='Renamed'))
        part.refresh_from_db()
        self.assertEqual(part.name, 'Renamed')
        exercise.questions.all().delete()
        self.client.post(url, self.part_data(kind='choice'))
        part.refresh_from_db()
        self.assertEqual(part.kind, 'choice')

    def test_part_form_has_an_optional_question_count(self):
        response = self.client.get(reverse('panel:part_create', args=[self.course1.pk]))
        self.assertContains(response, 'name="questions_count"')
        self.assertContains(response, 'Mashqdagi savollar soni')
        self.assertContains(response, 'placeholder="Avtomatik"')

    def test_question_count_is_saved_and_blank_means_by_kind(self):
        response = self.client.post(
            reverse('panel:part_create', args=[self.course1.pk]),
            self.part_data(kind='choice', first_question_number=24, questions_count=6),
        )
        part = Part.objects.get(course=self.course1)
        edit = reverse('panel:part_edit', args=[part.pk])
        self.assertRedirects(response, edit)
        self.assertEqual((part.questions_count, part.expected_questions), (6, 6))
        self.assertEqual(self.client.get(edit).context['form']['questions_count'].value(), 6)

        self.client.post(edit, self.part_data(kind='choice', first_question_number=24, questions_count=''))
        part.refresh_from_db()
        self.assertEqual((part.questions_count, part.expected_questions), (0, 8))
        self.assertIsNone(self.client.get(edit).context['form']['questions_count'].value())

    def test_question_count_must_be_between_1_and_60(self):
        url = reverse('panel:part_create', args=[self.course1.pk])
        for value in (0, -1, 61, 'many'):
            self.assertEqual(self.client.post(url, self.part_data(questions_count=value)).status_code, 200, value)
        self.assertEqual(Part.objects.count(), 0)

    def test_invalid_kind_and_numbers_are_rejected(self):
        url = reverse('panel:part_create', args=[self.course1.pk])
        for overrides in ({'kind': 'nonsense'}, {'first_question_number': 0}, {'first_question_number': ''}):
            self.assertEqual(self.client.post(url, self.part_data(**overrides)).status_code, 200)
        self.assertEqual(Part.objects.count(), 0)


class GapFillEditorTests(TempMediaMixin, PanelTestCase):
    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()
        cls.listening = Course.objects.create(title='Listening', category=Category.LISTENING, short_description='x')
        cls.part = Part.objects.create(
            course=cls.listening, number=2, name='Gap filling', icon='✍️', kind='gap_fill', first_question_number=9,
            instructions='Write **ONE WORD**.',
        )

    def setUp(self):
        self.client.force_login(self.admin)
        self.exercise = Exercise.objects.create(part=self.part, number=1)
        self.url = reverse('panel:exercise_edit', args=[self.exercise.pk])

    def save(self, rows=None, **extra):
        data = {
            'duration_minutes': 6, 'title': 'Video game review',
            **formset_data('questions', rows if rows is not None else gap_rows()),
            **extra,
        }
        return self.client.post(self.url, data)

    def test_editor_shows_title_and_six_note_rows_numbered_from_nine(self):
        response = self.client.get(self.url)
        self.assertEqual(len(response.context['questions'].forms), 6)
        self.assertContains(response, 'name="title"')
        self.assertContains(response, 'name="instructions"')
        self.assertNotContains(response, 'name="options"')
        self.assertContains(response, 'name="questions-0-answer"')
        self.assertContains(response, 'name="questions-0-intro"')
        self.assertContains(response, 'name="questions-5-text_before"')
        self.assertNotContains(response, 'name="questions-0-option_a"')
        self.assertContains(response, 'counter-reset: qrow 8;')
        self.assertContains(response, '9-savoldan boshlanadi')
        self.assertContains(response, 'Write **ONE WORD**.')  # the part text is shown as the fallback hint

    def test_save_audio_title_instructions_and_gaps(self):
        response = self.save(audio=wav_upload(), instructions='Own **text**')
        self.assertRedirects(response, self.url)
        self.exercise.refresh_from_db()
        self.assertEqual((self.exercise.title, self.exercise.instructions), ('Video game review', 'Own **text**'))
        self.assertEqual(self.exercise.duration_minutes, 6)
        questions = list(self.exercise.questions.all())
        self.assertEqual([q.order for q in questions], list(range(6)))
        self.assertEqual(questions[0].text_before, 'a')
        self.assertEqual(questions[5].text_after, '.com')
        self.assertEqual(questions[2].answer, 'answer2 / alt2')
        self.assertTrue(self.exercise.is_ready)

    def test_blank_rows_are_ignored_and_every_filled_row_needs_an_answer(self):
        rows = gap_rows(6)
        for row in rows[3:]:
            row.update(text='', text_before='', text_after='', answer='')
        self.save(rows=rows, audio=wav_upload())
        self.assertEqual(self.exercise.questions.count(), 3)

        rows = [{'text': 'No answer here', 'text_before': '', 'text_after': '', 'answer': ''}]
        response = self.client.post(self.url, {'duration_minutes': 5, **formset_data('questions', rows, initial=0)})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(self.exercise.questions.count(), 3)

    def test_editing_and_deleting_gaps(self):
        self.save(rows=gap_rows(3), audio=wav_upload())
        first, second, third = list(self.exercise.questions.all())
        rows = [
            {'id': first.pk, 'text': 'Changed label', 'text_before': 'the', 'text_after': '', 'answer': 'moon'},
            {'id': second.pk, 'text': second.text, 'text_before': '', 'text_after': '', 'answer': second.answer, 'DELETE': 'on'},
            {'id': third.pk, 'text': third.text, 'text_before': '', 'text_after': '.com', 'answer': third.answer},
        ]
        self.client.post(self.url, {'duration_minutes': 6, **formset_data('questions', rows, initial=3)})
        remaining = list(self.exercise.questions.all())
        self.assertEqual([(q.text, q.answer, q.order) for q in remaining],
                         [('Changed label', 'moon', 0), ('Label 2', 'answer2 / alt2', 1)])

    def test_a_plain_line_can_be_put_above_a_gap(self):
        rows = gap_rows(3)
        rows[2]['intro'] = LECTURE_NOTE
        self.save(rows=rows, audio=wav_upload())
        self.assertEqual([q.intro for q in self.exercise.questions.all()], ['', '', LECTURE_NOTE])

        student = Client()
        student.force_login(self.alice)
        play = student.get(reverse('courses:exercise_play', args=['listening', 2, 1]))
        self.assertContains(play, f'<p class="gap-note">{LECTURE_NOTE}</p>', count=1)
        self.assertEqual(re.findall(r'class="gap-number">(\d+)<', play.content.decode()), ['9', '10', '11'])

        data = rendered_form_data(self.client.get(self.url))
        self.assertEqual(data['questions-2-intro'], LECTURE_NOTE)

    def test_a_plain_line_needs_a_gap_to_sit_above(self):
        rows = [{'intro': 'Just a line', 'text': '', 'text_before': '', 'text_after': '', 'answer': ''}]
        response = self.save(rows=rows, audio=wav_upload())
        self.assertEqual(response.status_code, 200)
        self.assertEqual(self.exercise.questions.count(), 0)

    def test_round_trip_posts_back_unchanged(self):
        self.save(rows=gap_rows(4), audio=wav_upload())
        data = rendered_form_data(self.client.get(self.url))
        self.assertEqual(data['questions-INITIAL_FORMS'], '4')
        self.assertEqual(data['title'], 'Video game review')
        self.assertRedirects(self.client.post(self.url, data), self.url)
        self.assertEqual(self.exercise.questions.count(), 4)
        self.assertEqual(self.exercise.questions.first().answer, 'answer0 / alt0')

    def test_admin_builds_it_and_a_student_fills_the_gaps(self):
        self.save(rows=gap_rows(3), audio=wav_upload())
        student = Client()
        student.force_login(self.alice)
        args = ['listening', 2, 1]
        play = student.get(reverse('courses:exercise_play', args=args))
        self.assertEqual(re.findall(r'class="gap-number">(\d+)<', play.content.decode()), ['9', '10', '11'])
        self.assertContains(play, 'Video game review')
        questions = list(self.exercise.questions.all())
        answers = {f'q{questions[0].pk}': 'ALT0', f'q{questions[1].pk}': ' answer1 ', f'q{questions[2].pk}': 'nope'}
        result = student.post(reverse('courses:exercise_submit', args=args), answers)
        self.assertContains(result, '<span>2</span> / 3')


class LectureNotesEditorTests(TempMediaMixin, PanelTestCase):
    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()
        cls.listening = Course.objects.create(title='Listening', category=Category.LISTENING, short_description='x')
        cls.part = Part.objects.create(
            course=cls.listening, number=6, name='Lecture notes', icon='🧑‍🏫', kind='gap_fill',
            first_question_number=30, questions_count=6,
            instructions='You will hear a part of a lecture. Write **ONE WORD and / or A NUMBER**.',
        )

    def setUp(self):
        self.client.force_login(self.admin)
        self.exercise = Exercise.objects.create(part=self.part, number=1)
        self.url = reverse('panel:exercise_edit', args=[self.exercise.pk])

    def rows(self):
        return [
            {'intro': LECTURE_NOTE if index == 2 else '', 'text': '', 'text_before': before, 'text_after': after,
             'answer': answer}
            for index, (before, after, answer) in enumerate(LECTURE_LINES)
        ]

    def save(self, **extra):
        data = {'duration_minutes': 8, 'title': 'Labyrinths', **formset_data('questions', self.rows()), **extra}
        return self.client.post(self.url, data)

    def test_editor_has_a_title_and_six_rows_numbered_30_to_35(self):
        response = self.client.get(self.url)
        self.assertEqual(len(response.context['questions'].forms), 6)
        self.assertContains(response, 'name="title"')
        self.assertContains(response, 'name="questions-5-answer"')
        self.assertNotContains(response, 'name="questions-6-answer"')
        self.assertContains(response, 'counter-reset: qrow 29;')
        self.assertContains(response, '30-savoldan boshlanadi')
        self.assertContains(response, 'You will hear a part of a lecture.')  # the part text is the fallback hint

    def test_save_the_lecture_with_its_plain_line(self):
        self.assertRedirects(self.save(audio=wav_upload()), self.url)
        self.exercise.refresh_from_db()
        self.assertEqual(self.exercise.title, 'Labyrinths')
        self.assertEqual(self.exercise.duration_minutes, 8)
        questions = list(self.exercise.questions.all())
        self.assertEqual(len(questions), 6)
        self.assertEqual(questions[2].intro, LECTURE_NOTE)
        self.assertEqual(questions[2].answer, 'meditation / worship')
        self.assertTrue(self.exercise.is_ready)

    def test_admin_builds_it_and_a_student_fills_the_lecture_notes(self):
        self.save(audio=wav_upload())
        student = Client()
        student.force_login(self.alice)
        args = ['listening', 6, 1]
        play = student.get(reverse('courses:exercise_play', args=args))
        html = play.content.decode()
        self.assertEqual(re.findall(r'class="gap-number">(\d+)<', html), [str(n) for n in range(30, 36)])
        self.assertContains(play, '<h3 class="gap-title">Labyrinths</h3>')
        self.assertContains(play, '>08:00<')
        self.assertContains(play, f'<p class="gap-note">{LECTURE_NOTE}</p>')

        questions = list(self.exercise.questions.all())
        answers = {f'q{q.pk}': value for q, value in zip(questions, ('PUZZLE', 'fear', 'worship', 'Rocks', '', ' tree '))}
        result = student.post(reverse('courses:exercise_submit', args=args), answers)
        self.assertContains(result, '<span>4</span> / 6')


class MatchingEditorTests(TempMediaMixin, PanelTestCase):
    OPTIONS = '\n'.join(MATCHING_OPTIONS)

    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()
        cls.listening = Course.objects.create(title='Listening', category=Category.LISTENING, short_description='x')
        cls.part = Part.objects.create(
            course=cls.listening, number=3, name='Speakers', icon='🗣️', kind='matching', first_question_number=15,
        )

    def setUp(self):
        self.client.force_login(self.admin)
        self.exercise = Exercise.objects.create(part=self.part, number=1)
        self.url = reverse('panel:exercise_edit', args=[self.exercise.pk])

    def save(self, rows=None, options=None, **extra):
        data = {
            'duration_minutes': 5, 'instructions': 'Match each speaker.',
            'options': self.OPTIONS if options is None else options,
            **formset_data('questions', rows if rows is not None else match_rows()),
            **extra,
        }
        return self.client.post(self.url, data)

    def test_editor_shows_options_and_four_speaker_rows_numbered_from_fifteen(self):
        response = self.client.get(self.url)
        self.assertEqual(len(response.context['questions'].forms), 4)
        self.assertContains(response, 'name="options"')
        self.assertContains(response, 'name="instructions"')
        self.assertContains(response, 'name="title"')  # optional: the heading of the Reading "Headings" Part
        self.assertContains(response, 'name="questions-0-label"')
        self.assertContains(response, 'name="questions-0-text"')
        self.assertContains(response, 'name="questions-3-correct"')
        self.assertNotContains(response, 'name="questions-0-answer"')
        self.assertContains(response, 'counter-reset: qrow 14;')
        self.assertContains(response, '15-savoldan boshlanadi')

    def test_save_options_and_correct_letters(self):
        response = self.save(audio=wav_upload())
        self.assertRedirects(response, self.url)
        self.exercise.refresh_from_db()
        self.assertEqual(self.exercise.option_list[3], ('d', 'Watching too much television.'))
        self.assertEqual([q.correct for q in self.exercise.questions.all()], list('daec'))
        self.assertEqual([q.text for q in self.exercise.questions.all()], [f'Speaker {i}' for i in range(1, 5)])
        self.assertTrue(self.exercise.is_ready)

    def test_a_letter_beyond_the_option_list_is_refused(self):
        response = self.save(rows=match_rows('dj'), options='One\nTwo\nThree', audio=wav_upload())
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'variantlar ro&#x27;yxatidan tashqarida')
        self.assertEqual(self.exercise.questions.count(), 0)
        self.exercise.refresh_from_db()
        self.assertFalse(self.exercise.audio)

    def test_questions_need_at_least_two_options(self):
        for options in ('', 'Only one'):
            response = self.save(options=options)
            self.assertContains(response, 'kamida 2 ta variant')
        self.assertEqual(self.exercise.questions.count(), 0)

    def test_more_than_ten_options_are_refused(self):
        response = self.save(options='\n'.join(f'Option {i}' for i in range(11)))
        self.assertContains(response, '10 tadan oshmasligi kerak')

    def test_each_row_needs_a_text_and_a_letter(self):
        for row in ({'text': '', 'correct': 'a'}, {'text': 'Speaker 1', 'correct': ''}):
            response = self.save(rows=[row])
            self.assertEqual(response.status_code, 200)
        self.assertEqual(self.exercise.questions.count(), 0)

    def test_saving_only_the_audio_without_questions_needs_no_options(self):
        response = self.save(rows=[], options='', audio=wav_upload())
        self.assertRedirects(response, self.url)
        self.exercise.refresh_from_db()
        self.assertTrue(self.exercise.audio)
        self.assertFalse(self.exercise.is_ready)

    def test_round_trip_posts_back_unchanged(self):
        self.save(audio=wav_upload())
        data = rendered_form_data(self.client.get(self.url))
        self.assertEqual(data['questions-INITIAL_FORMS'], '4')
        self.assertEqual(data['questions-0-correct'], 'd')
        self.assertRedirects(self.client.post(self.url, data), self.url)
        self.assertEqual([q.correct for q in self.exercise.questions.all()], list('daec'))
        self.exercise.refresh_from_db()
        self.assertEqual(len(self.exercise.option_list), 6)

    def test_part_page_marks_a_matching_exercise_without_options_as_empty(self):
        self.save(rows=match_rows('ab'), options='A\nB', audio=wav_upload())
        part_url = reverse('panel:part_edit', args=[self.part.pk])
        self.assertContains(self.client.get(part_url), 'Tayyor', count=2)
        Exercise.objects.filter(pk=self.exercise.pk).update(options='')
        self.assertContains(self.client.get(part_url), "Bo'sh")

    def test_admin_builds_it_and_a_student_matches_the_speakers(self):
        self.save(audio=wav_upload())
        student = Client()
        student.force_login(self.alice)
        args = ['listening', 3, 1]
        play = student.get(reverse('courses:exercise_play', args=args))
        self.assertContains(play, 'class="match-select"', count=4)
        self.assertContains(play, '<strong>15.</strong> Speaker 1')
        questions = list(self.exercise.questions.all())
        answers = {f'q{q.pk}': letter for q, letter in zip(questions, 'daeb')}
        result = student.post(reverse('courses:exercise_submit', args=args), answers)
        self.assertContains(result, '<span>3</span> / 4')


class MapEditorTests(TempMediaMixin, PanelTestCase):
    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()
        cls.listening = Course.objects.create(title='Listening', category=Category.LISTENING, short_description='x')
        cls.part = Part.objects.create(
            course=cls.listening, number=4, name='Map labelling', icon='🗺️', kind='map', first_question_number=19,
        )

    def setUp(self):
        self.client.force_login(self.admin)
        self.exercise = Exercise.objects.create(part=self.part, number=1)
        self.url = reverse('panel:exercise_edit', args=[self.exercise.pk])

    def save(self, rows=None, letters=9, **extra):
        data = {
            'duration_minutes': 5, 'instructions': 'Label the map.', 'letters_count': letters,
            **formset_data('questions', rows if rows is not None else map_rows()),
            **extra,
        }
        return self.client.post(self.url, data)

    def test_editor_has_the_map_upload_letters_and_five_place_rows_numbered_from_19(self):
        response = self.client.get(self.url)
        self.assertEqual(len(response.context['questions'].forms), 5)
        self.assertEqual(response.context['form']['letters_count'].value(), 9)
        for name in ('image', 'letters_count', 'instructions', 'questions-0-text', 'questions-4-correct'):
            self.assertContains(response, f'name="{name}"')
        for name in ('options', 'title', 'remove_image', 'questions-0-option_a'):
            self.assertNotContains(response, f'name="{name}"')
        self.assertContains(response, 'counter-reset: qrow 18;')
        self.assertContains(response, '19-savoldan boshlanadi')
        self.assertContains(response, 'Masalan: Gift shop')
        self.assertContains(response, 'Rasm hali yuklanmagan.')
        self.assertNotContains(response, 'class="admin-map"')

    def test_save_the_picture_audio_letters_and_answers(self):
        response = self.save(audio=wav_upload(), image=png_upload())
        self.assertRedirects(response, self.url)
        self.exercise.refresh_from_db()
        self.assertTrue(self.exercise.image.name.startswith('practice/images/'))
        self.assertEqual(self.exercise.letters_count, 9)
        self.assertEqual(
            [(q.text, q.correct) for q in self.exercise.questions.all()], list(zip(MAP_PLACES, 'caheb')))
        self.assertTrue(self.exercise.is_ready)

        page = self.client.get(self.url)
        self.assertContains(page, 'class="admin-map"')
        self.assertContains(page, reverse('courses:exercise_image', args=[self.exercise.pk]))
        self.assertContains(page, 'name="remove_image"')

    def test_exercise_without_a_picture_is_not_ready(self):
        self.save(audio=wav_upload())
        self.exercise.refresh_from_db()
        self.assertEqual(self.exercise.questions.count(), 5)
        self.assertFalse(self.exercise.is_ready)
        self.assertContains(self.client.get(reverse('panel:part_edit', args=[self.part.pk])), "Bo'sh")

    def test_only_pictures_are_accepted(self):
        uploads = [
            SimpleUploadedFile('notes.txt', b'hello', content_type='text/plain'),
            SimpleUploadedFile('fake.png', b'not really a picture', content_type='image/png'),
        ]
        for upload in uploads:
            self.assertEqual(self.save(image=upload).status_code, 200, upload.name)
        response = self.save(image=SimpleUploadedFile('map.bmp', make_png(), content_type='image/bmp'))
        self.assertContains(response, 'Faqat rasm yuklash mumkin')
        self.exercise.refresh_from_db()
        self.assertFalse(self.exercise.image)
        self.assertEqual(self.exercise.questions.count(), 0)

    def test_a_letter_beyond_the_letter_count_is_refused(self):
        response = self.save(rows=map_rows('ch'), letters=4, audio=wav_upload(), image=png_upload())
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'xaritadagi harflardan tashqarida (4 ta harf bor)')
        self.assertEqual(self.exercise.questions.count(), 0)
        self.exercise.refresh_from_db()
        self.assertFalse(self.exercise.audio)
        self.assertFalse(self.exercise.image)

    def test_questions_need_at_least_two_letters(self):
        for letters in (0, 1, ''):
            self.assertContains(self.save(letters=letters), 'kamida 2 ta harf')
        self.assertEqual(self.exercise.questions.count(), 0)

    def test_more_than_ten_letters_are_refused(self):
        self.assertEqual(self.save(letters=11).status_code, 200)
        self.assertEqual(self.exercise.questions.count(), 0)

    def test_each_row_needs_a_place_and_a_letter(self):
        for row in ({'text': '', 'correct': 'a'}, {'text': 'Museum', 'correct': ''}):
            self.assertEqual(self.save(rows=[row]).status_code, 200)
        self.assertEqual(self.exercise.questions.count(), 0)

    def test_replacing_the_picture_deletes_the_old_file(self):
        self.save(audio=wav_upload(), image=png_upload('first.png'))
        self.exercise.refresh_from_db()
        old_path = self.exercise.image.path
        self.assertTrue(os.path.exists(old_path))

        self.save(rows=[], image=png_upload('second.png'))
        self.exercise.refresh_from_db()
        self.assertFalse(os.path.exists(old_path))
        self.assertTrue(os.path.exists(self.exercise.image.path))
        self.assertEqual(self.exercise.questions.count(), 5)

    def test_remove_picture_checkbox_deletes_only_the_picture(self):
        self.save(audio=wav_upload(), image=png_upload())
        self.exercise.refresh_from_db()
        path = self.exercise.image.path

        self.save(rows=[], remove_image='on')
        self.exercise.refresh_from_db()
        self.assertFalse(self.exercise.image)
        self.assertFalse(os.path.exists(path))
        self.assertTrue(self.exercise.audio)
        self.assertFalse(self.exercise.is_ready)

    def test_round_trip_posts_back_unchanged(self):
        self.save(audio=wav_upload(), image=png_upload())
        data = rendered_form_data(self.client.get(self.url))
        self.assertEqual(data['questions-INITIAL_FORMS'], '5')
        self.assertEqual(data['letters_count'], '9')
        self.assertEqual(data['questions-0-correct'], 'c')
        self.assertRedirects(self.client.post(self.url, data), self.url)
        self.exercise.refresh_from_db()
        self.assertTrue(self.exercise.image)
        self.assertEqual([q.correct for q in self.exercise.questions.all()], list('caheb'))

    def test_admin_builds_it_and_a_student_labels_the_map(self):
        self.save(audio=wav_upload(), image=png_upload())
        student = Client()
        student.force_login(self.alice)
        args = ['listening', 4, 1]
        play = student.get(reverse('courses:exercise_play', args=args))
        self.assertContains(play, 'class="chip-row"', count=5)
        self.assertContains(play, '<strong>19.</strong> Gift shop')
        image = student.get(reverse('courses:exercise_image', args=[self.exercise.pk]))
        self.assertEqual(image.status_code, 200)
        image.close()

        questions = list(self.exercise.questions.all())
        answers = {f'q{q.pk}': letter for q, letter in zip(questions, 'cahea')}
        result = student.post(reverse('courses:exercise_submit', args=args), answers)
        self.assertContains(result, '<span>4</span> / 5')

    def test_part_page_explains_what_makes_a_map_exercise_ready(self):
        self.save(audio=wav_upload(), image=png_upload())
        page = self.client.get(reverse('panel:part_edit', args=[self.part.pk]))
        self.assertContains(page, 'Tayyor', count=2)
        self.assertContains(page, 'xarita rasmi')


class ExtractIntroEditorTests(TempMediaMixin, PanelTestCase):
    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()
        cls.listening = Course.objects.create(title='Listening', category=Category.LISTENING, short_description='x')
        cls.part = Part.objects.create(
            course=cls.listening, number=5, name='Extracts', icon='🎙️', first_question_number=24, questions_count=6,
        )

    def setUp(self):
        self.client.force_login(self.admin)
        self.exercise = Exercise.objects.create(part=self.part, number=1)
        self.url = reverse('panel:exercise_edit', args=[self.exercise.pk])

    def rows(self, count=6):
        intros = {0: '**Extract One** · You hear Fiona.', 2: '**Extract Two** · You hear two friends.'}
        return [
            {'intro': intros.get(i, ''), 'text': f'Question {i}', 'option_a': 'a', 'option_b': 'b', 'option_c': 'c',
             'correct': 'abc'[i % 3]}
            for i in range(count)
        ]

    def save(self, rows, **extra):
        data = {'duration_minutes': 8, **formset_data('questions', rows), **extra}
        return self.client.post(self.url, data)

    def test_editor_offers_exactly_the_six_questions_24_to_29_with_an_optional_card_title_each(self):
        response = self.client.get(self.url)
        self.assertEqual(len(response.context['questions'].forms), 6)
        for index in range(6):
            self.assertContains(response, f'name="questions-{index}-intro"')
        self.assertNotContains(response, 'name="questions-6-intro"')  # no rows for 30 and 31: they belong to Part 6
        self.assertContains(response, 'counter-reset: qrow 23;')
        self.assertContains(response, '24-savoldan boshlanadi')
        self.assertContains(response, 'Oldingi sarlavha')

    def test_without_a_question_count_the_choice_editor_falls_back_to_eight_rows(self):
        Part.objects.filter(pk=self.part.pk).update(questions_count=0)
        self.assertEqual(len(self.client.get(self.url).context['questions'].forms), 8)

    def test_intro_cards_are_saved_and_blank_ones_stay_blank(self):
        self.assertRedirects(self.save(self.rows(), audio=wav_upload()), self.url)
        intros = [q.intro for q in self.exercise.questions.all()]
        self.assertEqual(intros, ['**Extract One** · You hear Fiona.', '', '**Extract Two** · You hear two friends.', '', '', ''])

    def test_a_row_with_only_an_intro_is_incomplete(self):
        response = self.save([{'intro': 'Extract One', 'text': '', 'option_a': '', 'option_b': '', 'option_c': '', 'correct': ''}])
        self.assertEqual(response.status_code, 200)
        self.assertEqual(self.exercise.questions.count(), 0)

    def test_round_trip_keeps_the_intro_cards(self):
        self.save(self.rows(), audio=wav_upload())
        data = rendered_form_data(self.client.get(self.url))
        self.assertEqual(data['questions-0-intro'], '**Extract One** · You hear Fiona.')
        self.assertRedirects(self.client.post(self.url, data), self.url)
        self.assertEqual(self.exercise.questions.first().intro, '**Extract One** · You hear Fiona.')
        self.assertEqual(self.exercise.questions.count(), 6)

    def test_a_student_sees_the_cards_the_admin_wrote(self):
        self.save(self.rows(), audio=wav_upload())
        student = Client()
        student.force_login(self.alice)
        play = student.get(reverse('courses:exercise_play', args=['listening', 5, 1]))
        self.assertContains(play, 'class="q-intro"', count=2)
        self.assertContains(play, '<strong>Extract One</strong> · You hear Fiona.')
        self.assertContains(play, '<strong class="q-number">24.</strong> Question 0')


class ChoiceEditorKeepsItsShapeTests(TempMediaMixin, PanelTestCase):
    def test_choice_editor_has_instructions_but_no_title_or_options(self):
        listening = Course.objects.create(title='Listening', category=Category.LISTENING, short_description='x')
        part = Part.objects.create(course=listening, number=1, name='Short replies')
        exercise = Exercise.objects.create(part=part, number=1)
        self.client.force_login(self.admin)
        response = self.client.get(reverse('panel:exercise_edit', args=[exercise.pk]))
        self.assertContains(response, 'name="instructions"')
        self.assertNotContains(response, 'name="title"')
        self.assertNotContains(response, 'name="options"')
        self.assertNotContains(response, 'name="image"')
        self.assertNotContains(response, 'name="letters_count"')
        self.assertContains(response, 'name="questions-0-option_a"')
        self.assertEqual(len(response.context['questions'].forms), 8)
        self.assertContains(response, 'counter-reset: qrow 0;')
