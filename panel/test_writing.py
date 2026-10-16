import re
from datetime import date

from django.db import connection
from django.test.utils import CaptureQueriesContext
from django.urls import reverse

from accounts.models import User
from courses.models import Category
from writing.models import WritingAnswer, WritingSubmission, WritingTask, WritingTest
from writing.support import DISCUSSION_TASK, TRAVEL_INSTRUCTION, make_test, make_writing_course

from .support import PanelTestCase, rendered_form_data

SLOTS = (1, 2, 3)
LETTER_FIELDS = ('instruction', 'context', 'prompt', 'sample_answer')
# Tasks 1.1 and 1.2 answer a letter; Part 2 is one task text (no letter, no context, no sample answer)
TASK_FIELDS = {1: LETTER_FIELDS, 2: LETTER_FIELDS, 3: ('instruction',)}
PART_2_ABSENT = ('task3_context', 'task3_prompt', 'task3_sample_answer')


def form_data(**extra):
    """A whole test form as the browser sends it: the test itself and the fields of each task (all empty)."""
    data = {
        'title': 'Travel Club', 'date': '2025-10-18', 'shift': '1', 'duration_minutes': '60',
        'topic': 'Is a vegetarian diet better for health?',
    }
    for slot in SLOTS:
        for name in TASK_FIELDS[slot]:
            data[f'task{slot}_{name}'] = ''
    data.update(extra)
    return data


def make_submission(test, user, texts=('Dear friend, hello', '', 'My view'), seconds=754):
    submission = WritingSubmission.objects.create(test=test, user=user, seconds_used=seconds)
    for slot, text in enumerate(texts, start=1):
        WritingAnswer.objects.create(submission=submission, slot=slot, text=text, word_count=len(text.split()))
    return submission


class WritingPanelTestCase(PanelTestCase):
    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()
        cls.writing = make_writing_course()

    def setUp(self):
        self.client.force_login(self.admin)


class CourseFormWritingSectionTests(WritingPanelTestCase):
    def edit_url(self, course=None):
        return reverse('panel:course_edit', args=[(course or self.writing).pk])

    def test_a_writing_course_lists_its_tests_instead_of_parts(self):
        test = make_test(self.writing)
        make_test(self.writing, title='Sports Club', slots=(1,), when=date(2025, 11, 2), shift=2)
        make_submission(test, self.alice)
        response = self.client.get(self.edit_url())
        self.assertContains(response, 'Writing testlar (2)')
        self.assertNotContains(response, 'Mashqlar (Practice)')
        self.assertNotContains(response, "Part qo'shish")
        self.assertContains(response, f'href="{reverse("panel:writing_test_create", args=[self.writing.pk])}"')
        self.assertContains(response, '18 Oct 2025 · 1-smena · 3 ta topshiriq · 1 ta ish yuborilgan')
        self.assertContains(response, '2 Nov 2025 · 2-smena · 1 ta topshiriq · 0 ta ish yuborilgan')
        self.assertContains(response, f'href="{reverse("panel:writing_test_edit", args=[test.pk])}"')
        self.assertContains(response, f'href="{reverse("panel:writing_submissions", args=[self.writing.pk])}">Yuborilgan ishlar (1) →')

    def test_a_writing_course_without_tests_says_so(self):
        response = self.client.get(self.edit_url())
        self.assertContains(response, 'Writing testlar (0)')
        self.assertContains(response, 'Hali test yo')
        self.assertContains(response, 'Yuborilgan ishlar (0) →')

    def test_other_courses_keep_the_practice_section(self):
        response = self.client.get(self.edit_url(self.course2))
        self.assertContains(response, 'Mashqlar (Practice)')
        self.assertNotContains(response, 'Writing testlar')

    def test_a_new_course_form_does_not_need_either_list(self):
        response = self.client.get(reverse('panel:course_create'))
        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, 'Writing testlar')

    def test_saving_the_course_leaves_its_tests_alone(self):
        test = make_test(self.writing)
        data = rendered_form_data(self.client.get(self.edit_url()))
        response = self.client.post(self.edit_url(), data)
        self.assertRedirects(response, reverse('panel:course_list'))
        self.assertEqual(list(WritingTest.objects.values_list('pk', flat=True)), [test.pk])
        self.assertEqual(WritingTask.objects.filter(test=test).count(), 3)

    def test_changing_the_category_to_writing_shows_the_tests_after_saving(self):
        data = rendered_form_data(self.client.get(self.edit_url(self.course2)))
        data['category'] = Category.WRITING
        self.client.post(self.edit_url(self.course2), data)
        self.assertContains(self.client.get(self.edit_url(self.course2)), 'Writing testlar (0)')


