from django.db import models

from apps.core.models import TimestampedModel
from apps.core.users.models import User


class VerificationPurpose(models.TextChoices):
    SIGNUP = "signup", "Signup"


class EmailVerificationCode(TimestampedModel):
    user = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name="email_verification_codes",
    )
    purpose = models.CharField(max_length=32, choices=VerificationPurpose.choices)
    code_hash = models.CharField(max_length=255)
    expires_at = models.DateTimeField()
    consumed_at = models.DateTimeField(null=True, blank=True)
    attempt_count = models.PositiveSmallIntegerField(default=0)

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=("user", "purpose", "created_at")),
        ]

    def __str__(self) -> str:
        return f"{self.user.email}:{self.purpose}"
