from courses.models import Category, Part

from ._practice_seed import PracticeSeedCommand

# (number, icon, name, number of exercises)
LISTENING_PARTS = [
    (1, '💬', 'Short replies', 10),
    (2, '✍️', 'Gap filling', 11),
    (3, '🗣️', 'Speakers', 10),
    (4, '🗺️', 'Map labelling', 11),
    (5, '🎙️', 'Extracts', 10),
    (6, '🧑‍🏫', 'Lecture notes', 10),
]
# Exercise format of each Part: number -> (kind, first question number).
# A Part missing here would keep the default format (choice, starting at question 1).
FORMATS = {
    1: (Part.Kind.CHOICE, 1),
    2: (Part.Kind.GAP_FILL, 9),
    3: (Part.Kind.MATCHING, 15),
    4: (Part.Kind.MAP, 19),
    5: (Part.Kind.CHOICE, 24),
    6: (Part.Kind.GAP_FILL, 30),
}
# Questions per exercise (the admin editor opens with this many rows): 1–8, 9–14, 15–18, 19–23, 24–29, 30–35.
QUESTIONS = {1: 8, 2: 6, 3: 4, 4: 5, 5: 6, 6: 6}
INSTRUCTIONS = {
    1: (
        "You will hear some sentences. You will hear each sentence **twice**. "
        "Choose the correct reply to each sentence (A, B or C)."
    ),
    2: (
        "You will hear someone giving a talk. For each question, fill in the missing information in the "
        "numbered space. Write **ONE WORD and / or A NUMBER** for each answer."
    ),
    4: (
        "You will hear someone giving a talk. Label the places (19–23) on the map (A–I). "
        "There are **FOUR extra** options which you do not need to use."
    ),
    5: (
        "You will hear three extracts. Choose the correct answer (A, B or C) for each question (24–29). "
        "There are **TWO** questions for each extract."
    ),
    6: (
        "You will hear a part of a lecture. For each question, fill in the missing information in the "
        "numbered space. Write **ONE WORD and / or A NUMBER** for each answer."
    ),
}


class Command(PracticeSeedCommand):
    help = "Listening kursiga 6 ta Part va ularning mashqlarini qo'shadi (mavjud ma'lumotni buzmaydi)."
    category = Category.LISTENING
    parts = LISTENING_PARTS
    formats = FORMATS
    questions = QUESTIONS
    instructions = INSTRUCTIONS