class WritingTestCreateTests(WritingPanelTestCase):
    def setUp(self):
        super().setUp()
        self.url = reverse('panel:writing_test_create', args=[self.writing.pk])

    def test_the_form_has_the_test_and_the_fields_of_all_three_tasks(self):
        response = self.client.get(self.url)
        for name in ('title', 'date', 'shift', 'topic', 'duration_minutes'):
            self.assertContains(response, f'name="{name}"')
        for slot in SLOTS:
            for name in TASK_FIELDS[slot]:
                self.assertContains(response, f'name="task{slot}_{name}"')
        for heading in ('Task 1.1', 'Task 1.2', 'Part 2'):
            self.assertContains(response, f'{heading} <small')
        self.assertContains(response, 'informal e-mail to a friend, about 50 words')
        self.assertContains(response, 'formal e-mail, 120–150 words')
        self.assertContains(response, 'online discussion (essay), 180–200 words')
        self.assertContains(response, 'qolsa, bu topshiriq testda bo', count=3)  # the note under each of the three tasks
        self.assertContains(response, 'Hamma maydon bo', count=2)  # Tasks 1.1 and 1.2 have several fields
        self.assertNotContains(response, "O'quvchi ko'rinishi")  # nothing to show before the test exists
        self.assertNotContains(response, 'Testni o')

    def test_part_two_asks_only_for_the_task_text(self):
        response = self.client.get(self.url)
        for name in PART_2_ABSENT:
            self.assertNotContains(response, f'name="{name}"')
        html = response.content.decode()
        part_two = html[html.index('Part 2 <small'):]
        self.assertEqual(part_two.count('<textarea'), 1)  # nothing but the task text
        self.assertIn('name="task3_instruction"', part_two)
        self.assertIn('Write 180–200 words.', part_two)  # the help text explains the line added below the task
        self.assertNotIn('Namuna javob', part_two)

    def test_the_letter_tasks_say_where_the_letter_and_the_sample_go(self):
        response = self.client.get(self.url)
        self.assertContains(response, 'Namuna javob', count=2)
        self.assertContains(response, 'Xatning o&#x27;zini bu yerga emas', count=2)

    def test_a_new_test_starts_with_todays_date_the_first_shift_and_sixty_minutes(self):
        data = rendered_form_data(self.client.get(self.url))
        self.assertEqual(data['date'], date.today().isoformat())
        self.assertEqual(data['shift'], '1')
        self.assertEqual(data['duration_minutes'], '60')
        self.assertEqual(data['title'], '')

    def test_saving_creates_the_test_and_only_the_tasks_that_were_filled(self):
        response = self.client.post(self.url, form_data(
            task1_instruction=TRAVEL_INSTRUCTION, task1_context='You are a member...', task1_prompt='Dear Member,\nHello',
            task1_sample_answer='Hi Anna', task3_instruction=DISCUSSION_TASK,
        ))
        test = WritingTest.objects.get()
        self.assertRedirects(response, reverse('panel:writing_test_edit', args=[test.pk]))
        self.assertEqual((test.course, test.title, test.date, test.shift, test.duration_minutes),
                         (self.writing, 'Travel Club', date(2025, 10, 18), 1, 60))
        self.assertEqual(test.topic, 'Is a vegetarian diet better for health?')
        tasks = {task.slot: task for task in test.tasks.all()}
        self.assertEqual(sorted(tasks), [1, 3])
        self.assertEqual((tasks[1].context, tasks[1].prompt, tasks[1].instruction, tasks[1].sample_answer),
                         ('You are a member...', 'Dear Member,\nHello', TRAVEL_INSTRUCTION, 'Hi Anna'))
        self.assertEqual(tasks[3].instruction, DISCUSSION_TASK)
        self.assertEqual((tasks[3].context, tasks[3].prompt, tasks[3].sample_answer), ('', '', ''))

    def test_part_two_ignores_a_letter_or_a_sample_answer_sent_with_it(self):
        self.client.post(self.url, form_data(
            task3_instruction=DISCUSSION_TASK, task3_context='ctx', task3_prompt='letter', task3_sample_answer='sample'))
        task = WritingTask.objects.get(slot=3)
        self.assertEqual((task.instruction, task.context, task.prompt, task.sample_answer), (DISCUSSION_TASK, '', '', ''))

    def test_part_two_needs_nothing_but_its_task_text(self):
        # only a letter, context or sample sent for Part 2 does not make it a task, and it is not an error either
        response = self.client.post(self.url, form_data(task3_context='ctx', task3_sample_answer='sample', task1_instruction='x'))
        self.assertEqual(response.status_code, 302)
        self.assertEqual(list(WritingTask.objects.values_list('slot', flat=True)), [1])

    def test_a_confirmation_is_shown_after_saving(self):
        response = self.client.post(self.url, form_data(task1_instruction='Write'), follow=True)
        self.assertContains(response, 'testi saqlandi.')

    def test_a_test_may_be_saved_without_any_task_and_it_stays_unready(self):
        self.client.post(self.url, form_data())
        test = WritingTest.objects.get()
        self.assertEqual(test.tasks.count(), 0)
        self.assertFalse(test.is_ready)

    def test_a_filled_task_needs_its_instruction(self):
        response = self.client.post(self.url, form_data(task2_prompt='Dear student,', task2_context='ctx'))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(WritingTest.objects.count(), 0)
        errors = response.context['form'].errors
        self.assertEqual(list(errors), ['task2_instruction'])
        self.assertIn('Task 1.2', errors['task2_instruction'][0])
        self.assertContains(response, 'form-errors')

    def test_the_text_entered_is_kept_when_the_form_is_not_valid(self):
        response = self.client.post(self.url, form_data(task1_prompt='Dear Member,\nHello', title=''))
        self.assertEqual(response.status_code, 200)
        data = rendered_form_data(response)
        self.assertEqual(data['task1_prompt'], 'Dear Member,\nHello')
        self.assertEqual(data['topic'], 'Is a vegetarian diet better for health?')

    def test_spaces_only_count_as_empty(self):
        self.client.post(self.url, form_data(task1_instruction='Write', task2_prompt='   ', task3_context=' \n '))
        self.assertEqual(list(WritingTest.objects.get().tasks.values_list('slot', flat=True)), [1])

    def test_text_is_saved_without_surrounding_spaces(self):
        self.client.post(self.url, form_data(task1_instruction='  Write about 50 words.  \n', task1_prompt='\nDear Member,\n'))
        task = WritingTask.objects.get()
        self.assertEqual((task.instruction, task.prompt), ('Write about 50 words.', 'Dear Member,'))

    def test_the_test_needs_a_title_and_a_valid_date_shift_and_duration(self):
        cases = {
            'title': '', 'date': 'not a date', 'shift': '3', 'duration_minutes': '0',
        }
        for name, value in cases.items():
            response = self.client.post(self.url, form_data(**{name: value}))
            self.assertEqual(response.status_code, 200, name)
            self.assertIn(name, response.context['form'].errors, name)
        for value in ('0', '241', 'abc', ''):
            response = self.client.post(self.url, form_data(duration_minutes=value))
            self.assertIn('duration_minutes', response.context['form'].errors, value)
        self.assertEqual(WritingTest.objects.count(), 0)

    def test_the_longest_time_is_four_hours(self):
        self.client.post(self.url, form_data(duration_minutes='240', task1_instruction='Write'))
        self.assertEqual(WritingTest.objects.get().duration_minutes, 240)

    def test_the_topic_is_optional(self):
        self.client.post(self.url, form_data(topic='', task1_instruction='Write'))
        self.assertEqual(WritingTest.objects.get().subtitle, '')

    def test_only_writing_courses_can_get_tests(self):
        url = reverse('panel:writing_test_create', args=[self.course2.pk])
        self.assertEqual(self.client.get(url).status_code, 404)
        self.assertEqual(self.client.post(url, form_data(task1_instruction='Write')).status_code, 404)
        self.assertEqual(WritingTest.objects.count(), 0)

    def test_only_admins_can_create_tests(self):
        self.client.logout()
        response = self.client.get(self.url)
        self.assertRedirects(response, f"{reverse('accounts:login')}?next={self.url}", fetch_redirect_response=False)
        self.client.force_login(self.alice)
        self.assertEqual(self.client.get(self.url).status_code, 403)
        self.assertEqual(self.client.post(self.url, form_data(task1_instruction='Write')).status_code, 403)
        self.assertEqual(WritingTest.objects.count(), 0)


