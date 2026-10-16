from django.test import TestCase
from django.urls import reverse

from .models import Role, User

PASSWORD = 'StrongPass123!'


class RoleTests(TestCase):
    def test_default_role_is_student(self):
        user = User.objects.create_user(email='s@t.uz', password=PASSWORD)
        self.assertEqual(user.role, Role.STUDENT)
        self.assertFalse(user.is_admin)
        self.assertEqual(user.get_home_url(), reverse('courses:course_list'))

    def test_superuser_gets_admin_role(self):
        user = User.objects.create_superuser(email='a@t.uz', password=PASSWORD)
        self.assertEqual(user.role, Role.ADMIN)
        self.assertTrue(user.is_admin)
        self.assertEqual(user.get_home_url(), reverse('panel:dashboard'))

    def test_registration_always_creates_inactive_student(self):
        response = self.client.post(reverse('accounts:register'), {
            'first_name': 'Ali', 'last_name': 'Valiyev', 'birth_date': '2000-05-15',
            'email': 'ali@t.uz', 'password1': PASSWORD, 'password2': PASSWORD,
            'role': 'admin', 'is_active': 'on', 'is_staff': 'on',
        })
        self.assertRedirects(response, reverse('accounts:register_done'))
        user = User.objects.get(email='ali@t.uz')
        self.assertEqual(user.role, Role.STUDENT)
        self.assertFalse(user.is_active)
        self.assertFalse(user.is_staff)


class LoginRedirectTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.admin = User.objects.create_user(email='a@t.uz', password=PASSWORD, role=Role.ADMIN)
        cls.student = User.objects.create_user(email='s@t.uz', password=PASSWORD)

    def login(self, email, **query):
        url = reverse('accounts:login')
        return self.client.post(url, {'email': email, 'password': PASSWORD}, QUERY_STRING='&'.join(f'{k}={v}' for k, v in query.items()))

    def test_admin_lands_on_panel(self):
        self.assertRedirects(self.login('a@t.uz'), reverse('panel:dashboard'), fetch_redirect_response=False)

    def test_student_lands_on_courses(self):
        self.assertRedirects(self.login('s@t.uz'), reverse('courses:course_list'), fetch_redirect_response=False)

    def test_next_is_honored(self):
        self.assertRedirects(self.login('a@t.uz', next='/courses/'), '/courses/', fetch_redirect_response=False)

    def test_already_logged_in_users_skip_auth_pages(self):
        self.client.force_login(self.admin)
        for name in ('accounts:login', 'accounts:register'):
            self.assertRedirects(self.client.get(reverse(name)), reverse('panel:dashboard'), fetch_redirect_response=False)
        self.client.force_login(self.student)
        for name in ('accounts:login', 'accounts:register'):
            self.assertRedirects(self.client.get(reverse(name)), reverse('courses:course_list'), fetch_redirect_response=False)

    def test_panel_link_only_for_admins(self):
        self.client.force_login(self.admin)
        self.assertContains(self.client.get(reverse('courses:course_list')), reverse('panel:dashboard'))
        self.client.force_login(self.student)
        self.assertNotContains(self.client.get(reverse('courses:course_list')), reverse('panel:dashboard'))
        self.client.logout()
        self.assertNotContains(self.client.get(reverse('courses:course_list')), reverse('panel:dashboard'))
