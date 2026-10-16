import re
from datetime import date

from django.db import IntegrityError, connection, transaction
from django.test import SimpleTestCase, TestCase
from django.test.utils import CaptureQueriesContext
from django.urls import reverse

from accounts.models import Role, User
from courses.models import Category, Course

from .guides import INFORMAL_EMAIL
from .models import Slot, WritingAnswer, WritingSubmission, WritingTask, WritingTest, count_words
from .support import (
    DISCUSSION_TASK, TRAVEL_CONTEXT, TRAVEL_EMAIL, TRAVEL_INSTRUCTION, make_test, make_writing_course,
)

PASSWORD = 'StrongPass123!'


class CountWordsTests(SimpleTestCase):
    def test_words_are_runs_of_non_space_characters(self):
        self.assertEqual(count_words(''), 0)
        self.assertEqual(count_words(None), 0)
        self.assertEqual(count_words('   \n\t '), 0)
        self.assertEqual(count_words('Begin start'), 2)
        self.assertEqual(count_words("I don't like e-mail   at\nall.\tReally"), 7)
        self.assertEqual(count_words('Salom dunyo — bu test'), 5)


class PartTwoStatementTests(SimpleTestCase):
    def statement(self, text, slot=Slot.PART_2):
        return WritingTask(slot=slot, instruction=text).statement

    def test_a_closing_words_sentence_is_left_out_of_the_bold_text(self):
        cases = {
            'Post your response. Write 180–200 words.': 'Post your response.',
            'Post your response.\nWrite 180–200 words.': 'Post your response.',
            'Post your response.\n\n  Write 180–200 words.  ': 'Post your response.',
            'Post your response. Write 180-200 words': 'Post your response.',
            'Post your response. Write 180 — 200 words.': 'Post your response.',
            'Post your response. Write about 200 words.': 'Post your response.',
            'Post your response. WRITE 180–200 WORDS.': 'Post your response.',
            'Write 180–200 words.': '',
        }
        for text, expected in cases.items():
            self.assertEqual(self.statement(text), expected, text)

    def test_other_text_is_left_alone(self):
        for text in (
            'Post your response.', '  Post your response.  ', 'Please write 180–200 words about your trip. Thanks',
            'Write 180–200 words about your trip.', 'Do you agree? Write at least 180 words.',
        ):
            self.assertEqual(self.statement(text), text.strip(), text)

    def test_the_letter_tasks_keep_their_whole_text(self):
        text = 'Write a short email. Write about 50 words.'
        self.assertEqual(self.statement(text, Slot.TASK_11), text)
        self.assertEqual(self.statement(text, Slot.TASK_12), text)


