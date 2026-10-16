from courses.models import Category, Course

from .models import SpeakingPart, SpeakingQuestion, SpeakingSet

# The practice questions of the reference screenshots (Part 1.1, three sets of three questions).
SET_ONE = ['What do you do on the weekends?', 'Do you live in a house or a flat?', 'What kind of movies do you like?']
SET_TWO = [
    'Do you like listening to music?', "What kind of weather don't you like?", 'What do you do after work or school?',
]
SET_THREE = ['When do you usually listen to music?', 'What do you do to stay healthy?', 'Tell me about your school.']


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
