import io
import tempfile
import wave
from io import StringIO

from django.core.files.base import ContentFile
from django.core.management import call_command
from django.test import override_settings

from .models import Exercise, Question

EXPECTED_PARTS = [
    (1, 'Short replies', 10),
    (2, 'Gap filling', 11),
    (3, 'Speakers', 10),
    (4, 'Map labelling', 11),
    (5, 'Extracts', 10),
    (6, 'Lecture notes', 10),
]
TOTAL_EXERCISES = sum(count for _, _, count in EXPECTED_PARTS)


def seed(**options):
    call_command('seed_listening_parts', stdout=StringIO(), **options)


def seed_reading(**options):
    call_command('seed_reading_parts', stdout=StringIO(), **options)


def make_wav(seconds=1, rate=8000):
    """A silent 16-bit mono WAV, good enough as a stand-in for an exercise recording."""
    buffer = io.BytesIO()
    with wave.open(buffer, 'wb') as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(rate)
        wav.writeframes(b'\x00\x00' * rate * seconds)
    return buffer.getvalue()


def make_ready_exercise(part_number=1, exercise_number=1, questions=3, minutes=5):
    """Give an exercise an audio file and `questions` questions whose correct options cycle a, b, c."""
    exercise = Exercise.objects.get(part__number=part_number, number=exercise_number)
    exercise.audio.save('listening.wav', ContentFile(make_wav()), save=False)
    exercise.duration_minutes = minutes
    exercise.save()
    for index in range(questions):
        Question.objects.create(
            exercise=exercise, order=index, text='' if index else 'Where is the library?',
            option_a=f'A{index}', option_b=f'B{index}', option_c=f'C{index}', correct='abc'[index % 3],
        )
    return exercise


def _give_audio(exercise, minutes):
    exercise.audio.save('listening.wav', ContentFile(make_wav()), save=False)
    exercise.duration_minutes = minutes


def make_gap_exercise(part_number=2, exercise_number=1, minutes=6):
    """A write-what-you-hear exercise with three gaps (answers: space station / futuristic city, history, gamingworld)."""
    exercise = Exercise.objects.get(part__number=part_number, number=exercise_number)
    _give_audio(exercise, minutes)
    exercise.title = 'Video game review'
    exercise.save()
    rows = [
        {'text': 'Action takes place in:', 'text_before': 'a', 'answer': 'space station / futuristic city'},
        {'text': 'Players answer questions about:', 'answer': 'history'},
        {'text': 'Website for more details:', 'text_before': 'www.', 'text_after': '.com', 'answer': 'gamingworld'},
    ]
    for index, row in enumerate(rows):
        Question.objects.create(exercise=exercise, order=index, **row)
    return exercise


LECTURE_NOTE = 'Labyrinths represent a journey through life.'
# (text before the gap, text after it, answer); the plain line above question 32 is LECTURE_NOTE
LECTURE_LINES = [
    ('Mazes are a type of', '.', 'puzzle'),
    ('The word maze comes from a word meaning a feeling of', '.', 'confusion'),
    ('They have often been used in', 'and prayer.', 'meditation / worship'),
    ('Ancient carvings on', 'have been found across many cultures.', 'rocks'),
    ('Ancient Greeks used the symbol on', '.', 'coins'),
    ('The surviving example of a turf labyrinth once had a big', 'at its centre.', 'tree'),
]


def make_lecture_exercise(part_number=6, exercise_number=1, minutes=8):
    """Lecture notes (questions 30–35): six gaps, a heading and a plain line between gaps 31 and 32."""
    exercise = Exercise.objects.get(part__number=part_number, number=exercise_number)
    _give_audio(exercise, minutes)
    exercise.title = 'Labyrinths'
    exercise.save()
    for index, (before, after, answer) in enumerate(LECTURE_LINES):
        Question.objects.create(
            exercise=exercise, order=index, text_before=before, text_after=after, answer=answer,
            intro=LECTURE_NOTE if index == 2 else '',
        )
    return exercise


OLIVIA_PASSAGE = (
    'Olivia likes traveling and visiting new places. Last summer, she went to a seaside town with her family. '
    'Although the [[town]] was small, it was really wonderful. They chose a hotel that had a beautiful view of the sea. '
    'In the mornings, they went swimming in the [[sea]], and they also went to different restaurants in the town '
    'to try various foods. The [[foods]] were very delicious. They wanted to go on a boat trip, but she had never '
    'been on a [[boat]] before. For the trip, they went to an island. The [[island]] was full of colorful flowers. '
    'They took photos of the [[flowers]].'
)
OLIVIA_ANSWERS = ['town', 'sea', 'foods', 'boat', 'island', 'flowers']


