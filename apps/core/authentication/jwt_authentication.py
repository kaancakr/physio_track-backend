from __future__ import annotations

from rest_framework.exceptions import AuthenticationFailed
from rest_framework_simplejwt.authentication import JWTAuthentication
from rest_framework_simplejwt.tokens import Token

from apps.core.users.models import User


def parse_token_version_claim(validated_token: Token) -> int:
    token_version = validated_token.get("token_version")

    if not isinstance(token_version, int):
        raise AuthenticationFailed("Token is missing a valid token_version claim.")

    return token_version


class VersionedJWTAuthentication(JWTAuthentication):
    def get_user(self, validated_token: Token) -> User:
        user = super().get_user(validated_token)

        if not isinstance(user, User):
            raise AuthenticationFailed("Authenticated user type is invalid.")

        token_version = parse_token_version_claim(validated_token)

        if user.token_version != token_version:
            raise AuthenticationFailed("Token has been revoked.")

        return user