class WritingTestEditTests(WritingPanelTestCase):
    def setUp(self):
        super().setUp()
        self.test = make_test(self.writing)
        self.url = reverse('panel:writing_test_edit', args=[self.test.pk])

    def test_the_form_shows_what_was_saved(self):
        data = rendered_form_data(self.client.get(self.url))
        self.assertEqual((data['title'], data['date'], data['shift'], data['duration_minutes']),
                         ('Travel Club', '2025-10-18', '1', '60'))
        self.assertEqual(data['topic'], 'Is a vegetarian diet better for health?')
        self.assertEqual(data['task1_instruction'], TRAVEL_INSTRUCTION)
        self.assertTrue(data['task1_prompt'].startswith('Dear Member,\nWe are planning'))
        self.assertEqual(data['task1_sample_answer'], '')
        self.assertEqual(data['task3_instruction'], DISCUSSION_TASK)
        for name in PART_2_ABSENT:
            self.assertNotIn(name, data)

    def test_saving_the_form_unchanged_changes_nothing(self):
        before = list(WritingTask.objects.order_by('pk').values())
        response = self.client.post(self.url, rendered_form_data(self.client.get(self.url)))
        self.assertRedirects(response, self.url)
        self.assertEqual(list(WritingTask.objects.order_by('pk').values()), before)

    def test_the_page_links_to_the_student_view_and_the_delete_form(self):
        response = self.client.get(self.url)
        self.assertContains(response, f'href="{reverse("writing:intro", args=[self.writing.slug, self.test.pk])}" target="_blank"')
        self.assertContains(response, f'action="{reverse("panel:writing_test_delete", args=[self.test.pk])}"')
        self.assertContains(response, f'href="{reverse("panel:course_edit", args=[self.writing.pk])}#practice"')

    def test_changes_update_the_same_tasks(self):
        first = WritingTask.objects.get(test=self.test, slot=1)
        data = rendered_form_data(self.client.get(self.url))
        data.update(title='Travel Club 2', shift='2', topic='', task1_instruction='Write 50 words.', duration_minutes='45')
        self.client.post(self.url, data)
        self.test.refresh_from_db()
        self.assertEqual((self.test.title, self.test.shift, self.test.topic, self.test.duration_minutes),
                         ('Travel Club 2', 2, '', 45))
        first.refresh_from_db()
        self.assertEqual(first.instruction, 'Write 50 words.')
        self.assertEqual(WritingTask.objects.filter(test=self.test).count(), 3)
        self.assertEqual(WritingTest.objects.count(), 1)

    def test_clearing_every_field_of_a_task_removes_it(self):
        data = rendered_form_data(self.client.get(self.url))
        for name in TASK_FIELDS[2]:
            data[f'task2_{name}'] = ''
        self.client.post(self.url, data)
        self.assertEqual(list(self.test.tasks.values_list('slot', flat=True)), [1, 3])
        self.client.force_login(self.alice)
        page = self.client.get(reverse('writing:write', args=[self.writing.slug, self.test.pk]))
        self.assertContains(page, 'role="tab"', count=2)

    def test_clearing_the_task_text_of_part_two_removes_it(self):
        data = rendered_form_data(self.client.get(self.url))
        data['task3_instruction'] = ''
        self.client.post(self.url, data)
        self.assertEqual(list(self.test.tasks.values_list('slot', flat=True)), [1, 2])

    def test_saving_part_two_changes_only_its_task_text(self):
        # an older Part 2 row may still hold a letter, a context or a sample: they are no longer shown nor touched
        WritingTask.objects.filter(test=self.test, slot=3).update(context='Old', prompt='Old letter', sample_answer='Old sample')
        data = rendered_form_data(self.client.get(self.url))
        data['task3_instruction'] = 'New task text.'
        self.client.post(self.url, data)
        task = WritingTask.objects.get(test=self.test, slot=3)
        self.assertEqual((task.instruction, task.context, task.prompt, task.sample_answer),
                         ('New task text.', 'Old', 'Old letter', 'Old sample'))
        self.client.force_login(self.alice)
        page = self.client.get(reverse('writing:write', args=[self.writing.slug, self.test.pk]))
        for old in ('Old letter', 'Old sample'):
            self.assertNotContains(page, old)
        self.assertContains(page, 'New task text.')

    def test_a_missing_task_can_be_added_later(self):
        WritingTask.objects.filter(test=self.test, slot=2).delete()
        data = rendered_form_data(self.client.get(self.url))
        data['task2_instruction'] = 'Write a formal e-mail. Write 120–150 words.'
        self.client.post(self.url, data)
        self.assertEqual(list(self.test.tasks.values_list('slot', flat=True)), [1, 2, 3])

    def test_a_task_cannot_lose_its_instruction_while_other_fields_stay(self):
        data = rendered_form_data(self.client.get(self.url))
        data['task1_instruction'] = ''
        response = self.client.post(self.url, data)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(WritingTask.objects.get(test=self.test, slot=1).instruction, TRAVEL_INSTRUCTION)

    def test_editing_a_test_keeps_what_students_sent(self):
        make_submission(self.test, self.alice)
        data = rendered_form_data(self.client.get(self.url))
        data['task3_instruction'] = ''
        self.client.post(self.url, data)
        self.assertEqual(WritingSubmission.objects.count(), 1)
        self.assertEqual(WritingAnswer.objects.count(), 3)

    def test_unknown_tests_are_404(self):
        self.assertEqual(self.client.get(reverse('panel:writing_test_edit', args=[9999])).status_code, 404)

    def test_only_admins_can_edit_tests(self):
        self.client.logout()
        self.assertEqual(self.client.get(self.url).status_code, 302)
        self.client.force_login(self.alice)
        self.assertEqual(self.client.get(self.url).status_code, 403)
        data = form_data(title='Hacked', task1_instruction='x')
        self.assertEqual(self.client.post(self.url, data).status_code, 403)
        self.test.refresh_from_db()
        self.assertEqual(self.test.title, 'Travel Club')