class ModelTests(TestCase):
    def setUp(self):
        self.course = make_writing_course()
        self.test = make_test(self.course)

    def test_string_subtitle_and_url(self):
        self.assertEqual(str(self.test), 'Travel Club · 18 Oct 2025 · 1-smena')
        self.assertEqual(self.test.subtitle, 'Part 2: Is a vegetarian diet better for health?')
        self.assertEqual(
            self.test.get_absolute_url(), reverse('writing:intro', kwargs={'slug': self.course.slug, 'pk': self.test.pk}))
        self.test.topic = ''
        self.assertEqual(self.test.subtitle, '')

    def test_tasks_come_in_exam_order_with_their_rules(self):
        tasks = list(self.test.tasks.all())
        self.assertEqual([t.label for t in tasks], ['Task 1.1', 'Task 1.2', 'Part 2'])
        self.assertEqual([t.description for t in tasks], [
            'informal e-mail to a friend, about 50 words', 'formal e-mail, 120–150 words',
            'online discussion (essay), 180–200 words',
        ])
        self.assertEqual([t.rules['goal'] for t in tasks], [50, 150, 200])

    def test_only_task_one_one_has_phrases_so_far(self):
        tasks = list(self.test.tasks.all())
        self.assertEqual(tasks[0].phrases, INFORMAL_EMAIL)
        self.assertEqual([t.phrases for t in tasks[1:]], [None, None])
        self.assertEqual([len(group['phrases']) for group in INFORMAL_EMAIL], [3] * 6)
        self.assertEqual([group['title'] for group in INFORMAL_EMAIL],
                         ['Topic', 'About', 'Feelings', 'Problem', 'Suggestions', 'Ending'])

    def test_part_two_is_a_single_task_text_and_the_others_answer_a_letter(self):
        task_11, task_12, part_2 = self.test.tasks.all()
        self.assertEqual((task_11.has_letter, task_12.has_letter, part_2.has_letter), (True, True, False))
        self.assertEqual(part_2.statement, DISCUSSION_TASK)
        self.assertEqual(part_2.words_line, 'Write 180–200 words.')
        self.assertEqual((task_11.words_line, task_12.words_line), ('', ''))
        self.assertEqual(task_11.statement, TRAVEL_INSTRUCTION)  # "Write about 50 words." stays in the text

    def test_only_the_letter_tasks_have_a_sample_answer(self):
        WritingTask.objects.filter(test=self.test).update(sample_answer='A sample')
        self.assertEqual([task.sample for task in self.test.tasks.all()], ['A sample', 'A sample', ''])

    def test_a_test_is_ready_when_a_task_has_its_instruction(self):
        empty = WritingTest.objects.create(course=self.course, title='Empty', date=date(2025, 11, 1))
        self.assertTrue(self.test.is_ready)
        self.assertFalse(empty.is_ready)
        WritingTask.objects.create(test=empty, slot=Slot.TASK_11, instruction='')
        self.assertFalse(WritingTest.objects.get(pk=empty.pk).is_ready)

    def test_each_slot_exists_once_per_test(self):
        with self.assertRaises(IntegrityError), transaction.atomic():
            WritingTask.objects.create(test=self.test, slot=Slot.TASK_11, instruction='again')

    def test_tests_are_ordered_by_date_then_shift(self):
        later = make_test(self.course, title='Later', when=date(2025, 11, 15), shift=1)
        second_shift = make_test(self.course, title='Second', when=date(2025, 10, 18), shift=2)
        earlier = make_test(self.course, title='Earlier', when=date(2025, 10, 1), shift=2)
        titles = [test.title for test in WritingTest.objects.all()]
        self.assertEqual(titles, [earlier.title, 'Travel Club', second_shift.title, later.title])

    def test_submission_helpers(self):
        user = User.objects.create_user(email='s@t.uz', password=PASSWORD)
        submission = WritingSubmission.objects.create(test=self.test, user=user, seconds_used=754)
        WritingAnswer.objects.create(submission=submission, slot=1, text='a b c', word_count=3)
        WritingAnswer.objects.create(submission=submission, slot=2, text='d e', word_count=2)
        self.assertEqual((submission.total_words, submission.time_used), (5, '12:34'))
        self.assertEqual(WritingSubmission(seconds_used=None).time_used, '')
        self.assertEqual(WritingAnswer(slot=3).label, 'Part 2')

    def test_deleting_a_test_removes_its_tasks_and_submissions(self):
        user = User.objects.create_user(email='s@t.uz', password=PASSWORD)
        submission = WritingSubmission.objects.create(test=self.test, user=user)
        WritingAnswer.objects.create(submission=submission, slot=1, text='x', word_count=1)
        self.test.delete()
        self.assertEqual((WritingTask.objects.count(), WritingSubmission.objects.count(), WritingAnswer.objects.count()), (0, 0, 0))


