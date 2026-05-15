from __future__ import annotations

from datetime import date, timedelta
from dataclasses import dataclass
import logging
from typing import Iterable

from django.core.exceptions import ObjectDoesNotExist
from django.db import IntegrityError, transaction
from django.utils import timezone
from rest_framework.exceptions import ValidationError

from apps.core.logging_utils import build_log_extra
from apps.core.programs.models import (
    Exercise,
    ExerciseProgram,
    ExerciseProgramItem,
    ExerciseStepCompletion,
    UserFavouriteExercise,
)
from apps.core.programs.seed_data import PROGRAM_SEED_DATA
from apps.core.users.models import User

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class ExerciseProgressSnapshot:
    completed_step_indexes: list[int]
    next_step_index: int | None
    completed_steps_count: int
    steps_count: int
    is_finished: bool


@dataclass(frozen=True)
class ProgramProgressSnapshot:
    exercises_count: int
    completed_exercises_count: int
    is_finished: bool


@dataclass(frozen=True)
class UserOverallProgressSnapshot:
    programs_count: int
    completed_programs_count: int
    exercises_count: int
    completed_exercises_count: int
    steps_count: int
    completed_steps_count: int
    is_finished: bool


@dataclass(frozen=True)
class StepCompletionResult:
    exercise_progress: ExerciseProgressSnapshot
    program_progress: ProgramProgressSnapshot
    favourite_exercise: FavouriteExerciseSnapshot


@dataclass(frozen=True)
class FavouriteExerciseSnapshot:
    is_favorite: bool
    suggested_days_per_week: int | None
    current_streak_days: int | None
    longest_streak_days: int | None


def build_default_step_image(instruction_step: str) -> dict[str, str | int | None]:
    return {
        "url": "",
        "thumbnail_url": "",
        "width": None,
        "height": None,
        "alt": instruction_step,
    }


def normalize_step_image(image: object, instruction_step: str) -> dict[str, str | int | None]:
    if not isinstance(image, dict):
        return build_default_step_image(instruction_step)

    return {
        "url": str(image.get("url", "")),
        "thumbnail_url": str(image.get("thumbnail_url", "")),
        "width": image.get("width"),
        "height": image.get("height"),
        "alt": str(image.get("alt", instruction_step)),
    }


def build_instruction_step_details(
    instruction_steps: list[str],
    instruction_step_images: list[dict[str, str | int | None]],
) -> list[dict[str, object]]:
    step_details: list[dict[str, object]] = []

    for step_index, instruction_step in enumerate(instruction_steps):
        if step_index < len(instruction_step_images):
            step_image = normalize_step_image(instruction_step_images[step_index], instruction_step)
        else:
            step_image = normalize_step_image({}, instruction_step)

        step_details.append(
            {
                "step_index": step_index,
                "title": f"Step {step_index + 1}",
                "instruction": instruction_step,
                "image": step_image,
            }
        )

    return step_details


def get_instruction_steps_from_metadata(metadata: object) -> list[str]:
    if not isinstance(metadata, dict):
        return []

    instruction_steps = metadata.get("instruction_steps", [])

    if not isinstance(instruction_steps, list):
        return []

    return [str(step) for step in instruction_steps]


def normalize_step_detail(step: object, fallback_step_index: int) -> dict[str, object] | None:
    if not isinstance(step, dict):
        return None

    instruction = str(step.get("instruction", "")).strip()

    if instruction == "":
        return None

    step_index = step.get("step_index", fallback_step_index)
    title = str(step.get("title", f"Step {fallback_step_index + 1}"))

    return {
        "step_index": int(step_index),
        "title": title,
        "instruction": instruction,
        "image": normalize_step_image(step.get("image", {}), instruction),
    }


