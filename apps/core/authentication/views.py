from drf_spectacular.utils import extend_schema
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.status import HTTP_200_OK, HTTP_201_CREATED
from rest_framework.throttling import UserRateThrottle
from rest_framework.views import APIView
from rest_framework_simplejwt.serializers import TokenRefreshSerializer

from apps.core.authentication.permissions import IsUnauthenticated
from apps.core.authentication.services import (
    authenticate_user,
    logout_user,
    resend_signup_code,
    signup_user,
    verify_signup_code,
)
from apps.core.authentication.throttles import (
    LoginEmailRateThrottle,
    LoginIpRateThrottle,
    RefreshIpRateThrottle,
    SignupIpRateThrottle,
    SignupResendEmailRateThrottle,
    SignupResendIpRateThrottle,
    VerifySignupEmailRateThrottle,
    VerifySignupIpRateThrottle,
)
from apps.core.authentication.viewmodels import (
    LoginRequestViewModel,
    LogoutRequestViewModel,
    MessageViewModel,
    SendSignupCodeRequestViewModel,
    SignupRequestViewModel,
    SignupResponseViewModel,
    TokenRefreshResponseViewModel,
    TokenPairResponseViewModel,
    VerifySignupCodeRequestViewModel,
)
from apps.core.openapi import (
    BAD_REQUEST_RESPONSE,
    FORBIDDEN_RESPONSE,
    THROTTLED_RESPONSE,
    UNAUTHORIZED_RESPONSE,
)
from apps.core.users.viewmodels import CurrentUserViewModel


class SignupView(APIView):
    permission_classes = [IsUnauthenticated]
    throttle_classes = [SignupIpRateThrottle]

    @extend_schema(
        operation_id="signup",
        summary="Create account",
        description="Create an unverified account and send a signup verification code by email.",
        request=SignupRequestViewModel,
        responses={
            201: SignupResponseViewModel,
            400: BAD_REQUEST_RESPONSE,
            429: THROTTLED_RESPONSE,
        },
    )
    def post(self, request):
        serializer = SignupRequestViewModel(data=request.data)
        serializer.is_valid(raise_exception=True)

        signup_user(serializer.validated_data)

        return Response(
            {
                "message": "Account created. Verify the code sent to your email to activate access.",
                "verification_required": True,
            },
            status=HTTP_201_CREATED,
        )


class SendSignupCodeView(APIView):
    permission_classes = [IsUnauthenticated]
    throttle_classes = [SignupResendIpRateThrottle, SignupResendEmailRateThrottle]

    @extend_schema(
        operation_id="send_signup_code",
        summary="Resend signup code",
        description="Resend a signup verification code when the account is still unverified.",
        request=SendSignupCodeRequestViewModel,
        responses={
            200: MessageViewModel,
            400: BAD_REQUEST_RESPONSE,
            429: THROTTLED_RESPONSE,
        },
    )
    def post(self, request):
        serializer = SendSignupCodeRequestViewModel(data=request.data)
        serializer.is_valid(raise_exception=True)

        resend_signup_code(serializer.validated_data)

        return Response(
            {
                "message": "If the signup flow is still pending, a new verification code has been sent.",
            },
            status=HTTP_200_OK,
        )
        
class ResendSignupCodeView(APIView):
    permission_classes = [IsUnauthenticated]
    throttle_classes = [SignupResendIpRateThrottle, SignupResendEmailRateThrottle]

    @extend_schema(
        operation_id="resend_signup_code",
        summary="Resend signup code",
        description="Resend a signup verification code when the account is still unverified.",
        request=SendSignupCodeRequestViewModel,
        responses={
            200: MessageViewModel,
            400: BAD_REQUEST_RESPONSE,
            429: THROTTLED_RESPONSE,
        },
    )
    def post(self, request):
        serializer = SendSignupCodeRequestViewModel(data=request.data)
        serializer.is_valid(raise_exception=True)

        resend_signup_code(serializer.validated_data)

        return Response(
            {
                "message": "If the signup flow is still pending, a new verification code has been sent.",
            },
            status=HTTP_200_OK,
        )

