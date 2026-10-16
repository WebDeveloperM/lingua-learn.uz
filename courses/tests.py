from django.core.management import CommandError
from django.db import IntegrityError, transaction
from django.test import Client, TestCase

from accounts.models import Role, User

from .models import Category, Course, Exercise, ExerciseResult, Part
from .support import EXPECTED_PARTS, TOTAL_EXERCISES, seed


class SeedListeningPartsTests(TestCase):
    def setUp(self):
        self.course = Course.objects.create(title='Listening', category=Category.LISTENING, short_description='x')

    def test_part_one_gets_its_instructions_but_edits_are_kept(self):
        seed()
        part = Part.objects.get(number=1)
        self.assertIn('each sentence **twice**', part.instructions)
        self.assertEqual(Part.objects.exclude(number__in=(1, 2, 4, 5, 6)).exclude(instructions='').count(), 0)

        part.instructions = 'Edited in the panel'
        part.save()
        seed()
        part.refresh_from_db()
        self.assertEqual(part.instructions, 'Edited in the panel')

    def test_creates_the_six_parts_with_their_exercises(self):
        seed()
        parts = list(self.course.parts.all())
        self.assertEqual([(p.number, p.name, p.exercises.count()) for p in parts], EXPECTED_PARTS)
        self.assertEqual({p.key_words_count for p in parts}, {50})
        self.assertEqual([p.icon for p in parts], ['💬', '✍️', '🗣️', '🗺️', '🎙️', '🧑‍🏫'])

    def test_rerun_is_idempotent(self):
        seed()
        seed()
        self.assertEqual(Part.objects.count(), 6)
        self.assertEqual(Exercise.objects.count(), TOTAL_EXERCISES)

    def test_rerun_keeps_edited_parts_and_restores_missing_exercises(self):
        seed()
        part = Part.objects.get(number=1)
        part.name = 'Renamed in admin'
        part.key_words_count = 12
        part.save()
        Exercise.objects.filter(part=part, number=3).delete()

        seed()
        part.refresh_from_db()
        self.assertEqual((part.name, part.key_words_count), ('Renamed in admin', 12))
        self.assertEqual(part.exercises.count(), 10)

    def test_course_can_be_chosen_by_slug(self):
        other = Course.objects.create(title='Other Listening', category=Category.LISTENING, short_description='y')
        seed(course=other.slug)
        self.assertEqual(other.parts.count(), 6)
        self.assertEqual(self.course.parts.count(), 0)

    def test_fails_without_a_listening_course(self):
        Course.objects.all().delete()
        with self.assertRaises(CommandError):
            seed()


class PartConstraintTests(TestCase):
    def test_part_and_exercise_numbers_are_unique(self):
        course = Course.objects.create(title='Listening', category=Category.LISTENING, short_description='x')
        part = Part.objects.create(course=course, number=1, name='One')
        Exercise.objects.create(part=part, number=1)
        with self.assertRaises(IntegrityError), transaction.atomic():
            Part.objects.create(course=course, number=1, name='Duplicate')
        with self.assertRaises(IntegrityError), transaction.atomic():
            Exercise.objects.create(part=part, number=1)

    def test_deleting_a_course_removes_its_parts_and_exercises(self):
        course = Course.objects.create(title='Listening', category=Category.LISTENING, short_description='x')
        seed()
        course.delete()
        self.assertEqual((Part.objects.count(), Exercise.objects.count()), (0, 0))


class PracticePageTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.course = Course.objects.create(title='Listening', category=Category.LISTENING, short_description='x')
        seed()
        cls.url = cls.course.get_absolute_url()
        cls.student = User.objects.create_user(email='s@t.uz', password='StrongPass123!')
        cls.other = User.objects.create_user(email='o@t.uz', password='StrongPass123!')
        cls.admin = User.objects.create_user(email='a@t.uz', password='StrongPass123!', role=Role.ADMIN)

    def test_course_with_parts_uses_the_practice_template(self):
        response = self.client.get(self.url)
        self.assertTemplateUsed(response, 'courses/practice.html')
        self.assertTemplateNotUsed(response, 'courses/course_detail.html')
        self.assertContains(response, '🎧 Listening practice')
        self.assertContains(response, 'Put on your headphones, listen and answer.')

    def test_every_part_is_listed_with_its_counts(self):
        response = self.client.get(self.url)
        for number, name, count in EXPECTED_PARTS:
            self.assertContains(response, f'Part {number} · {name}')
            self.assertContains(response, f'{count} ready')
        self.assertContains(response, 'Key vocabulary · 50 words', count=6)
        self.assertContains(response, 'class="ex-tile', count=TOTAL_EXERCISES)

    def test_tiles_have_no_free_or_paid_labels(self):
        self.client.force_login(self.student)
        for client_response in (self.client.get(self.url), Client().get(self.url)):
            self.assertNotContains(client_response, 'Free')
            self.assertNotContains(client_response, 'Paid')
            self.assertNotContains(client_response, '🔒')
            self.assertNotContains(client_response, 'is-locked')
            self.assertNotContains(client_response, 'ex-status')

    def test_a_result_shows_only_on_that_students_tile(self):
        exercise = Exercise.objects.get(part__number=1, number=1)
        ExerciseResult.objects.create(user=self.student, exercise=exercise, score=0, total=8)

        self.client.force_login(self.student)
        response = self.client.get(self.url)
        self.assertContains(response, '⭐ 0/8', count=1)
        self.assertContains(response, 'class="ex-tile"', count=TOTAL_EXERCISES)

        self.client.force_login(self.other)
        self.assertNotContains(self.client.get(self.url), '⭐')

    def test_results_show_on_any_exercise(self):
        ExerciseResult.objects.create(
            user=self.student, exercise=Exercise.objects.get(part__number=2, number=5), score=7, total=9)
        ExerciseResult.objects.create(
            user=self.student, exercise=Exercise.objects.get(part__number=6, number=10), score=10, total=10)
        self.client.force_login(self.student)
        response = self.client.get(self.url)
        self.assertContains(response, '⭐ 7/9', count=1)
        self.assertContains(response, '⭐ 10/10', count=1)

    def test_course_without_parts_keeps_the_regular_page(self):
        grammar = Course.objects.create(title='Grammar', category=Category.GRAMMAR, short_description='y')
        response = self.client.get(grammar.get_absolute_url())
        self.assertTemplateUsed(response, 'courses/course_detail.html')
        self.assertTemplateNotUsed(response, 'courses/practice.html')

    def test_other_skills_get_a_generic_intro(self):
        reading = Course.objects.create(title='Reading', category=Category.READING, short_description='z')
        part = Part.objects.create(course=reading, number=1, name='Skimming', icon='📖')
        Exercise.objects.create(part=part, number=1)
        response = self.client.get(reading.get_absolute_url())
        self.assertContains(response, '📖 Reading practice')
        self.assertContains(response, 'Choose a part, then pick an exercise.')
        self.assertNotContains(response, 'headphones')

    def test_draft_practice_page_is_for_admins_only(self):
        self.course.is_published = False
        self.course.save()
        self.assertEqual(self.client.get(self.url).status_code, 404)
        self.client.force_login(self.student)
        self.assertEqual(self.client.get(self.url).status_code, 404)
        self.client.force_login(self.admin)
        response = self.client.get(self.url)
        self.assertContains(response, 'hali nashr etilmagan')
        self.assertTemplateUsed(response, 'courses/practice.html')
