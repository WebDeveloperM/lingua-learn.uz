from django.core.management.base import BaseCommand, CommandError

from courses.models import Category, Course, Exercise, Part, Question


class PracticeSeedCommand(BaseCommand):
    """Creates the Parts of a practice course and their (empty) exercises, without touching what an admin edited.

    Subclasses describe one skill: `category`, `parts` as (number, icon, name, exercises), `formats` as
    number -> (kind, first question number), `questions` (rows per exercise), `instructions` and `durations`.
    """

    category = None
    parts = ()
    formats = {}
    questions = {}
    instructions = {}
    durations = {}  # number -> minutes for the exercises created by this command
    key_words_count = 50

    def add_arguments(self, parser):
        parser.add_argument('--course', help="Kurs slug'i (berilmasa, birinchi shu skill kursi olinadi)")

    def handle(self, *args, **options):
        if options['course']:
            course = Course.objects.filter(slug=options['course']).first()
        else:
            course = Course.objects.filter(category=self.category).order_by('pk').first()
        if course is None:
            raise CommandError(f"{Category(self.category).label} kursi topilmadi. Avval kurs yarating yoki --course bering.")

        for number, icon, name, exercises_count in self.parts:
            self.seed_part(course, number, icon, name, exercises_count)

        total = Exercise.objects.filter(part__course=course).count()
        self.stdout.write(self.style.SUCCESS(
            f'"{course.title}" ({course.slug}): {course.parts.count()} ta Part, {total} ta mashq.'
        ))

    def seed_part(self, course, number, icon, name, exercises_count):
        kind, first_question = self.formats.get(number, (Part.Kind.CHOICE, 1))
        part, created = Part.objects.get_or_create(
            course=course, number=number,
            defaults={
                'icon': icon, 'name': name, 'key_words_count': self.key_words_count,
                'kind': kind, 'first_question_number': first_question,
                'questions_count': self.questions.get(number, 0),
            },
        )

        changed = []
        if (
            not created and number in self.formats
            and (part.kind, part.first_question_number) == (Part.Kind.CHOICE, 1)
            and not Question.objects.filter(exercise__part=part).exists()
        ):
            # Parts created before their format was known still have the defaults; edited ones
            # (or ones that already hold questions) are left alone.
            part.kind, part.first_question_number = kind, first_question
            changed += ['kind', 'first_question_number']
        if not part.questions_count and number in self.questions:
            part.questions_count = self.questions[number]
            changed.append('questions_count')
        if not part.instructions and number in self.instructions:
            part.instructions = self.instructions[number]
            changed.append('instructions')
        if changed:
            part.save(update_fields=changed)

        defaults = {'duration_minutes': self.durations[number]} if number in self.durations else {}
        standard = Exercise._meta.get_field('duration_minutes').default
        for exercise_number in range(1, exercises_count + 1):
            exercise, created = Exercise.objects.get_or_create(part=part, number=exercise_number, defaults=defaults)
            # An exercise nobody has filled in yet still has the standard time: give it the one its format calls for.
            if defaults and not created and exercise.duration_minutes == standard and not exercise.questions.exists():
                exercise.duration_minutes = defaults['duration_minutes']
                exercise.save(update_fields=['duration_minutes'])
