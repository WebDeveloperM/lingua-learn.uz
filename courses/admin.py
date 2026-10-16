from django.contrib import admin

from .models import Course, Enrollment, Exercise, KeyWord, LearningOutcome, Part, SkillTag


class ExerciseInline(admin.TabularInline):
    model = Exercise
    extra = 0


class KeyWordInline(admin.TabularInline):
    model = KeyWord
    extra = 0


@admin.register(Part)
class PartAdmin(admin.ModelAdmin):
    list_display = ('__str__', 'course', 'key_words')
    list_filter = ('course',)
    inlines = [KeyWordInline, ExerciseInline]

    @admin.display(description='Key vocabulary')
    def key_words(self, part):
        return part.key_words.count()


class LearningOutcomeInline(admin.TabularInline):
    model = LearningOutcome
    extra = 3


class SkillTagInline(admin.TabularInline):
    model = SkillTag
    extra = 3


@admin.register(Course)
class CourseAdmin(admin.ModelAdmin):
    list_display = ('title', 'category', 'level', 'is_published', 'is_new', 'enrolled_count', 'created_at')
    list_editable = ('is_new',)
    list_filter = ('category', 'level', 'is_published')
    search_fields = ('title', 'short_description')
    prepopulated_fields = {'slug': ('title',)}
    inlines = [LearningOutcomeInline, SkillTagInline]


@admin.register(Enrollment)
class EnrollmentAdmin(admin.ModelAdmin):
    list_display = ('user', 'course', 'enrolled_at', 'progress_percent')
    list_filter = ('course',)
