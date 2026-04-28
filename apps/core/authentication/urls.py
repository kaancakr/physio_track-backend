from django.urls import path

from apps.core.authentication.views import (
    LoginView,
    LogoutView,
    MeView,
    SendSignupCodeView,
    SignupView,
    TokenRefreshRouteView,
    VerifySignupCodeView,
)

urlpatterns = [
    path("signup", SignupView.as_view(), name="signup"),
    path("verify-signup-code", VerifySignupCodeView.as_view(), name="verify-signup-code"),
    path("send-signup-code", SendSignupCodeView.as_view(), name="send-signup-code"),
    path("login", LoginView.as_view(), name="login"),
    path("token/refresh", TokenRefreshRouteView.as_view(), name="token-refresh"),
    path("logout", LogoutView.as_view(), name="logout"),
    path("me", MeView.as_view(), name="me"),
]
