from datetime import datetime

from drf_spectacular.utils import extend_schema_field, inline_serializer
from rest_framework import serializers

from apps.core.programs.models import ExerciseProgram, ExerciseProgramCompletion, ExerciseProgramItem


class ExerciseImageViewModel(serializers.Serializer):
    url = serializers.CharField()
    thumbnail_url = serializers.CharField()
    width = serializers.IntegerField(allow_null=True)
    height = serializers.IntegerField(allow_null=True)
    alt = serializers.CharField()


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


class ExerciseProgramItemViewModel(serializers.ModelSerializer):
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
    instruction_steps = serializers.SerializerMethodField()
    instruction_step_images = serializers.SerializerMethodField()
    timing = serializers.SerializerMethodField()

    class Meta:
        model = ExerciseProgramItem
        fields = (
            "id",
            "item_id",
            "exercise_order",
            "title",
            "instruction",
            "instruction_steps",
            "instruction_step_images",
            "caution_note",
            "duration_sec",
            "timing",
            "body_area",
            "image",
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

    @extend_schema_field(serializers.ListField(child=serializers.CharField()))
    def get_instruction_steps(self, obj: ExerciseProgramItem) -> list[str]:
        instruction_steps = obj.exercise.metadata.get("instruction_steps", [])

        if not isinstance(instruction_steps, list):
            return []

        return [str(step) for step in instruction_steps]

    @extend_schema_field(serializers.ListSerializer(child=ExerciseImageViewModel()))
    def get_instruction_step_images(self, obj: ExerciseProgramItem) -> list[dict[str, str | int | None]]:
        instruction_step_images = obj.exercise.metadata.get("instruction_step_images", [])
        instruction_steps = obj.exercise.metadata.get("instruction_steps", [])

        if not isinstance(instruction_step_images, list):
            instruction_step_images = []

        if not isinstance(instruction_steps, list):
            instruction_steps = []

        normalized_images: list[dict[str, str | int | None]] = []

        for image in instruction_step_images:
            if not isinstance(image, dict):
                continue

            normalized_images.append(
                {
                    "url": image.get("url", ""),
                    "thumbnail_url": image.get("thumbnail_url", ""),
                    "width": image.get("width"),
                    "height": image.get("height"),
                    "alt": image.get("alt", ""),
                }
            )

        if len(normalized_images) == 0 and len(instruction_steps) > 0:
            return [
                {
                    "url": "",
                    "thumbnail_url": "",
                    "width": None,
                    "height": None,
                    "alt": str(instruction_step),
                }
                for instruction_step in instruction_steps
            ]

        return normalized_images

    @extend_schema_field(TimingViewModel)
    def get_timing(self, obj: ExerciseProgramItem) -> dict[str, str | int]:
        timing = obj.exercise.metadata.get("timing", {})

        if not isinstance(timing, dict):
            return {}

        return timing


class ExerciseProgramCompletionViewModel(serializers.ModelSerializer):
    class Meta:
        model = ExerciseProgramCompletion
        fields = (
            "is_finished",
            "finished_at",
        )


def get_program_completion(program: ExerciseProgram) -> ExerciseProgramCompletion | None:
    completion_records = getattr(program, "current_user_completion_records", [])

    if len(completion_records) == 0:
        return None

    return completion_records[0]


class ExerciseProgramListItemViewModel(serializers.ModelSerializer):
    cover_image = serializers.SerializerMethodField()
    exercises_count = serializers.SerializerMethodField()
    is_finished = serializers.SerializerMethodField()
    finished_at = serializers.SerializerMethodField()

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
            "is_finished",
            "finished_at",
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
        return len(obj.exercise_items.all())

    def get_is_finished(self, obj: ExerciseProgram) -> bool:
        completion = get_program_completion(obj)

        if completion is None:
            return False

        return completion.is_finished

    def get_finished_at(self, obj: ExerciseProgram) -> datetime | None:
        completion = get_program_completion(obj)

        if completion is None:
            return None

        return completion.finished_at


class ExerciseProgramDetailViewModel(serializers.ModelSerializer):
    cover_image = serializers.SerializerMethodField()
    exercises = ExerciseProgramItemViewModel(many=True, read_only=True, source="exercise_items")
    is_finished = serializers.SerializerMethodField()
    finished_at = serializers.SerializerMethodField()

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
            "is_finished",
            "finished_at",
            "exercises",
            "metadata",
        )

    @extend_schema_field(
        inline_serializer(
            name="ProgramDetailCoverImageViewModel",
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

    def get_is_finished(self, obj: ExerciseProgram) -> bool:
        completion = get_program_completion(obj)

        if completion is None:
            return False

        return completion.is_finished

    def get_finished_at(self, obj: ExerciseProgram) -> datetime | None:
        completion = get_program_completion(obj)

        if completion is None:
            return None

        return completion.finished_at


class ExerciseProgramCompletionUpdateViewModel(serializers.Serializer):
    finished_at = serializers.DateTimeField(
        help_text="UTC timestamp for when the user finished the program.",
    )
