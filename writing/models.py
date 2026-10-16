import re

from django.conf import settings
from django.db import models
from django.urls import reverse

from courses.models import Course

from . import guides

WORD_RE = re.compile(r'\S+')
# A closing "Write 180–200 words." sentence of a task text (Part 2 shows that line on its own, so it is not repeated).
TRAILING_WORDS = re.compile(r'(?:^|\s)write\s+(?:about\s+|around\s+)?\d+(?:\s*[-–—]\s*\d+)?\s+words\.?\s*$', re.IGNORECASE)


def count_words(text):
    """How many words a text has: runs of non-space characters, so "e-mail" and "don't" are one word."""
    return len(WORD_RE.findall(text or ''))


class Slot(models.IntegerChoices):
    TASK_11 = 1, 'Task 1.1'
    TASK_12 = 2, 'Task 1.2'
    PART_2 = 3, 'Part 2'


# What the exam asks of each task (the same in every test): what to write, the word target shown to the student,
# the goal the progress bar fills up to, and the range of words that counts as "about right". `letter` tells whether
# the task answers a letter shown above the writing box (Tasks 1.1 and 1.2) or is a single task text (Part 2).
TASK_RULES = {
    Slot.TASK_11: {
        'label': 'Task 1.1', 'about': 'informal e-mail to a friend', 'target': 'about 50', 'goal': 50, 'low': 45,
        'high': 60, 'letter': True,
    },
    Slot.TASK_12: {
        'label': 'Task 1.2', 'about': 'formal e-mail', 'target': '120–150', 'goal': 150, 'low': 120,
        'high': 150, 'letter': True,
    },
    Slot.PART_2: {
        'label': 'Part 2', 'about': 'online discussion (essay)', 'target': '180–200', 'goal': 200, 'low': 180,
        'high': 200, 'letter': False,
    },
}
# Useful phrases are only written down for the tasks whose structure is known.
PHRASES = {Slot.TASK_11: guides.INFORMAL_EMAIL}


class WritingTest(models.Model):
    """A real exam: three tasks written within one time limit (60 minutes), checked by the teacher."""

    SHIFTS = [(1, '1-smena'), (2, '2-smena')]

    course = models.ForeignKey(Course, on_delete=models.CASCADE, related_name='writing_tests')
    title = models.CharField(max_length=120)
    date = models.DateField()
    shift = models.PositiveSmallIntegerField(choices=SHIFTS, default=1)
    topic = models.CharField(
        max_length=255, blank=True,
        help_text="Ro'yxatda «Part 2: ...» ko'rinishida chiqadi (masalan: Is a vegetarian diet better for health?).",
    )
    duration_minutes = models.PositiveSmallIntegerField(default=60)

    class Meta:
        ordering = ['date', 'shift', 'pk']

    def __str__(self):
        return f'{self.title} · {self.date:%d %b %Y} · {self.get_shift_display()}'

    def get_absolute_url(self):
        return reverse('writing:intro', kwargs={'slug': self.course.slug, 'pk': self.pk})

    @property
    def subtitle(self):
        return f'Part 2: {self.topic}' if self.topic else ''

    @property
    def is_ready(self):
        """A test can be written once at least one of its tasks has been entered."""
        return self.tasks.exclude(instruction='').exists()


class WritingTask(models.Model):
    test = models.ForeignKey(WritingTest, on_delete=models.CASCADE, related_name='tasks')
    slot = models.PositiveSmallIntegerField(choices=Slot.choices)
    context = models.CharField(
        max_length=500, blank=True,
        help_text="Xat tepasida kichik yozuv bilan chiqadi (masalan: You are a member of the Travel Club...).",
    )
    prompt = models.TextField(
        blank=True, help_text="O'quvchi javob yozadigan xat yoki muhokama matni.",
    )
    instruction = models.TextField(help_text="Topshiriq: nima yozish kerak (qalin yoziladi).")
    sample_answer = models.TextField(blank=True, help_text="Namuna javob (ixtiyoriy).")

    class Meta:
        ordering = ['slot']
        constraints = [
            models.UniqueConstraint(fields=['test', 'slot'], name='unique_writing_slot_per_test'),
        ]

    def __str__(self):
        return f'{self.test} · {self.label}'

    @property
    def rules(self):
        return TASK_RULES[self.slot]

    @property
    def label(self):
        return self.rules['label']

    @property
    def description(self):
        return f"{self.rules['about']}, {self.rules['target']} words"

    @property
    def phrases(self):
        return PHRASES.get(self.slot)

    @property
    def has_letter(self):
        """Tasks 1.1 and 1.2 answer a letter (small context + text) and may have a sample answer; Part 2 has neither."""
        return self.rules['letter']

    @property
    def statement(self):
        """The task text the student reads in bold. Part 2 shows "Write 180–200 words." as a line of its own below it."""
        text = self.instruction.strip()
        return text if self.has_letter else TRAILING_WORDS.sub('', text).strip()

    @property
    def words_line(self):
        return '' if self.has_letter else f"Write {self.rules['target']} words."

    @property
    def sample(self):
        return self.sample_answer if self.has_letter else ''


class WritingSubmission(models.Model):
    """What a student sent to the teacher for one test."""

    test = models.ForeignKey(WritingTest, on_delete=models.CASCADE, related_name='submissions')
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='writing_submissions')
    sent_at = models.DateTimeField(auto_now_add=True)
    seconds_used = models.PositiveIntegerField(null=True, blank=True)

    class Meta:
        ordering = ['-sent_at', '-pk']

    def __str__(self):
        return f'{self.user} · {self.test}'

    @property
    def total_words(self):
        return sum(answer.word_count for answer in self.answers.all())

    @property
    def time_used(self):
        """"12:34" — how long the student wrote (empty when the page did not report it)."""
        if self.seconds_used is None:
            return ''
        return f'{self.seconds_used // 60:02d}:{self.seconds_used % 60:02d}'


class WritingAnswer(models.Model):
    submission = models.ForeignKey(WritingSubmission, on_delete=models.CASCADE, related_name='answers')
    slot = models.PositiveSmallIntegerField(choices=Slot.choices)
    text = models.TextField(blank=True)
    word_count = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ['slot']
        constraints = [
            models.UniqueConstraint(fields=['submission', 'slot'], name='unique_writing_answer_per_slot'),
        ]

    def __str__(self):
        return f'{self.submission} · {self.label}'

    @property
    def label(self):
        return TASK_RULES[self.slot]['label']
