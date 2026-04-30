from django.apps import AppConfig


class AuthenticationConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.core.authentication"
    label = "authentication"

    def ready(self) -> None:
        import apps.core.authentication.openapi
