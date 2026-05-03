from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin

from apps.core.users.models import Profile, User


class ProfileInline(admin.StackedInline):
    model = Profile
    extra = 0
    can_delete = False
    fields = ("full_name", "focus_area", "weekly_goal", "age_range", "daily_step_goal", "gender", "metadata")


@admin.register(User)
class UserAdmin(BaseUserAdmin):
    list_display = (
        "email",
        "full_name",
        "focus_area",
        "gender",
        "is_active",
        "is_email_verified",
        "is_staff",
        "is_superuser",
        "created_at",
    )
    list_filter = ("is_active", "is_email_verified", "is_staff", "is_superuser", "groups")
    search_fields = ("email", "profile__full_name")
    ordering = ("-created_at",)
    readonly_fields = ("id", "public_id", "created_at", "updated_at", "last_login")
    inlines = (ProfileInline,)
    fieldsets = (
        (None, {"fields": ("email", "password")}),
        ("Personal info", {"fields": ("id", "public_id")}),
        (
            "Permissions",
            {
                "fields": (
                    "is_active",
                    "is_staff",
                    "is_superuser",
                    "is_email_verified",
                    "groups",
                    "user_permissions",
                )
            },
        ),
        ("Important dates", {"fields": ("last_login", "created_at", "updated_at")}),
    )
    add_fieldsets = (
        (
            None,
            {
                "classes": ("wide",),
                "fields": ("email", "password1", "password2", "is_active", "is_staff", "is_superuser"),
            },
        ),
    )

    def get_queryset(self, request):
        return super().get_queryset(request).select_related("profile")

    @admin.display(ordering="profile__full_name", description="Full name")
    def full_name(self, obj: User) -> str:
        if hasattr(obj, "profile"):
            return obj.profile.full_name

        return ""

    @admin.display(ordering="profile__focus_area", description="Focus area")
    def focus_area(self, obj: User) -> str:
        if hasattr(obj, "profile"):
            return obj.profile.focus_area

        return ""


@admin.register(Profile)
class ProfileAdmin(admin.ModelAdmin):
    list_display = ("user", "full_name", "focus_area", "weekly_goal", "daily_step_goal", "gender")
    list_filter = ("focus_area", "weekly_goal", "age_range", "daily_step_goal", "gender")
    search_fields = ("user__email", "full_name")
