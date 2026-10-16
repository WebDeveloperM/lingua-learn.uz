from django.urls import reverse

from accounts.models import Role, User
from courses.models import Category, Course, Enrollment, Exercise, LearningOutcome, Part, SkillTag

from .stats import student_leaderboard
from .support import COURSE_BASE, PanelTestCase, formset_data, make_user, rendered_form_data


class AccessControlTests(PanelTestCase):
    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()
        cls.part = Part.objects.create(course=cls.course1, number=1, name='Short replies')
        cls.exercise = Exercise.objects.create(part=cls.part, number=1)

    def get_urls(self):
        return [
            reverse('panel:dashboard'),
            reverse('panel:student_list'),
            reverse('panel:student_detail', args=[self.alice.pk]),
            reverse('panel:rating'),
            reverse('panel:course_list'),
            reverse('panel:course_create'),
            reverse('panel:course_edit', args=[self.course1.pk]),
            reverse('panel:part_create', args=[self.course1.pk]),
            reverse('panel:part_edit', args=[self.part.pk]),
            reverse('panel:exercise_edit', args=[self.exercise.pk]),
        ]

    def post_urls(self):
        return [
            reverse('panel:student_toggle_active', args=[self.pending.pk]),
            reverse('panel:student_delete', args=[self.alice.pk]),
            reverse('panel:course_toggle_published', args=[self.course1.pk]),
            reverse('panel:course_delete', args=[self.course1.pk]),
            reverse('panel:part_delete', args=[self.part.pk]),
            reverse('panel:exercise_add', args=[self.part.pk]),
            reverse('panel:exercise_delete', args=[self.exercise.pk]),
        ]

    def test_anonymous_is_sent_to_login(self):
        for url in self.get_urls() + self.post_urls():
            response = self.client.get(url)
            self.assertRedirects(response, f"{reverse('accounts:login')}?next={url}", fetch_redirect_response=False)

    def test_student_is_forbidden_everywhere(self):
        self.client.force_login(self.alice)
        for url in self.get_urls():
            self.assertEqual(self.client.get(url).status_code, 403, url)
        for url in self.post_urls():
            self.assertEqual(self.client.post(url).status_code, 403, url)

    def test_student_cannot_change_anything(self):
        self.client.force_login(self.alice)
        self.client.post(reverse('panel:student_toggle_active', args=[self.pending.pk]))
        self.client.post(reverse('panel:student_delete', args=[self.bob.pk]))
        self.client.post(reverse('panel:course_delete', args=[self.course1.pk]))
        self.pending.refresh_from_db()
        self.assertFalse(self.pending.is_active)
        self.assertTrue(User.objects.filter(pk=self.bob.pk).exists())
        self.assertTrue(Course.objects.filter(pk=self.course1.pk).exists())

    def test_admin_can_open_every_page(self):
        self.client.force_login(self.admin)
        for url in self.get_urls():
            self.assertEqual(self.client.get(url).status_code, 200, url)

    def test_post_only_views_reject_get_for_admin(self):
        self.client.force_login(self.admin)
        for url in self.post_urls():
            self.assertEqual(self.client.get(url).status_code, 405, url)


class DashboardTests(PanelTestCase):
    def test_counts_only_students(self):
        Enrollment.objects.create(user=self.alice, course=self.course1, progress_percent=100)
        Enrollment.objects.create(user=self.bob, course=self.course1, progress_percent=30)
        Enrollment.objects.create(user=self.admin, course=self.course1, progress_percent=100)
        self.client.force_login(self.admin)

        context = self.client.get(reverse('panel:dashboard')).context
        self.assertEqual(context['total_students'], 3)
        self.assertEqual(context['active_students'], 2)
        self.assertEqual(context['pending_count'], 1)
        self.assertEqual(context['courses_total'], 2)
        self.assertEqual(context['enrollments_total'], 2)
        self.assertEqual(context['completed_total'], 1)
        self.assertEqual([s.pk for s in context['pending_students']], [self.pending.pk])