class HubTests(TestCase):
    def setUp(self):
        self.course = make_writing_course()
        self.first = make_test(self.course)
        self.second = make_test(
            self.course, title='Sports Club', shift=2, topic='Plastic pollution: problems and solutions')
        self.november = make_test(self.course, title='School Trip', when=date(2025, 11, 15), topic='')
        self.student = User.objects.create_user(email='s@t.uz', password=PASSWORD)
        self.url = self.course.get_absolute_url()

    def test_the_writing_course_opens_the_writing_practice_page(self):
        response = self.client.get(self.url)
        self.assertTemplateUsed(response, 'writing/hub.html')
        self.assertContains(response, '✍️ Writing practice')
        self.assertContains(
            response,
            'Real exam tasks. Each test has Task 1.1, Task 1.2 and Part 2, with 60 minutes in total. '
            'Your teacher checks your answers and writes feedback.')
        self.assertContains(response, 'Tests · 3')

    def test_the_guide_card_links_to_the_guide(self):
        response = self.client.get(self.url)
        self.assertContains(response, 'How to write Task 1.1, 1.2 and Part 2')
        self.assertContains(response, 'Step-by-step structure and useful phrases for every task, with Uzbek translation.')
        self.assertContains(response, f'href="{reverse("writing:guide", args=[self.course.slug])}">Open the guide</a>')

    def test_tests_are_grouped_by_month_in_date_order(self):
        html = self.client.get(self.url).content.decode()
        self.assertEqual(re.findall(r'class="wt-month">([^<]+)<', html), ['October 2025', 'November 2025'])
        self.assertEqual(re.findall(r'class="wt-name">([^<]+)<', html), ['Travel Club', 'Sports Club', 'School Trip'])

    def test_a_row_shows_the_date_the_shift_the_title_and_the_part_two_topic(self):
        response = self.client.get(self.url)
        self.assertContains(response, '<strong>18 Oct</strong><small>1-smena</small>')
        self.assertContains(response, '<strong>18 Oct</strong><small>2-smena</small>')
        self.assertContains(response, 'Part 2: Is a vegetarian diet better for health?')
        self.assertContains(response, 'Part 2: Plastic pollution: problems and solutions')
        self.assertContains(response, f'href="{reverse("writing:intro", args=[self.course.slug, self.first.pk])}"')
        self.assertContains(response, 'class="wt-sub"', count=2)  # the November test has no topic

    def test_there_is_no_free_or_paid_label(self):
        response = self.client.get(self.url)
        self.assertNotContains(response, 'Paid')
        self.assertNotContains(response, 'Free')

    def test_the_number_of_queries_does_not_grow_with_the_number_of_tests(self):
        self.client.force_login(self.student)
        with CaptureQueriesContext(connection) as few:
            self.client.get(self.url)
        for index in range(6):
            make_test(self.course, title=f'Extra {index}', when=date(2025, 12, index + 1))
        with CaptureQueriesContext(connection) as many:
            self.client.get(self.url)
        self.assertEqual(len(few), len(many))

    def test_an_empty_course_still_shows_the_page(self):
        WritingTest.objects.all().delete()
        response = self.client.get(self.url)
        self.assertTemplateUsed(response, 'writing/hub.html')
        self.assertContains(response, 'Tests · 0')
        self.assertContains(response, 'No tests yet.')

    def test_sent_tests_are_marked_for_that_student_only(self):
        WritingSubmission.objects.create(test=self.first, user=self.student)
        self.client.force_login(self.student)
        response = self.client.get(self.url)
        self.assertContains(response, '✓ Sent', count=1)
        other = User.objects.create_user(email='o@t.uz', password=PASSWORD)
        self.client.force_login(other)
        self.assertNotContains(self.client.get(self.url), '✓ Sent')
        self.client.logout()
        self.assertNotContains(self.client.get(self.url), '✓ Sent')

    def test_a_draft_course_is_for_admins_only(self):
        Course.objects.filter(pk=self.course.pk).update(is_published=False)
        self.assertEqual(self.client.get(self.url).status_code, 404)
        admin = User.objects.create_user(email='a@t.uz', password=PASSWORD, role=Role.ADMIN)
        self.client.force_login(admin)
        response = self.client.get(self.url)
        self.assertContains(response, 'hali nashr etilmagan')

    def test_other_courses_keep_their_own_pages(self):
        reading = Course.objects.create(title='Plain', category=Category.READING, short_description='x')
        self.assertTemplateUsed(self.client.get(reading.get_absolute_url()), 'courses/course_detail.html')


