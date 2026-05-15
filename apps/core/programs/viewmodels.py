from __future__ import annotations

from drf_spectacular.utils import extend_schema_field, inline_serializer
from rest_framework import serializers

from apps.core.programs.models import ExerciseProgram, ExerciseProgramItem
from apps.core.programs.services import (
    ExerciseProgressSnapshot,
    FavouriteExerciseSnapshot,
    ProgramProgressSnapshot,
    get_instruction_step_details,
)


class ExerciseImageViewModel(serializers.Serializer):
    url = serializers.CharField()
    thumbnail_url = serializers.CharField()
    width = serializers.IntegerField(allow_null=True)
    height = serializers.IntegerField(allow_null=True)
    alt = serializers.CharField()


ExerciseStepViewModel = inline_serializer(
    name="ExerciseStepViewModel",
    fields={
        "step_index": serializers.IntegerField(),
        "title": serializers.CharField(),
        "instruction": serializers.CharField(),
        "image": ExerciseImageViewModel(),
    },
)


TimingViewModel = inline_serializer(
    name="TimingViewModel",
    fields={
        "type": serializers.CharField(required=False),
        "seconds": serializers.JSONField(required=False),
        "repetitions": serializers.CharField(required=False),
        "sets": serializers.CharField(required=False),
        "prescription": serializers.CharField(required=False),
    },
)


ProgramProgressViewModel = inline_serializer(
    name="ProgramProgressViewModel",
    fields={
        "exercises_count": serializers.IntegerField(),
        "completed_exercises_count": serializers.IntegerField(),
        "is_finished": serializers.BooleanField(),
    },
)

ExerciseStepCompletionProgramProgressViewModel = inline_serializer(
    name="ExerciseStepCompletionProgramProgressViewModel",
    fields={
        "exercises_count": serializers.IntegerField(),
        "completed_exercises_count": serializers.IntegerField(),
        "is_finished": serializers.BooleanField(),
    },
)

ExerciseFavouriteProgramItemViewModel = inline_serializer(
    name="ExerciseFavouriteProgramItemViewModel",
    fields={
        "program_id": serializers.UUIDField(),
        "program_title": serializers.CharField(),
        "item_id": serializers.UUIDField(),
        "exercise_order": serializers.IntegerField(),
    },
)


def get_program_progress(program: ExerciseProgram) -> ProgramProgressSnapshot:
    progress = getattr(program, "current_user_program_progress", None)

    if progress is None:
        raise RuntimeError("Program progress was not attached to the serializer instance.")

    return progress


def get_exercise_progress(program_item: ExerciseProgramItem) -> ExerciseProgressSnapshot:
    progress = getattr(program_item, "current_user_exercise_progress", None)

    if progress is None:
        raise RuntimeError("Exercise progress was not attached to the serializer instance.")

    return progress


def get_favourite_exercise(program_item: ExerciseProgramItem) -> FavouriteExerciseSnapshot:
    favourite_exercise = getattr(program_item, "current_user_favourite_exercise", None)

    if favourite_exercise is None:
        raise RuntimeError("Favourite exercise state was not attached to the serializer instance.")

    return favourite_exercise


class ExerciseProgressFieldsMixin:
    def get_steps_count(self, obj: ExerciseProgramItem) -> int:
        return get_exercise_progress(obj).steps_count

    def get_completed_steps_count(self, obj: ExerciseProgramItem) -> int:
        return get_exercise_progress(obj).completed_steps_count

    def get_next_step_index(self, obj: ExerciseProgramItem) -> int | None:
        return get_exercise_progress(obj).next_step_index

    def get_is_finished(self, obj: ExerciseProgramItem) -> bool:
        return get_exercise_progress(obj).is_finished

    def get_is_completed(self, obj: ExerciseProgramItem) -> bool:
        return get_exercise_progress(obj).is_finished


class FavouriteExerciseFieldsMixin:
    def get_is_favorite(self, obj: ExerciseProgramItem) -> bool:
        return get_favourite_exercise(obj).is_favorite

    def get_suggested_days_per_week(self, obj: ExerciseProgramItem) -> int | None:
        return get_favourite_exercise(obj).suggested_days_per_week

    def get_current_streak_days(self, obj: ExerciseProgramItem) -> int | None:
        return get_favourite_exercise(obj).current_streak_days

    def get_longest_streak_days(self, obj: ExerciseProgramItem) -> int | None:
        return get_favourite_exercise(obj).longest_streak_days


