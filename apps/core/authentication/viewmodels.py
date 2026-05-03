from __future__ import annotations

from typing import TypedDict

from rest_framework import serializers

from apps.core.users.models import (
    AGE_RANGE_CHOICES,
    DAILY_STEP_GOAL_CHOICES,
    FOCUS_AREA_CHOICES,
    GENDER_CHOICES,
    WEEKLY_GOAL_CHOICES,
)
from apps.core.users.viewmodels import UserViewModel


class SignupPayload(TypedDict):
    email: str
    password: str
    full_name: str
    focus_area: str
    weekly_goal: int
    age_range: str
    daily_step_goal: int
    gender: str


class LoginPayload(TypedDict):
    email: str
    password: str


class VerifyCodePayload(TypedDict):
    email: str
    code: str


class EmailPayload(TypedDict):
    email: str


class LogoutPayload(TypedDict):
    refresh: str


class SignupRequestViewModel(serializers.Serializer):
    email = serializers.EmailField()
    password = serializers.CharField(write_only=True, min_length=8, max_length=128)
    full_name = serializers.CharField(max_length=255)
    focus_area = serializers.ChoiceField(choices=FOCUS_AREA_CHOICES)
    weekly_goal = serializers.ChoiceField(choices=WEEKLY_GOAL_CHOICES)
    age_range = serializers.ChoiceField(choices=AGE_RANGE_CHOICES)
    gender = serializers.ChoiceField(choices=GENDER_CHOICES, allow_blank=True)
    daily_step_goal = serializers.ChoiceField(choices=DAILY_STEP_GOAL_CHOICES)


class SendSignupCodeRequestViewModel(serializers.Serializer):
    email = serializers.EmailField()


class VerifySignupCodeRequestViewModel(serializers.Serializer):
    email = serializers.EmailField()
    code = serializers.RegexField(regex=r"^\d{6}$")


class LoginRequestViewModel(serializers.Serializer):
    email = serializers.EmailField()
    password = serializers.CharField(write_only=True, max_length=128)


class LogoutRequestViewModel(serializers.Serializer):
    refresh = serializers.CharField()


class MessageViewModel(serializers.Serializer):
    message = serializers.CharField()


class TokenPairResponseViewModel(serializers.Serializer):
    access = serializers.CharField()
    refresh = serializers.CharField()
    user = UserViewModel()


class TokenRefreshResponseViewModel(serializers.Serializer):
    access = serializers.CharField()
    refresh = serializers.CharField()


class SignupResponseViewModel(serializers.Serializer):
    message = serializers.CharField()
    verification_required = serializers.BooleanField()