class IntroTests(TestCase):
    def setUp(self):
        self.course = make_writing_course()
        self.test = make_test(self.course)
        self.student = User.objects.create_user(email='s@t.uz', password=PASSWORD)
        self.url = reverse('writing:intro', args=[self.course.slug, self.test.pk])

    def test_login_is_required(self):
        self.assertRedirects(
            self.client.get(self.url), f"{reverse('accounts:login')}?next={self.url}", fetch_redirect_response=False)

    def test_intro_lists_the_tasks_and_the_time(self):
        self.client.force_login(self.student)
        response = self.client.get(self.url)
        self.assertContains(response, 'Travel Club <small class="wt-title-meta">· 18 Oct 2025 · 1-smena</small>')
        self.assertContains(response, 'Ready? ⏱')
        self.assertContains(response, '3 tasks · <strong>60 minutes</strong> in total.')
        self.assertContains(response, '<li>Task 1.1: informal e-mail to a friend, about 50 words</li>')
        self.assertContains(response, '<li>Task 1.2: formal e-mail, 120–150 words</li>')
        self.assertContains(response, '<li>Part 2: online discussion (essay), 180–200 words</li>')
        self.assertContains(
            response,
            'The timer starts when you press Start. You can move between tasks. If you leave the test before sending, '
            'your writing is deleted. When time is up, your answers are sent automatically.')
        self.assertContains(
            response, f'href="{reverse("writing:write", args=[self.course.slug, self.test.pk])}">Start writing 🚀</a>')
        self.assertContains(response, f'href="{self.course.get_absolute_url()}">← Writing practice</a>')

    def test_only_the_entered_tasks_are_listed_and_counted(self):
        WritingTask.objects.filter(test=self.test, slot__in=(2, 3)).delete()
        self.client.force_login(self.student)
        response = self.client.get(self.url)
        self.assertContains(response, '1 task · <strong>60 minutes</strong> in total.')
        self.assertNotContains(response, 'Task 1.2:')

    def test_the_time_comes_from_the_test(self):
        WritingTest.objects.filter(pk=self.test.pk).update(duration_minutes=45)
        self.client.force_login(self.student)
        self.assertContains(self.client.get(self.url), '<strong>45 minutes</strong>')

    def test_a_test_without_tasks_cannot_be_started(self):
        WritingTask.objects.all().delete()
        self.client.force_login(self.student)
        response = self.client.get(self.url)
        self.assertContains(response, 'not ready yet')
        self.assertContains(response, 'disabled')
        self.assertNotContains(response, 'Add them in the panel')
        admin = User.objects.create_user(email='a@t.uz', password=PASSWORD, role=Role.ADMIN)
        self.client.force_login(admin)
        self.assertContains(self.client.get(self.url), reverse('panel:writing_test_edit', args=[self.test.pk]))

    def test_unknown_or_foreign_tests_are_404(self):
        self.client.force_login(self.student)
        self.assertEqual(self.client.get(reverse('writing:intro', args=[self.course.slug, 9999])).status_code, 404)
        other = make_writing_course()
        other_test = make_test(other)
        self.assertEqual(
            self.client.get(reverse('writing:intro', args=[self.course.slug, other_test.pk])).status_code, 404)
        reading = Course.objects.create(title='Reading', category=Category.READING, short_description='x')
        self.assertEqual(self.client.get(reverse('writing:intro', args=[reading.slug, self.test.pk])).status_code, 404)