class WritingTestDeleteTests(WritingPanelTestCase):
    def setUp(self):
        super().setUp()
        self.test = make_test(self.writing)
        self.url = reverse('panel:writing_test_delete', args=[self.test.pk])

    def test_deleting_removes_the_test_its_tasks_and_what_students_sent(self):
        make_submission(self.test, self.alice)
        other = make_test(self.writing, title='Other')
        response = self.client.post(self.url, follow=True)
        self.assertRedirects(response, reverse('panel:course_edit', args=[self.writing.pk]))
        self.assertContains(response, 'testi o')
        self.assertEqual(list(WritingTest.objects.all()), [other])
        self.assertEqual(WritingTask.objects.exclude(test=other).count(), 0)
        self.assertEqual((WritingSubmission.objects.count(), WritingAnswer.objects.count()), (0, 0))

    def test_it_needs_a_post_and_an_admin(self):
        self.assertEqual(self.client.get(self.url).status_code, 405)
        self.client.force_login(self.alice)
        self.assertEqual(self.client.post(self.url).status_code, 403)
        self.client.logout()
        self.assertEqual(self.client.post(self.url).status_code, 302)
        self.assertEqual(WritingTest.objects.count(), 1)

    def test_unknown_tests_are_404(self):
        self.assertEqual(self.client.post(reverse('panel:writing_test_delete', args=[9999])).status_code, 404)


