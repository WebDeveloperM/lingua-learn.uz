from django.db import models
from django.urls import reverse
from django.utils.text import slugify


class Category(models.TextChoices):
    GRAMMAR = 'grammar', 'Grammatika'
    VOCABULARY = 'vocabulary', "Lug'at (Vocabulary)"
    READING = 'reading', 'Reading'
    WRITING = 'writing', 'Writing'
    SPEAKING = 'speaking', 'Speaking'
    LISTENING = 'listening', 'Listening'


CATEGORY_ICONS = {
    Category.GRAMMAR: '🧩',
    Category.VOCABULARY: '🧠',
    Category.READING: '📖',
    Category.WRITING: '✍️',
    Category.SPEAKING: '🎤',
    Category.LISTENING: '🎧',
}


class Level(models.TextChoices):
    BEGINNER = 'beginner', 'Beginner Level'
    INTERMEDIATE = 'intermediate', 'Intermediate Level'
    ADVANCED = 'advanced', 'Advanced Level'


class Course(models.Model):
    title = models.CharField(max_length=255)
    slug = models.SlugField(max_length=255, unique=True, blank=True)
    category = models.CharField(max_length=20, choices=Category.choices, default=Category.GRAMMAR)
    level = models.CharField(max_length=20, choices=Level.choices, default=Level.INTERMEDIATE)
    cefr_badge = models.CharField(
        max_length=50, blank=True,
        help_text="Masalan: B2 Upper-Intermediate",
    )

    short_description = models.TextField(
        help_text="Kurs sarlavhasi ostidagi qisqa tavsif (hero bo'limda)",
    )

    cover_image = models.ImageField(upload_to='courses/covers/', blank=True, null=True)

    publisher_name = models.CharField(max_length=255, default="Advance Learning - Learn English")
    publisher_logo = models.ImageField(upload_to='courses/publishers/', blank=True, null=True)

    enrolled_count = models.PositiveIntegerField(default=0)
    positive_ratings_count = models.PositiveIntegerField(default=0)
    duration_text = models.CharField(max_length=100, default="1.5-3 Hours (Contains Video)")
    language = models.CharField(max_length=50, default="English")
    is_cpd_accredited = models.BooleanField(default=True)

    about_this_course = models.TextField(blank=True)
    course_description = models.TextField(blank=True)

    is_published = models.BooleanField(default=True)
    is_new = models.BooleanField("Yangi", default=False, help_text='Kurs kartochkasida "YANGI" belgisini ko\'rsatadi')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return self.title

    def save(self, *args, **kwargs):
        if not self.slug:
            base_slug = slugify(self.title)[:240] or 'kurs'
            slug = base_slug
            n = 1
            while Course.objects.filter(slug=slug).exclude(pk=self.pk).exists():
                n += 1
                slug = f"{base_slug}-{n}"
            self.slug = slug
        super().save(*args, **kwargs)

    def get_absolute_url(self):
        return reverse('courses:course_detail', kwargs={'slug': self.slug})

    @property
    def icon(self):
        return CATEGORY_ICONS[self.category]


class LearningOutcome(models.Model):
    course = models.ForeignKey(Course, on_delete=models.CASCADE, related_name='learning_outcomes')
    text = models.CharField(max_length=255)
    order = models.PositiveSmallIntegerField(default=0)

    class Meta:
        ordering = ['order', 'id']

    def __str__(self):
        return self.text


class SkillTag(models.Model):
    course = models.ForeignKey(Course, on_delete=models.CASCADE, related_name='skill_tags')
    name = models.CharField(max_length=100)
    highlighted = models.BooleanField(default=False)
    order = models.PositiveSmallIntegerField(default=0)

    class Meta:
        ordering = ['order', 'id']

    def __str__(self):
        return self.name


class Enrollment(models.Model):
    user = models.ForeignKey('accounts.User', on_delete=models.CASCADE, related_name='enrollments')
    course = models.ForeignKey(Course, on_delete=models.CASCADE, related_name='enrollments')
    enrolled_at = models.DateTimeField(auto_now_add=True)
    progress_percent = models.PositiveSmallIntegerField(default=0)

    class Meta:
        unique_together = ('user', 'course')

    def __str__(self):
        return f"{self.user} -> {self.course}"


