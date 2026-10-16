import re

from django.urls import reverse

from speaking.models import SpeakingPart, SpeakingPractice, SpeakingQuestion, SpeakingSet
from speaking.support import SET_ONE, SET_THREE, SET_TWO, make_set, make_speaking_course
from writing.support import make_writing_course

from .support import PanelTestCase, formset_data, rendered_form_data

P11, P12, P2 = SpeakingPart.PART_11, SpeakingPart.PART_12, SpeakingPart.PART_2


def part_url(course, part=1):
    return reverse('panel:speaking_part', args=[course.pk, part])


def questions_of(speaking_set):
    return [question.text for question in speaking_set.questions.all()]


class SpeakingPanelTestCase(PanelTestCase):
    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()
        cls.speaking = make_speaking_course()

    def setUp(self):
        self.client.force_login(self.admin)


class CourseFormSpeakingSectionTests(SpeakingPanelTestCase):
    def edit_url(self, course=None):
        return reverse('panel:course_edit', args=[(course or self.speaking).pk])

    def test_a_speaking_course_lists_its_four_parts_with_what_they_hold(self):
        make_set(self.speaking)
        make_set(self.speaking, questions=SET_TWO)
        make_set(self.speaking, part=P2)
        response = self.client.get(self.edit_url())
        self.assertContains(response, 'Speaking partlar')
        self.assertNotContains(response, 'Mashqlar (Practice)')
        self.assertNotContains(response, 'Writing testlar')
        self.assertContains(response, '💬 Part 1.1')
        self.assertContains(response, 'Questions about you · 2 ta set · 6 ta savol')
        self.assertContains(response, 'Talk about two pictures · 0 ta set · 0 ta savol')
        self.assertContains(response, 'Three questions, one long answer · 1 ta set · 3 ta savol')
        self.assertContains(response, 'Discuss both sides of a topic · 0 ta set · 0 ta savol')
        for part in SpeakingPart:
            self.assertContains(response, f'href="{part_url(self.speaking, part.value)}"')

    def test_other_courses_keep_their_own_sections(self):
        writing = make_writing_course()
        self.assertContains(self.client.get(self.edit_url(writing)), 'Writing testlar')
        self.assertNotContains(self.client.get(self.edit_url(writing)), 'Speaking partlar')
        self.assertContains(self.client.get(self.edit_url(self.course2)), 'Mashqlar (Practice)')
        self.assertNotContains(self.client.get(self.edit_url(self.course2)), 'Speaking partlar')

    def test_a_new_course_form_does_not_need_the_parts(self):
        response = self.client.get(reverse('panel:course_create'))
        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, 'Speaking partlar')

    def test_saving_the_course_leaves_its_sets_alone(self):
        speaking_set = make_set(self.speaking)
        data = rendered_form_data(self.client.get(self.edit_url()))
        response = self.client.post(self.edit_url(), data)
        self.assertRedirects(response, reverse('panel:course_list'))
        self.assertEqual(list(SpeakingSet.objects.values_list('pk', flat=True)), [speaking_set.pk])
        self.assertEqual(questions_of(speaking_set), SET_ONE)


