import os
import uuid

from django.conf import settings
from django.db import models
from django.urls import reverse

from courses.models import Course

# How many questions a set has when no set has been entered yet (shown in the part's description line).
DEFAULT_QUESTIONS = 3
# Part 1.1 is answered question by question: the question is read aloud, then THINK seconds to prepare, then TALK
# seconds to speak (the part card says "5 sec to think · 30 sec to talk").
THINK_SECONDS_11, TALK_SECONDS_11 = 5, 30
SET_NAMES = [
    'One', 'Two', 'Three', 'Four', 'Five', 'Six', 'Seven', 'Eight', 'Nine', 'Ten', 'Eleven', 'Twelve', 'Thirteen',
    'Fourteen', 'Fifteen', 'Sixteen', 'Seventeen', 'Eighteen', 'Nineteen', 'Twenty',
]
# The four criteria a speaking answer is scored on (the "How you are scored" card): percent, icon, name.
SCORING = [(25, '🧩', 'Grammar'), (25, '🧠', 'Vocabulary'), (25, '🌊', 'Fluency'), (25, '🗣️', 'Pronunciation')]


class SpeakingPart(models.IntegerChoices):
    PART_11 = 1, 'Part 1.1'
    PART_12 = 2, 'Part 1.2'
    PART_2 = 3, 'Part 2'
    PART_3 = 4, 'Part 3'


# What the exam asks in each part (the same for every course): icon, what it is about, the timing line shown on the
# part card ({questions} becomes "3 questions"), how many seconds a set of n questions takes to answer and, for the
# parts whose practice session exists, its timings (think / talk seconds for every question).
PART_RULES = {
    SpeakingPart.PART_11: {
        'icon': '💬', 'tagline': 'Questions about you',
        'details': '{questions} · 5 sec to think · 30 sec to talk',
        'seconds': lambda n: n * (THINK_SECONDS_11 + TALK_SECONDS_11),
        'session': {'think': THINK_SECONDS_11, 'talk': TALK_SECONDS_11},
    },
    SpeakingPart.PART_12: {
        'icon': '🖼️', 'tagline': 'Talk about two pictures',
        'details': '{questions} · first: 10 sec + 45 sec · then: 5 sec + 30 sec',
        'seconds': lambda n: (10 + 45) + max(n - 1, 0) * (5 + 30),
        'session': None,
    },
    SpeakingPart.PART_2: {
        'icon': '🧭', 'tagline': 'Three questions, one long answer',
        'details': '1 min to prepare · 2 min to talk',
        'seconds': lambda n: 60 + 120,
        'session': None,
    },
    SpeakingPart.PART_3: {
        'icon': '⚖️', 'tagline': 'Discuss both sides of a topic',
        'details': '1 min to prepare · 2 min to talk',
        'seconds': lambda n: 60 + 120,
        'session': None,
    },
}


def set_name(number):
    """"Set One", "Set Two"... (plain numbers after Set Twenty)."""
    return f'Set {SET_NAMES[number - 1] if 1 <= number <= len(SET_NAMES) else number}'


def questions_label(count):
    return f"{count} question{'' if count == 1 else 's'}"


def part_details(part, question_count=DEFAULT_QUESTIONS):
    """The timing line of a part card, e.g. "3 questions · 5 sec to think · 30 sec to talk"."""
    return PART_RULES[part]['details'].format(questions=questions_label(question_count))


def part_info(part, question_count=DEFAULT_QUESTIONS):
    """What a template needs to draw a part: number, label, icon, tagline and the timing line."""
    rules = PART_RULES[part]
    return {
        'number': part.value, 'label': part.label, 'icon': rules['icon'], 'tagline': rules['tagline'],
        'details': part_details(part, question_count),
    }


def minutes_label(part, question_count):
    """"2 minutes": how long a set of this part takes, rounded to whole minutes (shown as "about 2 minutes")."""
    minutes = max(1, int(PART_RULES[part]['seconds'](question_count) / 60 + 0.5))
    return f"{minutes} minute{'' if minutes == 1 else 's'}"


class SpeakingSet(models.Model):
    """A set of practice questions of one part ("Set One": three questions to answer out loud)."""

    course = models.ForeignKey(Course, on_delete=models.CASCADE, related_name='speaking_sets')
    part = models.PositiveSmallIntegerField(choices=SpeakingPart.choices)
    number = models.PositiveSmallIntegerField()

    class Meta:
        ordering = ['part', 'number']
        constraints = [
            models.UniqueConstraint(fields=['course', 'part', 'number'], name='unique_speaking_set_number'),
        ]

    def __str__(self):
        return f'{self.course} · {self.get_part_display()} · {self.title}'

    @property
    def title(self):
        return set_name(self.number)

    @property
    def rules(self):
        return PART_RULES[self.part]

    def get_absolute_url(self):
        return reverse('speaking:ready', kwargs={'slug': self.course.slug, 'part': self.part, 'set_pk': self.pk})


