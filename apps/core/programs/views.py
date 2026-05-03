from drf_spectacular.utils import OpenApiExample, OpenApiParameter, extend_schema, extend_schema_view
from django.db.models import Prefetch, Q
from rest_framework.generics import ListAPIView, RetrieveAPIView, get_object_or_404
from rest_framework.permissions import IsAdminUser, IsAuthenticated
from rest_framework.response import Response
from rest_framework.status import HTTP_200_OK
from rest_framework.throttling import UserRateThrottle
from rest_framework.views import APIView

from apps.core.openapi import (
    BAD_REQUEST_RESPONSE,
    FORBIDDEN_RESPONSE,
    NOT_FOUND_RESPONSE,
    PROGRAM_ID_PATH_PARAMETER,
    THROTTLED_RESPONSE,
    UNAUTHORIZED_RESPONSE,
)
from apps.core.pagination import StandardResultsSetPagination
from apps.core.programs.models import ExerciseProgram, ExerciseProgramCompletion, ExerciseProgramItem
from apps.core.programs.services import mark_program_as_finished
from apps.core.programs.viewmodels import (
    ExerciseProgramCompletionUpdateViewModel,
    ExerciseProgramCompletionViewModel,
    ExerciseProgramDetailViewModel,
    ExerciseProgramListItemViewModel,
)

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


def build_completion_prefetch(user):
    return Prefetch(
        "completions",
        queryset=ExerciseProgramCompletion.objects.filter(user=user).order_by("-finished_at", "-created_at"),
        to_attr="current_user_completion_records",
    )


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
        queryset = (
            ExerciseProgram.objects.filter(is_active=True)
            .prefetch_related(
                Prefetch(
                    "exercise_items",
                    queryset=ExerciseProgramItem.objects.select_related("exercise").order_by("exercise_order"),
                ),
                build_completion_prefetch(self.request.user),
            )
            .order_by("title")
        )
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
        queryset = (
            ExerciseProgram.objects.all()
            .prefetch_related(
                Prefetch(
                    "exercise_items",
                    queryset=ExerciseProgramItem.objects.select_related("exercise").order_by("exercise_order"),
                ),
                build_completion_prefetch(self.request.user),
            )
            .order_by("title")
        )
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
        description="Return one exercise program with its ordered reusable exercises.",
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
    lookup_url_kwarg = "id"

    def get_queryset(self):
        return ExerciseProgram.objects.filter(is_active=True).prefetch_related(
            Prefetch(
                "exercise_items",
                queryset=ExerciseProgramItem.objects.select_related("exercise").order_by("exercise_order"),
            ),
            build_completion_prefetch(self.request.user),
        )


@extend_schema_view(
    post=extend_schema(
        operation_id="complete_program",
        summary="Mark exercise program as finished",
        description="Store the completion flag and finish timestamp for the authenticated user and program.",
        parameters=[PROGRAM_ID_PATH_PARAMETER],
        request=ExerciseProgramCompletionUpdateViewModel,
        examples=[
            OpenApiExample(
                "Completion request",
                value={
                    "finished_at": "2026-05-03T10:15:00Z",
                },
                request_only=True,
            ),
            OpenApiExample(
                "Completion response",
                value={
                    "is_finished": True,
                    "finished_at": "2026-05-03T10:15:00Z",
                },
                response_only=True,
                status_codes=["200"],
            ),
        ],
        responses={
            200: ExerciseProgramCompletionViewModel,
            400: BAD_REQUEST_RESPONSE,
            401: UNAUTHORIZED_RESPONSE,
            403: FORBIDDEN_RESPONSE,
            404: NOT_FOUND_RESPONSE,
            429: THROTTLED_RESPONSE,
        },
    )
)
class ProgramCompletionView(APIView):
    permission_classes = [IsAuthenticated]
    throttle_classes = [UserRateThrottle]

    def post(self, request, id: str):
        serializer = ExerciseProgramCompletionUpdateViewModel(data=request.data)
        serializer.is_valid(raise_exception=True)

        program = get_object_or_404(ExerciseProgram.objects.filter(is_active=True), id=id)
        completion = mark_program_as_finished(
            user=request.user,
            program=program,
            finished_at=serializer.validated_data["finished_at"],
        )

        return Response(ExerciseProgramCompletionViewModel(completion).data, status=HTTP_200_OK)
