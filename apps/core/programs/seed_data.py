def build_image_asset(alt: str) -> dict[str, str | int | None]:
    return {
        "url": "",
        "thumbnail_url": "",
        "width": None,
        "height": None,
        "alt": alt,
        "blurhash": "",
    }


def build_instruction_step_images(instruction_steps: list[str]) -> list[dict[str, str | int | None]]:
    return [
        build_image_asset(instruction_step)
        for instruction_step in instruction_steps
    ]


def build_instruction_step_details(
    instruction_steps: list[str],
    instruction_step_images: list[dict[str, str | int | None]],
) -> list[dict[str, object]]:
    step_details: list[dict[str, object]] = []

    for step_index, instruction_step in enumerate(instruction_steps):
        if step_index < len(instruction_step_images):
            step_image = instruction_step_images[step_index]
        else:
            step_image = build_image_asset(instruction_step)

        step_details.append(
            {
                "step_index": step_index,
                "title": f"Step {step_index + 1}",
                "instruction": instruction_step,
                "image": {
                    "url": step_image.get("url", ""),
                    "thumbnail_url": step_image.get("thumbnail_url", ""),
                    "width": step_image.get("width"),
                    "height": step_image.get("height"),
                    "alt": step_image.get("alt", instruction_step),
                },
            }
        )

    return step_details


def derive_equipment(title: str, instruction: str) -> list[str]:
    normalized_text = f"{title} {instruction}".lower()

    if "towel" in normalized_text:
        return ["towel"]

    if "chair" in normalized_text or "sit to stand" in normalized_text:
        return ["chair"]

    if "wall" in normalized_text:
        return ["wall"]

    if "support" in normalized_text:
        return ["support_surface"]

    return ["bodyweight"]


def derive_movement_type(title: str, instruction: str) -> str:
    normalized_text = f"{title} {instruction}".lower()

    if "mobilization" in normalized_text or "glide" in normalized_text:
        return "mobilization"

    if "stretch" in normalized_text or "tilt" in normalized_text:
        return "stretch"

    if "press" in normalized_text or "set" in normalized_text:
        return "isometric"

    if "sit to stand" in normalized_text:
        return "functional_strength"

    return "mobility"


def derive_primary_targets(body_area: str) -> list[str]:
    if body_area == "neck":
        return ["cervical_mobility", "postural_support"]

    if body_area == "shoulder":
        return ["scapular_control", "shoulder_mobility"]

    if body_area == "back":
        return ["thoracic_mobility", "lumbar_mobility"]

    if body_area == "knee":
        return ["knee_range_of_motion", "quadriceps_activation"]

    return ["general_mobility", "movement_preparation"]


def derive_therapeutic_goals(body_area: str) -> list[str]:
    if body_area == "neck":
        return ["reduce_stiffness", "improve_range_of_motion", "support_daily_posture"]

    if body_area == "shoulder":
        return ["reduce_tension", "restore_mobility", "improve_control"]

    if body_area == "back":
        return ["reduce_back_stiffness", "improve_spinal_motion", "support_daily_movement"]

    if body_area == "knee":
        return ["restore_confidence", "improve_joint_motion", "build_light_strength"]

    return ["reduce_general_stiffness", "improve_coordination", "prepare_for_activity"]


def build_seed_exercise_metadata(
    body_area: str,
    title: str,
    instruction: str,
    caution_note: str,
    metadata: dict[str, object],
) -> dict[str, object]:
    instruction_steps = metadata.get("instruction_steps", [])
    instruction_step_images = metadata.get("instruction_step_images", [])

    if not isinstance(instruction_steps, list):
        instruction_steps = []

    if not isinstance(instruction_step_images, list):
        instruction_step_images = build_instruction_step_images([str(step) for step in instruction_steps])

    normalized_instruction_steps = [str(step) for step in instruction_steps]
    normalized_instruction_step_images = [
        image if isinstance(image, dict) else build_image_asset(normalized_instruction_steps[index])
        for index, image in enumerate(instruction_step_images[: len(normalized_instruction_steps)])
    ]

    if len(normalized_instruction_step_images) < len(normalized_instruction_steps):
        remaining_steps = normalized_instruction_steps[len(normalized_instruction_step_images) :]
        normalized_instruction_step_images.extend(build_instruction_step_images(remaining_steps))

    return {
        **metadata,
        "instruction_steps": normalized_instruction_steps,
        "instruction_step_images": normalized_instruction_step_images,
        "steps": build_instruction_step_details(
            instruction_steps=normalized_instruction_steps,
            instruction_step_images=normalized_instruction_step_images,
        ),
        "equipment": derive_equipment(title, instruction),
        "movement_type": derive_movement_type(title, instruction),
        "primary_targets": derive_primary_targets(body_area),
        "therapeutic_goals": derive_therapeutic_goals(body_area),
        "safety_flags": [caution_note],
        "content_source": "seed_programs",
    }