class WritingSubmissionListTests(WritingPanelTestCase):
    def setUp(self):
        super().setUp()
        self.test = make_test(self.writing)
        self.url = reverse('panel:writing_submissions', args=[self.writing.pk])

    def test_an_empty_list_says_so(self):
        response = self.client.get(self.url)
        self.assertContains(response, 'Hali hech kim ish yubormagan.')
        self.assertContains(response, f'href="{reverse("panel:course_edit", args=[self.writing.pk])}#practice"')

    def test_each_row_shows_the_student_the_test_the_words_of_each_task_and_the_time(self):
        submission = make_submission(self.test, self.alice, texts=('one two three', '', 'a b c d e'), seconds=754)
        response = self.client.get(self.url)
        self.assertContains(response, 'Alice Aliyeva')
        self.assertContains(response, '<strong>Travel Club</strong>')
        self.assertContains(response, '18 Oct 2025 · 1-smena')
        self.assertContains(response, '3 / 0 / 5')
        self.assertContains(response, '12:34')
        self.assertContains(response, f'href="{reverse("panel:writing_submission", args=[submission.pk])}"')

    def test_a_missing_time_is_a_dash(self):
        make_submission(self.test, self.alice, seconds=None)
        self.assertContains(self.client.get(self.url), '<td class="num">—</td>')

    def test_a_student_without_a_name_is_shown_by_email(self):
        nameless = WritingSubmission.objects.create(
            test=self.test, user=User.objects.create_user(email='noname@t.uz', password='x'))
        WritingAnswer.objects.create(submission=nameless, slot=1, text='x', word_count=1)
        self.assertContains(self.client.get(self.url), 'noname@t.uz')

    def test_the_newest_work_comes_first(self):
        older = make_submission(self.test, self.alice)
        newer = make_submission(self.test, self.bob)
        html = self.client.get(self.url).content.decode()
        links = re.findall(r'/panel/writing/submissions/(\d+)/', html)
        self.assertEqual(links, [str(newer.pk), str(older.pk)])

    def test_only_the_work_of_this_course_is_listed(self):
        other_course = make_writing_course()
        make_submission(make_test(other_course, title='Elsewhere'), self.bob)
        response = self.client.get(self.url)
        self.assertNotContains(response, 'Elsewhere')
        self.assertContains(response, 'Hali hech kim ish yubormagan.')

    def test_twenty_rows_a_page(self):
        for index in range(21):
            make_submission(self.test, self.alice, texts=(f'work {index}', '', ''))
        first = self.client.get(self.url)
        self.assertEqual(len(re.findall(r'/panel/writing/submissions/\d+/', first.content.decode())), 20)
        self.assertContains(first, '1 / 2')
        second = self.client.get(self.url, {'page': 2})
        self.assertEqual(len(re.findall(r'/panel/writing/submissions/\d+/', second.content.decode())), 1)

    def test_the_number_of_queries_does_not_grow_with_the_number_of_rows(self):
        make_submission(self.test, self.alice)
        with CaptureQueriesContext(connection) as few:
            self.client.get(self.url)
        for _ in range(8):
            make_submission(self.test, self.bob)
        with CaptureQueriesContext(connection) as many:
            self.client.get(self.url)
        self.assertEqual(len(few), len(many))

    def test_only_for_writing_courses_and_admins(self):
        self.assertEqual(self.client.get(reverse('panel:writing_submissions', args=[self.course2.pk])).status_code, 404)
        self.client.force_login(self.alice)
        self.assertEqual(self.client.get(self.url).status_code, 403)
        self.client.logout()
        self.assertEqual(self.client.get(self.url).status_code, 302)