class Part(models.Model):
    """A numbered section of a practice course (e.g. "Part 1 · Short replies")."""

    class Kind(models.TextChoices):
        CHOICE = 'choice', 'Variantlardan tanlash (A, B, C)'
        GAP_FILL = 'gap_fill', "Eshitib yozish (bo'sh joyni to'ldirish)"
        MATCHING = 'matching', "Ro'yxatdan tanlash (moslashtirish)"
        MAP = 'map', "Xaritada belgilash (rasmdagi harfni tanlash)"
        PASSAGE_GAP = 'passage_gap', "Matndagi bo'sh joylar (so'zni yozish)"
        PASSAGE_MIXED = 'passage_mixed', "Matn: bo'sh joylar va undan keyin test savollari"

    course = models.ForeignKey(Course, on_delete=models.CASCADE, related_name='parts')
    number = models.PositiveSmallIntegerField()
    name = models.CharField(max_length=100)
    icon = models.CharField(max_length=16, blank=True)
    kind = models.CharField(max_length=20, choices=Kind.choices, default=Kind.CHOICE)
    first_question_number = models.PositiveSmallIntegerField(
        default=1,
        help_text="Bu Part mashqlaridagi birinchi savol raqami (savollar Part'lar bo'ylab davom etadi).",
    )
    questions_count = models.PositiveSmallIntegerField(
        default=0,
        help_text="Mashqda nechta savol bo'lishi (admin muharririda shuncha qator ochiladi). 0 bo'lsa, turiga qarab olinadi.",
    )
    instructions = models.TextField(
        blank=True,
        help_text="Mashq sahifasida audio ostida ko'rinadi. **matn** qalin bo'ladi.",
    )

    # How many questions an exercise usually has, by kind (used while `questions_count` is 0).
    # (a "gaps, then test" Part counts only its test questions here: its gaps come from the text itself)
    USUAL_QUESTIONS = {
        Kind.CHOICE: 8, Kind.GAP_FILL: 6, Kind.MATCHING: 4, Kind.MAP: 5, Kind.PASSAGE_GAP: 6, Kind.PASSAGE_MIXED: 2,
    }

    class Meta:
        ordering = ['number']
        constraints = [
            models.UniqueConstraint(fields=['course', 'number'], name='unique_part_number_per_course'),
        ]

    def __str__(self):
        return f"Part {self.number} · {self.name}"

    @property
    def expected_questions(self):
        return self.questions_count or self.USUAL_QUESTIONS[self.kind]

    @property
    def needs_audio(self):
        """Only Listening exercises are played from a recording; Reading and the others have no audio."""
        return self.course.category == Category.LISTENING


class KeyWord(models.Model):
    """A word of a Part's key vocabulary: one of the cards students see when they open "Key vocabulary"."""

    part = models.ForeignKey(Part, on_delete=models.CASCADE, related_name='key_words')
    order = models.PositiveSmallIntegerField(default=0)
    word = models.CharField(max_length=100)
    transcription = models.CharField(max_length=100, blank=True, help_text="Talaffuz belgilari, / belgilarisiz: ˈpensl")
    meaning = models.CharField(max_length=200, help_text="So'zning o'zbekcha ma'nosi.")
    example = models.CharField(max_length=300, blank=True)

    class Meta:
        ordering = ['order', 'pk']

    def __str__(self):
        return f'{self.word} — {self.meaning}'


class Exercise(models.Model):
    part = models.ForeignKey(Part, on_delete=models.CASCADE, related_name='exercises')
    number = models.PositiveSmallIntegerField()
    audio = models.FileField(upload_to='practice/audio/', blank=True)
    duration_minutes = models.PositiveSmallIntegerField(default=5)
    title = models.CharField(
        max_length=200, blank=True,
        help_text="Eshitib yozish mashqlarida bo'sh joylar tepasida ko'rinadigan sarlavha (masalan: Video game review).",
    )
    instructions = models.TextField(
        blank=True,
        help_text="Bo'sh qoldirilsa, Part ko'rsatmasi ishlatiladi. **matn** qalin bo'ladi.",
    )
    options = models.TextField(
        blank=True,
        help_text="Ro'yxatdan tanlash mashqlari uchun variantlar: har qatorga bittadan (A, B, C... avtomatik qo'yiladi).",
    )
    image = models.ImageField(
        upload_to='practice/images/', blank=True,
        help_text="Xaritada belgilash mashqlari uchun xarita rasmi.",
    )
    letters_count = models.PositiveSmallIntegerField(
        default=0,
        help_text="Xarita mashqlarida javob harflari soni, A dan boshlab (9 — A dan I gacha).",
    )
    transcript = models.TextField(
        blank=True,
        help_text="Audio matni: natijalar sahifasida ko'rsatiladi. To'g'ri javobli joylar **qalin** belgilansa, ajralib turadi.",
    )
    passage = models.TextField(
        blank=True,
        help_text="Reading matni. Bo'sh joylar [[so'z]] ko'rinishida belgilanadi (har biri bitta savol).",
    )

    class Meta:
        ordering = ['number']
        constraints = [
            models.UniqueConstraint(fields=['part', 'number'], name='unique_exercise_number_per_part'),
        ]

    MAX_OPTIONS = 10

    def __str__(self):
        return f"{self.part} · Exercise {self.number}"

    @property
    def question_count(self):
        annotated = getattr(self, 'questions_total', None)
        return self.questions.count() if annotated is None else annotated

    @property
    def effective_instructions(self):
        return self.instructions or self.part.instructions

    @property
    def option_list(self):
        """(letter, text) pairs the student can pick from: typed options, or bare map letters."""
        if self.part.kind == Part.Kind.MAP:
            return [(chr(ord('a') + index), '') for index in range(min(self.letters_count, self.MAX_OPTIONS))]
        lines = [line.strip() for line in self.options.splitlines() if line.strip()]
        return [(chr(ord('a') + index), text) for index, text in enumerate(lines[:self.MAX_OPTIONS])]

    @property
    def is_ready(self):
        if self.question_count == 0 or (self.part.needs_audio and not self.audio):
            return False
        kind = self.part.kind
        if kind in (Part.Kind.MATCHING, Part.Kind.MAP) and len(self.option_list) < 2:
            return False
        if kind == Part.Kind.MAP and not self.image:
            return False
        if kind in (Part.Kind.PASSAGE_GAP, Part.Kind.PASSAGE_MIXED) and not self.passage.strip():
            return False
        return True


