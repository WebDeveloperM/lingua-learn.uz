from django.contrib import admin

from .models import Course, Enrollment, Exercise, LearningOutcome, Part, SkillTag


class ExerciseInline(admin.TabularInline):
    model = Exercise
    extra = 0


@admin.register(Part)
class PartAdmin(admin.ModelAdmin):
    list_display = ('__str__', 'course', 'key_words_count')
    list_filter = ('course',)
    inlines = [ExerciseInline]


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