def enrich_program_seed_data(program_seed_data: list[dict[str, object]]) -> list[dict[str, object]]:
    enriched_programs: list[dict[str, object]] = []

    for program_payload in program_seed_data:
        raw_exercises = program_payload["exercises"]

        if not isinstance(raw_exercises, list):
            raise ValueError(f"Expected a list of exercises for program {program_payload['code']}.")

        enriched_exercises: list[dict[str, object]] = []

        for raw_exercise in raw_exercises:
            if not isinstance(raw_exercise, dict):
                raise ValueError(f"Expected each exercise to be a dictionary in program {program_payload['code']}.")

            raw_metadata = raw_exercise.get("metadata", {})

            if not isinstance(raw_metadata, dict):
                raise ValueError(f"Expected exercise metadata to be a dictionary for exercise {raw_exercise['code']}.")

            enriched_exercises.append(
                {
                    **raw_exercise,
                    "metadata": build_seed_exercise_metadata(
                        body_area=str(raw_exercise["body_area"]),
                        title=str(raw_exercise["title"]),
                        instruction=str(raw_exercise["instruction"]),
                        caution_note=str(raw_exercise["caution_note"]),
                        metadata=raw_metadata,
                    ),
                }
            )

        enriched_programs.append(
            {
                **program_payload,
                "exercises": enriched_exercises,
            }
        )

    return enriched_programs