class Question(models.Model):
    """One question of an exercise; which fields are used depends on the Part's kind.

    choice:   optional `text` and `intro`, `option_a/b/c` and an optional `option_d`, `correct` (a to d)
    gap_fill: `text` (label), `text_before`, `text_after`, `answer` (accepted answers separated by "/"),
              optional `intro` (a plain line without a gap, shown above this one)
    passage_gap: only `answer`; the rows are generated from the [[gaps]] of the exercise's `passage`
    passage_mixed: the gap rows of passage_gap first, then ordinary choice rows
    (a row with `option_a` filled in is a choice question, whatever its Part's kind)
    matching: `text` ("Speaker 1", or a whole paragraph), optional bold `label` ("Paragraph I"),
              `correct` (letter of the exercise's option list)
    map:      `text` (e.g. "Gift shop"), `correct` (letter on the map)
    """

    class Option(models.TextChoices):
        A = 'a', 'A'
        B = 'b', 'B'
        C = 'c', 'C'
        D = 'd', 'D'
        E = 'e', 'E'
        F = 'f', 'F'
        G = 'g', 'G'
        H = 'h', 'H'
        I = 'i', 'I'
        J = 'j', 'J'

    exercise = models.ForeignKey(Exercise, on_delete=models.CASCADE, related_name='questions')
    order = models.PositiveSmallIntegerField(default=0)
    intro = models.CharField(
        max_length=500, blank=True,
        help_text="Shu savoldan oldin alohida kartochkada chiqadi (masalan: **Extract One** · You hear ...).",
    )
    label = models.CharField(
        max_length=120, blank=True,
        help_text="Savol raqami yonida qalin yoziladigan sarlavha (masalan: Paragraph I).",
    )
    text = models.TextField(blank=True)
    text_before = models.CharField(max_length=255, blank=True)
    text_after = models.CharField(max_length=255, blank=True)
    answer = models.CharField(max_length=255, blank=True)
    option_a = models.CharField(max_length=255, blank=True)
    option_b = models.CharField(max_length=255, blank=True)
    option_c = models.CharField(max_length=255, blank=True)
    option_d = models.CharField(max_length=255, blank=True)
    correct = models.CharField(max_length=1, choices=Option.choices, default=Option.A)

    class Meta:
        ordering = ['order', 'id']

    def __str__(self):
        return self.text or self.answer or self.option_a

    @property
    def is_choice(self):
        return bool(self.option_a)

    @property
    def options(self):
        """(letter, text) of the options this question offers: A–C always, D only when it was written."""
        offered = [('a', self.option_a), ('b', self.option_b), ('c', self.option_c)]
        return offered + [('d', self.option_d)] if self.option_d else offered


class ExerciseResult(models.Model):
    user = models.ForeignKey('accounts.User', on_delete=models.CASCADE, related_name='exercise_results')
    exercise = models.ForeignKey(Exercise, on_delete=models.CASCADE, related_name='results')
    score = models.PositiveSmallIntegerField()
    total = models.PositiveSmallIntegerField()
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=['user', 'exercise'], name='unique_result_per_user_exercise'),
        ]

    def __str__(self):
        return f"{self.user} · {self.exercise}: {self.score}/{self.total}"
