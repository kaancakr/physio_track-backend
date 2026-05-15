from django.contrib import admin
from django.db.models import Count

from apps.core.programs.models import (
    Exercise,
    ExerciseProgram,
    ExerciseProgramCompletion,
    ExerciseProgramItem,
    ExerciseStepCompletion,
    UserFavouriteExercise,
)


class ExerciseProgramItemInline(admin.TabularInline):
    model = ExerciseProgramItem
    extra = 0
    ordering = ("exercise_order",)
    autocomplete_fields = ("exercise",)


class ExerciseProgramCompletionInline(admin.TabularInline):
    model = ExerciseProgramCompletion
    extra = 0
    ordering = ("-finished_at",)


class UserFavouriteExerciseInline(admin.TabularInline):
    model = UserFavouriteExercise
    extra = 0
    autocomplete_fields = ("user",)
    verbose_name = "User favourite for this exercise"
    verbose_name_plural = "Users who favourited this exercise"
    readonly_fields = (
        "suggested_days_per_week",
        "current_streak_days",
        "longest_streak_days",
        "last_completed_on",
        "created_at",
        "updated_at",
    )


@admin.register(ExerciseProgram)
class ExerciseProgramAdmin(admin.ModelAdmin):
    inlines = [ExerciseProgramItemInline, ExerciseProgramCompletionInline]
    list_display = ("id", "code", "title", "focus_area", "difficulty", "difficulty_label", "is_active")
    list_filter = ("focus_area", "difficulty", "is_active")
    search_fields = ("id", "code", "title", "description")


@admin.register(Exercise)
class ExerciseAdmin(admin.ModelAdmin):
    inlines = [UserFavouriteExerciseInline]
    list_display = ("id", "code", "title", "body_area", "duration_sec", "favourites_count")
    list_filter = ("body_area",)
    search_fields = ("id", "code", "title", "instruction")
    fieldsets = (
        (
            "Exercise",
            {
                "fields": (
                    "code",
                    "title",
                    "instruction",
                    "caution_note",
                    "duration_sec",
                    "body_area",
                )
            },
        ),
        (
            "Images",
            {
                "fields": (
                    "image_url",
                    "image_thumbnail_url",
                    "image_width",
                    "image_height",
                    "image_alt",
                    "image_blurhash",
                )
            },
        ),
        (
            "Step Metadata",
            {
                "fields": ("metadata",),
                "description": (
                    "This JSON stores the instruction steps for the exercise. "
                    "Favourites are applied to the whole exercise below, not to individual steps."
                ),
            },
        ),
    )

    def get_queryset(self, request):
        return super().get_queryset(request).annotate(user_favourites_count=Count("user_favourite_exercises"))

    @admin.display(ordering="user_favourites_count", description="Favourites")
    def favourites_count(self, obj: Exercise) -> int:
        return int(getattr(obj, "user_favourites_count", 0))


@admin.register(ExerciseProgramItem)
class ExerciseProgramItemAdmin(admin.ModelAdmin):
    list_display = ("program", "exercise_order", "exercise")
    list_filter = ("program__focus_area", "exercise__body_area")
    search_fields = ("program__code", "exercise__code", "exercise__title")
    autocomplete_fields = ("program", "exercise")


@admin.register(ExerciseProgramCompletion)
class ExerciseProgramCompletionAdmin(admin.ModelAdmin):
    list_display = ("user", "program", "is_finished", "finished_at")
    list_filter = ("is_finished", "program__focus_area")
    search_fields = ("user__email", "program__code", "program__title")


@admin.register(ExerciseStepCompletion)
class ExerciseStepCompletionAdmin(admin.ModelAdmin):
    list_display = ("user", "program", "exercise", "step_index", "completed_at")
    list_filter = ("program__focus_area", "exercise__body_area")
    search_fields = ("user__email", "program__code", "exercise__code", "exercise__title")


@admin.register(UserFavouriteExercise)
class UserFavouriteExerciseAdmin(admin.ModelAdmin):
    list_display = (
        "user",
        "exercise",
        "suggested_days_per_week",
        "current_streak_days",
        "longest_streak_days",
        "last_completed_on",
    )
    list_filter = ("exercise__body_area", "suggested_days_per_week")
    search_fields = ("user__email", "exercise__code", "exercise__title")
    autocomplete_fields = ("user", "exercise")
