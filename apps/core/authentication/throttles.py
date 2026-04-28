from rest_framework.throttling import SimpleRateThrottle


def read_email_identifier(request) -> str | None:
    raw_email = request.data.get("email")

    if not isinstance(raw_email, str):
        return None

    normalized_email = raw_email.strip().lower()

    if normalized_email == "":
        return None

    return normalized_email


class BaseIpRateThrottle(SimpleRateThrottle):
    def get_cache_key(self, request, view) -> str:
        return self.cache_format % {
            "scope": self.scope,
            "ident": self.get_ident(request),
        }


class BaseEmailRateThrottle(SimpleRateThrottle):
    def get_cache_key(self, request, view) -> str | None:
        email = read_email_identifier(request)

        if email is None:
            return None

        return self.cache_format % {
            "scope": self.scope,
            "ident": email,
        }


class SignupIpRateThrottle(BaseIpRateThrottle):
    scope = "signup_ip"


class SignupResendIpRateThrottle(BaseIpRateThrottle):
    scope = "signup_resend_ip"


class SignupResendEmailRateThrottle(BaseEmailRateThrottle):
    scope = "signup_resend_email"


class VerifySignupIpRateThrottle(BaseIpRateThrottle):
    scope = "verify_signup_ip"


class VerifySignupEmailRateThrottle(BaseEmailRateThrottle):
    scope = "verify_signup_email"


class LoginIpRateThrottle(BaseIpRateThrottle):
    scope = "login_ip"


class LoginEmailRateThrottle(BaseEmailRateThrottle):
    scope = "login_email"


class RefreshIpRateThrottle(BaseIpRateThrottle):
    scope = "refresh_ip"
