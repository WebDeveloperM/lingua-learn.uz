import re

from django.db import IntegrityError, connection, transaction
from django.test import SimpleTestCase, TestCase
from django.test.utils import CaptureQueriesContext
from django.urls import reverse

from accounts.models import Role, User
from courses.models import Category, Course

from .models import (
    SpeakingPart, SpeakingPractice, SpeakingQuestion, SpeakingSet, minutes_label, part_details, part_info,
    questions_label, set_name,
)
from .support import SET_ONE, SET_THREE, SET_TWO, make_set, make_speaking_course

PASSWORD = 'StrongPass123!'
P11, P12, P2, P3 = SpeakingPart.PART_11, SpeakingPart.PART_12, SpeakingPart.PART_2, SpeakingPart.PART_3


class HelperTests(SimpleTestCase):
    def test_sets_are_named_with_words(self):
        self.assertEqual([set_name(n) for n in (1, 2, 3, 10, 20)],
                         ['Set One', 'Set Two', 'Set Three', 'Set Ten', 'Set Twenty'])
        self.assertEqual(set_name(21), 'Set 21')

    def test_question_counts(self):
        self.assertEqual([questions_label(n) for n in (0, 1, 3)], ['0 questions', '1 question', '3 questions'])

    def test_the_timing_line_of_each_part(self):
        self.assertEqual(part_details(P11), '3 questions · 5 sec to think · 30 sec to talk')
        self.assertEqual(part_details(P12), '3 questions · first: 10 sec + 45 sec · then: 5 sec + 30 sec')
        self.assertEqual(part_details(P2), '1 min to prepare · 2 min to talk')
        self.assertEqual(part_details(P3), '1 min to prepare · 2 min to talk')

    def test_the_timing_line_follows_the_number_of_questions(self):
        self.assertEqual(part_details(P11, 4), '4 questions · 5 sec to think · 30 sec to talk')
        self.assertEqual(part_details(P11, 1), '1 question · 5 sec to think · 30 sec to talk')
        self.assertEqual(part_details(P2, 5), '1 min to prepare · 2 min to talk')

    def test_how_long_a_set_takes(self):
        self.assertEqual(minutes_label(P11, 3), '2 minutes')  # 3 × (5 + 30) s = 105 s
        self.assertEqual(minutes_label(P11, 1), '1 minute')
        self.assertEqual(minutes_label(P11, 2), '1 minute')
        self.assertEqual(minutes_label(P11, 4), '2 minutes')
        self.assertEqual(minutes_label(P11, 6), '4 minutes')  # 210 s = 3.5 minutes rounds up
        self.assertEqual(minutes_label(P12, 3), '2 minutes')  # (10 + 45) + 2 × (5 + 30) = 125 s
        self.assertEqual(minutes_label(P2, 3), '3 minutes')  # 1 min + 2 min
        self.assertEqual(minutes_label(P3, 1), '3 minutes')

    def test_a_part_is_described_for_the_templates(self):
        info = part_info(P12)
        self.assertEqual(info, {
            'number': 2, 'label': 'Part 1.2', 'icon': '🖼️', 'tagline': 'Talk about two pictures',
            'details': '3 questions · first: 10 sec + 45 sec · then: 5 sec + 30 sec',
        })
        self.assertEqual([part_info(part)['icon'] for part in SpeakingPart], ['💬', '🖼️', '🧭', '⚖️'])
        self.assertEqual([part.label for part in SpeakingPart], ['Part 1.1', 'Part 1.2', 'Part 2', 'Part 3'])