class StudentManagementTests(PanelTestCase):
    def setUp(self):
        self.client.force_login(self.admin)

    def listed(self, **params):
        response = self.client.get(reverse('panel:student_list'), params)
        return {s.email for s in response.context['page_obj']}

    def test_list_excludes_admins(self):
        self.assertEqual(self.listed(), {'alice@t.uz', 'bob@t.uz', 'pending@t.uz'})

    def test_status_filter(self):
        self.assertEqual(self.listed(status='pending'), {'pending@t.uz'})
        self.assertEqual(self.listed(status='active'), {'alice@t.uz', 'bob@t.uz'})
        self.assertEqual(self.listed(status='nonsense'), {'alice@t.uz', 'bob@t.uz', 'pending@t.uz'})

    def test_search_matches_name_and_email(self):
        self.assertEqual(self.listed(q='aliyeva'), {'alice@t.uz'})
        self.assertEqual(self.listed(q='BOB@'), {'bob@t.uz'})
        self.assertEqual(self.listed(q='nobody'), set())

    def test_pagination_keeps_filters(self):
        for i in range(20):
            make_user(f'extra{i}@t.uz', active=False)
        response = self.client.get(reverse('panel:student_list'), {'status': 'pending'})
        self.assertEqual(len(response.context['page_obj']), 15)
        self.assertIn('status=pending', response.context['query_string'])
        self.assertContains(response, 'status=pending&amp;page=2')

    def test_activate_pending_student(self):
        url = reverse('panel:student_toggle_active', args=[self.pending.pk])
        response = self.client.post(url, {'next': reverse('panel:dashboard')})
        self.assertRedirects(response, reverse('panel:dashboard'))
        self.pending.refresh_from_db()
        self.assertTrue(self.pending.is_active)

    def test_deactivate_active_student(self):
        self.client.post(reverse('panel:student_toggle_active', args=[self.alice.pk]))
        self.alice.refresh_from_db()
        self.assertFalse(self.alice.is_active)

    def test_external_next_is_ignored(self):
        url = reverse('panel:student_toggle_active', args=[self.pending.pk])
        response = self.client.post(url, {'next': 'https://evil.example.com/'})
        self.assertRedirects(response, reverse('panel:student_list'))

    def test_panel_cannot_touch_admins(self):
        for name in ('student_toggle_active', 'student_delete'):
            self.assertEqual(self.client.post(reverse(f'panel:{name}', args=[self.admin.pk])).status_code, 404)
        self.assertEqual(self.client.get(reverse('panel:student_detail', args=[self.admin.pk])).status_code, 404)
        self.admin.refresh_from_db()
        self.assertTrue(self.admin.is_active)

    def test_delete_student_removes_enrollments(self):
        Enrollment.objects.create(user=self.alice, course=self.course1)
        response = self.client.post(reverse('panel:student_delete', args=[self.alice.pk]))
        self.assertRedirects(response, reverse('panel:student_list'))
        self.assertFalse(User.objects.filter(pk=self.alice.pk).exists())
        self.assertEqual(Enrollment.objects.count(), 0)

    def test_detail_shows_enrollments(self):
        Enrollment.objects.create(user=self.alice, course=self.course1, progress_percent=40)
        response = self.client.get(reverse('panel:student_detail', args=[self.alice.pk]))
        self.assertContains(response, 'Course One')
        self.assertEqual(response.context['student'].score, 40)