def make_passage_exercise(part_number=1, exercise_number=1, minutes=8, passage=OLIVIA_PASSAGE):
    """A Reading exercise with a text and six gaps inside it (no audio): Olivia, answers town … flowers."""
    from .passages import sync_passage_questions

    exercise = Exercise.objects.get(part__course__category='reading', part__number=part_number, number=exercise_number)
    exercise.title = 'Olivia'
    exercise.passage = passage
    exercise.duration_minutes = minutes
    exercise.save()
    sync_passage_questions(exercise)
    return exercise


MEAT_TEXT = (  # Reading Part 4: a text to read, no gaps in it
    'Do you hate the idea of animal-free meat? Many people do. Unsurprisingly, livestock farmers are often furiously '
    'opposed. More surprisingly, so are some vegans.\n\n'
    'So, here\'s a question for all the sceptics. Already, 60% of the mammals on Earth by weight are livestock. Humans '
    'account for 36%, and wild mammals account for just 4%.\n\n'
    'So far, only one of the people I\'ve asked has answered it directly: the food campaigner Vandana Shiva.\n\n'
    'It\'s as if we were urging people to burn less fossil fuel without offering a replacement. Meat is consuming the planet.'
)
MEAT_QUESTIONS = [  # (intro card, text, options, correct letter): 21–24 are A–D, 25–29 are True / False / Not given
    ('**Questions 21-24:** choose the correct answer A, B, C or D.', 'New type of meat is ....',
     ['not for vegans', 'prepared for vegans', 'only made from plants', "for people who don't like meat"], 'a'),
    ('', 'The biggest part of the mammals on our planet are ....', ['people', 'poultry', 'livestock', 'wild mammals'], 'c'),
    ('', 'In some cultures, consuming meat is ....', ['the same as in the UK', 'staying still', 'decreasing', 'rising'], 'd'),
    ('', 'The writer thinks livestock farming is ....', ['harmless', 'a small problem', 'a big problem', 'improving'], 'c'),
] + [
    ('**Questions 25-29:** write True, False or Not given.' if number == 25 else '', f'Statement number {number}.',
     ['True', 'False', 'Not given'], 'abc'[number % 3])
    for number in range(25, 30)
]


def make_meat_exercise(part_number=4, exercise_number=1, minutes=15):
    """Reading Part 4: a titled text and nine test questions (21–29) under it; no audio."""
    exercise = Exercise.objects.get(part__course__category='reading', part__number=part_number, number=exercise_number)
    exercise.title = 'Eating meat'
    exercise.passage = MEAT_TEXT
    exercise.duration_minutes = minutes
    exercise.save()
    for index, (intro, text, options, correct) in enumerate(MEAT_QUESTIONS):
        Question.objects.create(
            exercise=exercise, order=index, intro=intro, text=text, correct=correct,
            option_a=options[0], option_b=options[1], option_c=options[2], option_d=options[3] if len(options) > 3 else '',
        )
    return exercise


SUMMARY_PASSAGE = (  # Reading Part 5: gaps 30–33 inside the text, then two test questions
    'The city of Riverton grew quickly. By 1900 its [[port]] was one of the busiest in the country. A new [[bridge]] '
    'joined the two banks, and every Friday a large [[market]] filled the square below the old [[tower]].'
)
SUMMARY_ANSWERS = ['port', 'bridge', 'market', 'tower']


def make_summary_exercise(part_number=5, exercise_number=1, minutes=12):
    """Reading Part 5: four gaps (30–33) and two choice questions (34–35, correct b and d), no audio."""
    from .passages import sync_passage_questions

    exercise = Exercise.objects.get(part__course__category='reading', part__number=part_number, number=exercise_number)
    exercise.title = 'Riverton'
    exercise.passage = SUMMARY_PASSAGE
    exercise.duration_minutes = minutes
    exercise.save()
    sync_passage_questions(exercise)
    rows = [
        ('**Questions 34-35:** choose the correct answer A, B, C or D.', 'Riverton became famous because of its ....',
         ['castle', 'port', 'university', 'railway'], 'b'),
        ('', 'The writer describes the Friday market as ....', ['small', 'quiet', 'dangerous', 'large'], 'd'),
    ]
    for offset, (intro, text, options, correct) in enumerate(rows):
        Question.objects.create(
            exercise=exercise, order=len(SUMMARY_ANSWERS) + offset, intro=intro, text=text, correct=correct,
            option_a=options[0], option_b=options[1], option_c=options[2], option_d=options[3],
        )
    return exercise