class SpeakingQuestion(models.Model):
    set = models.ForeignKey(SpeakingSet, on_delete=models.CASCADE, related_name='questions')
    order = models.PositiveSmallIntegerField()
    text = models.CharField(max_length=300)

    class Meta:
        ordering = ['order']
        constraints = [
            models.UniqueConstraint(fields=['set', 'order'], name='unique_speaking_question_order'),
        ]

    def __str__(self):
        return self.text


class SpeakingPractice(models.Model):
    """A set a student has practised ("✓ 1 / 3 practised", "Practise this again ✓")."""

    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='speaking_practices')
    set = models.ForeignKey(SpeakingSet, on_delete=models.CASCADE, related_name='practices')
    practised_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=['user', 'set'], name='unique_speaking_practice'),
        ]

    def __str__(self):
        return f'{self.user} · {self.set}'


# The longest transcript of one answer that is kept (and sent to the AI).
MAX_TRANSCRIPT_LENGTH = 2000
# The kinds of recording a browser makes (MediaRecorder) and the file extension each is stored with.
AUDIO_EXTENSIONS = {
    'audio/webm': '.webm', 'video/webm': '.webm', 'audio/ogg': '.ogg', 'audio/mp4': '.m4a', 'audio/mpeg': '.mp3',
    'audio/wav': '.wav', 'audio/x-wav': '.wav',
}
AUDIO_CONTENT_TYPES = {'.webm': 'audio/webm', '.ogg': 'audio/ogg', '.m4a': 'audio/mp4', '.mp3': 'audio/mpeg', '.wav': 'audio/wav'}


def answer_audio_path(instance, filename):
    """Recordings get an unguessable name; they are only ever served to their owner and to admins."""
    extension = os.path.splitext(filename)[1].lower()
    return f'speaking/answers/{uuid.uuid4().hex}{extension if extension in AUDIO_CONTENT_TYPES else ".webm"}'


class SpeakingAttempt(models.Model):
    """One run through a set: what the student said, the coins earned and the AI feedback on it."""

    class Feedback(models.TextChoices):
        PENDING = 'pending', 'Pending'
        READY = 'ready', 'Ready'
        UNCONFIGURED = 'unconfigured', 'AI is not set up'
        FAILED = 'failed', 'AI request failed'
        EMPTY = 'empty', 'Nothing to check'

    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='speaking_attempts')
    set = models.ForeignKey(SpeakingSet, on_delete=models.CASCADE, related_name='attempts')
    created_at = models.DateTimeField(auto_now_add=True)
    coins = models.PositiveSmallIntegerField(default=0)
    feedback_status = models.CharField(max_length=20, choices=Feedback.choices, default=Feedback.PENDING)
    feedback_error = models.CharField(max_length=300, blank=True)

    class Meta:
        ordering = ['-created_at', '-pk']

    def __str__(self):
        return f'{self.user} · {self.set} · {self.created_at:%d.%m.%Y %H:%M}'

    def get_absolute_url(self):
        return reverse('speaking:result', kwargs={'slug': self.set.course.slug, 'attempt_pk': self.pk})


class SpeakingAnswer(models.Model):
    """The answer to one question of an attempt: the recording, what the speech recogniser heard and the feedback."""

    attempt = models.ForeignKey(SpeakingAttempt, on_delete=models.CASCADE, related_name='answers')
    order = models.PositiveSmallIntegerField()
    question = models.CharField(max_length=300)  # the wording at the time: the question may be edited later
    transcript = models.TextField(blank=True)
    audio = models.FileField(upload_to=answer_audio_path, blank=True)
    seconds = models.FloatField(default=0)
    finished_early = models.BooleanField(default=False)
    confidence = models.FloatField(null=True, blank=True)
    feedback = models.JSONField(default=dict, blank=True)

    class Meta:
        ordering = ['order']
        constraints = [
            models.UniqueConstraint(fields=['attempt', 'order'], name='unique_speaking_answer_order'),
        ]

    def __str__(self):
        return f'{self.attempt} · {self.number}'

    @property
    def number(self):
        return self.order + 1

    @property
    def audio_content_type(self):
        return AUDIO_CONTENT_TYPES.get(os.path.splitext(self.audio.name)[1].lower(), 'audio/webm')
