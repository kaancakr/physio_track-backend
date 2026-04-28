from django.contrib import admin

from apps.core.programs.models import ExerciseProgram, ExerciseStep


class ExerciseStepInline(admin.TabularInline):
    model = ExerciseStep
    extra = 0
    ordering = ("step_order",)


@admin.register(ExerciseProgram)
class ExerciseProgramAdmin(admin.ModelAdmin):
    inlines = [ExerciseStepInline]
    list_display = ("id", "title", "focus_area", "difficulty_label", "is_active")
    list_filter = ("focus_area", "difficulty_label", "is_active")
    search_fields = ("id", "title", "description")


@admin.register(ExerciseStep)
class ExerciseStepAdmin(admin.ModelAdmin):
    list_display = ("program", "step_order", "step_id", "title", "body_area", "duration_sec")
    list_filter = ("body_area",)
    search_fields = ("program__id", "step_id", "title")