PROGRAM_SEED_DATA = enrich_program_seed_data([
    {
        "code": "neck-release-flow",
        "title": "Neck Pain Relief Stretching Program",
        "description": "A structured neck pain relief routine with mobility, stretching, and stability work based on the updated clinic exercise sheet.",
        "focus_area": "neck",
        "focus_area_label": "Neck relief",
        "difficulty": "beginner",
        "difficulty_label": "Beginner",
        "total_duration_sec": 1848,
        "cover_image": build_image_asset("Cover image for the neck pain relief stretching program."),
        "metadata": {},
        "exercises": [
            {
                "code": "neck-glide",
                "title": "Neck Glide",
                "instruction": "Slide the head forward and then gently draw it back to align the neck.",
                "caution_note": "Keep the movement horizontal only and stop if symptoms increase.",
                "duration_sec": 100,
                "body_area": "neck",
                "image": build_image_asset("Person performing a neck glide exercise."),
                "metadata": {
                    "instruction_steps": [
                        "Sit or stand upright with the head in a neutral position.",
                        "Gently move the chin and head forward without looking up or down.",
                        "Pull the head back to stack the ears over the shoulders.",
                    ],
                    "timing": {
                        "type": "repetition_hold",
                        "prescription": "10-12 reps, hold each rep for 5 seconds, 2-3 sets",
                        "seconds": 5,
                        "repetitions": "10-12",
                        "sets": "2-3",
                    },
                },
            },
            {
                "code": "neck-extension",
                "title": "Neck Extension",
                "instruction": "Tip the head back slowly, then bring the chin toward the chest with control.",
                "caution_note": "Move slowly and keep the range gentle.",
                "duration_sec": 320,
                "body_area": "neck",
                "image": build_image_asset("Person performing a neck extension exercise."),
                "metadata": {
                    "instruction_steps": [
                        "Start in an upright position.",
                        "Slowly let the head move backward into extension.",
                        "Return and continue into flexion by bringing the chin toward the chest.",
                    ],
                    "timing": {
                        "type": "repetition_hold",
                        "prescription": "Hold 10 seconds in each direction, 8-10 reps, 2 sets",
                        "seconds": 10,
                        "repetitions": "8-10",
                        "sets": "2",
                    },
                },
            },
            {
                "code": "neck-rotation",
                "title": "Neck Rotation",
                "instruction": "Rotate the head right and left in a slow, controlled range.",
                "caution_note": "Keep the shoulders still while the neck rotates.",
                "duration_sec": 160,
                "body_area": "neck",
                "image": build_image_asset("Person performing a neck rotation exercise."),
                "metadata": {
                    "instruction_steps": [
                        "Maintain a tall posture with relaxed shoulders.",
                        "Turn the head to one side without twisting the trunk.",
                        "Return to center and repeat on the other side.",
                    ],
                    "timing": {
                        "type": "repetition_hold",
                        "prescription": "10 reps each direction, hold each turn for 3-5 seconds, 2-3 sets",
                        "seconds": "3-5",
                        "repetitions": "10 each side",
                        "sets": "2-3",
                    },
                },
            },
            {
                "code": "lateral-extension",
                "title": "Lateral Extension",
                "instruction": "Tilt the head toward each shoulder to stretch the side of the neck.",
                "caution_note": "Use only light hand assistance if you add support.",
                "duration_sec": 200,
                "body_area": "neck",
                "image": build_image_asset("Person performing a lateral neck stretch."),
                "metadata": {
                    "instruction_steps": [
                        "Keep the chest open and shoulders level.",
                        "Lower one ear toward the same-side shoulder.",
                        "Repeat on the opposite side and use light hand support only if needed.",
                    ],
                    "timing": {
                        "type": "repetition_hold",
                        "prescription": "Hold 10-15 seconds on each side, 5-6 reps, 2 sets",
                        "seconds": "10-15",
                        "repetitions": "5-6 each side",
                        "sets": "2",
                    },
                },
            },
            {
                "code": "shoulder-shrugs",
                "title": "Shoulder Shrugs",
                "instruction": "Raise the shoulders toward the ears, then relax them back down.",
                "caution_note": "Lift and lower with control instead of snapping the shoulders down.",
                "duration_sec": 48,
                "body_area": "shoulder",
                "image": build_image_asset("Person performing shoulder shrug exercise."),
                "metadata": {
                    "instruction_steps": [
                        "Stand or sit tall.",
                        "Lift both shoulders up toward the ears.",
                        "Release them downward in a relaxed, controlled way.",
                    ],
                    "timing": {
                        "type": "repetition_hold",
                        "prescription": "12-15 reps, 2-3 seconds each rep, 2-3 sets",
                        "seconds": "2-3",
                        "repetitions": "12-15",
                        "sets": "2-3",
                    },
                },
            },
            {
                "code": "tilted-forward-flexion",
                "title": "Tilted Forward Flexion",
                "instruction": "Bend the head slightly forward, then side bend to stretch the back and side neck muscles together.",
                "caution_note": "Avoid forcing the stretch into pain.",
                "duration_sec": 240,
                "body_area": "neck",
                "image": build_image_asset("Person performing a tilted forward neck stretch."),
                "metadata": {
                    "instruction_steps": [
                        "Bring the head slightly forward.",
                        "From that position, side bend to one side.",
                        "Return and repeat on the other side.",
                    ],
                    "timing": {
                        "type": "repetition_hold",
                        "prescription": "Hold 10 seconds on each side, 6-8 reps, 2 sets",
                        "seconds": 10,
                        "repetitions": "6-8 each side",
                        "sets": "2",
                    },
                },
            },
            {
                "code": "deep-stretching",
                "title": "Deep Stretching",
                "instruction": "Hold the head in a forward, side, or diagonal stretch and add light hand pressure for a deeper stretch.",
                "caution_note": "Do not apply sudden force with the hand.",
                "duration_sec": 120,
                "body_area": "neck",
                "image": build_image_asset("Person performing a deep neck stretch."),
                "metadata": {
                    "instruction_steps": [
                        "Move the head into the target stretch direction.",
                        "Rest the hand gently on the head.",
                        "Apply light pressure only until a comfortable stretch is felt.",
                    ],
                    "timing": {
                        "type": "repetition_hold",
                        "prescription": "Hold 15-20 seconds, 4-5 reps, 2 sets",
                        "seconds": "15-20",
                        "repetitions": "4-5",
                        "sets": "2",
                    },
                },
            },
            {
                "code": "resistance-presses",
                "title": "Resistance Presses",
                "instruction": "Press the head gently into the hand from the front, back, and sides without visible neck motion.",
                "caution_note": "Keep the effort light and steady during the isometric press.",
                "duration_sec": 200,
                "body_area": "neck",
                "image": build_image_asset("Person performing isometric neck resistance presses."),
                "metadata": {
                    "instruction_steps": [
                        "Place the hand against the forehead, back of the head, or side of the head.",
                        "Press the head into the hand without moving the neck.",
                        "Repeat for each direction with light resistance.",
                    ],
                    "timing": {
                        "type": "repetition_hold",
                        "prescription": "Hold 5-10 seconds in each direction, 5 reps, 2-3 sets",
                        "seconds": "5-10",
                        "repetitions": "5 each direction",
                        "sets": "2-3",
                    },
                },
            },
            {
                "code": "towel-pull",
                "title": "Towel Pull",
                "instruction": "Place a towel behind the neck and use it for light support while the head eases backward.",
                "caution_note": "Support the neck with the towel and avoid jerking backward.",
                "duration_sec": 100,
                "body_area": "neck",
                "image": build_image_asset("Person performing a towel-assisted neck stretch."),
                "metadata": {
                    "instruction_steps": [
                        "Position a towel behind the neck and hold both ends.",
                        "Gently move the head backward while the towel supports the motion.",
                        "Return slowly and keep the stretch comfortable.",
                    ],
                    "timing": {
                        "type": "repetition_hold",
                        "prescription": "Hold 10-15 seconds, 5-6 reps, 2 sets",
                        "seconds": "10-15",
                        "repetitions": "5-6",
                        "sets": "2",
                    },
                },
            },
            {
                "code": "neural-mobilization",
                "title": "Neural Mobilization",
                "instruction": "Coordinate the arm, wrist, and neck to gently glide the nerve tissue.",
                "caution_note": "Keep the movement rhythmic and stop if symptoms travel strongly into the arm.",
                "duration_sec": 60,
                "body_area": "neck",
                "image": build_image_asset("Person performing a neural mobilization exercise."),
                "metadata": {
                    "instruction_steps": [
                        "Reach one arm straight out to the side with the palm facing forward.",
                        "Tilt the head away while bending the wrist back toward you.",
                        "Return the head to center while relaxing the wrist position.",
                    ],
                    "timing": {
                        "type": "repetitions",
                        "prescription": "10 slow rhythmic reps, 2 sets",
                        "repetitions": "10",
                        "sets": "2",
                    },
                },
            },
            {
                "code": "t-exercise",
                "title": "Shoulder T Exercise",
                "instruction": "Lift the arms out to the sides in a prone T position to support the upper back and reduce neck load.",
                "caution_note": "Keep the neck long and avoid shrugging during the lift.",
                "duration_sec": 90,
                "body_area": "shoulder",
                "image": build_image_asset("Person performing a prone shoulder T exercise."),
                "metadata": {
                    "instruction_steps": [
                        "Lie face down and move the arms out to the side to form a T shape.",
                        "Point the thumbs upward.",
                        "Lift the arms with control while keeping the shoulder blades stable.",
                    ],
                    "timing": {
                        "type": "repetitions",
                        "prescription": "12 reps, 3 sets",
                        "repetitions": "12",
                        "sets": "3",
                    },
                },
            },
            {
                "code": "i-exercise",
                "title": "Shoulder I Exercise",
                "instruction": "Reach the arms overhead in a prone I position to improve postural control.",
                "caution_note": "Lift only as high as you can without compressing the neck.",
                "duration_sec": 90,
                "body_area": "shoulder",
                "image": build_image_asset("Person performing a prone shoulder I exercise."),
                "metadata": {
                    "instruction_steps": [
                        "Lie face down with the arms reaching overhead.",
                        "Lift the arms upward with control.",
                        "Lower them slowly while keeping the trunk steady.",
                    ],
                    "timing": {
                        "type": "repetitions",
                        "prescription": "12 reps, 3 sets",
                        "repetitions": "12",
                        "sets": "3",
                    },
                },
            },
            {
                "code": "scalene-stretch",
                "title": "Scalene Stretch",
                "instruction": "Gently anchor above the collarbone, tilt the head away, and look slightly upward to stretch the front-side neck muscles.",
                "caution_note": "Apply only light pressure above the collarbone.",
                "duration_sec": 120,
                "body_area": "neck",
                "image": build_image_asset("Person performing a scalene neck stretch."),
                "metadata": {
                    "instruction_steps": [
                        "Place light pressure above the collarbone.",
                        "Tilt the head to the opposite side.",
                        "Turn the gaze slightly upward until the front-side neck stretch is felt.",
                    ],
                    "timing": {
                        "type": "repetition_hold",
                        "prescription": "Hold 30 seconds, 2 reps on each side",
                        "seconds": 30,
                        "repetitions": "2 each side",
                    },
                },
            },
        ],
    },
    {
        "code": "shoulder-mobility-reset",
        "title": "Shoulder Mobility Reset",
        "description": "Simple shoulder mobility movements to open the chest, improve control, and reduce stiffness.",
        "focus_area": "shoulder",
        "focus_area_label": "Shoulder mobility",
        "difficulty": "beginner",
        "difficulty_label": "Beginner",
        "total_duration_sec": 105,
        "cover_image": build_image_asset("Cover image for the shoulder mobility reset program."),
        "metadata": {},
        "exercises": [
            {
                "code": "shoulder-circles",
                "title": "Shoulder circles",
                "instruction": "Make slow shoulder circles forward, then reverse the direction with control.",
                "caution_note": "Keep the movement pain-free and avoid compensating with your lower back.",
                "duration_sec": 35,
                "body_area": "shoulder",
                "image": build_image_asset("Person performing shoulder circles."),
                "metadata": {},
            },
            {
                "code": "wall-slide-air",
                "title": "Air wall slide",
                "instruction": "Reach your arms upward as if sliding along a wall, then lower back down slowly.",
                "caution_note": "Only lift as high as your symptoms allow.",
                "duration_sec": 40,
                "body_area": "shoulder",
                "image": build_image_asset("Person performing an air wall slide."),
                "metadata": {},
            },
            {
                "code": "open-book-press",
                "title": "Chest opener press",
                "instruction": "Open your elbows outward to stretch the chest, then return to the starting position.",
                "caution_note": "Keep your ribs down and avoid arching your back.",
                "duration_sec": 30,
                "body_area": "shoulder",
                "image": build_image_asset("Person performing a chest opener press."),
                "metadata": {},
            },
        ],
    },
    {
        "code": "lower-back-calm",
        "title": "Lower Back Calm",
        "description": "A calm lower-back routine focused on breathing, core support, and controlled mobility.",
        "focus_area": "back",
        "focus_area_label": "Lower back care",
        "difficulty": "beginner",
        "difficulty_label": "Beginner",
        "total_duration_sec": 125,
        "cover_image": build_image_asset("Cover image for the lower back calm program."),
        "metadata": {},
        "exercises": [
            {
                "code": "pelvic-tilt",
                "title": "Pelvic tilt",
                "instruction": "Gently tilt your pelvis to flatten your lower back, then release.",
                "caution_note": "Keep the movement small and comfortable.",
                "duration_sec": 45,
                "body_area": "back",
                "image": build_image_asset("Person performing a pelvic tilt."),
                "metadata": {},
            },
            {
                "code": "single-knee-hug",
                "title": "Alternating knee hug",
                "instruction": "Bring one knee toward your chest, hold softly, then switch sides.",
                "caution_note": "Breathe out during the reach and do not rush the movement.",
                "duration_sec": 40,
                "body_area": "back",
                "image": build_image_asset("Person performing an alternating knee hug."),
                "metadata": {},
            },
            {
                "code": "cat-cow-standing",
                "title": "Standing cat-cow",
                "instruction": "Round and extend your upper back slowly while keeping the movement comfortable.",
                "caution_note": "Move within a pain-free range only.",
                "duration_sec": 40,
                "body_area": "mobility",
                "image": build_image_asset("Person performing a standing cat-cow movement."),
                "metadata": {},
            },
        ],
    },
    {
        "code": "knee-support-sequence",
        "title": "Knee Support Sequence",
        "description": "A short knee-support routine for gentle activation, range of motion, and confidence in daily movement.",
        "focus_area": "knee",
        "focus_area_label": "Knee support",
        "difficulty": "beginner",
        "difficulty_label": "Beginner",
        "total_duration_sec": 105,
        "cover_image": build_image_asset("Cover image for the knee support sequence program."),
        "metadata": {},
        "exercises": [
            {
                "code": "quad-set",
                "title": "Quad set",
                "instruction": "Tighten the front of your thigh and gently press the knee downward.",
                "caution_note": "Do not force the knee into pain.",
                "duration_sec": 35,
                "body_area": "knee",
                "image": build_image_asset("Person performing a quad set exercise."),
                "metadata": {},
            },
            {
                "code": "heel-slide",
                "title": "Heel slide",
                "instruction": "Slide your heel toward you, then extend the leg back out slowly.",
                "caution_note": "Keep the movement smooth and stop if the knee catches.",
                "duration_sec": 40,
                "body_area": "knee",
                "image": build_image_asset("Person performing a heel slide exercise."),
                "metadata": {},
            },
            {
                "code": "sit-to-stand",
                "title": "Sit to stand",
                "instruction": "Stand up from a chair with control, then sit down slowly.",
                "caution_note": "Hold onto support if you feel unsteady.",
                "duration_sec": 30,
                "body_area": "knee",
                "image": build_image_asset("Person performing a sit to stand exercise."),
                "metadata": {},
            },
        ],
    },
])
