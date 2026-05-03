import uuid

from django.db import models

from apps.core.models import TimestampedModel
from apps.core.users.models import FOCUS_AREA_CHOICES
from apps.core.users.models import User


DIFFICULTY_CHOICES: list[tuple[str, str]] = [
    ("beginner", "Beginner"),
    ("intermediate", "Intermediate"),
    ("advanced", "Advanced"),
]


class ExerciseProgram(TimestampedModel):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    code = models.SlugField(max_length=128, unique=True)
    title = models.CharField(max_length=255)
    description = models.TextField()
    focus_area = models.CharField(max_length=32, choices=FOCUS_AREA_CHOICES)
    focus_area_label = models.CharField(max_length=64)
    difficulty = models.CharField(max_length=32, choices=DIFFICULTY_CHOICES)
    difficulty_label = models.CharField(max_length=64)
    total_duration_sec = models.PositiveIntegerField()
    cover_image_url = models.URLField(blank=True)
    cover_image_thumbnail_url = models.URLField(blank=True)
    cover_image_width = models.PositiveIntegerField(null=True, blank=True)
    cover_image_height = models.PositiveIntegerField(null=True, blank=True)
    cover_image_alt = models.CharField(max_length=255, blank=True)
    cover_image_blurhash = models.CharField(max_length=255, blank=True)
    is_active = models.BooleanField(default=True)
    metadata = models.JSONField(default=dict, blank=True)

    class Meta:
        ordering = ["title"]

    def __str__(self) -> str:
        return self.title


class Exercise(TimestampedModel):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    code = models.SlugField(max_length=128, unique=True)
    title = models.CharField(max_length=255)
    instruction = models.TextField()
    caution_note = models.TextField()
    duration_sec = models.PositiveIntegerField()
    body_area = models.CharField(max_length=32, choices=FOCUS_AREA_CHOICES)
    image_url = models.URLField(blank=True)
    image_thumbnail_url = models.URLField(blank=True)
    image_width = models.PositiveIntegerField(null=True, blank=True)
    image_height = models.PositiveIntegerField(null=True, blank=True)
    image_alt = models.CharField(max_length=255, blank=True)
    image_blurhash = models.CharField(max_length=255, blank=True)
    metadata = models.JSONField(default=dict, blank=True)

    class Meta:
        ordering = ["title"]

    def __str__(self) -> str:
        return self.title


class ExerciseProgramItem(TimestampedModel):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    program = models.ForeignKey(
        ExerciseProgram,
        on_delete=models.CASCADE,
        related_name="exercise_items",
    )
    exercise = models.ForeignKey(
        Exercise,
        on_delete=models.CASCADE,
        related_name="program_items",
    )
    exercise_order = models.PositiveIntegerField()

    class Meta:
        ordering = ["program_id", "exercise_order"]
        constraints = [
            models.UniqueConstraint(
                fields=("program", "exercise"),
                name="unique_program_exercise",
            ),
            models.UniqueConstraint(
                fields=("program", "exercise_order"),
                name="unique_program_exercise_order",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.program_id}#{self.exercise_order}:{self.exercise_id}"


class ExerciseProgramCompletion(TimestampedModel):
    user = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name="exercise_program_completions",
    )
    program = models.ForeignKey(
        ExerciseProgram,
        on_delete=models.CASCADE,
        related_name="completions",
    )
    is_finished = models.BooleanField(default=False)
    finished_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-finished_at", "-created_at"]
        constraints = [
            models.UniqueConstraint(
                fields=("user", "program"),
                name="unique_user_program_completion",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.user_id}:{self.program_id}:{self.is_finished}"