class ProgressTests(PanelTestCase):
    def setUp(self):
        self.client.force_login(self.admin)
        self.enrollment = Enrollment.objects.create(user=self.alice, course=self.course1, progress_percent=10)
        self.url = reverse('panel:enrollment_progress', args=[self.enrollment.pk])

    def progress(self):
        self.enrollment.refresh_from_db()
        return self.enrollment.progress_percent

    def test_valid_values_are_saved(self):
        for value in (0, 55, 100):
            response = self.client.post(self.url, {'progress_percent': value})
            self.assertRedirects(response, reverse('panel:student_detail', args=[self.alice.pk]))
            self.assertEqual(self.progress(), value)

    def test_invalid_values_are_rejected(self):
        for value in ('101', '-1', 'abc', '', '5.5'):
            self.client.post(self.url, {'progress_percent': value})
            self.assertEqual(self.progress(), 10, value)

    def test_admin_enrollment_is_not_editable(self):
        enrollment = Enrollment.objects.create(user=self.admin, course=self.course1)
        url = reverse('panel:enrollment_progress', args=[enrollment.pk])
        self.assertEqual(self.client.post(url, {'progress_percent': 50}).status_code, 404)


class RatingTests(PanelTestCase):
    def test_ranking_ties_and_exclusions(self):
        carol = make_user('carol@t.uz', first_name='Carol')
        Enrollment.objects.create(user=self.alice, course=self.course1, progress_percent=100)
        Enrollment.objects.create(user=self.alice, course=self.course2, progress_percent=50)
        Enrollment.objects.create(user=self.bob, course=self.course1, progress_percent=100)
        Enrollment.objects.create(user=carol, course=self.course1, progress_percent=100)
        Enrollment.objects.create(user=self.pending, course=self.course1, progress_percent=100)
        Enrollment.objects.create(user=self.admin, course=self.course1, progress_percent=100)

        ranking = [(row['student'].email, row['rank']) for row in student_leaderboard()]
        self.assertEqual(ranking, [
            ('alice@t.uz', 1),
            ('bob@t.uz', 2),
            ('carol@t.uz', 2),
        ])

    def test_student_without_enrollments_scores_zero(self):
        row = student_leaderboard()[0]
        self.assertEqual((row['student'].score, row['student'].courses_count, row['rank']), (0, 0, 1))

    def test_limit(self):
        self.assertEqual(len(student_leaderboard(limit=1)), 1)

    def test_rating_page_renders(self):
        Enrollment.objects.create(user=self.alice, course=self.course1, progress_percent=80)
        self.client.force_login(self.admin)
        response = self.client.get(reverse('panel:rating'))
        self.assertContains(response, 'Alice Aliyeva')
        self.assertNotContains(response, 'Pen Ding')