def get_step_details_from_metadata(metadata: object) -> list[dict[str, object]]:
    if not isinstance(metadata, dict):
        return []

    raw_steps = metadata.get("steps")

    if isinstance(raw_steps, list):
        normalized_steps = [
            normalized_step
            for step_index, step in enumerate(raw_steps)
            for normalized_step in [normalize_step_detail(step, step_index)]
            if normalized_step is not None
        ]

        if len(normalized_steps) > 0:
            return normalized_steps

    instruction_steps = get_instruction_steps_from_metadata(metadata)
    instruction_step_images = metadata.get("instruction_step_images")

    if not isinstance(instruction_step_images, list):
        instruction_step_images = [
            build_default_step_image(instruction_step)
            for instruction_step in instruction_steps
        ]

    normalized_instruction_step_images = [
        normalize_step_image(image, instruction_steps[index])
        for index, image in enumerate(instruction_step_images[: len(instruction_steps)])
    ]

    if len(normalized_instruction_step_images) < len(instruction_steps):
        for instruction_step in instruction_steps[len(normalized_instruction_step_images) :]:
            normalized_instruction_step_images.append(build_default_step_image(instruction_step))

    return build_instruction_step_details(
        instruction_steps=instruction_steps,
        instruction_step_images=normalized_instruction_step_images,
    )


def normalize_exercise_metadata(metadata: object) -> dict[str, object]:
    if not isinstance(metadata, dict):
        return {}

    normalized_steps = get_step_details_from_metadata(metadata)
    metadata_without_legacy_step_fields = {
        key: value
        for key, value in metadata.items()
        if key not in {"instruction_steps", "instruction_step_images", "steps"}
    }

    return {
        **metadata_without_legacy_step_fields,
        "steps": normalized_steps,
    }


def get_instruction_steps(exercise: Exercise) -> list[str]:
    return [
        str(step["instruction"])
        for step in get_instruction_step_details(exercise)
    ]


def get_instruction_step_details(exercise: Exercise) -> list[dict[str, object]]:
    return get_step_details_from_metadata(exercise.metadata)


def get_completed_step_indexes(completions: Iterable[ExerciseStepCompletion]) -> list[int]:
    unique_step_indexes = {completion.step_index for completion in completions}
    return sorted(unique_step_indexes)


def build_completed_step_indexes_by_program_and_exercise(
    completions: Iterable[ExerciseStepCompletion],
) -> dict[tuple[str, str], list[int]]:
    completed_step_indexes_by_program_and_exercise: dict[tuple[str, str], set[int]] = {}

    for completion in completions:
        completion_key = (str(completion.program_id), str(completion.exercise_id))
        existing_indexes = completed_step_indexes_by_program_and_exercise.get(completion_key, set())
        completed_step_indexes_by_program_and_exercise[completion_key] = {
            *existing_indexes,
            completion.step_index,
        }

    return {
        key: sorted(step_indexes)
        for key, step_indexes in completed_step_indexes_by_program_and_exercise.items()
    }


def build_exercise_progress(
    exercise: Exercise,
    completed_step_indexes: list[int],
) -> ExerciseProgressSnapshot:
    steps_count = len(get_instruction_steps(exercise))
    completed_steps_count = len(completed_step_indexes)
    is_finished = steps_count > 0 and completed_steps_count == steps_count

    if is_finished or steps_count == 0:
        next_step_index = None
    else:
        next_step_index = completed_steps_count

    return ExerciseProgressSnapshot(
        completed_step_indexes=completed_step_indexes,
        next_step_index=next_step_index,
        completed_steps_count=completed_steps_count,
        steps_count=steps_count,
        is_finished=is_finished,
    )


def build_program_progress(
    program_items: Iterable[ExerciseProgramItem],
    progress_by_exercise_id: dict[str, ExerciseProgressSnapshot],
) -> ProgramProgressSnapshot:
    items = list(program_items)
    exercises_count = len(items)

    completed_exercises_count = 0

    for item in items:
        exercise_progress = progress_by_exercise_id.get(str(item.exercise_id))

        if exercise_progress is not None and exercise_progress.is_finished:
            completed_exercises_count += 1

    is_finished = exercises_count > 0 and completed_exercises_count == exercises_count

    return ProgramProgressSnapshot(
        exercises_count=exercises_count,
        completed_exercises_count=completed_exercises_count,
        is_finished=is_finished,
    )


