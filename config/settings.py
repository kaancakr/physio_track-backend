from config.settings_base import *

SECRET_KEY = read_required_env("DJANGO_SECRET_KEY")
DEBUG = parse_bool(read_optional_env("DJANGO_DEBUG"))
ALLOWED_HOSTS = parse_csv(read_optional_env("DJANGO_ALLOWED_HOSTS"))

if len(ALLOWED_HOSTS) == 0:
    ALLOWED_HOSTS = ["127.0.0.1", "localhost"]

DATABASES: dict[str, dict[str, object]] = {
    "default": {
        "ENGINE": "django.db.backends.postgresql",
        "NAME": read_required_env("POSTGRES_DB"),
        "USER": read_required_env("POSTGRES_USER"),
        "PASSWORD": read_required_env("POSTGRES_PASSWORD"),
        "HOST": read_required_env("POSTGRES_HOST"),
        "PORT": int(read_required_env("POSTGRES_PORT")),
    }
}

PYHSIOTRACK_EMAIL_PROVIDER = read_required_env("PYHSIOTRACK_EMAIL_PROVIDER")
RESEND_API_KEY = read_required_env("RESEND_API_KEY")
RESEND_FROM_EMAIL = read_required_env("RESEND_FROM_EMAIL")
