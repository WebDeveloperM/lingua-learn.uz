from datetime import date

from courses.models import Category, Course

from .models import Slot, WritingTask, WritingTest

TRAVEL_CONTEXT = (
    'You are a member of the Travel Club at your language center. You received an email from the club organizer.'
)
TRAVEL_EMAIL = (
    'Dear Member,\n'
    'We are planning our trips for next year and would like to hear your thoughts. Which city would you like to visit '
    'and why? When do you think would be the best time for the trip? Would you prefer to go with your family or just '
    'with other club members? Your suggestions will help us organize a more enjoyable trip for everyone.\n'
    'Best wishes,\n'
    'Travel Club Organizer'
)
TRAVEL_INSTRUCTION = (
    "Write a short email to your friend (who is also a member of the travel club). Say what city you'd like to visit, "
    'when, and whether you want to go with your family. Write about 50 words.'
)
DISCUSSION_TASK = (
    'You are participating in an online discussion for language learners. The question is: “Some people say a '
    'vegetarian diet is better for health. Do you agree?” Post your response, giving reasons and examples.'
)


def make_writing_course(**extra):
    return Course.objects.create(title='Writing', category=Category.WRITING, short_description='x', **extra)


def make_test(
    course, title='Travel Club', when=date(2025, 10, 18), shift=1, topic='Is a vegetarian diet better for health?',
    slots=(Slot.TASK_11, Slot.TASK_12, Slot.PART_2), **extra,
):
    """A test with the requested tasks; Task 1.1 is the Travel Club e-mail and Part 2 the discussion of the reference."""
    test = WritingTest.objects.create(course=course, title=title, date=when, shift=shift, topic=topic, **extra)
    for slot in slots:
        if slot == Slot.TASK_11:
            WritingTask.objects.create(
                test=test, slot=slot, context=TRAVEL_CONTEXT, prompt=TRAVEL_EMAIL, instruction=TRAVEL_INSTRUCTION)
        elif slot == Slot.TASK_12:
            WritingTask.objects.create(
                test=test, slot=slot, context='You received an e-mail from the head of your language center.',
                prompt='Dear student,\nPlease tell us how the course could improve.',
                instruction='Write a formal e-mail to the head. Write 120–150 words.')
        else:
            WritingTask.objects.create(test=test, slot=slot, instruction=DISCUSSION_TASK)
    return test
