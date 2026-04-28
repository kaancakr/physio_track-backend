from django.contrib import admin

from apps.core.users.models import Profile, User


@admin.register(User)
class UserAdmin(admin.ModelAdmin):
    list_display = ("email", "is_active", "is_email_verified", "is_staff", "created_at")
    list_filter = ("is_active", "is_email_verified", "is_staff")
    search_fields = ("email",)
    ordering = ("-created_at",)


@admin.register(Profile)
class ProfileAdmin(admin.ModelAdmin):
    list_display = ("user", "full_name", "focus_area", "weekly_goal", "daily_step_goal")
    list_filter = ("focus_area", "weekly_goal", "age_range", "daily_step_goal")
    search_fields = ("user__email", "full_name")
