from __future__ import annotations

import json
import secrets
from datetime import datetime, timedelta
from dataclasses import dataclass
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from django.conf import settings
from django.contrib.auth import authenticate
from django.contrib.auth.hashers import check_password, make_password
from django.core.exceptions import ImproperlyConfigured
from django.core.mail import send_mail
from django.db import transaction
from django.utils import timezone
from rest_framework.exceptions import AuthenticationFailed, ValidationError
from rest_framework_simplejwt.tokens import RefreshToken

from apps.core.authentication.models import EmailVerificationCode, VerificationPurpose
from apps.core.authentication.viewmodels import EmailPayload, LoginPayload, SignupPayload, VerifyCodePayload
from apps.core.users.models import Profile, User


@dataclass(frozen=True)
class TokenBundle:
    user: User
    access: str
    refresh: str


class ResendEmailConnector:
    endpoint = "https://api.resend.com/emails"

    def __init__(self, api_key: str, from_email: str) -> None:
        self.api_key = api_key
        self.from_email = from_email

    def send_signup_code(self, recipient_email: str, code: str) -> None:
        payload = {
            "from": self.from_email,
            "to": [recipient_email],
            "subject": "Your PhysioTrack verification code",
            "text": f"Your PhysioTrack verification code is {code}. It expires in 10 minutes.",
        }
        request = Request(
            self.endpoint,
            data=json.dumps(payload).encode("utf-8"),
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
            },
            method="POST",
        )

        try:
            with urlopen(request, timeout=10) as response:
                response_body = response.read().decode("utf-8")
        except HTTPError as error:
            response_body = error.read().decode("utf-8", errors="replace")
            raise RuntimeError(
                "Resend email delivery failed with "
                f"status={error.code} recipient={recipient_email} body={response_body}"
            ) from error
        except URLError as error:
            raise RuntimeError(
                "Resend email delivery failed with "
                f"recipient={recipient_email} reason={error.reason}"
            ) from error

        parsed_response = json.loads(response_body)

        if "id" not in parsed_response:
            raise RuntimeError(
                "Resend email delivery returned an unexpected response "
                f"for recipient={recipient_email} body={response_body}"
            )


class DjangoEmailConnector:
    def __init__(self, from_email: str) -> None:
        self.from_email = from_email

    def send_signup_code(self, recipient_email: str, code: str) -> None:
        send_mail(
            subject="Your PhysioTrack verification code",
            message=f"Your PhysioTrack verification code is {code}. It expires in 10 minutes.",
            from_email=self.from_email,
            recipient_list=[recipient_email],
            fail_silently=False,
        )


def normalize_email(email: str) -> str:
    return email.strip().lower()


def get_email_connector() -> ResendEmailConnector | DjangoEmailConnector:
    provider = settings.PHYSIOTRACK_EMAIL_PROVIDER

    if provider == "resend":
        return ResendEmailConnector(
            api_key=settings.RESEND_API_KEY,
            from_email=settings.RESEND_FROM_EMAIL,
        )

    if provider == "django":
        return DjangoEmailConnector(from_email=settings.RESEND_FROM_EMAIL)

    raise ImproperlyConfigured(f"Unsupported email provider: {provider}")


def generate_verification_code() -> str:
    numeric_value = secrets.randbelow(900000) + 100000
    return str(numeric_value)


def build_code_expiry() -> datetime:
    ttl_seconds = settings.PHYSIOTRACK_VERIFICATION_CODE_TTL_SECONDS
    return timezone.now() + timedelta(seconds=ttl_seconds)


def build_token_bundle(user: User) -> TokenBundle:
    refresh = RefreshToken.for_user(user)
    refresh["token_version"] = user.token_version
    refresh.access_token["token_version"] = user.token_version
    return TokenBundle(
        user=user,
        access=str(refresh.access_token),
        refresh=str(refresh),
    )


def build_signup_profile_metadata() -> dict[str, object]:
    return {}


def upsert_signup_user(payload: SignupPayload) -> User:
    normalized_email = normalize_email(payload["email"])

    with transaction.atomic():
        existing_user = User.objects.select_for_update().filter(email=normalized_email).first()

        if existing_user is not None and existing_user.is_email_verified:
            raise ValidationError({"email": "An account with this email already exists."})

        if existing_user is None:
            user = User.objects.create_user(
                email=normalized_email,
                password=payload["password"],
                is_active=False,
                is_email_verified=False,
            )
        else:
            user = existing_user
            user.set_password(payload["password"])
            user.is_active = False
            user.is_email_verified = False
            user.save(update_fields=["password", "is_active", "is_email_verified", "updated_at"])

        Profile.objects.update_or_create(
            user=user,
            defaults={
                "full_name": payload["full_name"],
                "focus_area": payload["focus_area"],
                "weekly_goal": payload["weekly_goal"],
                "age_range": payload["age_range"],
                "daily_step_goal": payload["daily_step_goal"],
                "metadata": build_signup_profile_metadata(),
            },
        )

    return user


