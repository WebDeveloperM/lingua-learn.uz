from .models import Part

ANSWER_SEPARATOR = '/'


def normalize_answer(text):
    return ' '.join((text or '').casefold().split())


def accepted_answers(answer):
    """The alternatives an admin typed for a gap, e.g. "space / outer space"."""
    return [alternative.strip() for alternative in (answer or '').split(ANSWER_SEPARATOR) if alternative.strip()]


def question_type(part, question):
    """How a question is answered: typing a word ('gap'), picking from the exercise's list ('list') or A–D ('choice')."""
    if part.kind in (Part.Kind.GAP_FILL, Part.Kind.PASSAGE_GAP):
        return 'gap'
    if part.kind == Part.Kind.PASSAGE_MIXED:
        return 'choice' if question.is_choice else 'gap'
    if part.kind in (Part.Kind.MATCHING, Part.Kind.MAP):
        return 'list'
    return 'choice'


def grade_exercise(exercise, post):
    """Check a submitted form against the exercise; returns (review items, score).

    Each review item carries what the result page needs for its question: its `type` (see `question_type`),
    plus `given_display` and `correct_display` (what the answers table shows: typed text, or the letter).
    The question numbers continue across Parts, so the first one is the Part's `first_question_number`.
    """
    part = exercise.part
    labels = {letter: f'{letter.upper()}) {text}' if text else letter.upper() for letter, text in exercise.option_list}
    review = []
    score = 0

    for index, question in enumerate(exercise.questions.all()):
        given = (post.get(f'q{question.pk}') or '').strip()
        kind = question_type(part, question)
        item = {'number': part.first_question_number + index, 'question': question, 'given': given, 'type': kind}

        if kind == 'gap':
            accepted = accepted_answers(question.answer)
            item['correct_text'] = ' / '.join(accepted)
            item['is_correct'] = bool(given) and normalize_answer(given) in {normalize_answer(a) for a in accepted}
            item['given_display'] = given
            item['correct_display'] = item['correct_text']
        elif kind == 'list':
            chosen = given if given in labels else None
            item.update(
                chosen=chosen,
                chosen_label=labels.get(chosen),
                correct_label=labels.get(question.correct),
                is_correct=chosen is not None and chosen == question.correct,
                given_display=(chosen or '').upper(),
                correct_display=question.correct.upper(),
            )
        else:
            offered = {letter for letter, _ in question.options}
            chosen = given if given in offered else None
            item.update(
                chosen=chosen,
                is_correct=chosen == question.correct,
                given_display=(chosen or '').upper(),
                correct_display=question.correct.upper(),
                options=[
                    {'letter': letter, 'text': text, 'is_correct': letter == question.correct, 'is_chosen': letter == chosen}
                    for letter, text in question.options
                ],
            )

        score += item['is_correct']
        review.append(item)

    return review, score