class ModelTests(TestCase):
    def setUp(self):
        self.course = make_speaking_course()
        self.set = make_set(self.course)

    def test_title_string_and_url(self):
        self.assertEqual(self.set.title, 'Set One')
        self.assertEqual(str(self.set), 'Speaking · Part 1.1 · Set One')
        self.assertEqual(
            self.set.get_absolute_url(),
            reverse('speaking:ready', kwargs={'slug': self.course.slug, 'part': 1, 'set_pk': self.set.pk}))
        self.assertEqual(str(self.set.questions.first()), SET_ONE[0])

    def test_questions_keep_their_order(self):
        self.assertEqual([question.text for question in self.set.questions.all()], SET_ONE)

    def test_a_set_number_is_used_once_per_part(self):
        with self.assertRaises(IntegrityError), transaction.atomic():
            SpeakingSet.objects.create(course=self.course, part=P11, number=1)
        SpeakingSet.objects.create(course=self.course, part=P12, number=1)  # another part may reuse it
        SpeakingSet.objects.create(course=make_speaking_course(), part=P11, number=1)  # and so may another course

    def test_a_question_place_is_used_once_per_set(self):
        with self.assertRaises(IntegrityError), transaction.atomic():
            SpeakingQuestion.objects.create(set=self.set, order=0, text='again')

    def test_a_student_practises_a_set_once(self):
        student = User.objects.create_user(email='s@t.uz', password=PASSWORD)
        SpeakingPractice.objects.create(user=student, set=self.set)
        with self.assertRaises(IntegrityError), transaction.atomic():
            SpeakingPractice.objects.create(user=student, set=self.set)
        self.assertIn('s@t.uz', str(SpeakingPractice.objects.get()))

    def test_deleting_a_set_removes_its_questions_and_practices(self):
        student = User.objects.create_user(email='s@t.uz', password=PASSWORD)
        SpeakingPractice.objects.create(user=student, set=self.set)
        self.set.delete()
        self.assertEqual((SpeakingQuestion.objects.count(), SpeakingPractice.objects.count()), (0, 0))

    def test_deleting_a_course_removes_its_sets(self):
        self.course.delete()
        self.assertEqual(SpeakingSet.objects.count(), 0)


class HubTests(TestCase):
    def setUp(self):
        self.course = make_speaking_course()
        self.url = self.course.get_absolute_url()
        self.student = User.objects.create_user(email='s@t.uz', password=PASSWORD)

    def test_the_speaking_course_opens_the_speaking_practice_page(self):
        response = self.client.get(self.url)
        self.assertTemplateUsed(response, 'speaking/hub.html')
        self.assertContains(response, '🎤 Speaking practice')

    def test_the_scoring_card_lists_the_four_criteria(self):
        response = self.client.get(self.url)
        self.assertContains(response, 'How you are scored <small>· Baholash tartibi</small>')
        html = response.content.decode()
        boxes = re.findall(r'<li><strong>(\d+)%</strong><span><span aria-hidden="true">(\S+)</span> (\w+)</span></li>', html)
        self.assertEqual(boxes, [('25', '🧩', 'Grammar'), ('25', '🧠', 'Vocabulary'), ('25', '🌊', 'Fluency'),
                                 ('25', '🗣️', 'Pronunciation')])

    def test_the_four_parts_come_in_exam_order_with_their_descriptions(self):
        html = self.client.get(self.url).content.decode()
        self.assertEqual(re.findall(r'class="sp-part-name">([^<]+)<', html), ['Part 1.1', 'Part 1.2', 'Part 2', 'Part 3'])
        self.assertEqual(re.findall(r'class="sp-part-tagline">([^<]+)<', html), [
            'Questions about you', 'Talk about two pictures', 'Three questions, one long answer',
            'Discuss both sides of a topic'])
        self.assertEqual(re.findall(r'class="sp-part-details">([^<]+)<', html), [
            '3 questions · 5 sec to think · 30 sec to talk',
            '3 questions · first: 10 sec + 45 sec · then: 5 sec + 30 sec',
            '1 min to prepare · 2 min to talk', '1 min to prepare · 2 min to talk'])
        self.assertEqual(re.findall(r'class="sp-part-icon" aria-hidden="true">([^<]+)<', html), ['💬', '🖼️', '🧭', '⚖️'])

    def test_each_part_links_to_its_page(self):
        response = self.client.get(self.url)
        for part in SpeakingPart:
            self.assertContains(response, f'href="{reverse("speaking:part", args=[self.course.slug, part.value])}"')

    def test_there_is_no_free_or_paid_label(self):
        response = self.client.get(self.url)
        for word in ('Free', 'FREE', 'Paid', 'Full access', '🔒'):
            self.assertNotContains(response, word)

    def test_parts_without_sets_say_so(self):
        response = self.client.get(self.url)
        self.assertContains(response, 'No sets yet', count=4)
        self.assertNotContains(response, 'practised')

    def test_practised_sets_are_counted_for_the_student(self):
        sets = [make_set(self.course, questions=questions) for questions in (SET_ONE, SET_TWO, SET_THREE)]
        SpeakingPractice.objects.create(user=self.student, set=sets[1])
        self.client.force_login(self.student)
        html = self.client.get(self.url).content.decode()
        self.assertEqual(re.findall(r'class="sp-badge[^"]*">([^<]+)<', html),
                         ['✓ 1 / 3 practised', 'No sets yet', 'No sets yet', 'No sets yet'])
        self.assertIn('sp-badge is-done', html)

    def test_a_part_nobody_practised_shows_zero(self):
        make_set(self.course)
        make_set(self.course, questions=SET_TWO)
        self.client.force_login(self.student)
        response = self.client.get(self.url)
        self.assertContains(response, '0 / 2 practised')
        self.assertNotContains(response, '✓ 0')
        self.assertNotContains(response, 'sp-badge is-done')

    def test_practice_is_counted_per_student_and_not_for_visitors(self):
        speaking_set = make_set(self.course)
        other = User.objects.create_user(email='o@t.uz', password=PASSWORD)
        SpeakingPractice.objects.create(user=other, set=speaking_set)
        self.client.force_login(self.student)
        self.assertContains(self.client.get(self.url), '0 / 1 practised')
        self.client.logout()
        self.assertContains(self.client.get(self.url), '0 / 1 practised')
        self.client.force_login(other)
        self.assertContains(self.client.get(self.url), '✓ 1 / 1 practised')

    def test_only_sets_with_questions_count(self):
        make_set(self.course)
        make_set(self.course, questions=[])
        self.assertContains(self.client.get(self.url), '0 / 1 practised')

    def test_the_other_parts_count_their_own_sets(self):
        make_set(self.course, part=P12)
        make_set(self.course, part=P2)
        make_set(self.course, part=P2, questions=SET_TWO)
        html = self.client.get(self.url).content.decode()
        self.assertEqual(re.findall(r'class="sp-badge[^"]*">([^<]+)<', html),
                         ['No sets yet', '0 / 1 practised', '0 / 2 practised', 'No sets yet'])

    def test_the_timing_line_shows_how_many_questions_the_sets_have(self):
        make_set(self.course, questions=SET_ONE + ['One more?'])
        html = self.client.get(self.url).content.decode()
        self.assertIn('4 questions · 5 sec to think · 30 sec to talk', html)
        self.assertIn('3 questions · first: 10 sec + 45 sec', html)  # no Part 1.2 set yet: the usual three

    def test_a_draft_course_is_for_admins_only(self):
        Course.objects.filter(pk=self.course.pk).update(is_published=False)
        self.assertEqual(self.client.get(self.url).status_code, 404)
        admin = User.objects.create_user(email='a@t.uz', password=PASSWORD, role=Role.ADMIN)
        self.client.force_login(admin)
        self.assertContains(self.client.get(self.url), 'hali nashr etilmagan')

    def test_other_courses_keep_their_own_pages(self):
        grammar = Course.objects.create(title='Plain', category=Category.GRAMMAR, short_description='x')
        self.assertTemplateUsed(self.client.get(grammar.get_absolute_url()), 'courses/course_detail.html')

    def test_the_number_of_queries_does_not_grow_with_the_number_of_sets(self):
        make_set(self.course)
        self.client.force_login(self.student)
        with CaptureQueriesContext(connection) as few:
            self.client.get(self.url)
        for part in SpeakingPart:
            for _ in range(3):
                make_set(self.course, part=part)
        with CaptureQueriesContext(connection) as many:
            self.client.get(self.url)
        self.assertEqual(len(few), len(many))


