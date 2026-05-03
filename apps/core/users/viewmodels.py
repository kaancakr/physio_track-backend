from operator import ge

from rest_framework import serializers

from apps.core.users.models import Profile, User


class ProfileViewModel(serializers.ModelSerializer):
    class Meta:
        model = Profile
        fields = (
            "full_name",
            "focus_area",
            "weekly_goal",
            "age_range",
            "gender",
            "daily_step_goal",
            "metadata",
        )


class UserViewModel(serializers.ModelSerializer):
    id = serializers.UUIDField(source="public_id", read_only=True)
    profile = ProfileViewModel(read_only=True)

    class Meta:
        model = User
        fields = (
            "id",
            "email",
            "is_active",
            "is_staff",
            "is_email_verified",
            "profile",
        )


class UserProfileUpdateViewModel(serializers.Serializer):
    full_name = serializers.CharField(max_length=255, required=False)
    focus_area = serializers.ChoiceField(choices=Profile._meta.get_field("focus_area").choices, required=False)
    weekly_goal = serializers.ChoiceField(choices=Profile._meta.get_field("weekly_goal").choices, required=False)
    age_range = serializers.ChoiceField(choices=Profile._meta.get_field("age_range").choices, required=False)
    daily_step_goal = serializers.ChoiceField(
        choices=Profile._meta.get_field("daily_step_goal").choices,
        required=False,
    )
    gender = serializers.ChoiceField(
        choices=Profile._meta.get_field("gender").choices,
        required=False,
        allow_blank=True,
    )
    metadata = serializers.JSONField(required=False)

    def validate(self, attrs):
        if len(attrs) == 0:
            raise serializers.ValidationError("At least one profile field must be provided.")

        return attrs