class WritingSubmissionDetailTests(WritingPanelTestCase):
    def setUp(self):
        super().setUp()
        self.test = make_test(self.writing)
        self.submission = make_submission(
            self.test, self.alice, texts=('Dear friend,\nI like Rome.', '', '<script>alert(1)</script> text'), seconds=65)
        self.url = reverse('panel:writing_submission', args=[self.submission.pk])

    def test_the_page_shows_who_wrote_what_and_how_long_it_took(self):
        response = self.client.get(self.url)
        self.assertContains(response, 'Alice Aliyeva')
        self.assertContains(response, 'alice@t.uz')
        self.assertContains(response, 'Travel Club · 18 Oct 2025 · 1-smena')
        self.assertContains(response, '<dd>01:05</dd>')
        self.assertContains(response, f'<dd>{self.submission.total_words}</dd>')
        self.assertContains(response, f'href="{reverse("panel:writing_submissions", args=[self.writing.pk])}"')

    def test_every_task_is_shown_with_its_words_and_its_instruction(self):
        response = self.client.get(self.url)
        self.assertContains(response, 'Task 1.1 <small class="muted-sm">· 5 so')
        self.assertContains(response, 'Task 1.2 <small class="muted-sm">· 0 so')
        self.assertContains(response, 'Part 2 <small class="muted-sm">· 2 so')
        self.assertContains(response, '<strong>Topshiriq:</strong> Write a short email to your friend')
        self.assertContains(response, 'informal e-mail to a friend, about 50 words')

    def test_the_text_keeps_its_line_breaks_and_is_escaped(self):
        response = self.client.get(self.url)
        self.assertContains(response, '<div class="submission-text">Dear friend,<br>I like Rome.</div>')
        self.assertNotContains(response, '<script>alert(1)</script>')
        self.assertContains(response, '&lt;script&gt;alert(1)&lt;/script&gt; text')

    def test_an_empty_task_is_marked(self):
        self.assertContains(self.client.get(self.url), 'empty-note', count=1)

    def test_work_for_a_task_that_was_removed_later_still_shows(self):
        WritingTask.objects.filter(test=self.test, slot=3).delete()
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'text')
        self.assertContains(response, 'Part 2 <small class="muted-sm">· 2 so')
        self.assertNotContains(response, '<strong>Topshiriq:</strong> You are participating in an online discussion')

    def test_unknown_work_is_404_and_only_admins_may_read_it(self):
        self.assertEqual(self.client.get(reverse('panel:writing_submission', args=[9999])).status_code, 404)
        self.client.force_login(self.alice)
        self.assertEqual(self.client.get(self.url).status_code, 403)
        self.client.logout()
        self.assertEqual(self.client.get(self.url).status_code, 302)


class WritingNavigationTests(WritingPanelTestCase):
    def test_the_courses_menu_stays_highlighted_on_every_writing_page(self):
        test = make_test(self.writing)
        submission = make_submission(test, self.alice)
        urls = [
            reverse('panel:writing_test_create', args=[self.writing.pk]),
            reverse('panel:writing_test_edit', args=[test.pk]),
            reverse('panel:writing_submissions', args=[self.writing.pk]),
            reverse('panel:writing_submission', args=[submission.pk]),
        ]
        marker = f'<a href="{reverse("panel:course_list")}" class="active">'
        for url in urls:
            self.assertContains(self.client.get(url), marker, msg_prefix=url)
        self.assertNotContains(self.client.get(reverse('panel:dashboard')), marker)
