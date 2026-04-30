from drf_spectacular.utils import OpenApiParameter, extend_schema, extend_schema_view
from django.db.models import Q
from rest_framework.generics import ListAPIView, RetrieveAPIView
from rest_framework.permissions import IsAdminUser, IsAuthenticated
from rest_framework.throttling import UserRateThrottle

from apps.core.openapi import (
    FORBIDDEN_RESPONSE,
    NOT_FOUND_RESPONSE,
    PROGRAM_ID_PATH_PARAMETER,
    THROTTLED_RESPONSE,
    UNAUTHORIZED_RESPONSE,
)
from apps.core.pagination import StandardResultsSetPagination
from apps.core.programs.models import ExerciseProgram
from apps.core.programs.viewmodels import ExerciseProgramDetailViewModel, ExerciseProgramListItemViewModel

PROGRAM_LIST_PARAMETERS = [
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
        name="focus_area",
        type=str,
        location=OpenApiParameter.QUERY,
        description="Filter programs by focus area.",
    ),
    OpenApiParameter(
        name="search",
        type=str,
        location=OpenApiParameter.QUERY,
        description="Search programs by title, description, or focus area label.",
    ),
]


def apply_program_list_filters(queryset, focus_area: str | None, search: str | None):
    next_queryset = queryset

    if focus_area is not None and focus_area != "":
        next_queryset = next_queryset.filter(focus_area=focus_area)

    if search is not None and search != "":
        next_queryset = next_queryset.filter(
            Q(title__icontains=search)
            | Q(description__icontains=search)
            | Q(focus_area_label__icontains=search)
        )

    return next_queryset


@extend_schema_view(
    get=extend_schema(
        operation_id="list_programs",
        summary="List exercise programs",
        description="Return all active exercise programs available to authenticated users.",
        parameters=PROGRAM_LIST_PARAMETERS,
        responses={
            200: ExerciseProgramListItemViewModel,
            401: UNAUTHORIZED_RESPONSE,
            403: FORBIDDEN_RESPONSE,
            429: THROTTLED_RESPONSE,
        },
    )
)
class ProgramListView(ListAPIView):
    permission_classes = [IsAuthenticated]
    throttle_classes = [UserRateThrottle]
    serializer_class = ExerciseProgramListItemViewModel
    pagination_class = StandardResultsSetPagination

    def get_queryset(self):
        queryset = ExerciseProgram.objects.filter(is_active=True).prefetch_related("steps").order_by("title")
        focus_area = self.request.query_params.get("focus_area")
        search = self.request.query_params.get("search")
        return apply_program_list_filters(queryset, focus_area, search)


@extend_schema_view(
    get=extend_schema(
        operation_id="list_all_programs",
        summary="List all exercise programs",
        description="Return all exercise programs including inactive ones. This endpoint is for administrators only.",
        parameters=[
            *PROGRAM_LIST_PARAMETERS,
            OpenApiParameter(
                name="is_active",
                type=bool,
                location=OpenApiParameter.QUERY,
                description="Filter programs by active status.",
            ),
        ],
        responses={
            200: ExerciseProgramListItemViewModel,
            401: UNAUTHORIZED_RESPONSE,
            403: FORBIDDEN_RESPONSE,
            429: THROTTLED_RESPONSE,
        },
    )
)
class ProgramAdminListView(ListAPIView):
    permission_classes = [IsAdminUser]
    throttle_classes = [UserRateThrottle]
    serializer_class = ExerciseProgramListItemViewModel
    pagination_class = StandardResultsSetPagination

    def get_queryset(self):
        queryset = ExerciseProgram.objects.all().prefetch_related("steps").order_by("title")
        focus_area = self.request.query_params.get("focus_area")
        search = self.request.query_params.get("search")
        is_active = self.request.query_params.get("is_active")

        queryset = apply_program_list_filters(queryset, focus_area, search)

        if is_active == "true":
            queryset = queryset.filter(is_active=True)

        if is_active == "false":
            queryset = queryset.filter(is_active=False)

        return queryset


@extend_schema_view(
    get=extend_schema(
        operation_id="get_program",
        summary="Get exercise program",
        description="Return one exercise program with its ordered steps.",
        parameters=[PROGRAM_ID_PATH_PARAMETER],
        responses={
            200: ExerciseProgramDetailViewModel,
            401: UNAUTHORIZED_RESPONSE,
            403: FORBIDDEN_RESPONSE,
            404: NOT_FOUND_RESPONSE,
            429: THROTTLED_RESPONSE,
        },
    )
)
class ProgramDetailView(RetrieveAPIView):
    permission_classes = [IsAuthenticated]
    throttle_classes = [UserRateThrottle]
    serializer_class = ExerciseProgramDetailViewModel
    lookup_field = "id"

    def get_queryset(self):
        return ExerciseProgram.objects.filter(is_active=True).prefetch_related("steps")
