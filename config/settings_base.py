from datetime import timedelta
from pathlib import Path
from typing import Final

from dotenv import load_dotenv

BASE_DIR: Final[Path] = Path(__file__).resolve().parent.parent

load_dotenv(BASE_DIR / ".env")


def read_optional_env(name: str) -> str | None:
    import os

    value = os.environ.get(name)

    if value is None:
        return None

    stripped_value = value.strip()

    if stripped_value == "":
        return None

    return stripped_value


def read_required_env(name: str) -> str:
    value = read_optional_env(name)

    if value is None:
        raise RuntimeError(f"Missing required environment variable: {name}")

    return value


def parse_bool(value: str | None) -> bool:
    if value is None:
        return False

    normalized_value = value.lower()

    if normalized_value in {"1", "true", "yes", "on"}:
        return True

    if normalized_value in {"0", "false", "no", "off"}:
        return False

    raise RuntimeError(f"Invalid boolean environment value: {value}")


def parse_csv(value: str | None) -> list[str]:
    if value is None:
        return []

    return [item.strip() for item in value.split(",") if item.strip() != ""]


INSTALLED_APPS: list[str] = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "rest_framework",
    "drf_spectacular",
    "rest_framework_simplejwt.token_blacklist",
    "apps.core.apps.CoreConfig",
    "apps.core.users.apps.UsersConfig",
    "apps.core.authentication.apps.AuthenticationConfig",
    "apps.core.programs.apps.ProgramsConfig",
]

MIDDLEWARE: list[str] = [
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "config.urls"
WSGI_APPLICATION = "config.wsgi.application"
ASGI_APPLICATION = "config.asgi.application"

TEMPLATES: list[dict[str, object]] = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.debug",
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    }
]

AUTH_USER_MODEL = "users.User"
LANGUAGE_CODE = "en-us"
TIME_ZONE = "UTC"
USE_I18N = True
USE_TZ = True
STATIC_URL = "static/"
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

REST_FRAMEWORK: dict[str, object] = {
    "DEFAULT_AUTHENTICATION_CLASSES": (
        "apps.core.authentication.jwt_authentication.VersionedJWTAuthentication",
    ),
    "DEFAULT_PERMISSION_CLASSES": (
        "rest_framework.permissions.AllowAny",
    ),
    "DEFAULT_SCHEMA_CLASS": "drf_spectacular.openapi.AutoSchema",
    "DEFAULT_THROTTLE_RATES": {
        "signup_ip": "5/hour",
        "signup_resend_ip": "1/minute",
        "signup_resend_email": "1/minute",
        "verify_signup_ip": "10/hour",
        "verify_signup_email": "1/minute",
        "login_ip": "10/hour",
        "login_email": "10/hour",
        "refresh_ip": "30/hour",
        "user": "120/hour",
    },
}

SIMPLE_JWT: dict[str, object] = {
    "AUTH_HEADER_TYPES": ("Bearer",),
    "BLACKLIST_AFTER_ROTATION": True,
    "ROTATE_REFRESH_TOKENS": True,
    "ACCESS_TOKEN_LIFETIME": timedelta(minutes=15),
    "REFRESH_TOKEN_LIFETIME": timedelta(days=30),
}

SPECTACULAR_SETTINGS: dict[str, object] = {
    "TITLE": "PhysioTrack Backend API",
    "DESCRIPTION": "OpenAPI schema for the PhysioTrack Django backend.",
    "VERSION": "0.1.0",
    "SERVE_INCLUDE_SCHEMA": False,
    "ENUM_NAME_OVERRIDES": {
        "FocusAreaEnum": "apps.core.users.models.FOCUS_AREA_CHOICES",
    },
    "SWAGGER_UI_SETTINGS": {
        "deepLinking": True,
        "displayOperationId": True,
        "persistAuthorization": True,
    },
}

AUTH_PASSWORD_VALIDATORS: list[dict[str, str]] = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

PHYSIOTRACK_VERIFICATION_CODE_TTL_SECONDS = 600
PHYSIOTRACK_VERIFICATION_CODE_MAX_ATTEMPTS = 5
