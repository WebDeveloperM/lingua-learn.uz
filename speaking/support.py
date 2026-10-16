from django.core.files.uploadedfile import SimpleUploadedFile

from courses.models import Category, Course

from .models import SpeakingAnswer, SpeakingAttempt, SpeakingPart, SpeakingQuestion, SpeakingSet

# The practice questions of the reference screenshots (Part 1.1, three sets of three questions).
SET_ONE = ['What do you do on the weekends?', 'Do you live in a house or a flat?', 'What kind of movies do you like?']
SET_TWO = [
    'Do you like listening to music?', "What kind of weather don't you like?", 'What do you do after work or school?',
]
SET_THREE = ['When do you usually listen to music?', 'What do you do to stay healthy?', 'Tell me about your school.']

# What a student could say to SET_ONE, and the feedback the AI could give on it.
SPOKEN = [
    'I usually play football with my friends and sometimes I go to the cinema.',
    'I live in a flat with my family. It is small but very comfortable.',
    'I like comedy movies because they make me laugh after a hard week.',
]
FEEDBACK = {
    'summary': 'Clear answer with good ideas; add one more detail.',
    'grammar': 'Good use of the Present Simple.',
    'vocabulary': 'Try "hang out" instead of "play with friends".',
    'fluency': 'Your answer was a little short.',
    'pronunciation': 'It cannot be judged exactly from text. Practise the sentence stress.',
    'try_saying': 'At the weekend I usually play football and then I relax at home.',
}


def make_speaking_course(**extra):
    return Course.objects.create(title='Speaking', category=Category.SPEAKING, short_description='x', **extra)


def make_set(course, part=SpeakingPart.PART_11, questions=SET_ONE, number=None):
    """A set with the given questions; numbered after the last set of the part unless a number is given."""
    if number is None:
        last = SpeakingSet.objects.filter(course=course, part=part).order_by('-number').first()
        number = last.number + 1 if last else 1
    speaking_set = SpeakingSet.objects.create(course=course, part=part, number=number)
    for order, text in enumerate(questions):
        SpeakingQuestion.objects.create(set=speaking_set, order=order, text=text)
    return speaking_set


def recording(content_type='audio/webm', size=2000):
    return SimpleUploadedFile('answer.webm', b'x' * size, content_type=content_type)


def answers_post(speaking_set, transcripts=SPOKEN, early=(), seconds='30.0', audio=True, confidence='0.88'):
    """What the practice page posts when it is done: one entry per question of the set."""
    data = {}
    for index, question in enumerate(speaking_set.questions.all()):
        data[f'question_{index}'] = str(question.pk)
        data[f'transcript_{index}'] = transcripts[index] if index < len(transcripts) else ''
        data[f'seconds_{index}'] = seconds
        data[f'early_{index}'] = '1' if index in early else '0'
        if confidence is not None:
            data[f'confidence_{index}'] = confidence
        if audio:
            data[f'audio_{index}'] = recording()
    return data


def make_attempt(user, speaking_set, transcripts=SPOKEN, early=(), feedback=None, status=None, coins=None):
    """An attempt saved as the finish view saves it (recordings aside)."""
    attempt = SpeakingAttempt.objects.create(
        user=user, set=speaking_set,
        coins=len(transcripts) if coins is None and not early else (coins or 0),
        feedback_status=status or (SpeakingAttempt.Feedback.READY if feedback else SpeakingAttempt.Feedback.PENDING),
    )
    for order, question in enumerate(speaking_set.questions.all()):
        SpeakingAnswer.objects.create(
            attempt=attempt, order=order, question=question.text,
            transcript=transcripts[order] if order < len(transcripts) else '', seconds=30.0,
            finished_early=order in early, confidence=0.9, feedback=dict(feedback) if feedback else {},
        )
    return attempt
