import re

from django.contrib.staticfiles import finders
from django.test import Client, TestCase, override_settings
from django.urls import reverse

LOGIN_URL = reverse('accounts:login')
TRUST_PROXY = {'SECURE_PROXY_SSL_HEADER': ('HTTP_X_FORWARDED_PROTO', 'https')}


class HomePageTests(TestCase):
    def test_the_hero_shows_the_picture_instead_of_the_book_emoji(self):
        html = self.client.get(reverse('core:home')).content.decode()
        art = re.search(r'<div class="home-hero-art">(.*?)</div>', html, re.S).group(1)
        self.assertRegex(art, r'<img src="/static/img/main\.png" width="1280" height="720"\s+alt="[^"]+">')
        self.assertNotIn('📚', art)

    def test_the_picture_file_is_there(self):
        self.assertIsNotNone(finders.find('img/main.png'))


class HttpsBehindTheProxyTests(TestCase):
    """The https service (nginx) ends the TLS connection and passes the request on to Django with
    X-Forwarded-Proto: https and the Host the browser used (192.168.2.72:8443). Django must then treat the request as
    https, otherwise its CSRF check compares the browser's https:// origin with http:// and refuses every login."""

    def post_login(self, host, scheme, forwarded=None):
        client = Client(enforce_csrf_checks=True)
        headers = {'HTTP_HOST': host}
        if forwarded:
            headers['HTTP_X_FORWARDED_PROTO'] = forwarded
        page = client.get(LOGIN_URL, **headers)
        token = re.search(r'name="csrfmiddlewaretoken" value="([^"]+)"', page.content.decode()).group(1)
        return client.post(
            LOGIN_URL, {'email': 'nobody@t.uz', 'password': 'wrong-password', 'csrfmiddlewaretoken': token},
            HTTP_ORIGIN=f'{scheme}://{host}', HTTP_REFERER=f'{scheme}://{host}{LOGIN_URL}', **headers)

    @override_settings(**TRUST_PROXY)
    def test_a_form_posted_over_https_passes_the_csrf_check(self):
        response = self.post_login('192.168.2.72:8443', 'https', forwarded='https')
        self.assertEqual(response.status_code, 200)  # the form again, with "wrong email or password": not a 403

    @override_settings(SECURE_PROXY_SSL_HEADER=None)
    def test_without_the_proxy_setting_the_same_post_is_refused(self):
        self.assertEqual(self.post_login('192.168.2.72:8443', 'https', forwarded='https').status_code, 403)

    @override_settings(**TRUST_PROXY)
    def test_plain_http_keeps_working_next_to_https(self):
        self.assertEqual(self.post_login('192.168.2.72:8000', 'http').status_code, 200)
        self.assertEqual(self.post_login('localhost:8000', 'http').status_code, 200)

    @override_settings(**TRUST_PROXY)
    def test_a_post_from_another_site_is_still_refused_over_https(self):
        client = Client(enforce_csrf_checks=True)
        headers = {'HTTP_HOST': '192.168.2.72:8443', 'HTTP_X_FORWARDED_PROTO': 'https'}
        client.get(LOGIN_URL, **headers)
        response = client.post(
            LOGIN_URL, {'email': 'a@t.uz', 'password': 'x'}, HTTP_ORIGIN='https://evil.example',
            HTTP_REFERER='https://evil.example/login', **headers)
        self.assertEqual(response.status_code, 403)

    @override_settings(**TRUST_PROXY)
    def test_the_proxy_header_marks_the_request_as_secure_and_nothing_else_does(self):
        from django.http import HttpRequest

        request = HttpRequest()
        request.META.update({'HTTP_HOST': '192.168.2.72:8443', 'SERVER_PORT': '8000'})
        self.assertFalse(request.is_secure())
        request.META['HTTP_X_FORWARDED_PROTO'] = 'https'
        self.assertTrue(request.is_secure())
        request.META['HTTP_X_FORWARDED_PROTO'] = 'http'
        self.assertFalse(request.is_secure())
        self.assertEqual(request.get_host(), '192.168.2.72:8443')
