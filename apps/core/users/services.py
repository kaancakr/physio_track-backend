from typing import Any

from django.db import transaction

from apps.core.users.models import Profile, User


def update_user_profile(
    user: User,
    profile_data: dict[str, Any],
) -> User:
    allowed_profile_fields = {
        "full_name",
        "focus_area",
        "weekly_goal",
        "age_range",
        "daily_step_goal",
        "metadata",
    }
    next_profile_values = {
        field_name: field_value
        for field_name, field_value in profile_data.items()
        if field_name in allowed_profile_fields
    }

    if len(next_profile_values) == 0:
        return user

    with transaction.atomic():
        profile, _ = Profile.objects.select_for_update().get_or_create(
            user=user,
            defaults={
                "full_name": "",
                "focus_area": "mobility",
                "weekly_goal": 2,
                "age_range": "18-29",
                "daily_step_goal": 3000,
                "metadata": {},
            },
        )

        for field_name, field_value in next_profile_values.items():
            setattr(profile, field_name, field_value)

        update_fields = list(next_profile_values.keys()) + ["updated_at"]
        profile.save(update_fields=update_fields)

    user.refresh_from_db()
    return user