WALK_OPTIONS = [  # Reading Part 2: "Each statement is used once. Two are extra!"
    'You want a peaceful short walk and a chance to enjoy a tea shop.',
    'You want your kids to have outdoor fun and see animals.',
    'You are an experienced hiker who enjoys wild, remote landscapes.',
    'You want a long but gentle walk with scenic countryside views.',
    'You want to see historical buildings and enjoy nature.',
    'You prefer a quiet walk with a chance to explore rivers and wildlife.',
    'You want to explore a village, visit small shops, and rest in cafes.',
    'You want to walk near water and let your children try safe water sports.',
    'You enjoy guided nature walks and want to visit ruins.',
    'You want to walk in flower gardens with short guided tours.',
]
WALKS = [  # questions 7–14: (text, correct letter)
    ("Willow Farm is perfect for families. Kids can meet animals, ride ponies, and enjoy the outdoor playground. "
     "There's also a short trail through the trees, with signs showing animal facts. A peaceful place for children and parents.", 'b'),
    ("Northpoint Ridge offers a tough hike through wild hills and rocky paths. It takes about six hours and is only for "
     "experienced walkers. There are no cafés, just open views, silence, and nature. Don't forget water and snacks!", 'c'),
    ("Walk along the Meadowlake trail beside a gentle stream and grassy fields. This calm two-hour walk is ideal for "
     "spotting birds and flowers. Perfect if you enjoy nature, but want a peaceful, relaxing experience away from busy roads.", 'f'),
    ("Visit Rosehill Manor and explore its colorful flower gardens. Join one of the short guided tours offered every hour. "
     "The nearby teahouse serves snacks and drinks. It's a lovely place for quiet walks and peaceful afternoons in nature.", 'j'),
    ('Stonebridge is a small village with a market, little shops and cafes around the green.', 'g'),
    ('The Old Mill Path leads past ruins, with a guide who explains the history of the valley.', 'i'),
    ('Lakeside Park has a calm bay where children can try kayaks and paddle boats.', 'h'),
    ('Greenfield Lane is a gentle countryside route with wide views over the hills.', 'd'),
]


def make_statements_exercise(part_number=2, exercise_number=1, minutes=10):
    """Reading Part 2: ten statements (A–J) and eight paragraphs (7–14) to match them with; no audio."""
    exercise = Exercise.objects.get(part__course__category='reading', part__number=part_number, number=exercise_number)
    exercise.options = '\n'.join(WALK_OPTIONS)
    exercise.duration_minutes = minutes
    exercise.save()
    for index, (text, correct) in enumerate(WALKS):
        Question.objects.create(exercise=exercise, order=index, text=text, correct=correct)
    return exercise


HEADINGS = [  # Reading Part 3: more headings than paragraphs
    'A negative impact on certain types of stores',
    'How citizens were persuaded',
    'A plan with clear environmental goals',
    'The origins of traffic-free shopping areas',
    'Unexpected advantages for business',
    'Initial objections to the scheme',
    'A system copied worldwide',
    'When the modern idea began',
]
PARAGRAPHS = [  # questions 15–20: (label, text, correct letter)
    ('Paragraph I', 'Modern traffic-free shopping streets may seem like a new idea, but they actually have a long '
                    'history. Even in ancient Rome, daytime traffic was banned in the city center to create safer '
                    'shopping conditions. Similarly, in the Middle East, souks were built centuries ago where only '
                    'pedestrians could enter, prioritizing comfort and safety for shoppers.', 'd'),
    ('Paragraph II', 'The first modern pedestrian street opened in Germany after the war, when city centers were rebuilt.', 'h'),
    ('Paragraph III', 'Not everyone welcomed the idea. Many shopkeepers feared it would hurt their sales, believing that '
                      'without car access customers would stay away.', 'f'),
    ('Paragraph IV', 'Surprisingly, sales rose in most streets once the cars had gone.', 'e'),
    ('Paragraph V', 'Cities explained the plan with meetings, trials and clear targets for cleaner air.', 'c'),
    ('Paragraph VI', 'Today pedestrian zones can be found on every continent.', 'g'),
]


