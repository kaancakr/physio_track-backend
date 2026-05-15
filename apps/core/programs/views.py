from __future__ import annotations

from calendar import monthrange
from datetime import date
import hashlib

from drf_spectacular.utils import OpenApiParameter, extend_schema, extend_schema_view
from django.db.models import Max, Prefetch, Q
from django.shortcuts import get_object_or_404
from django.utils.http import quote_etag
from rest_framework.generics import ListAPIView, RetrieveAPIView
from rest_framework.permissions import IsAdminUser, IsAuthenticated
from rest_framework.response import Response
from rest_framework.status import HTTP_304_NOT_MODIFIED
from rest_framework.status import HTTP_200_OK
from rest_framework.throttling import UserRateThrottle
from rest_framework.views import APIView

from apps.core.openapi import (
    BAD_REQUEST_RESPONSE,
    EXERCISE_ID_PATH_PARAMETER,
    FORBIDDEN_RESPONSE,
    NOT_FOUND_RESPONSE,
    PROGRAM_ID_PATH_PARAMETER,
    STEP_INDEX_PATH_PARAMETER,
    THROTTLED_RESPONSE,
    UNAUTHORIZED_RESPONSE,
)
from apps.core.pagination import StandardResultsSetPagination
from apps.core.programs.models import ExerciseProgram, ExerciseProgramItem
from apps.core.programs.services import (
    ProgramProgressSnapshot,
    build_program_progress,
    build_favourite_exercise_snapshot,
    complete_exercise_step,
    create_or_update_favourite_exercise,
    get_exercise_progress_by_program_item_for_user,
    get_favourite_exercises_by_exercise_id_for_user,
    get_program_item,
)
from apps.core.programs.viewmodels import (
    FavouriteCalendarViewModel,
    FavouriteExerciseCalendarQueryViewModel,
    FavouriteExerciseUpdateRequestViewModel,
    FavouriteExerciseUpdateResponseViewModel,
    ExerciseStepCompletionResponseViewModel,
    ExerciseProgramExerciseDetailViewModel,
    ExerciseProgramExerciseListItemViewModel,
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

FAVOURITE_CALENDAR_PARAMETERS = [
    OpenApiParameter(
        name="year",
        type=int,
        location=OpenApiParameter.QUERY,
        description="Calendar year.",
        required=True,
    ),
    OpenApiParameter(
        name="month",
        type=int,
        location=OpenApiParameter.QUERY,
        description="Calendar month as a number between 1 and 12.",
        required=True,
    ),
]


def serialize_etag_value(*parts: object) -> str:
    raw_value = "|".join(str(part) for part in parts)
    return quote_etag(hashlib.sha256(raw_value.encode("utf-8")).hexdigest())


def get_if_none_match_value(request) -> str | None:
    header_value = request.headers.get("If-None-Match")

    if header_value is None:
        return None

    stripped_header_value = header_value.strip()

    if stripped_header_value == "":
        return None

    return stripped_header_value


def build_not_modified_response(etag: str) -> Response:
    response = Response(status=HTTP_304_NOT_MODIFIED)
    response["ETag"] = etag
    return response


def add_etag_header(response: Response, etag: str) -> Response:
    response["ETag"] = etag
    return response


def format_timestamp(value) -> str:
    if value is None:
        return "none"

    return value.isoformat()


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


def build_program_queryset():
    return ExerciseProgram.objects.prefetch_related(
        Prefetch(
            "exercise_items",
            queryset=ExerciseProgramItem.objects.select_related("exercise").order_by("exercise_order"),
        ),
    ).order_by("title")


def build_program_list_etag(queryset, request) -> str:
    program_aggregate = queryset.aggregate(
        latest_program_updated_at=Max("updated_at"),
        latest_exercise_item_updated_at=Max("exercise_items__updated_at"),
    )
    user_progress_aggregate = queryset.filter(step_completions__user=request.user).aggregate(
        latest_step_completion_updated_at=Max("step_completions__updated_at"),
    )

    return serialize_etag_value(
        "program-list",
        request.user.id,
        request.get_full_path(),
        queryset.count(),
        format_timestamp(program_aggregate["latest_program_updated_at"]),
        format_timestamp(program_aggregate["latest_exercise_item_updated_at"]),
        format_timestamp(user_progress_aggregate["latest_step_completion_updated_at"]),
    )


def build_program_admin_list_etag(queryset, request) -> str:
    aggregate = queryset.aggregate(
        latest_program_updated_at=Max("updated_at"),
        latest_exercise_item_updated_at=Max("exercise_items__updated_at"),
    )

    return serialize_etag_value(
        "program-admin-list",
        request.user.id,
        request.get_full_path(),
        queryset.count(),
        format_timestamp(aggregate["latest_program_updated_at"]),
        format_timestamp(aggregate["latest_exercise_item_updated_at"]),
    )


def build_program_exercise_list_etag(program_id: str, queryset, request) -> str:
    aggregate = queryset.aggregate(
        latest_program_item_updated_at=Max("updated_at"),
        latest_exercise_updated_at=Max("exercise__updated_at"),
    )
    user_progress_aggregate = queryset.filter(exercise__step_completions__user=request.user).aggregate(
        latest_step_completion_updated_at=Max("exercise__step_completions__updated_at"),
    )
    favourite_aggregate = queryset.filter(exercise__user_favourite_exercises__user=request.user).aggregate(
        latest_favourite_updated_at=Max("exercise__user_favourite_exercises__updated_at"),
    )

    return serialize_etag_value(
        "program-exercise-list",
        request.user.id,
        program_id,
        request.get_full_path(),
        queryset.count(),
        format_timestamp(aggregate["latest_program_item_updated_at"]),
        format_timestamp(aggregate["latest_exercise_updated_at"]),
        format_timestamp(user_progress_aggregate["latest_step_completion_updated_at"]),
        format_timestamp(favourite_aggregate["latest_favourite_updated_at"]),
    )


def build_program_exercise_detail_etag(program_item: ExerciseProgramItem, request) -> str:
    latest_step_completion = program_item.exercise.step_completions.filter(
        user=request.user,
        program=program_item.program,
    ).aggregate(
        latest_step_completion_updated_at=Max("updated_at"),
    )
    latest_favourite_update = program_item.exercise.user_favourite_exercises.filter(user=request.user).aggregate(
        latest_favourite_updated_at=Max("updated_at"),
    )

    return serialize_etag_value(
        "program-exercise-detail",
        request.user.id,
        program_item.program_id,
        program_item.exercise_id,
        request.get_full_path(),
        format_timestamp(program_item.updated_at),
        format_timestamp(program_item.exercise.updated_at),
        format_timestamp(program_item.program.updated_at),
        format_timestamp(latest_step_completion["latest_step_completion_updated_at"]),
        format_timestamp(latest_favourite_update["latest_favourite_updated_at"]),
    )


def build_favourite_calendar_etag(request, year: int, month: int) -> str:
    favourite_queryset = request.user.favourite_exercises.filter(exercise__program_items__program__is_active=True).distinct()
    favourite_aggregate = favourite_queryset.aggregate(
        latest_favourite_updated_at=Max("updated_at"),
        latest_exercise_updated_at=Max("exercise__updated_at"),
        latest_program_item_updated_at=Max("exercise__program_items__updated_at"),
        latest_program_updated_at=Max("exercise__program_items__program__updated_at"),
    )
    progress_aggregate = request.user.exercise_step_completions.filter(
        exercise__user_favourite_exercises__user=request.user,
        program__is_active=True,
    ).aggregate(
        latest_step_completion_updated_at=Max("updated_at"),
    )

    return serialize_etag_value(
        "favourite-calendar",
        request.user.id,
        year,
        month,
        request.get_full_path(),
        favourite_queryset.count(),
        format_timestamp(favourite_aggregate["latest_favourite_updated_at"]),
        format_timestamp(favourite_aggregate["latest_exercise_updated_at"]),
        format_timestamp(favourite_aggregate["latest_program_item_updated_at"]),
        format_timestamp(favourite_aggregate["latest_program_updated_at"]),
        format_timestamp(progress_aggregate["latest_step_completion_updated_at"]),
    )


def attach_program_progress(programs: list[ExerciseProgram], user) -> None:
    all_program_items = [
        exercise_item
        for program in programs
        for exercise_item in program.exercise_items.all()
    ]
    exercise_progress_by_program_and_exercise = get_exercise_progress_by_program_item_for_user(
        user=user,
        program_items=all_program_items,
    )

    for program in programs:
        exercise_items = list(program.exercise_items.all())
        progress_by_exercise_id = {}

        for exercise_item in exercise_items:
            exercise_progress = exercise_progress_by_program_and_exercise[
                (str(exercise_item.program_id), str(exercise_item.exercise_id))
            ]
            exercise_item.current_user_exercise_progress = exercise_progress
            progress_by_exercise_id[str(exercise_item.exercise_id)] = exercise_progress

        program.current_user_program_progress = build_program_progress(exercise_items, progress_by_exercise_id)


def attach_empty_program_progress(programs: list[ExerciseProgram]) -> None:
    for program in programs:
        exercise_items = list(program.exercise_items.all())
        program.current_user_program_progress = ProgramProgressSnapshot(
            exercises_count=len(exercise_items),
            completed_exercises_count=0,
            is_finished=False,
        )


def attach_exercise_progress(program_items: list[ExerciseProgramItem], user) -> None:
    exercise_progress_by_program_and_exercise = get_exercise_progress_by_program_item_for_user(
        user=user,
        program_items=program_items,
    )
    favourite_exercises_by_exercise_id = get_favourite_exercises_by_exercise_id_for_user(
        user=user,
        exercise_ids=[str(program_item.exercise_id) for program_item in program_items],
    )

    for program_item in program_items:
        program_item.current_user_exercise_progress = exercise_progress_by_program_and_exercise[
            (str(program_item.program_id), str(program_item.exercise_id))
        ]
        program_item.current_user_favourite_exercise = build_favourite_exercise_snapshot(
            favourite_exercises_by_exercise_id.get(str(program_item.exercise_id))
        )


def build_calendar_days(
    year: int,
    month: int,
    exercises: list[dict[str, object]],
) -> list[dict[str, object]]:
    days_in_month = monthrange(year, month)[1]
    return [
        {
            "date": date(year, month, day_number),
            "exercises": exercises,
        }
        for day_number in range(1, days_in_month + 1)
    ]


@extend_schema_view(
    get=extend_schema(
        operation_id="get_favorite_exercise_calendar",
        summary="Get favourite exercises for the calendar",
        description="Return month date buckets containing the current user's favourited exercises.",
        parameters=FAVOURITE_CALENDAR_PARAMETERS,
        responses={
            200: FavouriteCalendarViewModel,
            400: BAD_REQUEST_RESPONSE,
            401: UNAUTHORIZED_RESPONSE,
            403: FORBIDDEN_RESPONSE,
            429: THROTTLED_RESPONSE,
        },
    )
)
class FavouriteExerciseCalendarView(APIView):
    permission_classes = [IsAuthenticated]
    throttle_classes = [UserRateThrottle]

    def get(self, request):
        query_serializer = FavouriteExerciseCalendarQueryViewModel(data=request.query_params)
        query_serializer.is_valid(raise_exception=True)
        year = int(query_serializer.validated_data["year"])
        month = int(query_serializer.validated_data["month"])
        etag = build_favourite_calendar_etag(request, year=year, month=month)

        if get_if_none_match_value(request) == etag:
            return build_not_modified_response(etag)

        favourite_exercises = list(
            request.user.favourite_exercises.select_related("exercise")
            .prefetch_related(
                Prefetch(
                    "exercise__program_items",
                    queryset=ExerciseProgramItem.objects.select_related("program", "exercise")
                    .filter(program__is_active=True)
                    .order_by("program__title", "exercise_order"),
                    to_attr="active_program_items",
                )
            )
            .order_by("exercise__title")
        )
        all_active_program_items = [
            program_item
            for favourite_exercise in favourite_exercises
            for program_item in getattr(favourite_exercise.exercise, "active_program_items", [])
        ]
        attach_exercise_progress(all_active_program_items, request.user)

        exercises: list[dict[str, object]] = []

        for favourite_exercise in favourite_exercises:
            active_program_items = getattr(favourite_exercise.exercise, "active_program_items", [])
            is_completed = any(program_item.current_user_exercise_progress.is_finished for program_item in active_program_items)
            favourite_snapshot = build_favourite_exercise_snapshot(favourite_exercise)
            exercises.append(
                {
                    "exercise_id": favourite_exercise.exercise_id,
                    "title": favourite_exercise.exercise.title,
                    "is_completed": is_completed,
                    "current_streak_days": favourite_snapshot.current_streak_days,
                    "longest_streak_days": favourite_snapshot.longest_streak_days,
                    "suggested_days_per_week": favourite_snapshot.suggested_days_per_week,
                    "days_of_week": favourite_snapshot.days_of_week,
                }
            )

        response_serializer = FavouriteCalendarViewModel(
            {
                "year": year,
                "month": month,
                "days": build_calendar_days(year=year, month=month, exercises=exercises),
            }
        )
        return add_etag_header(Response(response_serializer.data, status=HTTP_200_OK), etag)


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
        queryset = build_program_queryset().filter(is_active=True)
        focus_area = self.request.query_params.get("focus_area")
        search = self.request.query_params.get("search")
        return apply_program_list_filters(queryset, focus_area, search)

    def list(self, request, *args, **kwargs):
        queryset = self.filter_queryset(self.get_queryset())
        etag = build_program_list_etag(queryset, request)

        if get_if_none_match_value(request) == etag:
            return build_not_modified_response(etag)

        page = self.paginate_queryset(queryset)

        if page is not None:
            attach_program_progress(list(page), request.user)
            serializer = self.get_serializer(page, many=True)
            return add_etag_header(self.get_paginated_response(serializer.data), etag)

        programs = list(queryset)
        attach_program_progress(programs, request.user)
        serializer = self.get_serializer(programs, many=True)
        return add_etag_header(Response(serializer.data, status=HTTP_200_OK), etag)


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
        queryset = build_program_queryset()
        focus_area = self.request.query_params.get("focus_area")
        search = self.request.query_params.get("search")
        is_active = self.request.query_params.get("is_active")

        queryset = apply_program_list_filters(queryset, focus_area, search)

        if is_active == "true":
            queryset = queryset.filter(is_active=True)

        if is_active == "false":
            queryset = queryset.filter(is_active=False)

        return queryset

    def list(self, request, *args, **kwargs):
        queryset = self.filter_queryset(self.get_queryset())
        etag = build_program_admin_list_etag(queryset, request)

        if get_if_none_match_value(request) == etag:
            return build_not_modified_response(etag)

        page = self.paginate_queryset(queryset)

        if page is not None:
            attach_empty_program_progress(list(page))
            serializer = self.get_serializer(page, many=True)
            return add_etag_header(self.get_paginated_response(serializer.data), etag)

        programs = list(queryset)
        attach_empty_program_progress(programs)
        serializer = self.get_serializer(programs, many=True)
        return add_etag_header(Response(serializer.data, status=HTTP_200_OK), etag)


@extend_schema_view(
    get=extend_schema(
        operation_id="list_program_exercises",
        summary="List exercises for a program",
        description="Return the ordered exercises for one active program together with current-user progress.",
        parameters=[PROGRAM_ID_PATH_PARAMETER],
        responses={
            200: ExerciseProgramExerciseListItemViewModel,
            401: UNAUTHORIZED_RESPONSE,
            403: FORBIDDEN_RESPONSE,
            404: NOT_FOUND_RESPONSE,
            429: THROTTLED_RESPONSE,
        },
    )
)
class ProgramExerciseListView(ListAPIView):
    permission_classes = [IsAuthenticated]
    throttle_classes = [UserRateThrottle]
    serializer_class = ExerciseProgramExerciseListItemViewModel

    def get_queryset(self):
        self.program = get_object_or_404(ExerciseProgram.objects.filter(is_active=True), id=self.kwargs["id"])
        return ExerciseProgramItem.objects.select_related("exercise", "program").filter(program=self.program).order_by(
            "exercise_order"
        )

    def list(self, request, *args, **kwargs):
        queryset = self.filter_queryset(self.get_queryset())
        etag = build_program_exercise_list_etag(self.kwargs["id"], queryset, request)

        if get_if_none_match_value(request) == etag:
            return build_not_modified_response(etag)

        program_items = list(queryset)
        attach_exercise_progress(program_items, request.user)
        serializer = self.get_serializer(program_items, many=True)
        return add_etag_header(Response(serializer.data, status=HTTP_200_OK), etag)


@extend_schema_view(
    get=extend_schema(
        operation_id="get_program_exercise",
        summary="Get one exercise for a program",
        description="Return one exercise from one active program together with ordered steps and current-user progress.",
        parameters=[PROGRAM_ID_PATH_PARAMETER, EXERCISE_ID_PATH_PARAMETER],
        responses={
            200: ExerciseProgramExerciseDetailViewModel,
            401: UNAUTHORIZED_RESPONSE,
            403: FORBIDDEN_RESPONSE,
            404: NOT_FOUND_RESPONSE,
            429: THROTTLED_RESPONSE,
        },
    )
)
class ProgramExerciseDetailView(RetrieveAPIView):
    permission_classes = [IsAuthenticated]
    throttle_classes = [UserRateThrottle]
    serializer_class = ExerciseProgramExerciseDetailViewModel
    lookup_field = "exercise_id"
    lookup_url_kwarg = "exercise_id"

    def get_object(self):
        return get_object_or_404(
            ExerciseProgramItem.objects.select_related("program", "exercise").filter(
                program_id=self.kwargs["id"],
                exercise_id=self.kwargs["exercise_id"],
                program__is_active=True,
            )
        )

    def retrieve(self, request, *args, **kwargs):
        program_item = self.get_object()
        etag = build_program_exercise_detail_etag(program_item, request)

        if get_if_none_match_value(request) == etag:
            return build_not_modified_response(etag)

        attach_exercise_progress([program_item], request.user)
        serializer = self.get_serializer(program_item)
        return add_etag_header(Response(serializer.data, status=HTTP_200_OK), etag)


@extend_schema_view(
    post=extend_schema(
        operation_id="update_exercise_favorite",
        summary="Add or remove an exercise favourite",
        description="Create or remove a favourite exercise for the authenticated user.",
        parameters=[PROGRAM_ID_PATH_PARAMETER, EXERCISE_ID_PATH_PARAMETER],
        request=FavouriteExerciseUpdateRequestViewModel,
        responses={
            200: FavouriteExerciseUpdateResponseViewModel,
            400: BAD_REQUEST_RESPONSE,
            401: UNAUTHORIZED_RESPONSE,
            403: FORBIDDEN_RESPONSE,
            404: NOT_FOUND_RESPONSE,
            429: THROTTLED_RESPONSE,
        },
    )
)
class ExerciseFavouriteUpdateView(APIView):
    permission_classes = [IsAuthenticated]
    throttle_classes = [UserRateThrottle]

    def post(self, request, id: str, exercise_id: str):
        serializer = FavouriteExerciseUpdateRequestViewModel(data=request.data)
        serializer.is_valid(raise_exception=True)
        program_item = get_program_item(program_id=id, exercise_id=exercise_id)
        favourite_exercise, message = create_or_update_favourite_exercise(
            user=request.user,
            exercise=program_item.exercise,
            is_favorite=bool(serializer.validated_data["is_favorite"]),
            days_of_week=serializer.validated_data.get("days_of_week"),
        )
        favourite_snapshot = build_favourite_exercise_snapshot(favourite_exercise)

        return Response(
            {
                "exercise_id": str(program_item.exercise_id),
                "is_favorite": favourite_snapshot.is_favorite,
                "suggested_days_per_week": favourite_snapshot.suggested_days_per_week,
                "days_of_week": favourite_snapshot.days_of_week,
                "message": message,
            },
            status=HTTP_200_OK,
        )


@extend_schema_view(
    post=extend_schema(
        operation_id="complete_exercise_step",
        summary="Complete the next exercise step",
        description="Mark the next required instruction step as completed for the authenticated user.",
        parameters=[PROGRAM_ID_PATH_PARAMETER, EXERCISE_ID_PATH_PARAMETER, STEP_INDEX_PATH_PARAMETER],
        responses={
            200: ExerciseStepCompletionResponseViewModel,
            400: BAD_REQUEST_RESPONSE,
            401: UNAUTHORIZED_RESPONSE,
            403: FORBIDDEN_RESPONSE,
            404: NOT_FOUND_RESPONSE,
            429: THROTTLED_RESPONSE,
        },
    )
)
class ExerciseStepCompletionView(APIView):
    permission_classes = [IsAuthenticated]
    throttle_classes = [UserRateThrottle]
    serializer_class = ExerciseStepCompletionResponseViewModel

    def post(self, request, id: str, exercise_id: str, step_index: int):
        program_item = get_program_item(program_id=id, exercise_id=exercise_id)
        completion_result = complete_exercise_step(
            user=request.user,
            program_item=program_item,
            step_index=step_index,
        )

        return Response(
            {
                "program_id": str(program_item.program_id),
                "exercise_id": str(program_item.exercise_id),
                "completed_step_indexes": completion_result.exercise_progress.completed_step_indexes,
                "completed_steps_count": completion_result.exercise_progress.completed_steps_count,
                "steps_count": completion_result.exercise_progress.steps_count,
                "next_step_index": completion_result.exercise_progress.next_step_index,
                "is_finished": completion_result.exercise_progress.is_finished,
                "is_completed": completion_result.exercise_progress.is_finished,
                "is_favorite": completion_result.favourite_exercise.is_favorite,
                "suggested_days_per_week": completion_result.favourite_exercise.suggested_days_per_week,
                "days_of_week": completion_result.favourite_exercise.days_of_week,
                "current_streak_days": completion_result.favourite_exercise.current_streak_days,
                "longest_streak_days": completion_result.favourite_exercise.longest_streak_days,
                "program_progress": {
                    "exercises_count": completion_result.program_progress.exercises_count,
                    "completed_exercises_count": completion_result.program_progress.completed_exercises_count,
                    "is_finished": completion_result.program_progress.is_finished,
                },
            },
            status=HTTP_200_OK,
        )