class WritePageTests(TestCase):
    def setUp(self):
        self.course = make_writing_course()
        self.test = make_test(self.course)
        self.student = User.objects.create_user(email='s@t.uz', password=PASSWORD)
        self.url = reverse('writing:write', args=[self.course.slug, self.test.pk])
        self.client.force_login(self.student)

    def test_login_is_required_and_a_test_without_tasks_goes_back_to_the_intro(self):
        self.client.logout()
        self.assertRedirects(
            self.client.get(self.url), f"{reverse('accounts:login')}?next={self.url}", fetch_redirect_response=False)
        self.client.force_login(self.student)
        WritingTask.objects.all().delete()
        self.assertRedirects(self.client.get(self.url), reverse('writing:intro', args=[self.course.slug, self.test.pk]))

    def test_top_bar_has_the_tabs_with_their_word_counts_and_the_timer(self):
        response = self.client.get(self.url)
        self.assertContains(response, '← All tests</a>')
        for label in ('Task 1.1', 'Task 1.2', 'Part 2'):
            self.assertContains(response, f'{label} · <span data-tab-count=')
        self.assertContains(response, 'role="tab"', count=3)
        self.assertContains(response, 'data-duration="3600"')
        self.assertContains(response, '>60:00<')
        self.assertContains(response, '⏸ Pause')

    def test_task_one_one_shows_the_context_the_email_the_instruction_and_an_empty_box(self):
        response = self.client.get(self.url)
        self.assertContains(response, 'Task 1.1 <small>· Travel Club · 18 Oct 2025 · 1-smena</small>')
        self.assertContains(response, f'<p class="wt-context">{TRAVEL_CONTEXT}</p>')
        self.assertContains(response, 'Dear Member,<br>We are planning our trips for next year')
        self.assertContains(response, 'Best wishes,<br>Travel Club Organizer</p>')
        self.assertContains(response, 'Write a short email to your friend (who is also a member of the travel club).')
        self.assertContains(response, 'Write about 50 words.</p>')
        self.assertContains(response, 'name="answer_1"')
        self.assertContains(response, 'placeholder="Start writing here..."')

    def test_the_word_counter_starts_at_zero_with_each_tasks_target(self):
        response = self.client.get(self.url)
        self.assertContains(response, '<strong class="wt-words">0 words</strong>', count=3)
        self.assertContains(response, 'target about 50 words')
        self.assertContains(response, 'target 120–150 words')
        self.assertContains(response, 'target 180–200 words')
        self.assertRegex(response.content.decode(), r'data-goal="50"\s+data-low="45"\s+data-high="60"')
        self.assertRegex(response.content.decode(), r'data-goal="150"\s+data-low="120"\s+data-high="150"')
        self.assertRegex(response.content.decode(), r'data-goal="200"\s+data-low="180"\s+data-high="200"')

    def test_only_the_first_task_is_open_and_navigation_starts_at_the_beginning(self):
        html = self.client.get(self.url).content.decode()
        panels = re.findall(r'<section class="wt-card" data-panel="(\d)"( hidden)?>', html)
        self.assertEqual(panels, [('1', ''), ('2', ' hidden'), ('3', ' hidden')])
        self.assertIn('id="wt-prev" disabled>← Previous</button>', html)
        self.assertIn('id="wt-next">Next →</button>', html)

    def test_task_one_one_has_the_static_structure_and_phrases_for_tapping(self):
        response = self.client.get(self.url)
        html = response.content.decode()
        self.assertContains(
            response, '<strong>Structure and useful phrases</strong> · tap a phrase to add it</summary>', count=1)
        self.assertEqual(re.findall(r'<h4 class="phrase-group"><span>(\d)\. (\w+)</span>', html), [
            ('1', 'Topic'), ('2', 'About'), ('3', 'Feelings'), ('4', 'Problem'), ('5', 'Suggestions'), ('6', 'Ending')])
        self.assertContains(response, 'nima mazmunida kimdan xabar olganingiz')
        self.assertContains(response, 'class="phrase" data-phrase=', count=18)
        self.assertContains(response, 'data-phrase="I just received an e-mail about ____ from ____."')
        self.assertContains(response, 'Men xozirgina ____ dan ____ xaqida e-mail oldim.')
        self.assertContains(response, '<span class="phrase-en">I am not really happy about this change as it may cause some inconvenience.</span>')

    def panels(self):
        html = self.client.get(self.url).content.decode()
        panels = re.split(r'<section class="wt-card" data-panel="', html)[1:]
        self.assertEqual(len(panels), 3)
        return panels

    def test_the_phrases_are_not_offered_for_the_other_tasks(self):
        panels = self.panels()
        self.assertIn('useful phrases', panels[0])
        self.assertNotIn('useful phrases', panels[1])
        self.assertNotIn('useful phrases', panels[2])

    def test_a_sample_answer_shows_only_when_the_admin_gave_one(self):
        WritingTask.objects.filter(test=self.test, slot=2).update(
            sample_answer='Dear Sir,\n\nI am writing to complain.')
        panels = self.panels()
        self.assertNotIn('Sample answer', panels[0])
        self.assertIn('<strong>Sample answer</strong> · try your own first</summary>', panels[1])
        self.assertIn('Dear Sir,<br><br>I am writing to complain.', panels[1])

    def test_part_two_is_one_bold_task_text_with_its_words_line_below(self):
        part_two = self.panels()[2]
        self.assertIn('Part 2 <small>· Travel Club · 18 Oct 2025 · 1-smena</small>', part_two)
        self.assertIn(f'<p class="wt-instruction">{DISCUSSION_TASK}</p>', part_two)
        self.assertIn('<p class="wt-words-line">Write 180–200 words.</p>', part_two)
        self.assertLess(part_two.index('wt-instruction'), part_two.index('wt-words-line'))
        self.assertLess(part_two.index('wt-words-line'), part_two.index('<textarea'))
        for absent in ('wt-prompt', 'wt-context', 'Sample answer', 'useful phrases'):
            self.assertNotIn(absent, part_two)

    def test_part_two_never_shows_a_letter_or_a_sample_even_when_an_old_one_is_stored(self):
        WritingTask.objects.filter(test=self.test, slot=3).update(
            context='Old context', prompt='Old letter', sample_answer='Old sample')
        part_two = self.panels()[2]
        for old in ('Old context', 'Old letter', 'Old sample', 'wt-prompt', 'Sample answer'):
            self.assertNotIn(old, part_two)
        self.assertIn(DISCUSSION_TASK, part_two)

    def test_a_words_sentence_the_admin_typed_at_the_end_is_not_repeated(self):
        for ending in (' Write 180–200 words.', '\nWrite 180-200 words.', ' Write about 200 words', ' write 180–200 WORDS.'):
            WritingTask.objects.filter(test=self.test, slot=3).update(instruction=DISCUSSION_TASK + ending)
            part_two = self.panels()[2]
            self.assertIn(f'<p class="wt-instruction">{DISCUSSION_TASK}</p>', part_two, ending)
            self.assertEqual(part_two.lower().count('write '), 1, ending)
            self.assertIn('<p class="wt-words-line">Write 180–200 words.</p>', part_two, ending)

    def test_part_two_with_only_the_words_sentence_shows_just_the_line(self):
        WritingTask.objects.filter(test=self.test, slot=3).update(instruction='Write 180–200 words.')
        part_two = self.panels()[2]
        self.assertNotIn('class="wt-instruction"', part_two)
        self.assertIn('<p class="wt-words-line">Write 180–200 words.</p>', part_two)

    def test_the_task_text_of_part_two_is_escaped_and_keeps_its_line_breaks(self):
        WritingTask.objects.filter(test=self.test, slot=3).update(instruction='Is <b>this</b> fine?\nExplain.')
        part_two = self.panels()[2]
        self.assertIn('Is &lt;b&gt;this&lt;/b&gt; fine?<br>Explain.', part_two)
        self.assertNotIn('<b>this</b>', part_two)

    def test_tasks_one_one_and_one_two_keep_their_words_inside_the_bold_text(self):
        panels = self.panels()
        self.assertIn('Write about 50 words.</p>', panels[0])
        self.assertNotIn('wt-words-line', panels[0])
        self.assertNotIn('wt-words-line', panels[1])

    def test_send_button_and_the_hidden_confirmation_card(self):
        response = self.client.get(self.url)
        self.assertContains(response, 'id="send-btn">Send to my teacher</button>')
        self.assertRegex(response.content.decode(), r'<div class="submit-confirm" id="send-confirm" role="alert" hidden>')
        self.assertContains(response, '>Yes, send</button>')
        self.assertContains(response, '>Keep writing</button>')
        self.assertContains(response, '/static/js/writing.js')
        self.assertContains(response, f'action="{reverse("writing:send", args=[self.course.slug, self.test.pk])}"')

    def test_texts_are_escaped(self):
        WritingTask.objects.filter(test=self.test, slot=1).update(
            context='<b>ctx</b>', prompt='<script>alert(1)</script>\nSecond line', instruction='Do <i>this</i>')
        response = self.client.get(self.url)
        self.assertNotContains(response, '<script>alert(1)</script>')
        self.assertContains(response, '&lt;script&gt;alert(1)&lt;/script&gt;<br>Second line')
        self.assertContains(response, '&lt;b&gt;ctx&lt;/b&gt;')
        self.assertContains(response, 'Do &lt;i&gt;this&lt;/i&gt;')

    def test_a_task_without_a_prompt_has_no_empty_box(self):
        WritingTask.objects.filter(test=self.test, slot=1).update(context='', prompt='')
        html = self.client.get(self.url).content.decode()
        first_panel = re.split(r'<section class="wt-card" data-panel="', html)[1]
        self.assertNotIn('wt-prompt', first_panel)

    def test_a_single_task_has_one_tab_and_no_way_to_move(self):
        WritingTask.objects.filter(test=self.test, slot__in=(2, 3)).delete()
        response = self.client.get(self.url)
        self.assertContains(response, 'role="tab"', count=1)


