from datetime import datetime

from apps.core.programs.models import Exercise, ExerciseProgram, ExerciseProgramCompletion, ExerciseProgramItem
from apps.core.programs.seed_data import PROGRAM_SEED_DATA
from apps.core.users.models import User


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


def normalize_exercise_metadata(metadata: object) -> dict[str, object]:
    if not isinstance(metadata, dict):
        return {}

    instruction_steps = metadata.get("instruction_steps", [])

    if not isinstance(instruction_steps, list):
        instruction_steps = []

    instruction_step_images = metadata.get("instruction_step_images")

    if not isinstance(instruction_step_images, list):
        instruction_step_images = build_instruction_step_images([str(step) for step in instruction_steps])

    return {
        **metadata,
        "instruction_steps": [str(step) for step in instruction_steps],
        "instruction_step_images": instruction_step_images,
    }


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


def mark_program_as_finished(
    user: User,
    program: ExerciseProgram,
    finished_at: datetime,
) -> ExerciseProgramCompletion:
    completion, _ = ExerciseProgramCompletion.objects.update_or_create(
        user=user,
        program=program,
        defaults={
            "is_finished": True,
            "finished_at": finished_at,
        },
    )
    return completion
