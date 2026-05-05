from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

from django.db import IntegrityError, transaction
from django.utils import timezone
from rest_framework.exceptions import ValidationError

from apps.core.programs.models import Exercise, ExerciseProgram, ExerciseProgramItem, ExerciseStepCompletion
from apps.core.programs.seed_data import PROGRAM_SEED_DATA
from apps.core.users.models import User


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
class StepCompletionResult:
    exercise_progress: ExerciseProgressSnapshot
    program_progress: ProgramProgressSnapshot


def build_instruction_step_images(instruction_steps: list[str]) -> list[dict[str, str | int | None]]:
    return [
        {
            "url": "",
            "thumbnail_url": "",
            "width": None,
            "height": None,
            "alt": instruction_step,
        }
        for instruction_step in instruction_steps
    ]


def normalize_step_image(image: object, instruction_step: str) -> dict[str, str | int | None]:
    if not isinstance(image, dict):
        return {
            "url": "",
            "thumbnail_url": "",
            "width": None,
            "height": None,
            "alt": instruction_step,
        }

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


def normalize_exercise_metadata(metadata: object) -> dict[str, object]:
    if not isinstance(metadata, dict):
        return {}

    instruction_steps = get_instruction_steps_from_metadata(metadata)
    instruction_step_images = metadata.get("instruction_step_images")

    if not isinstance(instruction_step_images, list):
        instruction_step_images = build_instruction_step_images(instruction_steps)

    normalized_instruction_step_images = [
        normalize_step_image(image, instruction_steps[index])
        for index, image in enumerate(instruction_step_images[: len(instruction_steps)])
    ]

    if len(normalized_instruction_step_images) < len(instruction_steps):
        for instruction_step in instruction_steps[len(normalized_instruction_step_images) :]:
            normalized_instruction_step_images.append(normalize_step_image({}, instruction_step))

    return {
        **metadata,
        "instruction_steps": instruction_steps,
        "instruction_step_images": normalized_instruction_step_images,
        "steps": build_instruction_step_details(
            instruction_steps=instruction_steps,
            instruction_step_images=normalized_instruction_step_images,
        ),
    }


def get_instruction_steps(exercise: Exercise) -> list[str]:
    return get_instruction_steps_from_metadata(exercise.metadata)


def get_instruction_step_details(exercise: Exercise) -> list[dict[str, object]]:
    steps = exercise.metadata.get("steps", [])

    if not isinstance(steps, list):
        return build_instruction_step_details(
            instruction_steps=get_instruction_steps(exercise),
            instruction_step_images=exercise.metadata.get("instruction_step_images", []),
        )

    normalized_steps: list[dict[str, object]] = []

    for step_index, step in enumerate(steps):
        if not isinstance(step, dict):
            continue

        instruction = str(step.get("instruction", ""))
        normalized_steps.append(
            {
                "step_index": int(step.get("step_index", step_index)),
                "title": str(step.get("title", f"Step {step_index + 1}")),
                "instruction": instruction,
                "image": normalize_step_image(step.get("image", {}), instruction),
            }
        )

    return normalized_steps


def get_completed_step_indexes(completions: Iterable[ExerciseStepCompletion]) -> list[int]:
    unique_step_indexes = {completion.step_index for completion in completions}
    return sorted(unique_step_indexes)


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


def get_program_progress_for_user(
    user: User,
    program: ExerciseProgram,
) -> ProgramProgressSnapshot:
    program_items = list(
        ExerciseProgramItem.objects.select_related("exercise").filter(program=program).order_by("exercise_order")
    )
    progress_by_exercise_id: dict[str, ExerciseProgressSnapshot] = {}

    for item in program_items:
        progress_by_exercise_id[str(item.exercise_id)] = get_exercise_progress_for_user(
            user=user,
            program=program,
            exercise=item.exercise,
        )

    return build_program_progress(program_items, progress_by_exercise_id)


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
    updated_program_progress = get_program_progress_for_user(
        user=user,
        program=program_item.program,
    )

    return StepCompletionResult(
        exercise_progress=updated_exercise_progress,
        program_progress=updated_program_progress,
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

    return created_or_updated_count