class SendTests(TestCase):
    def setUp(self):
        self.course = make_writing_course()
        self.test = make_test(self.course)
        self.student = User.objects.create_user(email='s@t.uz', password=PASSWORD, first_name='Sara')
        self.url = reverse('writing:send', args=[self.course.slug, self.test.pk])
        self.client.force_login(self.student)

    def post(self, **data):
        return self.client.post(self.url, data)

    def test_login_and_post_are_required(self):
        self.assertEqual(self.client.get(self.url).status_code, 405)
        self.client.logout()
        self.assertRedirects(
            self.client.post(self.url, {}), f"{reverse('accounts:login')}?next={self.url}", fetch_redirect_response=False)

    def test_what_was_written_is_stored_per_task_with_its_word_count(self):
        response = self.post(
            answer_1='  Dear friend,\nI would like to visit Rome in May.  ', answer_2='', answer_3='My view is simple.',
            time_used='754')
        submission = WritingSubmission.objects.get()
        self.assertRedirects(response, reverse('writing:sent', args=[self.course.slug, submission.pk]))
        self.assertEqual((submission.user, submission.test, submission.seconds_used), (self.student, self.test, 754))
        answers = {a.slot: a for a in submission.answers.all()}
        self.assertEqual(answers[1].text, 'Dear friend,\nI would like to visit Rome in May.')
        self.assertEqual((answers[1].word_count, answers[2].word_count, answers[3].word_count), (10, 0, 4))
        self.assertEqual(answers[2].text, '')

    def test_the_sent_page_shows_a_copy_and_reloading_it_does_not_send_again(self):
        response = self.post(answer_1='One two three', time_used='65', answer_3='Four five')
        page = self.client.get(response['Location'])
        self.assertContains(page, '✅ Sent to your teacher')
        self.assertContains(page, '5 words in total · Time used: 01:05')
        self.assertContains(page, 'Task 1.1 <small>· 3 words</small>')
        self.assertContains(page, 'One two three')
        self.assertContains(page, 'You did not write anything for this task.', count=1)  # Task 1.2
        self.client.get(response['Location'])
        self.assertEqual(WritingSubmission.objects.count(), 1)

    def test_sending_nothing_stores_nothing(self):
        response = self.post(answer_1='   ', answer_2='', answer_3='\n')
        self.assertRedirects(
            response, reverse('writing:intro', args=[self.course.slug, self.test.pk]), fetch_redirect_response=False)
        self.assertEqual(WritingSubmission.objects.count(), 0)
        self.assertContains(self.client.get(response['Location']), 'Nothing was sent: you did not write anything.')

    def test_only_the_tests_own_tasks_are_taken(self):
        WritingTask.objects.filter(test=self.test, slot=3).delete()
        self.post(answer_1='Real', answer_3='Not part of this test', answer_9='Nonsense')
        slots = sorted(WritingSubmission.objects.get().answers.values_list('slot', flat=True))
        self.assertEqual(slots, [1, 2])

    def test_time_used_is_optional_and_limited_to_the_time_of_the_test(self):
        for raw, expected in (('', None), ('abc', None), ('-5', 0), ('99999', 3600), ('120', 120)):
            WritingSubmission.objects.all().delete()
            self.post(answer_1='Words here', time_used=raw)
            self.assertEqual(WritingSubmission.objects.get().seconds_used, expected, raw)

    def test_very_long_texts_are_cut(self):
        self.post(answer_1='word ' * 3000)
        answer = WritingAnswer.objects.get(slot=1)
        self.assertEqual(len(answer.text), 8000 - 1)  # cut at 8000 characters, then the trailing space is dropped
        self.assertEqual(answer.word_count, 1600)

    def test_line_breaks_are_stored_as_one_character(self):
        self.post(answer_1='First line\r\nSecond line\r\n\r\nThird')
        self.assertEqual(WritingAnswer.objects.get(slot=1).text, 'First line\nSecond line\n\nThird')

    def test_sending_twice_keeps_both_and_the_hub_marks_the_test(self):
        self.post(answer_1='First try')
        self.post(answer_1='Second try')
        self.assertEqual(WritingSubmission.objects.count(), 2)
        self.assertContains(self.client.get(self.course.get_absolute_url()), '✓ Sent', count=1)

    def test_a_test_without_tasks_cannot_receive_writing(self):
        WritingTask.objects.all().delete()
        self.assertEqual(self.post(answer_1='x').status_code, 404)

    def test_a_sent_page_belongs_to_its_writer_and_the_admin(self):
        response = self.post(answer_1='Private words')
        url = response['Location']
        self.assertEqual(self.client.get(url).status_code, 200)
        other = User.objects.create_user(email='o@t.uz', password=PASSWORD)
        self.client.force_login(other)
        self.assertEqual(self.client.get(url).status_code, 404)
        admin = User.objects.create_user(email='a@t.uz', password=PASSWORD, role=Role.ADMIN)
        self.client.force_login(admin)
        self.assertEqual(self.client.get(url).status_code, 200)
        self.client.logout()
        self.assertEqual(self.client.get(url).status_code, 302)

    def test_a_draft_course_does_not_take_writing_from_students(self):
        Course.objects.filter(pk=self.course.pk).update(is_published=False)
        self.assertEqual(self.post(answer_1='x').status_code, 404)


