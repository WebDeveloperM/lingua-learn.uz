import random
from datetime import date, timedelta

from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone

from accounts.models import User
from courses.models import Course, Enrollment

DEMO_DOMAIN = '@demo.example.com'
NAMES = [
    ('Aziz', 'Karimov'), ('Madina', 'Yusupova'), ('Jasur', 'Rahmonov'), ('Dilnoza', 'Qodirova'),
    ('Sardor', 'Aliyev'), ('Malika', 'Tursunova'), ('Bekzod', 'Ismoilov'), ('Zilola', 'Nazarova'),
    ('Otabek', 'Saidov'), ('Nigora', 'Hamidova'), ('Javlon', 'Abdullayev'), ('Shahzoda', 'Mirzayeva'),
]
PROGRESS_CHOICES = [0, 10, 25, 40, 60, 75, 90, 100, 100]


class Command(BaseCommand):
    help = "Panelni sinab ko'rish uchun namuna o'quvchilar yaratadi (--delete bilan o'chiradi)."

    def add_arguments(self, parser):
        parser.add_argument('--delete', action='store_true', help="Namuna o'quvchilarni o'chirish")

    def handle(self, *args, **options):
        demo_users = User.objects.filter(email__endswith=DEMO_DOMAIN)

        if options['delete']:
            count = demo_users.count()
            demo_users.delete()
            self.stdout.write(self.style.SUCCESS(f"{count} ta namuna o'quvchi o'chirildi."))
            return

        courses = list(Course.objects.filter(is_published=True))
        if not courses:
            raise CommandError("Avval kurslarni yuklang: python manage.py seed_courses")

        rng = random.Random(42)
        now = timezone.now()
        created = 0
        for index, (first, last) in enumerate(NAMES):
            email = f"{first.lower()}.{last.lower()}{DEMO_DOMAIN}"
            if User.objects.filter(email=email).exists():
                continue

            is_active = index % 4 != 3
            joined = now - (
                timedelta(days=rng.randint(8, 40), hours=rng.randint(0, 23)) if is_active
                else timedelta(hours=rng.randint(1, 70))
            )
            user = User.objects.create_user(
                email=email, first_name=first, last_name=last, is_active=is_active, date_joined=joined,
                birth_date=date(rng.randint(1985, 2012), rng.randint(1, 12), rng.randint(1, 28)),
            )
            if is_active:
                for course in rng.sample(courses, rng.randint(1, min(4, len(courses)))):
                    Enrollment.objects.create(
                        user=user, course=course, progress_percent=rng.choice(PROGRESS_CHOICES),
                    )
            created += 1

        self.stdout.write(self.style.SUCCESS(
            f"{created} ta namuna o'quvchi yaratildi. O'chirish: python manage.py seed_demo_students --delete"
        ))