class PartPageTests(TestCase):
    def setUp(self):
        self.course = make_speaking_course()
        self.sets = [make_set(self.course, questions=questions) for questions in (SET_ONE, SET_TWO, SET_THREE)]
        self.url = reverse('speaking:part', args=[self.course.slug, 1])
        self.student = User.objects.create_user(email='s@t.uz', password=PASSWORD)

    def test_the_page_shows_the_part_and_its_practice_questions(self):
        response = self.client.get(self.url)
        self.assertTemplateUsed(response, 'speaking/part.html')
        self.assertContains(response, '💬</span> Part 1.1 <small class="wt-title-meta">· Questions about you</small>')
        self.assertContains(response, '3 questions · 5 sec to think · 30 sec to talk')
        self.assertContains(response, '❓</span> Practice questions')
        self.assertContains(response, f'href="{self.course.get_absolute_url()}">← Speaking practice</a>')

    def test_every_set_lists_its_questions_in_order(self):
        html = self.client.get(self.url).content.decode()
        self.assertEqual(re.findall(r'class="sp-set-name">([^<]+)<', html), ['Set One', 'Set Two', 'Set Three'])
        shown = re.findall(r'<li>\s*<span>([^<]+)</span>', html)
        self.assertEqual(shown, SET_ONE + [q.replace("'", '&#x27;') for q in SET_TWO] + SET_THREE)

    def test_a_question_can_be_listened_to(self):
        response = self.client.get(self.url)
        self.assertContains(response, 'class="sp-listen"', count=9)
        self.assertContains(response, 'data-speak="What do you do on the weekends?"')
        self.assertContains(response, 'aria-label="Listen to question 1"')
        self.assertContains(response, 'aria-label="Listen to question 3"', count=3)
        self.assertContains(response, '/static/js/speaking.js')

    def test_each_set_has_a_practise_button_leading_to_its_ready_page(self):
        response = self.client.get(self.url)
        self.assertContains(response, 'Practise this</a>', count=3)
        for speaking_set in self.sets:
            self.assertContains(response, f'href="{reverse("speaking:ready", args=[self.course.slug, 1, speaking_set.pk])}"')

    def test_a_practised_set_says_so(self):
        SpeakingPractice.objects.create(user=self.student, set=self.sets[0])
        self.client.force_login(self.student)
        response = self.client.get(self.url)
        self.assertContains(response, 'Practise this again ✓</a>', count=1)
        self.assertContains(response, 'Practise this</a>', count=2)
        other = User.objects.create_user(email='o@t.uz', password=PASSWORD)
        self.client.force_login(other)
        self.assertNotContains(self.client.get(self.url), 'again')

    def test_the_page_shows_only_its_own_part_and_ready_sets(self):
        make_set(self.course, part=P12, questions=['Describe the first picture.'])
        make_set(self.course, questions=[])
        response = self.client.get(self.url)
        self.assertNotContains(response, 'Describe the first picture.')
        self.assertContains(response, 'class="sp-set"', count=3)
        other = self.client.get(reverse('speaking:part', args=[self.course.slug, 2]))
        self.assertContains(other, 'Describe the first picture.')
        self.assertContains(other, '🖼️</span> Part 1.2')

    def test_a_part_without_sets_says_so(self):
        response = self.client.get(reverse('speaking:part', args=[self.course.slug, 3]))
        self.assertContains(response, 'No practice questions yet.')
        self.assertNotContains(response, 'class="sp-set"')

    def test_each_part_has_its_own_description(self):
        response = self.client.get(reverse('speaking:part', args=[self.course.slug, 4]))
        self.assertContains(response, '⚖️</span> Part 3')
        self.assertContains(response, '· Discuss both sides of a topic')
        self.assertContains(response, '1 min to prepare · 2 min to talk')

    def test_questions_are_escaped(self):
        SpeakingQuestion.objects.filter(set=self.sets[0], order=0).update(text='Is <b>this</b> "fine"?')
        response = self.client.get(self.url)
        self.assertNotContains(response, '<b>this</b>')
        self.assertContains(response, 'Is &lt;b&gt;this&lt;/b&gt; &quot;fine&quot;?')
        self.assertContains(response, 'data-speak="Is &lt;b&gt;this&lt;/b&gt; &quot;fine&quot;?"')

    def test_unknown_parts_and_other_kinds_of_course_are_404(self):
        for number in (0, 5, 99):
            self.assertEqual(self.client.get(reverse('speaking:part', args=[self.course.slug, number])).status_code, 404)
        reading = Course.objects.create(title='Reading', category=Category.READING, short_description='x')
        self.assertEqual(self.client.get(reverse('speaking:part', args=[reading.slug, 1])).status_code, 404)

    def test_a_draft_course_is_for_admins_only(self):
        Course.objects.filter(pk=self.course.pk).update(is_published=False)
        self.assertEqual(self.client.get(self.url).status_code, 404)
        admin = User.objects.create_user(email='a@t.uz', password=PASSWORD, role=Role.ADMIN)
        self.client.force_login(admin)
        self.assertEqual(self.client.get(self.url).status_code, 200)

    def test_the_number_of_queries_does_not_grow_with_the_number_of_sets(self):
        with CaptureQueriesContext(connection) as few:
            self.client.get(self.url)
        for _ in range(5):
            make_set(self.course)
        with CaptureQueriesContext(connection) as many:
            self.client.get(self.url)
        self.assertEqual(len(few), len(many))