class ExerciseProgramListItemViewModel(serializers.ModelSerializer):
    cover_image = serializers.SerializerMethodField()
    exercises_count = serializers.SerializerMethodField()
    completed_exercises_count = serializers.SerializerMethodField()
    is_finished = serializers.SerializerMethodField()

    class Meta:
        model = ExerciseProgram
        fields = (
            "id",
            "title",
            "description",
            "focus_area",
            "focus_area_label",
            "difficulty",
            "difficulty_label",
            "total_duration_sec",
            "cover_image",
            "exercises_count",
            "completed_exercises_count",
            "is_finished",
            "metadata",
        )

    @extend_schema_field(
        inline_serializer(
            name="ProgramCoverImageViewModel",
            fields={
                "url": serializers.CharField(),
                "thumbnail_url": serializers.CharField(),
                "width": serializers.IntegerField(allow_null=True),
                "height": serializers.IntegerField(allow_null=True),
                "alt": serializers.CharField(),
                "blurhash": serializers.CharField(),
            },
        )
    )
    def get_cover_image(self, obj: ExerciseProgram) -> dict[str, str | int | None]:
        return {
            "url": obj.cover_image_url,
            "thumbnail_url": obj.cover_image_thumbnail_url,
            "width": obj.cover_image_width,
            "height": obj.cover_image_height,
            "alt": obj.cover_image_alt,
            "blurhash": obj.cover_image_blurhash,
        }

    def get_exercises_count(self, obj: ExerciseProgram) -> int:
        return get_program_progress(obj).exercises_count

    def get_completed_exercises_count(self, obj: ExerciseProgram) -> int:
        return get_program_progress(obj).completed_exercises_count

    def get_is_finished(self, obj: ExerciseProgram) -> bool:
        return get_program_progress(obj).is_finished


class ExerciseProgramExerciseListItemViewModel(
    ExerciseProgressFieldsMixin,
    FavouriteExerciseFieldsMixin,
    serializers.ModelSerializer,
):
    id = serializers.UUIDField(source="exercise.id")
    item_id = serializers.UUIDField(source="id")
    title = serializers.CharField(source="exercise.title")
    instruction = serializers.CharField(source="exercise.instruction")
    caution_note = serializers.CharField(source="exercise.caution_note")
    duration_sec = serializers.IntegerField(source="exercise.duration_sec")
    body_area = serializers.CharField(source="exercise.body_area")
    metadata = serializers.JSONField(source="exercise.metadata")
    exercise_order = serializers.IntegerField()
    image = serializers.SerializerMethodField()
    steps_count = serializers.SerializerMethodField()
    completed_steps_count = serializers.SerializerMethodField()
    next_step_index = serializers.SerializerMethodField()
    is_finished = serializers.SerializerMethodField()
    is_completed = serializers.SerializerMethodField()
    is_favorite = serializers.SerializerMethodField()
    suggested_days_per_week = serializers.SerializerMethodField()
    current_streak_days = serializers.SerializerMethodField()
    longest_streak_days = serializers.SerializerMethodField()

    class Meta:
        model = ExerciseProgramItem
        fields = (
            "id",
            "item_id",
            "exercise_order",
            "title",
            "instruction",
            "caution_note",
            "duration_sec",
            "body_area",
            "image",
            "steps_count",
            "completed_steps_count",
            "next_step_index",
            "is_finished",
            "is_completed",
            "is_favorite",
            "suggested_days_per_week",
            "current_streak_days",
            "longest_streak_days",
            "metadata",
        )

    @extend_schema_field(ExerciseImageViewModel)
    def get_image(self, obj: ExerciseProgramItem) -> dict[str, str | int | None]:
        return {
            "url": obj.exercise.image_url,
            "thumbnail_url": obj.exercise.image_thumbnail_url,
            "width": obj.exercise.image_width,
            "height": obj.exercise.image_height,
            "alt": obj.exercise.image_alt,
        }

