from html.parser import HTMLParser

from django.test import TestCase

from accounts.models import Role, User
from courses.models import Category, Course

PASSWORD = 'StrongPass123!'

COURSE_BASE = {
    'title': 'Learn English: Test Course',
    'category': 'grammar',
    'level': 'intermediate',
    'cefr_badge': 'B2',
    'short_description': 'Qisqa tavsif',
    'about_this_course': '',
    'course_description': '',
    'duration_text': '1 Hour',
    'language': 'English',
    'publisher_name': 'Advance Learning',
    'is_cpd_accredited': 'on',
    'is_published': 'on',
}


def make_user(email, role=Role.STUDENT, active=True, **extra):
    return User.objects.create_user(email=email, password=PASSWORD, role=role, is_active=active, **extra)


def formset_data(prefix, rows, initial=0):
    data = {
        f'{prefix}-TOTAL_FORMS': str(len(rows)),
        f'{prefix}-INITIAL_FORMS': str(initial),
        f'{prefix}-MIN_NUM_FORMS': '0',
        f'{prefix}-MAX_NUM_FORMS': '1000',
    }
    for index, row in enumerate(rows):
        for key, value in row.items():
            data[f'{prefix}-{index}-{key}'] = value
    return data


class FormParser(HTMLParser):
    """Collects the values a browser would submit for the rendered form (ignores <template>)."""

    def __init__(self):
        super().__init__()
        self.data = {}
        self._template_depth = 0
        self._select = None
        self._textarea = None
        self._textarea_text = []

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag == 'template':
            self._template_depth += 1
        if self._template_depth:
            return
        if tag == 'input' and attrs.get('name'):
            kind = attrs.get('type', 'text')
            if kind in ('checkbox', 'radio'):
                if 'checked' in attrs:
                    self.data[attrs['name']] = attrs.get('value') or 'on'
            elif kind not in ('submit', 'file'):
                self.data[attrs['name']] = attrs.get('value') or ''
        elif tag == 'select':
            self._select = attrs.get('name')
        elif tag == 'option' and self._select and 'selected' in attrs:
            self.data[self._select] = attrs.get('value', '')
        elif tag == 'textarea':
            self._textarea = attrs.get('name')
            self._textarea_text = []

    def handle_endtag(self, tag):
        if tag == 'template':
            self._template_depth -= 1
        elif tag == 'select':
            self._select = None
        elif tag == 'textarea' and self._textarea and not self._template_depth:
            self.data[self._textarea] = ''.join(self._textarea_text).lstrip('\n')
            self._textarea = None

    def handle_data(self, data):
        if self._textarea and not self._template_depth:
            self._textarea_text.append(data)


def rendered_form_data(response):
    parser = FormParser()
    parser.feed(response.content.decode())
    return parser.data


class PanelTestCase(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.admin = make_user('admin@t.uz', role=Role.ADMIN, first_name='Admin')
        cls.alice = make_user('alice@t.uz', first_name='Alice', last_name='Aliyeva')
        cls.bob = make_user('bob@t.uz', first_name='Bob', last_name='Bekov')
        cls.pending = make_user('pending@t.uz', active=False, first_name='Pen', last_name='Ding')
        cls.course1 = Course.objects.create(title='Course One', short_description='x')
        cls.course2 = Course.objects.create(title='Course Two', short_description='y', category=Category.READING)