class ReadyPageTests(TestCase):
    def setUp(self):
        self.course = make_speaking_course()
        self.set_one = make_set(self.course)
        self.set_two = make_set(self.course, questions=SET_TWO)
        self.student = User.objects.create_user(email='s@t.uz', password=PASSWORD)
        self.url = reverse('speaking:ready', args=[self.course.slug, 1, self.set_two.pk])

    def test_login_is_required(self):
        self.assertRedirects(
            self.client.get(self.url), f"{reverse('accounts:login')}?next={self.url}", fetch_redirect_response=False)

    def test_the_page_tells_how_the_practice_goes(self):
        self.client.force_login(self.student)
        response = self.client.get(self.url)
        self.assertTemplateUsed(response, 'speaking/ready.html')
        self.assertContains(response, '💬</span> Part 1.1 · Set Two</h1>')
        self.assertContains(response, 'Ready? <span aria-hidden="true">🎙️</span>')
        self.assertContains(response, '3 questions · about <strong>2 minutes</strong>.')
        self.assertContains(response, '<li>Each question is read aloud, then you get time to prepare.</li>')
        self.assertContains(
            response, "<li>After the beep, speak until the timer ends. Press <strong>I'm done</strong> to finish early.</li>")
        self.assertContains(
            response, '🪙</span> You get <strong>3 coins</strong> only if you speak until the timer ends for every question.')
        self.assertContains(response, '<li>Find a quiet place and speak out loud, like in the real exam.</li>')
        self.assertContains(response, f'href="{reverse("speaking:part", args=[self.course.slug, 1])}">← Part 1.1</a>')

    def test_reading_the_questions_aloud_is_a_checked_option(self):
        self.client.force_login(self.student)
        response = self.client.get(self.url)
        self.assertContains(response, '<input type="checkbox" id="read-aloud" checked> <span>Read the questions aloud</span>')
        self.assertContains(response, '/static/js/speaking.js')

    def test_the_session_itself_is_not_there_yet(self):
        self.client.force_login(self.student)
        response = self.client.get(self.url)
        self.assertRegex(response.content.decode(), r'<button type="button" class="btn btn-primary btn-lg start-btn" id="start-btn" disabled>')
        self.assertContains(response, 'The speaking session itself is coming soon.')

    def test_the_numbers_follow_the_set(self):
        one = make_set(self.course, questions=['Only one question?'])
        self.client.force_login(self.student)
        response = self.client.get(reverse('speaking:ready', args=[self.course.slug, 1, one.pk]))
        self.assertContains(response, 'Set Three</h1>')
        self.assertContains(response, '1 question · about <strong>1 minute</strong>.')
        self.assertContains(response, 'You get <strong>1 coin</strong> only if')

    def test_the_time_depends_on_the_part(self):
        long_set = make_set(self.course, part=P2, questions=['Describe a trip.', 'Why?', 'When?'])
        self.client.force_login(self.student)
        response = self.client.get(reverse('speaking:ready', args=[self.course.slug, 3, long_set.pk]))
        self.assertContains(response, '🧭</span> Part 2 · Set One</h1>')
        self.assertContains(response, '3 questions · about <strong>3 minutes</strong>.')

    def test_unknown_foreign_and_empty_sets_are_404(self):
        self.client.force_login(self.student)
        self.assertEqual(self.client.get(reverse('speaking:ready', args=[self.course.slug, 1, 9999])).status_code, 404)
        # the set belongs to Part 1.1, not to Part 1.2
        self.assertEqual(
            self.client.get(reverse('speaking:ready', args=[self.course.slug, 2, self.set_two.pk])).status_code, 404)
        other_course = make_speaking_course()
        foreign = make_set(other_course)
        self.assertEqual(
            self.client.get(reverse('speaking:ready', args=[self.course.slug, 1, foreign.pk])).status_code, 404)
        empty = make_set(self.course, questions=[])
        self.assertEqual(
            self.client.get(reverse('speaking:ready', args=[self.course.slug, 1, empty.pk])).status_code, 404)
        self.assertEqual(
            self.client.get(reverse('speaking:ready', args=[self.course.slug, 7, self.set_two.pk])).status_code, 404)

    def test_other_kinds_of_course_and_drafts(self):
        self.client.force_login(self.student)
        reading = Course.objects.create(title='Reading', category=Category.READING, short_description='x')
        self.assertEqual(self.client.get(reverse('speaking:ready', args=[reading.slug, 1, self.set_two.pk])).status_code, 404)
        Course.objects.filter(pk=self.course.pk).update(is_published=False)
        self.assertEqual(self.client.get(self.url).status_code, 404)
        admin = User.objects.create_user(email='a@t.uz', password=PASSWORD, role=Role.ADMIN)
        self.client.force_login(admin)
        self.assertEqual(self.client.get(self.url).status_code, 200)