class CourseManagementTests(PanelTestCase):
    def setUp(self):
        self.client.force_login(self.admin)

    def test_create_course_with_outcomes_and_tags(self):
        data = {
            **COURSE_BASE,
            **formset_data('outcomes', [{'text': 'First'}, {'text': ''}, {'text': 'Third'}]),
            **formset_data('tags', [{'name': 'English Grammar', 'highlighted': 'on'}, {'name': ''}]),
        }
        response = self.client.post(reverse('panel:course_create'), data)

        course = Course.objects.get(title='Learn English: Test Course')
        self.assertRedirects(response, reverse('panel:course_edit', args=[course.pk]))
        self.assertEqual(course.slug, 'learn-english-test-course')
        self.assertEqual(list(course.learning_outcomes.values_list('text', 'order')), [('First', 0), ('Third', 1)])
        self.assertEqual(list(course.skill_tags.values_list('name', 'highlighted')), [('English Grammar', True)])
        self.assertTrue(course.is_published)

    def test_invalid_course_is_not_saved(self):
        data = {
            **COURSE_BASE, 'title': '', 'short_description': 'Kept in the form',
            **formset_data('outcomes', [{'text': 'An outcome'}]),
            **formset_data('tags', []),
        }
        response = self.client.post(reverse('panel:course_create'), data)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(Course.objects.count(), 2)
        self.assertContains(response, 'Kept in the form')
        self.assertContains(response, 'This field is required')

    def test_blank_outcome_on_existing_row_is_an_error(self):
        outcome = LearningOutcome.objects.create(course=self.course1, text='Old', order=0)
        data = {
            **COURSE_BASE, 'title': self.course1.title,
            **formset_data('outcomes', [{'id': outcome.pk, 'text': ''}], initial=1),
            **formset_data('tags', []),
        }
        response = self.client.post(reverse('panel:course_edit', args=[self.course1.pk]), data)
        self.assertEqual(response.status_code, 200)
        outcome.refresh_from_db()
        self.assertEqual(outcome.text, 'Old')

    def test_edit_updates_adds_and_deletes_rows(self):
        first = LearningOutcome.objects.create(course=self.course1, text='Old A', order=0)
        second = LearningOutcome.objects.create(course=self.course1, text='Old B', order=1)
        data = {
            **COURSE_BASE, 'title': 'Course One Renamed',
            **formset_data('outcomes', [
                {'id': first.pk, 'text': 'New A'},
                {'id': second.pk, 'text': 'Old B', 'DELETE': 'on'},
                {'text': 'Brand new'},
            ], initial=2),
            **formset_data('tags', []),
        }
        response = self.client.post(reverse('panel:course_edit', args=[self.course1.pk]), data)
        self.assertRedirects(response, reverse('panel:course_list'))

        self.course1.refresh_from_db()
        self.assertEqual(self.course1.title, 'Course One Renamed')
        self.assertEqual(self.course1.slug, 'course-one')
        self.assertEqual(
            list(self.course1.learning_outcomes.values_list('text', 'order')),
            [('New A', 0), ('Brand new', 1)],
        )

    def test_unchecked_publish_makes_draft(self):
        data = {k: v for k, v in COURSE_BASE.items() if k != 'is_published'}
        data.update(formset_data('outcomes', []), **formset_data('tags', []))
        self.client.post(reverse('panel:course_create'), data)
        self.assertFalse(Course.objects.get(title=COURSE_BASE['title']).is_published)

    def test_non_latin_titles_get_usable_slugs(self):
        slugs = []
        for _ in range(2):
            data = {**COURSE_BASE, 'title': 'Инглиз тили', **formset_data('outcomes', []), **formset_data('tags', [])}
            self.client.post(reverse('panel:course_create'), data)
        for course in Course.objects.filter(title='Инглиз тили').order_by('pk'):
            slugs.append(course.slug)
            self.assertEqual(self.client.get(course.get_absolute_url()).status_code, 200)
        self.assertEqual(slugs, ['kurs', 'kurs-2'])

    def test_toggle_published(self):
        url = reverse('panel:course_toggle_published', args=[self.course1.pk])
        self.client.post(url)
        self.course1.refresh_from_db()
        self.assertFalse(self.course1.is_published)
        self.client.post(url)
        self.course1.refresh_from_db()
        self.assertTrue(self.course1.is_published)

    def test_delete_course_cascades(self):
        LearningOutcome.objects.create(course=self.course1, text='x')
        Enrollment.objects.create(user=self.alice, course=self.course1)
        response = self.client.post(reverse('panel:course_delete', args=[self.course1.pk]))
        self.assertRedirects(response, reverse('panel:course_list'))
        self.assertFalse(Course.objects.filter(pk=self.course1.pk).exists())
        self.assertEqual(LearningOutcome.objects.count(), 0)
        self.assertEqual(Enrollment.objects.count(), 0)

    def test_list_filters(self):
        self.course2.is_published = False
        self.course2.save()

        def titles(**params):
            response = self.client.get(reverse('panel:course_list'), params)
            return {c.title for c in response.context['page_obj']}

        self.assertEqual(titles(), {'Course One', 'Course Two'})
        self.assertEqual(titles(status='draft'), {'Course Two'})
        self.assertEqual(titles(status='published'), {'Course One'})
        self.assertEqual(titles(category='reading'), {'Course Two'})
        self.assertEqual(titles(q='one'), {'Course One'})

    def test_list_counts_only_student_enrollments(self):
        Enrollment.objects.create(user=self.alice, course=self.course1)
        Enrollment.objects.create(user=self.bob, course=self.course1)
        Enrollment.objects.create(user=self.admin, course=self.course1)
        LearningOutcome.objects.create(course=self.course1, text='a')
        LearningOutcome.objects.create(course=self.course1, text='b')
        response = self.client.get(reverse('panel:course_list'))
        row = next(c for c in response.context['page_obj'] if c.pk == self.course1.pk)
        self.assertEqual((row.students_count, row.outcomes_count), (2, 2))

    def test_row_actions_are_icon_buttons_that_keep_their_names(self):
        self.course2.is_published = False
        self.course2.save()
        response = self.client.get(reverse('panel:course_list'))
        html = response.content.decode()
        self.assertEqual(html.count('class="act-btn'), 8)
        self.assertContains(response, '<svg class="icon"', count=8)
        self.assertNotContains(response, 'btn-xs')
        self.assertContains(response, 'title="Tahrirlash" aria-label="Tahrirlash"', count=2)
        self.assertContains(response, 'title="Saytda ko\'rish" aria-label="Saytda ko\'rish"', count=2)
        self.assertContains(response, 'title="O\'chirish" aria-label="O\'chirish"', count=2)
        # the toggle names the action it will perform
        self.assertContains(response, 'title="Yashirish"', count=1)
        self.assertContains(response, 'title="Nashr etish"', count=1)

    def test_icon_buttons_still_post_and_ask_before_deleting(self):
        response = self.client.get(reverse('panel:course_list'))
        self.assertContains(response, f'action="{reverse("panel:course_toggle_published", args=[self.course1.pk])}"')
        self.assertContains(response, f'action="{reverse("panel:course_delete", args=[self.course1.pk])}"')
        self.assertContains(response, 'kursini o\'chirishga ishonchingiz komilmi', count=2)
        self.assertContains(response, 'target="_blank" rel="noopener"', count=2)


