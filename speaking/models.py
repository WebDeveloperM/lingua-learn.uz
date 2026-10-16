from django.conf import settings
from django.db import models
from django.urls import reverse

from courses.models import Course

# How many questions a set has when no set has been entered yet (shown in the part's description line).
DEFAULT_QUESTIONS = 3
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
# part card ({questions} becomes "3 questions") and how many seconds a set of n questions takes to answer.
PART_RULES = {
    SpeakingPart.PART_11: {
        'icon': '💬', 'tagline': 'Questions about you',
        'details': '{questions} · 5 sec to think · 30 sec to talk',
        'seconds': lambda n: n * (5 + 30),
    },
    SpeakingPart.PART_12: {
        'icon': '🖼️', 'tagline': 'Talk about two pictures',
        'details': '{questions} · first: 10 sec + 45 sec · then: 5 sec + 30 sec',
        'seconds': lambda n: (10 + 45) + max(n - 1, 0) * (5 + 30),
    },
    SpeakingPart.PART_2: {
        'icon': '🧭', 'tagline': 'Three questions, one long answer',
        'details': '1 min to prepare · 2 min to talk',
        'seconds': lambda n: 60 + 120,
    },
    SpeakingPart.PART_3: {
        'icon': '⚖️', 'tagline': 'Discuss both sides of a topic',
        'details': '1 min to prepare · 2 min to talk',
        'seconds': lambda n: 60 + 120,
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