class SpeakingPartPageTests(SpeakingPanelTestCase):
    def setUp(self):
        super().setUp()
        self.url = part_url(self.speaking)

    def test_an_empty_part_offers_one_new_set(self):
        response = self.client.get(self.url)
        self.assertContains(response, '💬 Part 1.1 <small class="muted-sm">· Questions about you</small>')
        self.assertContains(response, 'Yangi set <small class="muted-sm">· Set One</small>')
        self.assertContains(response, 'name="sets-0-questions"')
        self.assertNotContains(response, 'name="sets-1-questions"')
        self.assertNotContains(response, 'Setni o')  # nothing to delete yet
        self.assertContains(response, 'Har qatorga bitta savol')

    def test_the_sets_are_listed_with_their_questions_and_a_new_row_at_the_end(self):
        one = make_set(self.speaking)
        two = make_set(self.speaking, questions=SET_TWO)
        response = self.client.get(self.url)
        data = rendered_form_data(response)
        self.assertEqual((data['sets-TOTAL_FORMS'], data['sets-INITIAL_FORMS']), ('3', '2'))
        self.assertEqual((data['sets-0-set_id'], data['sets-0-questions']), (str(one.pk), '\n'.join(SET_ONE)))
        self.assertEqual((data['sets-1-set_id'], data['sets-1-questions']), (str(two.pk), '\n'.join(SET_TWO)))
        self.assertEqual((data['sets-2-set_id'], data['sets-2-questions']), ('', ''))
        titles = re.findall(r'<h2>(Set \w+|Yangi set) ?(?:<small[^>]*>· (Set \w+)</small>)?</h2>', response.content.decode())
        self.assertEqual(titles, [('Set One', ''), ('Set Two', ''), ('Yangi set', 'Set Three')])
        self.assertContains(response, 'Setni o', count=2)  # the delete box of each existing set only

    def test_the_first_set_is_created_from_the_new_row(self):
        data = rendered_form_data(self.client.get(self.url))
        data['sets-0-questions'] = '\n'.join(SET_ONE)
        response = self.client.post(self.url, data)
        self.assertRedirects(response, self.url)
        speaking_set = SpeakingSet.objects.get()
        self.assertEqual((speaking_set.course, speaking_set.part, speaking_set.number), (self.speaking, 1, 1))
        self.assertEqual(questions_of(speaking_set), SET_ONE)
        self.assertEqual([question.order for question in speaking_set.questions.all()], [0, 1, 2])

    def test_a_confirmation_is_shown_after_saving(self):
        data = rendered_form_data(self.client.get(self.url))
        data['sets-0-questions'] = 'What is your name?'
        self.assertContains(self.client.post(self.url, data, follow=True), 'Part 1.1: setlar saqlandi.')

    def test_a_new_set_gets_the_next_number_and_the_page_offers_another_row(self):
        make_set(self.speaking)
        make_set(self.speaking, questions=SET_TWO)
        data = rendered_form_data(self.client.get(self.url))
        data['sets-2-questions'] = '\n'.join(SET_THREE)
        self.client.post(self.url, data)
        self.assertEqual(list(SpeakingSet.objects.values_list('number', flat=True)), [1, 2, 3])
        response = self.client.get(self.url)
        self.assertContains(response, 'Yangi set <small class="muted-sm">· Set Four</small>')
        self.assertEqual(rendered_form_data(response)['sets-TOTAL_FORMS'], '4')

    def test_a_deleted_number_in_between_is_not_reused(self):
        sets = [make_set(self.speaking, questions=questions) for questions in (SET_ONE, SET_TWO, SET_THREE)]
        data = rendered_form_data(self.client.get(self.url))
        data['sets-1-delete'] = 'on'
        data['sets-3-questions'] = 'A new question?'
        self.client.post(self.url, data)
        self.assertEqual(list(SpeakingSet.objects.values_list('number', flat=True)), [1, 3, 4])
        self.assertEqual(SpeakingSet.objects.get(number=3).pk, sets[2].pk)

    def test_saving_the_form_unchanged_changes_nothing(self):
        make_set(self.speaking)
        make_set(self.speaking, questions=SET_TWO)
        before = list(SpeakingQuestion.objects.order_by('pk').values())
        response = self.client.post(self.url, rendered_form_data(self.client.get(self.url)))
        self.assertRedirects(response, self.url)
        self.assertEqual(list(SpeakingQuestion.objects.order_by('pk').values()), before)
        self.assertEqual(SpeakingSet.objects.count(), 2)

    def test_editing_a_question_keeps_the_rows_of_the_others(self):
        speaking_set = make_set(self.speaking)
        pks = list(speaking_set.questions.values_list('pk', flat=True))
        data = rendered_form_data(self.client.get(self.url))
        data['sets-0-questions'] = '\n'.join([SET_ONE[0], 'Do you live in a flat?', SET_ONE[2]])
        self.client.post(self.url, data)
        self.assertEqual(questions_of(speaking_set), [SET_ONE[0], 'Do you live in a flat?', SET_ONE[2]])
        self.assertEqual(list(speaking_set.questions.values_list('pk', flat=True)), pks)

    def test_questions_can_be_added_and_removed(self):
        speaking_set = make_set(self.speaking)
        data = rendered_form_data(self.client.get(self.url))
        data['sets-0-questions'] = '\n'.join(SET_ONE + ['A fourth question?'])
        self.client.post(self.url, data)
        self.assertEqual(questions_of(speaking_set), SET_ONE + ['A fourth question?'])
        data = rendered_form_data(self.client.get(self.url))
        data['sets-0-questions'] = SET_ONE[0]
        self.client.post(self.url, data)
        self.assertEqual(questions_of(speaking_set), [SET_ONE[0]])
        self.assertEqual(SpeakingQuestion.objects.count(), 1)

    def test_spaces_and_blank_lines_are_ignored(self):
        data = rendered_form_data(self.client.get(self.url))
        data['sets-0-questions'] = '  What is your name?  \r\n\r\n   \r\n Where do you live? \r\n'
        self.client.post(self.url, data)
        self.assertEqual(questions_of(SpeakingSet.objects.get()), ['What is your name?', 'Where do you live?'])

    def test_only_spaces_in_the_new_row_create_nothing(self):
        data = rendered_form_data(self.client.get(self.url))
        data['sets-0-questions'] = ' \n  \n'
        self.assertEqual(self.client.post(self.url, data).status_code, 302)
        self.assertEqual(SpeakingSet.objects.count(), 0)

    def test_a_set_can_be_deleted_with_its_questions_and_what_students_practised(self):
        first = make_set(self.speaking)
        second = make_set(self.speaking, questions=SET_TWO)
        SpeakingPractice.objects.create(user=self.alice, set=first)
        data = rendered_form_data(self.client.get(self.url))
        data['sets-0-delete'] = 'on'
        self.client.post(self.url, data)
        self.assertEqual(list(SpeakingSet.objects.all()), [second])
        self.assertEqual((SpeakingQuestion.objects.count(), SpeakingPractice.objects.count()), (3, 0))

    def test_a_set_left_without_questions_stays_but_students_do_not_see_it(self):
        speaking_set = make_set(self.speaking)
        data = rendered_form_data(self.client.get(self.url))
        data['sets-0-questions'] = ''
        self.client.post(self.url, data)
        self.assertTrue(SpeakingSet.objects.filter(pk=speaking_set.pk).exists())
        self.assertEqual(SpeakingQuestion.objects.count(), 0)
        self.assertContains(self.client.get(self.url), 'Set One')
        self.client.force_login(self.alice)
        student_page = self.client.get(reverse('speaking:part', args=[self.speaking.slug, 1]))
        self.assertContains(student_page, 'No practice questions yet.')

    def test_too_many_questions_are_refused(self):
        make_set(self.speaking)
        data = rendered_form_data(self.client.get(self.url))
        data['sets-0-questions'] = '\n'.join(f'Question {number}?' for number in range(13))
        response = self.client.post(self.url, data)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(SpeakingQuestion.objects.count(), 3)
        self.assertIn('questions', response.context['formset'].errors[0])
        self.assertContains(response, 'form-errors')
        self.assertEqual(rendered_form_data(response)['sets-0-questions'].count('\n'), 12)  # what was typed stays

    def test_a_too_long_question_is_refused(self):
        data = rendered_form_data(self.client.get(self.url))
        data['sets-0-questions'] = 'x' * 301
        response = self.client.post(self.url, data)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(SpeakingSet.objects.count(), 0)
        self.assertIn('questions', response.context['formset'].errors[0])

    def test_the_limits_themselves_are_accepted(self):
        data = rendered_form_data(self.client.get(self.url))
        data['sets-0-questions'] = '\n'.join('y' * 300 for _ in range(12))
        self.assertEqual(self.client.post(self.url, data).status_code, 302)
        self.assertEqual(SpeakingQuestion.objects.count(), 12)

    def test_a_set_of_another_part_or_course_is_left_alone(self):
        elsewhere = make_set(self.speaking, part=P12, questions=['Describe the first picture.'])
        foreign = make_set(make_speaking_course(), questions=['Not yours.'])
        data = rendered_form_data(self.client.get(self.url))
        data.update({
            'sets-TOTAL_FORMS': '3',
            'sets-1-set_id': str(elsewhere.pk), 'sets-1-questions': 'hacked', 'sets-1-delete': 'on',
            'sets-2-set_id': str(foreign.pk), 'sets-2-questions': 'hacked', 'sets-2-delete': 'on',
        })
        self.assertEqual(self.client.post(self.url, data).status_code, 302)
        self.assertEqual(questions_of(elsewhere), ['Describe the first picture.'])
        self.assertEqual(questions_of(foreign), ['Not yours.'])
        self.assertEqual(SpeakingSet.objects.count(), 2)

    def test_an_unknown_set_id_is_ignored(self):
        data = formset_data('sets', [{'set_id': '9999', 'questions': 'Ghost question?'}], initial=1)
        self.assertEqual(self.client.post(self.url, data).status_code, 302)
        self.assertEqual(SpeakingSet.objects.count(), 0)

    def test_the_page_links_to_the_student_view(self):
        response = self.client.get(self.url)
        self.assertContains(
            response, f'href="{reverse("speaking:part", args=[self.speaking.slug, 1])}" target="_blank"')
        self.assertContains(response, f'href="{reverse("panel:course_edit", args=[self.speaking.pk])}#practice"')

    def test_every_part_has_its_own_page(self):
        for part in SpeakingPart:
            response = self.client.get(part_url(self.speaking, part.value))
            self.assertContains(response, part.label)

    def test_the_courses_menu_stays_highlighted(self):
        marker = f'<a href="{reverse("panel:course_list")}" class="active">'
        self.assertContains(self.client.get(self.url), marker)

    def test_only_speaking_courses_and_known_parts_have_pages(self):
        writing = make_writing_course()
        self.assertEqual(self.client.get(part_url(writing)).status_code, 404)
        self.assertEqual(self.client.get(part_url(self.course2)).status_code, 404)
        for number in (0, 5, 42):
            self.assertEqual(self.client.get(part_url(self.speaking, number)).status_code, 404)
        self.assertEqual(self.client.get(reverse('panel:speaking_part', args=[9999, 1])).status_code, 404)
        self.assertEqual(self.client.post(part_url(writing), formset_data('sets', [], initial=0)).status_code, 404)

    def test_only_admins_can_manage_sets(self):
        self.client.logout()
        self.assertRedirects(
            self.client.get(self.url), f"{reverse('accounts:login')}?next={self.url}", fetch_redirect_response=False)
        self.client.force_login(self.alice)
        self.assertEqual(self.client.get(self.url).status_code, 403)
        data = formset_data('sets', [{'set_id': '', 'questions': 'Sneaky?'}], initial=0)
        self.assertEqual(self.client.post(self.url, data).status_code, 403)
        self.assertEqual(SpeakingSet.objects.count(), 0)


class StudentsSeeWhatTheAdminEntersTests(SpeakingPanelTestCase):
    def test_the_admin_builds_a_part_and_a_student_practises_from_it(self):
        url = part_url(self.speaking)
        for questions in (SET_ONE, SET_TWO):
            data = rendered_form_data(self.client.get(url))
            last_row = int(data['sets-TOTAL_FORMS']) - 1  # the empty row at the end is where a new set goes
            data[f'sets-{last_row}-questions'] = '\n'.join(questions)
            self.client.post(url, data)
        self.assertEqual(list(SpeakingSet.objects.values_list('number', flat=True)), [1, 2])

        self.client.force_login(self.alice)
        hub = self.client.get(self.speaking.get_absolute_url())
        self.assertContains(hub, '0 / 2 practised')
        part = self.client.get(reverse('speaking:part', args=[self.speaking.slug, 1]))
        for question in SET_ONE:
            self.assertContains(part, question)
        ready = self.client.get(SpeakingSet.objects.get(number=2).get_absolute_url())
        self.assertContains(ready, 'Part 1.1 · Set Two')
        self.assertContains(ready, '3 questions · about <strong>2 minutes</strong>.')
