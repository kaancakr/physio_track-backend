from config.settings_base import *

SECRET_KEY = "test-secret-key"
DEBUG = True
ALLOWED_HOSTS = ["testserver", "localhost", "127.0.0.1"]

DATABASES: dict[str, dict[str, object]] = {
    "default": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": BASE_DIR / "test.sqlite3",
    }
}

PASSWORD_HASHERS: list[str] = [
    "django.contrib.auth.hashers.MD5PasswordHasher",
]

EMAIL_BACKEND = "django.core.mail.backends.locmem.EmailBackend"
PHYSIOTRACK_EMAIL_PROVIDER = "django"
RESEND_API_KEY = "test-resend-api-key"
RESEND_FROM_EMAIL = "no-reply@physiotrack.test"
