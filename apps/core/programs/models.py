from django.db import models

from apps.core.models import TimestampedModel
from apps.core.users.models import FOCUS_AREA_CHOICES


class ExerciseProgram(TimestampedModel):
    id = models.SlugField(primary_key=True, max_length=128)
    title = models.CharField(max_length=255)
    description = models.TextField()
    focus_area = models.CharField(max_length=32, choices=FOCUS_AREA_CHOICES)
    focus_area_label = models.CharField(max_length=64)
    difficulty_label = models.CharField(max_length=64)
    total_duration_sec = models.PositiveIntegerField()
    cover_icon = models.CharField(max_length=64)
    cover_background = models.CharField(max_length=32)
    cover_tint = models.CharField(max_length=32)
    is_active = models.BooleanField(default=True)
    metadata = models.JSONField(default=dict, blank=True)

    class Meta:
        ordering = ["title"]

    def __str__(self) -> str:
        return self.title


class ExerciseStep(TimestampedModel):
    program = models.ForeignKey(
        ExerciseProgram,
        on_delete=models.CASCADE,
        related_name="steps",
    )
    step_id = models.SlugField(max_length=128)
    step_order = models.PositiveIntegerField()
    title = models.CharField(max_length=255)
    instruction = models.TextField()
    caution_note = models.TextField()
    duration_sec = models.PositiveIntegerField()
    body_area = models.CharField(max_length=32, choices=FOCUS_AREA_CHOICES)
    icon = models.CharField(max_length=64)
    background = models.CharField(max_length=32)
    tint = models.CharField(max_length=32)
    metadata = models.JSONField(default=dict, blank=True)

    class Meta:
        ordering = ["program_id", "step_order"]
        constraints = [
            models.UniqueConstraint(
                fields=("program", "step_id"),
                name="unique_program_step_id",
            ),
            models.UniqueConstraint(
                fields=("program", "step_order"),
                name="unique_program_step_order",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.program_id}#{self.step_order}"
