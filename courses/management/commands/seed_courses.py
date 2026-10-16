from django.core.management.base import BaseCommand

from courses.models import Course, LearningOutcome, SkillTag


class Command(BaseCommand):
    help = "Seeds the database with sample courses for demo purposes."

    def handle(self, *args, **options):
        courses_data = [
            {
                "title": "Learn English: Health and Wellness with Mixed Conditionals",
                "category": "grammar",
                "is_new": True,
                "level": "intermediate",
                "cefr_badge": "B2 Upper-Intermediate",
                "short_description": (
                    "This free online English course explains the grammar of mixed "
                    "conditionals and provides vocabulary related to health."
                ),
                "enrolled_count": 16358,
                "positive_ratings_count": 120,
                "duration_text": "1.5-3 Hours (Contains Video)",
                "about_this_course": (
                    "This English course introduces you to vocabulary related to health and "
                    "medicine. We also explain how to use zero, first, second, and third "
                    "conditionals in the affirmative or negative and how to use them to form "
                    "questions. We examine the grammar practices of mixed third/second "
                    "conditionals to discuss the impact of past actions on the present. Learn "
                    "English with these classes and confidently boost your ability to discuss "
                    "health and wellbeing."
                ),
                "course_description": (
                    "In this English course, we will introduce you to vocabulary related to "
                    "health, wellness, and healthcare. Not only will there be a focus on common "
                    "health issues and disorders but also on a variety of treatments that could "
                    "help manage or potentially cure these conditions. You will then move on to "
                    "study zero, first, second and third conditionals, before combining the "
                    "second and third conditionals to form mixed conditionals. By the end of "
                    "this course, you will be able to confidently discuss health topics using a "
                    "full range of conditional structures, both in the affirmative and negative, "
                    "and as questions."
                ),
                "outcomes": [
                    "Outline the vocabulary related to health, wellness and healthcare",
                    "Summarize how to use zero, first, second and third conditionals",
                    "Describe how to use conditionals in the negative and question form",
                    "Explain when to apply mixed conditionals",
                    "Compare third/second and second/third conditionals",
                    "Discuss how to use mixed conditionals in the negative form and as questions",
                ],
                "tags": [
                    ("English Grammar", False),
                    ("English Vocabulary", False),
                    ("English Language", False),
                    ("English Conversation", False),
                    ("English Writing", False),
                    ("English Speaking", True),
                    ("English Pronunciation", False),
                    ("Upper-Intermediate English", False),
                    ("ESOL", False),
                ],
            },
            {
                "title": "Learn English: Everyday Vocabulary for Travel and Tourism",
                "category": "vocabulary",
                "is_new": True,
                "level": "beginner",
                "cefr_badge": "A2 Elementary",
                "short_description": (
                    "This free online English course teaches essential vocabulary and phrases "
                    "for travelling, booking hotels, and getting around a new city."
                ),
                "enrolled_count": 9820,
                "positive_ratings_count": 74,
                "duration_text": "1-2 Hours (Contains Video)",
                "about_this_course": (
                    "This course builds practical travel vocabulary so you can check in at "
                    "airports, order food, ask for directions, and handle everyday situations "
                    "abroad with confidence."
                ),
                "course_description": (
                    "You will learn key words and expressions used at airports, hotels, "
                    "restaurants, and tourist attractions. The course also covers polite "
                    "question forms for asking for help and directions while travelling."
                ),
                "outcomes": [
                    "Use common travel and tourism vocabulary correctly",
                    "Ask for and understand directions",
                    "Order food and make hotel reservations in English",
                    "Handle common problems while travelling",
                ],
                "tags": [
                    ("English Vocabulary", True),
                    ("English Conversation", False),
                    ("Travel English", False),
                    ("Beginner English", False),
                ],
            },
            {
                "title": "Learn English: Reading Comprehension for Everyday Life",
                "category": "reading",
                "level": "intermediate",
                "cefr_badge": "B1 Intermediate",
                "short_description": (
                    "This free online English course improves your reading comprehension "
                    "skills using everyday texts, articles, and short stories."
                ),
                "enrolled_count": 7120,
                "positive_ratings_count": 58,
                "duration_text": "2-3 Hours (Contains Video)",
                "about_this_course": (
                    "This course trains you to read everyday English texts quickly and "
                    "accurately, including emails, news articles, and short stories."
                ),
                "course_description": (
                    "You will practise skimming and scanning techniques, learn to identify main "
                    "ideas and supporting details, and build strategies to understand "
                    "unfamiliar vocabulary from context."
                ),
                "outcomes": [
                    "Apply skimming and scanning techniques",
                    "Identify main ideas and supporting details in a text",
                    "Guess the meaning of new words from context",
                    "Summarize short articles and stories",
                ],
                "tags": [
                    ("English Reading", True),
                    ("English Vocabulary", False),
                    ("Intermediate English", False),
                ],
            },
            {
                "title": "Learn English: Writing Clear and Effective Emails",
                "category": "writing",
                "level": "intermediate",
                "cefr_badge": "B1 Intermediate",
                "short_description": (
                    "This free online English course teaches you how to write clear, "
                    "professional emails for work and study."
                ),
                "enrolled_count": 5430,
                "positive_ratings_count": 41,
                "duration_text": "1.5-2 Hours (Contains Video)",
                "about_this_course": (
                    "This course covers the structure, tone, and vocabulary needed to write "
                    "effective emails in professional and academic settings."
                ),
                "course_description": (
                    "You will learn how to open and close emails appropriately, use formal and "
                    "informal register correctly, and structure requests, complaints, and "
                    "follow-ups clearly."
                ),
                "outcomes": [
                    "Structure a professional email correctly",
                    "Choose the right tone for formal and informal emails",
                    "Write clear requests and follow-up messages",
                    "Proofread and edit your own writing",
                ],
                "tags": [
                    ("English Writing", True),
                    ("Business English", False),
                    ("Intermediate English", False),
                ],
            },
            {
                "title": "Learn English: Speaking Confidently in Job Interviews",
                "category": "speaking",
                "is_new": True,
                "level": "advanced",
                "cefr_badge": "C1 Advanced",
                "short_description": (
                    "This free online English course prepares you to speak confidently and "
                    "fluently in English-language job interviews."
                ),
                "enrolled_count": 4210,
                "positive_ratings_count": 36,
                "duration_text": "2-3 Hours (Contains Video)",
                "about_this_course": (
                    "This course focuses on spoken fluency, interview vocabulary, and strategies "
                    "for answering common interview questions naturally and confidently."
                ),
                "course_description": (
                    "You will practise answering typical interview questions, learn how to "
                    "describe your strengths and experience persuasively, and build strategies "
                    "to manage nerves while speaking English under pressure."
                ),
                "outcomes": [
                    "Answer common interview questions fluently",
                    "Describe skills and experience persuasively",
                    "Use appropriate register in a formal interview",
                    "Manage nerves and speak confidently under pressure",
                ],
                "tags": [
                    ("English Speaking", True),
                    ("Business English", False),
                    ("Advanced English", False),
                ],
            },
            {
                "title": "Learn English: Listening to Natural Conversations",
                "category": "listening",
                "level": "intermediate",
                "cefr_badge": "B2 Upper-Intermediate",
                "short_description": (
                    "This free online English course trains your ear to understand natural, "
                    "fast-paced English conversations."
                ),
                "enrolled_count": 3980,
                "positive_ratings_count": 29,
                "duration_text": "1.5-2.5 Hours (Contains Video)",
                "about_this_course": (
                    "This course uses authentic dialogues to help you understand connected "
                    "speech, reductions, and everyday expressions used by native speakers."
                ),
                "course_description": (
                    "You will practise listening for gist and detail, get used to different "
                    "accents, and learn common spoken expressions that do not appear in "
                    "textbooks."
                ),
                "outcomes": [
                    "Understand natural, connected speech",
                    "Recognize common spoken expressions and idioms",
                    "Listen for gist and specific detail",
                    "Follow conversations between multiple speakers",
                ],
                "tags": [
                    ("English Listening", True),
                    ("English Conversation", False),
                    ("Upper-Intermediate English", False),
                ],
            },
        ]

        for data in courses_data:
            outcomes = data.pop('outcomes')
            tags = data.pop('tags')

            course, created = Course.objects.update_or_create(
                title=data['title'],
                defaults=data,
            )

            course.learning_outcomes.all().delete()
            for order, text in enumerate(outcomes):
                LearningOutcome.objects.create(course=course, text=text, order=order)

            course.skill_tags.all().delete()
            for order, (name, highlighted) in enumerate(tags):
                SkillTag.objects.create(course=course, name=name, highlighted=highlighted, order=order)

            status = "Created" if created else "Updated"
            self.stdout.write(self.style.SUCCESS(f"{status}: {course.title}"))

        self.stdout.write(self.style.SUCCESS(f"Done. Total courses: {Course.objects.count()}"))