def build_favourite_exercise_message(suggested_days_per_week: int) -> str:
    return f"{suggested_days_per_week} days a week is ok for this exercise."


def build_favourite_exercise_snapshot(
    favourite_exercise: UserFavouriteExercise | None,
) -> FavouriteExerciseSnapshot:
    if favourite_exercise is None:
        return FavouriteExerciseSnapshot(
            is_favorite=False,
            suggested_days_per_week=None,
            current_streak_days=None,
            longest_streak_days=None,
        )

    return FavouriteExerciseSnapshot(
        is_favorite=True,
        suggested_days_per_week=favourite_exercise.suggested_days_per_week,
        current_streak_days=favourite_exercise.current_streak_days,
        longest_streak_days=favourite_exercise.longest_streak_days,
    )


def get_suggested_days_per_week_for_user(user: User) -> int:
    try:
        return int(user.profile.weekly_goal)
    except ObjectDoesNotExist:
        return 3


def get_favourite_exercises_by_exercise_id_for_user(
    user: User,
    exercise_ids: list[str],
) -> dict[str, UserFavouriteExercise]:
    favourite_exercises = UserFavouriteExercise.objects.filter(
        user=user,
        exercise_id__in=exercise_ids,
    ).select_related("exercise")
    return {str(favourite_exercise.exercise_id): favourite_exercise for favourite_exercise in favourite_exercises}


def get_favourite_exercise_for_user(
    user: User,
    exercise: Exercise,
) -> UserFavouriteExercise | None:
    return (
        UserFavouriteExercise.objects.filter(
            user=user,
            exercise=exercise,
        )
        .select_related("exercise")
        .first()
    )


def update_favourite_exercise_streak(
    favourite_exercise: UserFavouriteExercise,
    completed_on: date,
) -> UserFavouriteExercise:
    previous_completed_on = favourite_exercise.last_completed_on

    if previous_completed_on is None:
        current_streak_days = 1
    elif previous_completed_on == completed_on:
        current_streak_days = favourite_exercise.current_streak_days
    elif previous_completed_on == completed_on - timedelta(days=1):
        current_streak_days = favourite_exercise.current_streak_days + 1
    else:
        current_streak_days = 1

    longest_streak_days = max(favourite_exercise.longest_streak_days, current_streak_days)

    favourite_exercise.current_streak_days = current_streak_days
    favourite_exercise.longest_streak_days = longest_streak_days
    favourite_exercise.last_completed_on = completed_on
    favourite_exercise.save(
        update_fields=[
            "current_streak_days",
            "longest_streak_days",
            "last_completed_on",
            "updated_at",
        ]
    )
    return favourite_exercise


def create_or_update_favourite_exercise(
    user: User,
    exercise: Exercise,
    is_favorite: bool,
) -> tuple[UserFavouriteExercise | None, str]:
    if is_favorite:
        suggested_days_per_week = get_suggested_days_per_week_for_user(user)
        favourite_exercise, _ = UserFavouriteExercise.objects.update_or_create(
            user=user,
            exercise=exercise,
            defaults={
                "suggested_days_per_week": suggested_days_per_week,
            },
        )
        return favourite_exercise, build_favourite_exercise_message(suggested_days_per_week)

    deleted_count, _ = UserFavouriteExercise.objects.filter(user=user, exercise=exercise).delete()

    if deleted_count == 0:
        return None, "Exercise was already removed from favourites."

    return None, "Exercise removed from favourites."


def get_program_item(
    program_id: str,
    exercise_id: str,
) -> ExerciseProgramItem:
    try:
        return ExerciseProgramItem.objects.select_related("program", "exercise").get(
            program_id=program_id,
            exercise_id=exercise_id,
            program__is_active=True,
        )
    except ExerciseProgramItem.DoesNotExist as exc:
        logger.warning(
            "program_item_not_found",
            extra=build_log_extra(
                "program_progress",
                None,
                None,
                program_id,
                exercise_id,
                None,
            ),
        )
        raise ValidationError(
            {
                "exercise_id": [
                    "The requested exercise does not belong to the specified active program.",
                ],
            }
        ) from exc


