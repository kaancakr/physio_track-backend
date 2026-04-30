from drf_spectacular.utils import OpenApiParameter, extend_schema, extend_schema_view
from django.db.models import Q
from rest_framework.generics import ListAPIView, RetrieveAPIView
from rest_framework.permissions import IsAdminUser, IsAuthenticated
from rest_framework.response import Response
from rest_framework.status import HTTP_200_OK
from rest_framework.throttling import UserRateThrottle
from rest_framework.views import APIView

from apps.core.openapi import (
    BAD_REQUEST_RESPONSE,
    FORBIDDEN_RESPONSE,
    NOT_FOUND_RESPONSE,
    THROTTLED_RESPONSE,
    UNAUTHORIZED_RESPONSE,
    UUID_PATH_PARAMETER,
)
from apps.core.pagination import StandardResultsSetPagination
from apps.core.users.models import User
from apps.core.users.services import update_user_profile
from apps.core.users.viewmodels import UserProfileUpdateViewModel, UserViewModel


USER_LIST_PARAMETERS = [
    OpenApiParameter(
        name="page",
        type=int,
        location=OpenApiParameter.QUERY,
        description="Page number.",
    ),
    OpenApiParameter(
        name="page_size",
        type=int,
        location=OpenApiParameter.QUERY,
        description="Number of items per page.",
    ),
    OpenApiParameter(
        name="search",
        type=str,
        location=OpenApiParameter.QUERY,
        description="Search users by email or full name.",
    ),
    OpenApiParameter(
        name="is_active",
        type=bool,
        location=OpenApiParameter.QUERY,
        description="Filter users by active status.",
    ),
    OpenApiParameter(
        name="is_staff",
        type=bool,
        location=OpenApiParameter.QUERY,
        description="Filter users by staff status.",
    ),
]


def apply_user_list_filters(queryset, search: str | None, is_active: str | None, is_staff: str | None):
    next_queryset = queryset

    if search is not None and search != "":
        next_queryset = next_queryset.filter(
            Q(email__icontains=search) | Q(profile__full_name__icontains=search)
        )

    if is_active == "true":
        next_queryset = next_queryset.filter(is_active=True)

    if is_active == "false":
        next_queryset = next_queryset.filter(is_active=False)

    if is_staff == "true":
        next_queryset = next_queryset.filter(is_staff=True)

    if is_staff == "false":
        next_queryset = next_queryset.filter(is_staff=False)

    return next_queryset


@extend_schema_view(
    get=extend_schema(
        operation_id="get_user_profile",
        summary="Get current user details",
        description="Return the authenticated user's profile details.",
        responses={
            200: UserViewModel,
            401: UNAUTHORIZED_RESPONSE,
            403: FORBIDDEN_RESPONSE,
            429: THROTTLED_RESPONSE,
        },
    ),
    patch=extend_schema(
        operation_id="patch_user_profile",
        summary="Update current user details",
        description="Partially update the authenticated user's profile fields.",
        request=UserProfileUpdateViewModel,
        responses={
            200: UserViewModel,
            400: BAD_REQUEST_RESPONSE,
            401: UNAUTHORIZED_RESPONSE,
            403: FORBIDDEN_RESPONSE,
            429: THROTTLED_RESPONSE,
        },
    ),
    put=extend_schema(
        operation_id="put_user_profile",
        summary="Replace current user details",
        description="Update the authenticated user's profile fields with an explicit payload.",
        request=UserProfileUpdateViewModel,
        responses={
            200: UserViewModel,
            400: BAD_REQUEST_RESPONSE,
            401: UNAUTHORIZED_RESPONSE,
            403: FORBIDDEN_RESPONSE,
            429: THROTTLED_RESPONSE,
        },
    ),
)
class CurrentUserView(APIView):
    permission_classes = [IsAuthenticated]
    throttle_classes = [UserRateThrottle]

    def get(self, request):
        return Response(UserViewModel(request.user).data, status=HTTP_200_OK)

    def patch(self, request):
        serializer = UserProfileUpdateViewModel(data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)

        user = update_user_profile(request.user, serializer.validated_data)

        return Response(UserViewModel(user).data, status=HTTP_200_OK)

    def put(self, request):
        serializer = UserProfileUpdateViewModel(data=request.data)
        serializer.is_valid(raise_exception=True)

        user = update_user_profile(request.user, serializer.validated_data)

        return Response(UserViewModel(user).data, status=HTTP_200_OK)


@extend_schema_view(
    get=extend_schema(
        operation_id="list_all_users",
        summary="List all users",
        description="Return all users in the system. This endpoint is for administrators only.",
        parameters=USER_LIST_PARAMETERS,
        responses={
            200: UserViewModel,
            401: UNAUTHORIZED_RESPONSE,
            403: FORBIDDEN_RESPONSE,
            429: THROTTLED_RESPONSE,
        },
    )
)
class UserListView(ListAPIView):
    permission_classes = [IsAdminUser]
    throttle_classes = [UserRateThrottle]
    serializer_class = UserViewModel
    pagination_class = StandardResultsSetPagination

    def get_queryset(self):
        queryset = User.objects.select_related("profile").order_by("-created_at")
        search = self.request.query_params.get("search")
        is_active = self.request.query_params.get("is_active")
        is_staff = self.request.query_params.get("is_staff")
        return apply_user_list_filters(queryset, search, is_active, is_staff)


@extend_schema_view(
    get=extend_schema(
        operation_id="get_user_by_id",
        summary="Get user by id",
        description="Return a single user by public UUID. This endpoint is for administrators only.",
        parameters=[UUID_PATH_PARAMETER],
        responses={
            200: UserViewModel,
            401: UNAUTHORIZED_RESPONSE,
            403: FORBIDDEN_RESPONSE,
            404: NOT_FOUND_RESPONSE,
            429: THROTTLED_RESPONSE,
        },
    )
)
class UserDetailView(RetrieveAPIView):
    permission_classes = [IsAdminUser]
    throttle_classes = [UserRateThrottle]
    serializer_class = UserViewModel
    lookup_field = "public_id"
    lookup_url_kwarg = "user_id"

    def get_queryset(self):
        return User.objects.select_related("profile").all()