class GuideTests(TestCase):
    def setUp(self):
        self.course = make_writing_course()
        self.url = reverse('writing:guide', args=[self.course.slug])

    def test_the_guide_shows_the_phrases_without_buttons(self):
        response = self.client.get(self.url)
        self.assertContains(response, 'How to write Task 1.1, 1.2 and Part 2')
        self.assertContains(response, 'informal e-mail to a friend, about 50 words')
        self.assertContains(response, 'class="phrase"', count=18)
        self.assertNotContains(response, 'data-phrase')
        self.assertContains(response, '6. Ending')
        self.assertContains(response, "Ishonchim komilki, ular bizning fikrlarimizni inobatga olib, ijobiy o&#x27;zgarishlar qilishadi.")
        self.assertContains(response, f'href="{self.course.get_absolute_url()}">← Writing practice</a>')

    def test_it_is_only_for_writing_courses_and_published_ones(self):
        reading = Course.objects.create(title='Reading', category=Category.READING, short_description='x')
        self.assertEqual(self.client.get(reverse('writing:guide', args=[reading.slug])).status_code, 404)
        Course.objects.filter(pk=self.course.pk).update(is_published=False)
        self.assertEqual(self.client.get(self.url).status_code, 404)


class StaticTextsTests(SimpleTestCase):
    def test_the_example_texts_of_the_reference_are_in_the_support_data(self):
        self.assertIn('Travel Club', TRAVEL_CONTEXT)
        self.assertTrue(TRAVEL_EMAIL.startswith('Dear Member,'))
        self.assertTrue(TRAVEL_INSTRUCTION.endswith('Write about 50 words.'))