def make_headings_exercise(part_number=3, exercise_number=1, minutes=10):
    """Reading Part 3: a titled text-less list of eight headings and six labelled paragraphs (15–20)."""
    exercise = Exercise.objects.get(part__course__category='reading', part__number=part_number, number=exercise_number)
    exercise.title = 'Pedestrian Zones and Their Growth'
    exercise.options = '\n'.join(HEADINGS)
    exercise.duration_minutes = minutes
    exercise.save()
    for index, (label, text, correct) in enumerate(PARAGRAPHS):
        Question.objects.create(exercise=exercise, order=index, label=label, text=text, correct=correct)
    return exercise


MATCHING_OPTIONS = [
    'Arriving late for everything.',
    'Doing too much exercise.',
    'Buying unnecessary items.',
    'Watching too much television.',
    'Spending too much time online.',
    'Oversleeping.',
]


def make_matching_exercise(part_number=3, exercise_number=1, minutes=5):
    """A choose-from-a-list exercise: Speaker 1-4 with correct letters d, a, e, c."""
    exercise = Exercise.objects.get(part__number=part_number, number=exercise_number)
    _give_audio(exercise, minutes)
    exercise.options = '\n'.join(MATCHING_OPTIONS)
    exercise.instructions = (
        'You will hear people speaking about habits they find difficult to control. '
        'Match each speaker (15–18) to their habit (A–F). There are **TWO extra** options which you do not need to use.'
    )
    exercise.save()
    for index, correct in enumerate('daec'):
        Question.objects.create(exercise=exercise, order=index, text=f'Speaker {index + 1}', correct=correct)
    return exercise


def make_png(size=(40, 30), color=(60, 160, 90)):
    """A tiny valid PNG, good enough as a stand-in for a map picture."""
    from PIL import Image

    buffer = io.BytesIO()
    Image.new('RGB', size, color).save(buffer, format='PNG')
    return buffer.getvalue()


MAP_PLACES = ['Gift shop', 'Beehives', 'Holiday cottages', 'Dairy', 'Museum']


def make_map_exercise(part_number=4, exercise_number=1, minutes=5):
    """A map-labelling exercise: five places (19–23) to label with letters A–I, correct letters c, a, h, e, b."""
    exercise = Exercise.objects.get(part__number=part_number, number=exercise_number)
    _give_audio(exercise, minutes)
    exercise.image.save('map.png', ContentFile(make_png()), save=False)
    exercise.letters_count = 9
    exercise.instructions = (
        'You will hear someone giving a talk. Label the places (19–23) on the map (A–I). '
        'There are **FOUR extra** options which you do not need to use.'
    )
    exercise.save()
    for index, (place, correct) in enumerate(zip(MAP_PLACES, 'caheb')):
        Question.objects.create(exercise=exercise, order=index, text=place, correct=correct)
    return exercise


EXTRACT_INTROS = {
    0: '**Extract One** · You hear part of an interview with Fiona, a hotel manager.',
    2: '**Extract Two** · You hear two friends talking about a film.',
    4: '**Extract Three** · You hear a teacher giving advice to students.',
}


def make_extracts_exercise(part_number=5, exercise_number=1, minutes=8):
    """Six A/B/C questions (24–29) in three extracts of two; the correct options are a, b, c, a, b, c."""
    exercise = Exercise.objects.get(part__number=part_number, number=exercise_number)
    _give_audio(exercise, minutes)
    exercise.save()
    for index in range(6):
        Question.objects.create(
            exercise=exercise, order=index, intro=EXTRACT_INTROS.get(index, ''),
            text=f'How does speaker {index + 1} feel?',
            option_a=f'Happy {index}', option_b=f'Sad {index}', option_c=f'Bored {index}', correct='abc'[index % 3],
        )
    return exercise


class TempMediaMixin:
    """Run a TestCase against a throw-away MEDIA_ROOT so uploads never touch real media."""

    @classmethod
    def setUpClass(cls):
        cls._media_dir = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        cls._media_override = override_settings(MEDIA_ROOT=cls._media_dir.name)
        cls._media_override.enable()
        super().setUpClass()

    @classmethod
    def tearDownClass(cls):
        super().tearDownClass()
        cls._media_override.disable()
        cls._media_dir.cleanup()