class ExerciseProgramExerciseDetailViewModel(
    ExerciseProgressFieldsMixin,
    FavouriteExerciseFieldsMixin,
    serializers.ModelSerializer,
):
    id = serializers.UUIDField(source="exercise.id")
    item_id = serializers.UUIDField(source="id")
    title = serializers.CharField(source="exercise.title")
    instruction = serializers.CharField(source="exercise.instruction")
    caution_note = serializers.CharField(source="exercise.caution_note")
    duration_sec = serializers.IntegerField(source="exercise.duration_sec")
    body_area = serializers.CharField(source="exercise.body_area")
    metadata = serializers.JSONField(source="exercise.metadata")
    exercise_order = serializers.IntegerField()
    image = serializers.SerializerMethodField()
    steps = serializers.SerializerMethodField()
    instruction_steps = serializers.SerializerMethodField()
    instruction_step_images = serializers.SerializerMethodField()
    timing = serializers.SerializerMethodField()
    steps_count = serializers.SerializerMethodField()
    completed_steps_count = serializers.SerializerMethodField()
    completed_step_indexes = serializers.SerializerMethodField()
    next_step_index = serializers.SerializerMethodField()
    is_finished = serializers.SerializerMethodField()
    is_completed = serializers.SerializerMethodField()
    is_favorite = serializers.SerializerMethodField()
    suggested_days_per_week = serializers.SerializerMethodField()
    current_streak_days = serializers.SerializerMethodField()
    longest_streak_days = serializers.SerializerMethodField()

    class Meta:
        model = ExerciseProgramItem
        fields = (
            "id",
            "item_id",
            "exercise_order",
            "title",
            "instruction",
            "steps",
            "instruction_steps",
            "instruction_step_images",
            "caution_note",
            "duration_sec",
            "timing",
            "body_area",
            "image",
            "steps_count",
            "completed_steps_count",
            "completed_step_indexes",
            "next_step_index",
            "is_finished",
            "is_completed",
            "is_favorite",
            "suggested_days_per_week",
            "current_streak_days",
            "longest_streak_days",
            "metadata",
        )

    @extend_schema_field(ExerciseImageViewModel)
    def get_image(self, obj: ExerciseProgramItem) -> dict[str, str | int | None]:
        return {
            "url": obj.exercise.image_url,
            "thumbnail_url": obj.exercise.image_thumbnail_url,
            "width": obj.exercise.image_width,
            "height": obj.exercise.image_height,
            "alt": obj.exercise.image_alt,
        }

    @extend_schema_field(serializers.ListSerializer(child=ExerciseStepViewModel))
    def get_steps(self, obj: ExerciseProgramItem) -> list[dict[str, object]]:
        return get_instruction_step_details(obj.exercise)

    @extend_schema_field(serializers.ListField(child=serializers.CharField()))
    def get_instruction_steps(self, obj: ExerciseProgramItem) -> list[str]:
        return [
            str(step["instruction"])
            for step in get_instruction_step_details(obj.exercise)
        ]

    @extend_schema_field(serializers.ListSerializer(child=ExerciseImageViewModel()))
    def get_instruction_step_images(self, obj: ExerciseProgramItem) -> list[dict[str, str | int | None]]:
        return [
            dict(step["image"])
            for step in get_instruction_step_details(obj.exercise)
        ]

    @extend_schema_field(TimingViewModel)
    def get_timing(self, obj: ExerciseProgramItem) -> dict[str, str | int]:
        timing = obj.exercise.metadata.get("timing", {})

        if not isinstance(timing, dict):
            return {}

        return timing

    def get_completed_step_indexes(self, obj: ExerciseProgramItem) -> list[int]:
        return get_exercise_progress(obj).completed_step_indexes


class ExerciseStepCompletionResponseViewModel(serializers.Serializer):
    program_id = serializers.UUIDField()
    exercise_id = serializers.UUIDField()
    completed_step_indexes = serializers.ListField(child=serializers.IntegerField())
    completed_steps_count = serializers.IntegerField()
    steps_count = serializers.IntegerField()
    next_step_index = serializers.IntegerField(allow_null=True)
    is_finished = serializers.BooleanField()
    is_completed = serializers.BooleanField()
    is_favorite = serializers.BooleanField()
    suggested_days_per_week = serializers.IntegerField(allow_null=True)
    current_streak_days = serializers.IntegerField(allow_null=True)
    longest_streak_days = serializers.IntegerField(allow_null=True)
    program_progress = ExerciseStepCompletionProgramProgressViewModel


class FavouriteExerciseUpdateRequestViewModel(serializers.Serializer):
    is_favorite = serializers.BooleanField()


class FavouriteExerciseUpdateResponseViewModel(serializers.Serializer):
    exercise_id = serializers.UUIDField()
    is_favorite = serializers.BooleanField()
    suggested_days_per_week = serializers.IntegerField(allow_null=True)
    message = serializers.CharField()


class FavouriteExerciseCalendarQueryViewModel(serializers.Serializer):
    year = serializers.IntegerField(min_value=2000, max_value=2100)
    month = serializers.IntegerField(min_value=1, max_value=12)


class FavouriteCalendarExerciseViewModel(serializers.Serializer):
    exercise_id = serializers.UUIDField()
    title = serializers.CharField()
    is_completed = serializers.BooleanField()
    current_streak_days = serializers.IntegerField(allow_null=True)
    longest_streak_days = serializers.IntegerField(allow_null=True)
    suggested_days_per_week = serializers.IntegerField(allow_null=True)


class FavouriteCalendarDayViewModel(serializers.Serializer):
    date = serializers.DateField()
    exercises = FavouriteCalendarExerciseViewModel(many=True)


class FavouriteCalendarViewModel(serializers.Serializer):
    year = serializers.IntegerField()
    month = serializers.IntegerField()
    days = serializers.ListSerializer(child=FavouriteCalendarDayViewModel())