def replace_signup_code(user: User) -> str:
    code = generate_verification_code()
    code_hash = make_password(code)
    current_time = timezone.now()

    with transaction.atomic():
        EmailVerificationCode.objects.select_for_update().filter(
            user=user,
            purpose=VerificationPurpose.SIGNUP,
            consumed_at__isnull=True,
        ).update(consumed_at=current_time)

        EmailVerificationCode.objects.create(
            user=user,
            purpose=VerificationPurpose.SIGNUP,
            code_hash=code_hash,
            expires_at=build_code_expiry(),
        )

    return code


def send_signup_code(user: User) -> None:
    code = replace_signup_code(user)
    connector = get_email_connector()
    connector.send_signup_code(recipient_email=user.email, code=code)


def signup_user(payload: SignupPayload) -> User:
    user = upsert_signup_user(payload)
    send_signup_code(user)
    return user


def resend_signup_code(payload: EmailPayload) -> None:
    normalized_email = normalize_email(payload["email"])
    user = User.objects.filter(email=normalized_email, is_email_verified=False).first()

    if user is None:
        return

    send_signup_code(user)


def verify_signup_code(payload: VerifyCodePayload) -> TokenBundle:
    normalized_email = normalize_email(payload["email"])
    max_attempts = settings.PHYSIOTRACK_VERIFICATION_CODE_MAX_ATTEMPTS

    with transaction.atomic():
        user = User.objects.select_for_update().filter(email=normalized_email).first()

        if user is None:
            raise ValidationError({"code": "Invalid or expired verification code."})

        verification_code = EmailVerificationCode.objects.select_for_update().filter(
            user=user,
            purpose=VerificationPurpose.SIGNUP,
            consumed_at__isnull=True,
        ).order_by("-created_at").first()

        if verification_code is None:
            raise ValidationError({"code": "Invalid or expired verification code."})

        if verification_code.expires_at <= timezone.now():
            raise ValidationError({"code": "The verification code has expired."})

        if verification_code.attempt_count >= max_attempts:
            raise ValidationError({"code": "Too many verification attempts. Request a new code."})

        if not check_password(payload["code"], verification_code.code_hash):
            verification_code.attempt_count += 1
            verification_code.save(update_fields=["attempt_count", "updated_at"])

            if verification_code.attempt_count >= max_attempts:
                raise ValidationError({"code": "Too many verification attempts. Request a new code."})

            raise ValidationError({"code": "Invalid or expired verification code."})

        verification_code.consumed_at = timezone.now()
        verification_code.save(update_fields=["consumed_at", "updated_at"])

        user.is_active = True
        user.is_email_verified = True
        user.save(update_fields=["is_active", "is_email_verified", "updated_at"])

    return build_token_bundle(user)


def authenticate_user(payload: LoginPayload) -> TokenBundle:
    normalized_email = normalize_email(payload["email"])
    user = User.objects.filter(email=normalized_email).first()

    if user is None:
        raise AuthenticationFailed("Invalid email or password.")

    if not user.is_email_verified:
        raise AuthenticationFailed("Email verification is required before login.")

    if not user.is_active:
        raise AuthenticationFailed("This account is inactive.")

    authenticated_user = authenticate(email=normalized_email, password=payload["password"])

    if authenticated_user is None:
        raise AuthenticationFailed("Invalid email or password.")

    return build_token_bundle(authenticated_user)


def validate_refresh_token_owner(refresh_token: RefreshToken, user: User) -> None:
    token_user_id = refresh_token.payload.get("user_id")
    normalized_token_user_id = user._meta.pk.to_python(token_user_id)

    if normalized_token_user_id != user.id:
        raise ValidationError({"refresh": "Refresh token does not belong to the authenticated user."})


def logout_user(user: User, refresh_token: str) -> None:
    with transaction.atomic():
        token = RefreshToken(refresh_token)
        validate_refresh_token_owner(token, user)
        token.blacklist()
        user.token_version += 1
        user.save(update_fields=["token_version", "updated_at"])