def validate_step_index(step_index: int, instruction_steps: list[str]) -> None:
    steps_count = len(instruction_steps)

    if steps_count == 0:
        raise ValidationError(
            {
                "step_index": [
                    "This exercise has no instruction steps to complete.",
                ],
            }
        )

    if step_index < 0 or step_index >= steps_count:
        raise ValidationError(
            {
                "step_index": [
                    f"Step index {step_index} is out of range for an exercise with {steps_count} steps.",
                ],
            }
        )


def validate_next_step_index(
    requested_step_index: int,
    next_step_index: int | None,
) -> None:
    if next_step_index is None:
        raise ValidationError(
            {
                "step_index": [
                    "All steps for this exercise have already been completed.",
                ],
            }
        )

    if requested_step_index != next_step_index:
        raise ValidationError(
            {
                "step_index": [
                    f"Step {requested_step_index} cannot be completed yet. The next required step is {next_step_index}.",
                ],
            }
        )


def validate_repeat_completion_step_index(
    requested_step_index: int,
    steps_count: int,
) -> None:
    final_step_index = steps_count - 1

    if requested_step_index != final_step_index:
        raise ValidationError(
            {
                "step_index": [
                    f"Exercise is already completed. Repeat completion requests must target the final step {final_step_index}.",
                ],
            }
        )


def get_exercise_progress_for_user(
    user: User,
    program: ExerciseProgram,
    exercise: Exercise,
) -> ExerciseProgressSnapshot:
    completions = ExerciseStepCompletion.objects.filter(
        user=user,
        program=program,
        exercise=exercise,
    )
    return build_exercise_progress(exercise, get_completed_step_indexes(completions))


def get_exercise_progress_by_program_item_for_user(
    user: User,
    program_items: list[ExerciseProgramItem],
) -> dict[tuple[str, str], ExerciseProgressSnapshot]:
    if len(program_items) == 0:
        return {}

    program_ids = [str(program_item.program_id) for program_item in program_items]
    exercise_ids = [str(program_item.exercise_id) for program_item in program_items]
    completions = list(
        ExerciseStepCompletion.objects.filter(
            user=user,
            program_id__in=program_ids,
            exercise_id__in=exercise_ids,
        )
    )
    completed_step_indexes_by_program_and_exercise = build_completed_step_indexes_by_program_and_exercise(completions)

    return {
        (str(program_item.program_id), str(program_item.exercise_id)): build_exercise_progress(
            program_item.exercise,
            completed_step_indexes_by_program_and_exercise.get(
                (str(program_item.program_id), str(program_item.exercise_id)),
                [],
            ),
        )
        for program_item in program_items
    }


def get_program_progress_for_user(
    user: User,
    program: ExerciseProgram,
) -> ProgramProgressSnapshot:
    program_items = list(
        ExerciseProgramItem.objects.select_related("exercise").filter(program=program).order_by("exercise_order")
    )
    exercise_progress_by_program_and_exercise = get_exercise_progress_by_program_item_for_user(user, program_items)
    progress_by_exercise_id = {
        str(item.exercise_id): exercise_progress_by_program_and_exercise[
            (str(item.program_id), str(item.exercise_id))
        ]
        for item in program_items
    }

    return build_program_progress(program_items, progress_by_exercise_id)


