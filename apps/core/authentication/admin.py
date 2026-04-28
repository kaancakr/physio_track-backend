from django.contrib import admin

from apps.core.authentication.models import EmailVerificationCode


@admin.register(EmailVerificationCode)
class EmailVerificationCodeAdmin(admin.ModelAdmin):
    list_display = (
        "user",
        "purpose",
        "attempt_count",
        "expires_at",
        "consumed_at",
        "created_at",
    )
    list_filter = ("purpose", "consumed_at")
    search_fields = ("user__email",)
