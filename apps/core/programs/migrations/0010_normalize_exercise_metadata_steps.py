from __future__ import annotations

from django.db import migrations


def build_default_step_image(instruction: str) -> dict[str, str | int | None]:
    return {
        "url": "",
        "thumbnail_url": "",
        "width": None,
        "height": None,
        "alt": instruction,
    }


def normalize_step_image(image: object, instruction: str) -> dict[str, str | int | None]:
    if not isinstance(image, dict):
        return build_default_step_image(instruction)

    return {
        "url": str(image.get("url", "")),
        "thumbnail_url": str(image.get("thumbnail_url", "")),
        "width": image.get("width"),
        "height": image.get("height"),
        "alt": str(image.get("alt", instruction)),
    }


def normalize_step_detail(step: object, fallback_step_index: int) -> dict[str, object] | None:
    if not isinstance(step, dict):
        return None

    instruction = str(step.get("instruction", "")).strip()

    if instruction == "":
        return None

    return {
        "step_index": int(step.get("step_index", fallback_step_index)),
        "title": str(step.get("title", f"Step {fallback_step_index + 1}")),
        "instruction": instruction,
        "image": normalize_step_image(step.get("image", {}), instruction),
    }


def build_steps_from_legacy_metadata(metadata: dict[str, object]) -> list[dict[str, object]]:
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

    raw_instruction_steps = metadata.get("instruction_steps", [])

    if not isinstance(raw_instruction_steps, list):
        raw_instruction_steps = []

    instruction_steps = [str(step) for step in raw_instruction_steps]
    raw_instruction_step_images = metadata.get("instruction_step_images")

    if not isinstance(raw_instruction_step_images, list):
        raw_instruction_step_images = []

    normalized_steps: list[dict[str, object]] = []

    for step_index, instruction in enumerate(instruction_steps):
        raw_image = raw_instruction_step_images[step_index] if step_index < len(raw_instruction_step_images) else {}
        normalized_steps.append(
            {
                "step_index": step_index,
                "title": f"Step {step_index + 1}",
                "instruction": instruction,
                "image": normalize_step_image(raw_image, instruction),
            }
        )

    return normalized_steps


def normalize_exercise_metadata(metadata: object) -> dict[str, object]:
    if not isinstance(metadata, dict):
        return {}

    metadata_without_legacy_step_fields = {
        key: value
        for key, value in metadata.items()
        if key not in {"instruction_steps", "instruction_step_images", "steps"}
    }

    return {
        **metadata_without_legacy_step_fields,
        "steps": build_steps_from_legacy_metadata(metadata),
    }


def normalize_existing_exercise_metadata(apps, schema_editor) -> None:
    Exercise = apps.get_model("programs", "Exercise")

    for exercise in Exercise.objects.all().iterator():
        normalized_metadata = normalize_exercise_metadata(exercise.metadata)

        if normalized_metadata == exercise.metadata:
            continue

        exercise.metadata = normalized_metadata
        exercise.save(update_fields=["metadata", "updated_at"])


class Migration(migrations.Migration):
    dependencies = [
        ("programs", "0009_userfavouriteexercise"),
    ]

    operations = [
        migrations.RunPython(
            normalize_existing_exercise_metadata,
            migrations.RunPython.noop,
        ),
    ]
