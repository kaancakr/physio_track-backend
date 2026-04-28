from __future__ import annotations

import uuid
from typing import Final

from django.contrib.auth.base_user import BaseUserManager
from django.contrib.auth.models import AbstractBaseUser, PermissionsMixin
from django.db import models

from apps.core.models import TimestampedModel

FOCUS_AREA_CHOICES: Final[list[tuple[str, str]]] = [
    ("neck", "Neck"),
    ("shoulder", "Shoulder"),
    ("back", "Back"),
    ("knee", "Knee"),
    ("mobility", "Mobility"),
]

WEEKLY_GOAL_CHOICES: Final[list[tuple[int, str]]] = [
    (2, "2"),
    (3, "3"),
    (4, "4"),
    (5, "5"),
]

AGE_RANGE_CHOICES: Final[list[tuple[str, str]]] = [
    ("18-29", "18-29"),
    ("30-44", "30-44"),
    ("45-59", "45-59"),
    ("60+", "60+"),
]

DAILY_STEP_GOAL_CHOICES: Final[list[tuple[int, str]]] = [
    (3000, "3000"),
    (5000, "5000"),
    (7000, "7000"),
    (9000, "9000"),
]


class UserManager(BaseUserManager["User"]):
    use_in_migrations = True

    def _create_user(self, email: str, password: str, **extra_fields: object) -> "User":
        normalized_email = self.normalize_email(email)

        if normalized_email == "":
            raise ValueError("The email address must not be empty.")

        user = self.model(email=normalized_email, **extra_fields)
        user.set_password(password)
        user.save(using=self._db)
        return user

    def create_user(self, email: str, password: str, **extra_fields: object) -> "User":
        extra_fields.setdefault("is_superuser", False)
        return self._create_user(email, password, **extra_fields)

    def create_superuser(self, email: str, password: str, **extra_fields: object) -> "User":
        extra_fields.setdefault("is_active", True)
        extra_fields.setdefault("is_staff", True)
        extra_fields.setdefault("is_superuser", True)
        extra_fields.setdefault("is_email_verified", True)

        if extra_fields["is_staff"] is not True:
            raise ValueError("Superuser must have is_staff=True.")

        if extra_fields["is_superuser"] is not True:
            raise ValueError("Superuser must have is_superuser=True.")

        return self._create_user(email, password, **extra_fields)


class User(TimestampedModel, AbstractBaseUser, PermissionsMixin):
    public_id = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    email = models.EmailField(unique=True)
    is_active = models.BooleanField(default=False)
    is_staff = models.BooleanField(default=False)
    is_email_verified = models.BooleanField(default=False)

    USERNAME_FIELD = "email"
    REQUIRED_FIELDS: list[str] = []

    objects = UserManager()

    class Meta:
        ordering = ["-created_at"]

    def __str__(self) -> str:
        return self.email


class Profile(TimestampedModel):
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name="profile")
    full_name = models.CharField(max_length=255)
    focus_area = models.CharField(max_length=32, choices=FOCUS_AREA_CHOICES)
    weekly_goal = models.PositiveSmallIntegerField(choices=WEEKLY_GOAL_CHOICES)
    age_range = models.CharField(max_length=16, choices=AGE_RANGE_CHOICES)
    daily_step_goal = models.PositiveIntegerField(choices=DAILY_STEP_GOAL_CHOICES)
    metadata = models.JSONField(default=dict, blank=True)

    class Meta:
        ordering = ["user_id"]

    def __str__(self) -> str:
        return f"{self.user.email} profile"
