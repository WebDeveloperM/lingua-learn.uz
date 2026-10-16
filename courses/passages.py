"""Reading passages whose missing words are written as [[word]] in the text.

The admin types the whole text and wraps each word the student has to supply in double square brackets
(`Although the [[town]] was small`). The brackets are cut out for the student, who gets a numbered input
in their place; every gap is stored as a Question whose `answer` is the word.
"""
import re

GAP_RE = re.compile(r'\[\[(.+?)\]\]')
PARAGRAPH_RE = re.compile(r'\n\s*\n')
LINE_BREAK_RE = re.compile(r'\s*\n\s*')
MAX_GAPS = 30


def passage_answers(passage):
    """The answers written between [[ ]], in the order they appear."""
    return [match.group(1).strip() for match in GAP_RE.finditer(passage or '')]


def _number_label_re(number):
    """"3." "3)" "3:" "(3)" "Q3" or "(Q3)" at the end of a text: the gap shows its own number already."""
    return re.compile(rf'(?<!\w)(?:\(\s*Q?\s*{number}\s*\)|Q\s*{number}|{number}\s*[.):])\s*$')


def build_passage_blocks(passage, items, number_of=None):
    """Split the passage into paragraphs of pieces: {'text': str} or {'item': items[n]} for its n-th gap.

    A blank line starts a new paragraph; a single line break is only how the text was wrapped, so it reads as a
    space. `items` are whatever the page shows in a gap (questions while answering, review items afterwards);
    a gap without a matching item is dropped rather than leaking its answer. With `number_of`, a typed
    "1." or "(Q1)" right before gap 1 is left out, because the gap prints its own number.
    """
    paragraphs = []
    index = 0
    for raw in PARAGRAPH_RE.split((passage or '').strip()):
        pieces = []
        position = 0
        for match in GAP_RE.finditer(raw):
            if match.start() > position:
                pieces.append({'text': LINE_BREAK_RE.sub(' ', raw[position:match.start()])})
            if index < len(items):
                if number_of and pieces and 'text' in pieces[-1]:
                    text = _number_label_re(number_of(items[index])).sub('', pieces[-1]['text'])
                    if text.strip():
                        pieces[-1]['text'] = text
                    else:
                        pieces.pop()
                pieces.append({'item': items[index]})
            index += 1
            position = match.end()
        if position < len(raw):
            pieces.append({'text': LINE_BREAK_RE.sub(' ', raw[position:])})
        if pieces:
            paragraphs.append(pieces)
    return paragraphs


def passage_paragraphs(passage):
    """The paragraphs of a plain reading text (no gaps): a blank line starts a new one, a single break is a space."""
    return [
        LINE_BREAK_RE.sub(' ', paragraph) for paragraph in PARAGRAPH_RE.split((passage or '').strip()) if paragraph.strip()
    ]


def sync_passage_questions(exercise):
    """Make the exercise's gap questions mirror the gaps of its passage (updating rows in place, in order).

    A row with options is an ordinary test question (the second half of a "gaps, then test" exercise): it is
    left alone and only moved after the gaps, whose rows come first.
    """
    from .models import Question

    answers = passage_answers(exercise.passage)
    existing = list(exercise.questions.all())
    gap_rows = [question for question in existing if not question.is_choice]
    choice_rows = [question for question in existing if question.is_choice]

    for index, answer in enumerate(answers):
        if index < len(gap_rows):
            question = gap_rows[index]
            if (question.answer, question.order) != (answer, index):
                question.answer, question.order = answer, index
                question.save(update_fields=['answer', 'order'])
        else:
            Question.objects.create(exercise=exercise, order=index, answer=answer)
    for question in gap_rows[len(answers):]:
        question.delete()
    for position, question in enumerate(choice_rows, start=len(answers)):
        if question.order != position:
            question.order = position
            question.save(update_fields=['order'])