class CourseFormRoundTripTests(PanelTestCase):
    """Submit the form exactly as the browser would, using the markup the server rendered."""

    def setUp(self):
        self.client.force_login(self.admin)

    def test_edit_form_posts_back_unchanged(self):
        """Whatever sections the page shows, saving it as rendered must work and keep the other data."""
        for position, text in enumerate(('First', 'Second')):
            LearningOutcome.objects.create(course=self.course1, text=text, order=position)
        SkillTag.objects.create(course=self.course1, name='English Grammar', highlighted=True, order=0)
        Course.objects.filter(pk=self.course1.pk).update(about_this_course='About it', course_description='Long text')

        url = reverse('panel:course_edit', args=[self.course1.pk])
        data = rendered_form_data(self.client.get(url))
        self.assertNotIn('outcomes-__prefix__-text', data)

        self.assertRedirects(self.client.post(url, data), reverse('panel:course_list'))
        self.assertEqual(
            list(self.course1.learning_outcomes.values_list('text', 'order')), [('First', 0), ('Second', 1)],
        )
        self.assertEqual(list(self.course1.skill_tags.values_list('name', 'highlighted')), [('English Grammar', True)])
        self.course1.refresh_from_db()
        self.assertEqual((self.course1.about_this_course, self.course1.course_description), ('About it', 'Long text'))

    def test_hidden_sections_are_left_alone_when_the_page_does_not_send_them(self):
        LearningOutcome.objects.create(course=self.course1, text='Kept outcome', order=0)
        SkillTag.objects.create(course=self.course1, name='Kept tag', order=0)
        Course.objects.filter(pk=self.course1.pk).update(about_this_course='Kept about', course_description='Kept long')
        url = reverse('panel:course_edit', args=[self.course1.pk])
        data = {
            key: value for key, value in rendered_form_data(self.client.get(url)).items()
            if not key.startswith(('outcomes-', 'tags-')) and key not in ('about_this_course', 'course_description')
        }
        data['title'] = 'Renamed without the hidden sections'

        self.assertRedirects(self.client.post(url, data), reverse('panel:course_list'))
        self.course1.refresh_from_db()
        self.assertEqual(self.course1.title, 'Renamed without the hidden sections')
        self.assertEqual((self.course1.about_this_course, self.course1.course_description), ('Kept about', 'Kept long'))
        self.assertEqual(list(self.course1.learning_outcomes.values_list('text', flat=True)), ['Kept outcome'])
        self.assertEqual(list(self.course1.skill_tags.values_list('name', flat=True)), ['Kept tag'])

    def test_visible_sections_are_saved_when_the_page_sends_them(self):
        LearningOutcome.objects.create(course=self.course1, text='First', order=0)
        url = reverse('panel:course_edit', args=[self.course1.pk])
        data = rendered_form_data(self.client.get(url))
        outcome = self.course1.learning_outcomes.get()
        data.update(formset_data('outcomes', [
            {'id': outcome.pk, 'course': self.course1.pk, 'text': 'First'},
            {'text': 'Added in the extra row'},
        ], initial=1))
        data.update(formset_data('tags', [{'name': 'New tag', 'highlighted': 'on'}]))
        data.update({'about_this_course': 'Now written', 'course_description': ''})

        self.assertRedirects(self.client.post(url, data), reverse('panel:course_list'))
        self.assertEqual(
            list(self.course1.learning_outcomes.values_list('text', flat=True)), ['First', 'Added in the extra row'],
        )
        self.assertEqual(list(self.course1.skill_tags.values_list('name', 'highlighted')), [('New tag', True)])
        self.course1.refresh_from_db()
        self.assertEqual((self.course1.about_this_course, self.course1.course_description), ('Now written', ''))

    def test_new_course_form_round_trip(self):
        url = reverse('panel:course_create')
        data = rendered_form_data(self.client.get(url))
        data['title'] = 'Learn English: From The Form'
        data['short_description'] = 'Rendered, filled, submitted'
        data.update(formset_data('outcomes', [{'text': 'Only outcome'}]))

        response = self.client.post(url, data)
        course = Course.objects.get(title='Learn English: From The Form')
        self.assertRedirects(response, reverse('panel:course_edit', args=[course.pk]))
        self.assertEqual(list(course.learning_outcomes.values_list('text', flat=True)), ['Only outcome'])
        self.assertEqual(course.skill_tags.count(), 0)
        self.assertTrue(course.is_published)

    def test_new_course_can_be_created_from_the_page_alone(self):
        url = reverse('panel:course_create')
        data = rendered_form_data(self.client.get(url))
        data['title'] = 'Learn English: Page Only'
        data['short_description'] = 'No hidden sections posted'

        response = self.client.post(url, data)
        course = Course.objects.get(title='Learn English: Page Only')
        self.assertRedirects(response, reverse('panel:course_edit', args=[course.pk]))
        self.assertEqual((course.learning_outcomes.count(), course.skill_tags.count()), (0, 0))


class DraftPreviewTests(PanelTestCase):
    def setUp(self):
        self.course1.is_published = False
        self.course1.save()
        self.url = self.course1.get_absolute_url()

    def test_hidden_from_public_and_students(self):
        self.assertEqual(self.client.get(self.url).status_code, 404)
        self.client.force_login(self.alice)
        self.assertEqual(self.client.get(self.url).status_code, 404)

    def test_admin_can_preview_with_banner(self):
        self.client.force_login(self.admin)
        response = self.client.get(self.url)
        self.assertContains(response, 'hali nashr etilmagan')

    def test_drafts_stay_out_of_public_catalog(self):
        response = self.client.get(reverse('courses:course_list'))
        self.assertNotContains(response, 'Course One')
        self.assertContains(response, 'Course Two')

    def test_cannot_enroll_in_draft(self):
        self.client.force_login(self.alice)
        self.assertEqual(self.client.get(reverse('courses:enroll', args=[self.course1.slug])).status_code, 404)