class VerifySignupCodeView(APIView):
    permission_classes = [IsUnauthenticated]
    throttle_classes = [VerifySignupIpRateThrottle, VerifySignupEmailRateThrottle]

    @extend_schema(
        operation_id="verify_signup_code",
        summary="Verify signup code",
        description="Verify the email code for signup and return JWT tokens.",
        request=VerifySignupCodeRequestViewModel,
        responses={
            200: TokenPairResponseViewModel,
            400: BAD_REQUEST_RESPONSE,
            429: THROTTLED_RESPONSE,
        },
    )
    def post(self, request):
        serializer = VerifySignupCodeRequestViewModel(data=request.data)
        serializer.is_valid(raise_exception=True)

        token_bundle = verify_signup_code(serializer.validated_data)

        return Response(
            {
                "access": token_bundle.access,
                "refresh": token_bundle.refresh,
                "user": CurrentUserViewModel(token_bundle.user).data,
            },
            status=HTTP_200_OK,
        )


class LoginView(APIView):
    permission_classes = [IsUnauthenticated]
    throttle_classes = [LoginIpRateThrottle, LoginEmailRateThrottle]

    @extend_schema(
        operation_id="login",
        summary="Login",
        description="Authenticate with email and password and return JWT tokens.",
        request=LoginRequestViewModel,
        responses={
            200: TokenPairResponseViewModel,
            400: BAD_REQUEST_RESPONSE,
            401: UNAUTHORIZED_RESPONSE,
            429: THROTTLED_RESPONSE,
        },
    )
    def post(self, request):
        serializer = LoginRequestViewModel(data=request.data)
        serializer.is_valid(raise_exception=True)

        token_bundle = authenticate_user(serializer.validated_data)

        return Response(
            {
                "access": token_bundle.access,
                "refresh": token_bundle.refresh,
                "user": CurrentUserViewModel(token_bundle.user).data,
            },
            status=HTTP_200_OK,
        )


class TokenRefreshRouteView(APIView):
    throttle_classes = [RefreshIpRateThrottle]

    @extend_schema(
        operation_id="refresh_token",
        summary="Refresh JWT access token",
        description="Exchange a refresh token for a new access token.",
        request=TokenRefreshSerializer,
        responses={
            200: TokenRefreshResponseViewModel,
            400: BAD_REQUEST_RESPONSE,
            429: THROTTLED_RESPONSE,
        },
    )
    def post(self, request):
        serializer = TokenRefreshSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        return Response(serializer.validated_data, status=HTTP_200_OK)


class LogoutView(APIView):
    permission_classes = [IsAuthenticated]
    throttle_classes = [UserRateThrottle]

    @extend_schema(
        operation_id="logout",
        summary="Logout",
        description="Blacklist the submitted refresh token.",
        request=LogoutRequestViewModel,
        responses={
            200: MessageViewModel,
            400: BAD_REQUEST_RESPONSE,
            401: UNAUTHORIZED_RESPONSE,
            429: THROTTLED_RESPONSE,
        },
    )
    def post(self, request):
        serializer = LogoutRequestViewModel(data=request.data)
        serializer.is_valid(raise_exception=True)

        logout_user(request.user, serializer.validated_data["refresh"])

        return Response({"message": "Logout completed successfully."}, status=HTTP_200_OK)


class MeView(APIView):
    permission_classes = [IsAuthenticated]
    throttle_classes = [UserRateThrottle]

    @extend_schema(
        operation_id="get_current_user",
        summary="Current user",
        description="Return the authenticated user's profile and role flags.",
        responses={
            200: CurrentUserViewModel,
            401: UNAUTHORIZED_RESPONSE,
            403: FORBIDDEN_RESPONSE,
            429: THROTTLED_RESPONSE,
        },
    )
    def get(self, request):
        return Response(CurrentUserViewModel(request.user).data, status=HTTP_200_OK)