def get_user_overall_progress_for_user(user: User) -> UserOverallProgressSnapshot:
    active_programs = list(ExerciseProgram.objects.filter(is_active=True).order_by("title"))
    active_program_ids = [program.id for program in active_programs]
    program_items = list(
        ExerciseProgramItem.objects.select_related("program", "exercise")
        .filter(program_id__in=active_program_ids)
        .order_by("program_id", "exercise_order")
    )
    completions = list(
        ExerciseStepCompletion.objects.select_related("exercise")
        .filter(user=user, program_id__in=active_program_ids)
        .order_by("program_id", "exercise_id", "step_index")
    )

    completed_step_indexes_by_program_and_exercise = build_completed_step_indexes_by_program_and_exercise(
        completions
    )

    program_items_by_program_id: dict[str, list[ExerciseProgramItem]] = {}

    for program_item in program_items:
        program_key = str(program_item.program_id)
        existing_items = program_items_by_program_id.get(program_key, [])
        program_items_by_program_id[program_key] = [*existing_items, program_item]

    programs_count = len(active_programs)
    completed_programs_count = 0
    exercises_count = 0
    completed_exercises_count = 0
    steps_count = 0
    completed_steps_count = 0

    for program in active_programs:
        current_program_items = program_items_by_program_id.get(str(program.id), [])
        progress_by_exercise_id: dict[str, ExerciseProgressSnapshot] = {}

        for program_item in current_program_items:
            exercise_progress = build_exercise_progress(
                program_item.exercise,
                sorted(
                    completed_step_indexes_by_program_and_exercise.get(
                        (str(program_item.program_id), str(program_item.exercise_id)),
                        [],
                    )
                ),
            )
            progress_by_exercise_id[str(program_item.exercise_id)] = exercise_progress
            exercises_count += 1
            steps_count += exercise_progress.steps_count
            completed_steps_count += exercise_progress.completed_steps_count

            if exercise_progress.is_finished:
                completed_exercises_count += 1

        program_progress = build_program_progress(current_program_items, progress_by_exercise_id)

        if program_progress.is_finished:
            completed_programs_count += 1

    is_finished = programs_count > 0 and completed_programs_count == programs_count

    return UserOverallProgressSnapshot(
        programs_count=programs_count,
        completed_programs_count=completed_programs_count,
        exercises_count=exercises_count,
        completed_exercises_count=completed_exercises_count,
        steps_count=steps_count,
        completed_steps_count=completed_steps_count,
        is_finished=is_finished,
    )


def build_repeat_completion_result(
    user: User,
    program_item: ExerciseProgramItem,
    current_progress: ExerciseProgressSnapshot,
) -> StepCompletionResult:
    favourite_exercise = (
        UserFavouriteExercise.objects.select_for_update()
        .filter(user=user, exercise=program_item.exercise)
        .select_related("exercise")
        .first()
    )

    if favourite_exercise is not None:
        update_favourite_exercise_streak(favourite_exercise, timezone.localdate())

    return StepCompletionResult(
        exercise_progress=current_progress,
        program_progress=get_program_progress_for_user(
            user=user,
            program=program_item.program,
        ),
        favourite_exercise=build_favourite_exercise_snapshot(favourite_exercise),
    )


@transaction.atomic
def complete_exercise_step(
    user: User,
    program_item: ExerciseProgramItem,
    step_index: int,
) -> StepCompletionResult:
    instruction_steps = get_instruction_steps(program_item.exercise)
    validate_step_index(step_index, instruction_steps)

    current_completions = list(
        ExerciseStepCompletion.objects.select_for_update().filter(
            user=user,
            program=program_item.program,
            exercise=program_item.exercise,
        )
    )
    current_progress = build_exercise_progress(program_item.exercise, get_completed_step_indexes(current_completions))

    if current_progress.is_finished:
        validate_repeat_completion_step_index(step_index, len(instruction_steps))
        return build_repeat_completion_result(
            user=user,
            program_item=program_item,
            current_progress=current_progress,
        )

    validate_next_step_index(step_index, current_progress.next_step_index)

    try:
        ExerciseStepCompletion.objects.create(
            user=user,
            program=program_item.program,
            exercise=program_item.exercise,
            step_index=step_index,
            completed_at=timezone.now(),
        )
    except IntegrityError as exc:
        logger.warning(
            "exercise_step_completion_duplicate",
            extra=build_log_extra(
                "step_completion",
                user.id,
                user.email,
                program_item.program_id,
                program_item.exercise_id,
                None,
            ),
        )
        raise ValidationError(
            {
                "step_index": [
                    f"Step {step_index} has already been completed for this user, program, and exercise.",
                ],
            }
        ) from exc

    updated_exercise_progress = get_exercise_progress_for_user(
        user=user,
        program=program_item.program,
        exercise=program_item.exercise,
    )
    favourite_exercise = (
        UserFavouriteExercise.objects.select_for_update()
        .filter(user=user, exercise=program_item.exercise)
        .select_related("exercise")
        .first()
    )

    if updated_exercise_progress.is_finished and favourite_exercise is not None:
        update_favourite_exercise_streak(favourite_exercise, timezone.localdate())

    updated_program_progress = get_program_progress_for_user(
        user=user,
        program=program_item.program,
    )

    logger.info(
        "exercise_step_completed",
        extra=build_log_extra(
            "step_completion",
            user.id,
            user.email,
            program_item.program_id,
            program_item.exercise_id,
            None,
        ),
    )
    return StepCompletionResult(
        exercise_progress=updated_exercise_progress,
        program_progress=updated_program_progress,
        favourite_exercise=build_favourite_exercise_snapshot(favourite_exercise),
    )


