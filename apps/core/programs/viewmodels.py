from rest_framework import serializers

from apps.core.programs.models import ExerciseProgram, ExerciseStep


class IllustrationViewModel(serializers.Serializer):
    background = serializers.CharField()
    icon = serializers.CharField()
    tint = serializers.CharField()


class ExerciseStepViewModel(serializers.ModelSerializer):
    id = serializers.CharField(source="step_id")
    image = serializers.SerializerMethodField()

    class Meta:
        model = ExerciseStep
        fields = (
            "id",
            "step_order",
            "title",
            "instruction",
            "caution_note",
            "duration_sec",
            "body_area",
            "image",
            "metadata",
        )

    def get_image(self, obj: ExerciseStep) -> dict[str, str]:
        return {
            "background": obj.background,
            "icon": obj.icon,
            "tint": obj.tint,
        }


class ExerciseProgramListItemViewModel(serializers.ModelSerializer):
    cover_image = serializers.SerializerMethodField()
    steps_count = serializers.SerializerMethodField()

    class Meta:
        model = ExerciseProgram
        fields = (
            "id",
            "title",
            "description",
            "focus_area",
            "focus_area_label",
            "difficulty_label",
            "total_duration_sec",
            "cover_image",
            "steps_count",
            "metadata",
        )

    def get_cover_image(self, obj: ExerciseProgram) -> dict[str, str]:
        return {
            "background": obj.cover_background,
            "icon": obj.cover_icon,
            "tint": obj.cover_tint,
        }

    def get_steps_count(self, obj: ExerciseProgram) -> int:
        return len(obj.steps.all())


class ExerciseProgramDetailViewModel(serializers.ModelSerializer):
    cover_image = serializers.SerializerMethodField()
    steps = ExerciseStepViewModel(many=True, read_only=True)

    class Meta:
        model = ExerciseProgram
        fields = (
            "id",
            "title",
            "description",
            "focus_area",
            "focus_area_label",
            "difficulty_label",
            "total_duration_sec",
            "cover_image",
            "steps",
            "metadata",
        )

    def get_cover_image(self, obj: ExerciseProgram) -> dict[str, str]:
        return {
            "background": obj.cover_background,
            "icon": obj.cover_icon,
            "tint": obj.cover_tint,
        }
