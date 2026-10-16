from courses.models import Category, Part

from ._practice_seed import PracticeSeedCommand

# (number, icon, name, number of exercises)
READING_PARTS = [
    (1, '✍️', 'Gap filling', 10),
    (2, '🔗', 'Matching', 10),
    (3, '🏷️', 'Headings', 10),
    (4, '✅', 'Multiple choice & True / False', 10),
    (5, '🧩', 'Summary & questions', 10),
]
FORMATS = {
    1: (Part.Kind.PASSAGE_GAP, 1),      # questions 1–6 (one per gap of the text)
    2: (Part.Kind.MATCHING, 7),         # questions 7–14
    3: (Part.Kind.MATCHING, 15),        # questions 15–20 (paragraphs I–VI; the count can be changed in the panel)
    4: (Part.Kind.CHOICE, 21),          # a text, then test questions 21–29 (21–24 A–D; 25–29 True / False / Not given)
    5: (Part.Kind.PASSAGE_MIXED, 30),   # a text with gaps 30–33, then test questions 34–35
}
# Rows the admin editor opens with: Part 1's questions are the [[gaps]]; in Part 5 only the 2 test questions are rows.
QUESTIONS = {2: 8, 3: 6, 4: 9, 5: 2}
INSTRUCTIONS = {
    1: "Type ONE word for each gap. The word is somewhere in the rest of the text.",
    2: "Each statement is used once. Two are extra!",
    3: (
        "Choose the correct heading for each paragraph. There are more headings than paragraphs, "
        "and you cannot use a heading more than once."
    ),
    4: "Read the following text for questions 21-29.",
}
# minutes: the references show 8 for Part 1, about 10 for Parts 2 and 3 and 15 for Part 4
DURATIONS = {1: 8, 2: 10, 3: 10, 4: 15}


class Command(PracticeSeedCommand):
    help = "Reading kursiga 5 ta Part va ularning mashqlarini qo'shadi (mavjud ma'lumotni buzmaydi)."
    category = Category.READING
    parts = READING_PARTS
    formats = FORMATS
    questions = QUESTIONS
    instructions = INSTRUCTIONS
    durations = DURATIONS