def upsert_seed_programs() -> int:
    created_or_updated_count = 0

    for program_payload in PROGRAM_SEED_DATA:
        program, _ = ExerciseProgram.objects.update_or_create(
            code=program_payload["code"],
            defaults={
                "title": program_payload["title"],
                "description": program_payload["description"],
                "focus_area": program_payload["focus_area"],
                "focus_area_label": program_payload["focus_area_label"],
                "difficulty": program_payload["difficulty"],
                "difficulty_label": program_payload["difficulty_label"],
                "total_duration_sec": program_payload["total_duration_sec"],
                "cover_image_url": program_payload["cover_image"]["url"],
                "cover_image_thumbnail_url": program_payload["cover_image"]["thumbnail_url"],
                "cover_image_width": program_payload["cover_image"]["width"],
                "cover_image_height": program_payload["cover_image"]["height"],
                "cover_image_alt": program_payload["cover_image"]["alt"],
                "cover_image_blurhash": program_payload["cover_image"]["blurhash"],
                "is_active": True,
                "metadata": program_payload.get("metadata", {}),
            },
        )
        created_or_updated_count += 1

        existing_exercise_ids = set(
            ExerciseProgramItem.objects.filter(program=program).values_list("exercise_id", flat=True)
        )
        incoming_exercise_ids = {
            exercise_payload["code"] for exercise_payload in program_payload["exercises"]
        }

        stale_exercise_ids = existing_exercise_ids - incoming_exercise_ids

        if len(stale_exercise_ids) > 0:
            ExerciseProgramItem.objects.filter(program=program, exercise_id__in=stale_exercise_ids).delete()

        for exercise_index, exercise_payload in enumerate(program_payload["exercises"], start=1):
            exercise, _ = Exercise.objects.update_or_create(
                code=exercise_payload["code"],
                defaults={
                    "title": exercise_payload["title"],
                    "instruction": exercise_payload["instruction"],
                    "caution_note": exercise_payload["caution_note"],
                    "duration_sec": exercise_payload["duration_sec"],
                    "body_area": exercise_payload["body_area"],
                    "image_url": exercise_payload["image"]["url"],
                    "image_thumbnail_url": exercise_payload["image"]["thumbnail_url"],
                    "image_width": exercise_payload["image"]["width"],
                    "image_height": exercise_payload["image"]["height"],
                    "image_alt": exercise_payload["image"]["alt"],
                    "image_blurhash": exercise_payload["image"].get("blurhash", ""),
                    "metadata": normalize_exercise_metadata(exercise_payload.get("metadata", {})),
                },
            )
            ExerciseProgramItem.objects.update_or_create(
                program=program,
                exercise=exercise,
                defaults={
                    "exercise_order": exercise_index,
                },
            )

        logger.info(
            "program_seeded",
            extra=build_log_extra(
                "program_seed",
                None,
                None,
                program.id,
                None,
                None,
            ),
        )

    logger.info(
        "program_seed_completed",
        extra=build_log_extra(
            "program_seed",
            None,
            None,
            None,
            None,
            None,
        ),
    )
    return created_or_updated_count
