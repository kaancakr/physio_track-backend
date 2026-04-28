from apps.core.programs.models import ExerciseProgram, ExerciseStep
from apps.core.programs.seed_data import PROGRAM_SEED_DATA


def upsert_seed_programs() -> int:
    created_or_updated_count = 0

    for program_payload in PROGRAM_SEED_DATA:
        program, _ = ExerciseProgram.objects.update_or_create(
            id=program_payload["id"],
            defaults={
                "title": program_payload["title"],
                "description": program_payload["description"],
                "focus_area": program_payload["focus_area"],
                "focus_area_label": program_payload["focus_area_label"],
                "difficulty_label": program_payload["difficulty_label"],
                "total_duration_sec": program_payload["total_duration_sec"],
                "cover_icon": program_payload["cover_image"]["icon"],
                "cover_background": program_payload["cover_image"]["background"],
                "cover_tint": program_payload["cover_image"]["tint"],
                "is_active": True,
                "metadata": {},
            },
        )
        created_or_updated_count += 1

        existing_step_ids = set(
            ExerciseStep.objects.filter(program=program).values_list("step_id", flat=True)
        )
        incoming_step_ids = {step_payload["id"] for step_payload in program_payload["steps"]}

        stale_step_ids = existing_step_ids - incoming_step_ids

        if len(stale_step_ids) > 0:
            ExerciseStep.objects.filter(program=program, step_id__in=stale_step_ids).delete()

        for step_index, step_payload in enumerate(program_payload["steps"], start=1):
            ExerciseStep.objects.update_or_create(
                program=program,
                step_id=step_payload["id"],
                defaults={
                    "step_order": step_index,
                    "title": step_payload["title"],
                    "instruction": step_payload["instruction"],
                    "caution_note": step_payload["caution_note"],
                    "duration_sec": step_payload["duration_sec"],
                    "body_area": step_payload["body_area"],
                    "icon": step_payload["image"]["icon"],
                    "background": step_payload["image"]["background"],
                    "tint": step_payload["image"]["tint"],
                    "metadata": {},
                },
            )

    return created_or_updated_count
